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
PROMPT_TEMPLATE = """You are an expert code reviewer. You must respond with VALID JSON ONLY.

Analyze ONLY the newly added lines (lines starting with +) and their context.

REQUIRED JSON SCHEMA:
{{
  "summary": "brief overview of changes",
  "effort": "XS|S|M|L|XL",
  "findings": [
    {{
      "file": "path/to/file.py",
      "line": 123,
      "rule": "PEP8|SEC|PERF|STYLE|DOCS|TESTS|ARCH",
      "severity": "info|warn|error", 
      "title": "brief issue description",
      "description": "detailed explanation",
      "recommendation": "specific fix suggestion",
      "auto_fix_patch": "unified diff patch (optional)"
    }}
  ]
}}

Guidelines to check: {guidelines}

CODE DIFF TO REVIEW:
---
{hunk}
---

CRITICAL INSTRUCTIONS:
1. RESPOND ONLY WITH VALID JSON - NO OTHER TEXT
2. NO markdown code blocks (```), NO explanations, NO prose
3. If no issues found, return: {{"summary": "Code looks good", "effort": "XS", "findings": []}}
4. Focus on NEW code (+ lines) in the diff
5. Include auto_fix_patch only for simple, safe fixes

JSON RESPONSE:"""

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
    # Remove control characters
    cleaned = re.sub(r'[\x00-\x1F\x7F]', '', raw)
    
    # Find JSON boundaries
    start, end = cleaned.find("{"), cleaned.rfind("}")
    if start != -1 and end != -1:
        cleaned = cleaned[start:end+1]
    else:
        # No JSON found - save for debugging and return fallback
        Path(".ai_review_cache/last_failed_response.txt").write_text(raw)
        print(f"⚠️  Warning: LLM returned non-JSON response. Saved to .ai_review_cache/last_failed_response.txt")
        return {"summary": "LLM returned non-JSON response - check prompt template", "effort": "XS", "findings": []}
    
    # Try parsing JSON
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError as e:
        # Try fixing common issues
        fixed = cleaned.replace("'", '"')  # Single to double quotes
        fixed = re.sub(r',(\s*[}\]])', r'\1', fixed)  # Remove trailing commas
        
        try:
            return json.loads(fixed)
        except json.JSONDecodeError:
            # Save failed response for debugging
            Path(".ai_review_cache/last_failed_response.txt").write_text(raw)
            print(f"⚠️  Warning: Could not parse LLM JSON response. Error: {e}")
            print(f"📝 Raw response saved to .ai_review_cache/last_failed_response.txt")
            
            return {
                "summary": f"JSON parse error: {str(e)[:100]}...",
                "effort": "XS", 
                "findings": [{
                    "file": "unknown",
                    "line": 1,
                    "rule": "SYSTEM",
                    "severity": "warn",
                    "title": "AI response parsing failed",
                    "description": f"The LLM returned invalid JSON. Error: {e}",
                    "recommendation": "Check Ollama model compatibility and prompt template",
                    "auto_fix_patch": ""
                }]
            }

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
    
    # If parsing failed and we got a system error, try a simpler approach
    if data.get("summary", "").startswith(("JSON parse error", "LLM returned non-JSON")):
        print("🔄 Retrying with simplified prompt...")
        simple_prompt = f"""Respond with valid JSON only. Review this code diff and return:
{{"summary": "brief description", "effort": "S", "findings": []}}

Diff:
{joined_hunks[:2000]}  

JSON:"""
        
        raw_retry = ask_ollama(simple_prompt).strip()
        retry_data = safe_parse_json(raw_retry)
        
        # Use retry result if it's better, otherwise keep original
        if not retry_data.get("summary", "").startswith(("JSON parse error", "LLM returned non-JSON")):
            data = retry_data
        else:
            print("⚠️  Retry also failed - using fallback summary")

    # Prepare final report
    return {
        "summary": data.get("summary", "Review completed with parsing issues"),
        "effort": data.get("effort", "S"),
        "findings": data.get("findings", [])[:max_findings],
    }
