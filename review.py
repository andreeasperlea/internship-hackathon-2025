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

# === Ollama configuration (REMOTE ONLY) ===
OLLAMA_API_URL = os.getenv("OLLAMA_API_URL", "http://192.168.0.112:11434/api/generate")
OLLAMA_MODEL = cfg.get("model_ollama", os.getenv("OLLAMA_MODEL", "llama3.1:8b"))
MAX_FINDINGS = cfg.get("max_findings", 50)

# --- Quick remote server check ---
def ensure_ollama_online(url: str, timeout: float = 1.5):
    """Exit fast if the remote Ollama server is offline or unreachable."""
    parsed = urllib.parse.urlparse(url)
    host = parsed.hostname or "localhost"
    port = parsed.port or 11434

    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True  # success
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
    """Call the remote Ollama API."""
    ensure_ollama_online(OLLAMA_API_URL)

    payload = {"model": OLLAMA_MODEL, "prompt": prompt, "stream": False}
    try:
        resp = requests.post(
            OLLAMA_API_URL,
            json=payload,
            timeout=(3, 10)  # (connect_timeout, read_timeout)
        )
        resp.raise_for_status()
        data = resp.json()
        return data.get("response") or data.get("text") or str(data)
    except requests.exceptions.ConnectTimeout:
        print("❌ Connection timed out while contacting Ollama.")
        raise SystemExit(0)
    except requests.exceptions.RequestException as e:
        print(f"❌ Ollama request failed: {e}")
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

# --- Main review function ---
def review_hunks(hunks, rules, max_findings=MAX_FINDINGS):
    """Send each diff hunk to remote Ollama for review."""
    guidelines = "\n".join(f"- {r['id']}: {r['description']}" for r in rules)
    all_findings, summaries, efforts = [], [], []

    for h in hunks:
        prompt = PROMPT_TEMPLATE.format(
            guidelines=guidelines,
            hunk="\n".join(h["raw"])
        )
        raw = ask_ollama(prompt).strip()
        data = safe_parse_json(raw)

        summaries.append(data.get("summary", ""))
        efforts.append(data.get("effort", "S"))
        for f in data.get("findings", []):
            f.setdefault("file", h["file"])
            all_findings.append(f)
        if len(all_findings) >= max_findings:
            break

    return {
        "summary": " | ".join(x for x in summaries if x).strip(),
        "effort": max(efforts, key=lambda e: "XS S M L".split().index(e)) if efforts else "S",
        "findings": all_findings[:max_findings],
    }
