import os
import re
import json
import requests
import yaml
import socket
import urllib.parse
from pathlib import Path

# === Load config ===
CONFIG_PATH = "review_config.yaml"
if os.path.exists(CONFIG_PATH):
    with open(CONFIG_PATH) as f:
        cfg = yaml.safe_load(f)
else:
    cfg = {}

# === Ollama configuration ===
# Prefer env var → config → fallback localhost
OLLAMA_API_URL = os.getenv(
    "OLLAMA_API_URL",
    cfg.get("ollama_url", "http://localhost:11434/api/generate")
)
OLLAMA_MODEL = cfg.get("model_ollama", os.getenv("OLLAMA_MODEL", "llama3.1:8b"))
MAX_FINDINGS = cfg.get("max_findings", 50)

# --- Quick remote/local server check ---
def ensure_ollama_online(url: str, timeout: float = 1.5):
    """Exit fast if the Ollama server (remote or local) is offline or unreachable."""
    parsed = urllib.parse.urlparse(url)
    host = parsed.hostname or "localhost"
    port = parsed.port or 11434

    try:
        with socket.create_connection((host, port), timeout=timeout):
            print(f"🔌 Connected to Ollama at {url}")
            return True
    except Exception:
        print(f"❌ Ollama server not reachable at {host}:{port}")
        print("💤 Skipping AI review (server offline).")
        raise SystemExit(0)

# --- Prompt template for code review ---
PROMPT_TEMPLATE = """You are an expert code reviewer.
Analyze ONLY the newly added lines and their immediate context.
Return STRICT JSON matching this schema:

{{
  "summary": "short overview",
  "effort": "XS|S|M|L",
  "findings": [
    {{
      "file": "path/to/file.py",
      "line": 123,
      "rule": "PEP8|SEC|PERF|STYLE|DOCS|TESTS|ARCH",
      "severity": "info|warn|error",
      "title": "problem title",
      "description": "why it's a problem",
      "recommendation": "what to change",
      "auto_fix_patch": "unified diff patch applying the fix (optional)"
    }}
  ]
}}

Guidelines: {guidelines}

Now review the following DIFF HUNK:
---
{hunk}
---
IMPORTANT:
- Output ONLY the JSON (no backticks, no prose).
- Escape any special characters properly.
- Prefer adding 'auto_fix_patch' when safe.
"""

# --- Ollama API call ---
def ask_ollama(prompt: str) -> str:
    """Call the Ollama API (remote or local)."""
    ensure_ollama_online(OLLAMA_API_URL)

    payload = {"model": OLLAMA_MODEL, "prompt": prompt, "stream": False}
    try:
        resp = requests.post(
            OLLAMA_API_URL,
            json=payload,
            timeout=(3, 60)  # (connect_timeout, read_timeout)
        )
        resp.raise_for_status()
        data = resp.json()
        return data.get("response") or data.get("text") or str(data)
    except requests.exceptions.ConnectTimeout:
        print("⚠️  Connection timed out while contacting Ollama.")
        raise SystemExit(0)
    except requests.exceptions.RequestException as e:
        print(f"⚠️  Ollama request failed: {e}")
        raise SystemExit(0)

# --- safer JSON parsing ---
def safe_parse_json(raw: str):
    """Clean and parse possibly malformed JSON from LLM output."""
    cleaned = re.sub(r'[\x00-\x1F\x7F]', '', raw)
    start, end = cleaned.find("{"), cleaned.rfind("}")
    if start != -1 and end != -1:
        cleaned = cleaned[start:end+1]
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        cleaned = cleaned.replace("'", '"')
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            Path(".ai_review_cache/last_failed_response.txt").write_text(raw)
            return {"summary": "parse_error", "findings": []}

def review_hunks(hunks, rules, max_findings=MAX_FINDINGS):
    """Send all diff hunks in one batched Ollama request for faster review."""
    ensure_ollama_online(OLLAMA_API_URL)

    # Combine all hunks into one review payload
    joined_hunks = "\n\n---\n\n".join(
        f"File: {h['file']}\n" + "\n".join(h["raw"]) for h in hunks
    )
    guidelines = "\n".join(f"- {r['id']}: {r['description']}" for r in rules)

    prompt = PROMPT_TEMPLATE.format(guidelines=guidelines, hunk=joined_hunks)
    print("🚀 Sending combined diff to Ollama for review...")

    raw = ask_ollama(prompt).strip()
    data = safe_parse_json(raw)

    # Prepare final report
    return {
        "summary": data.get("summary", "Batch review summary"),
        "effort": data.get("effort", "S"),
        "findings": data.get("findings", [])[:max_findings],
    }
