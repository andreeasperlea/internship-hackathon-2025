import os
import requests
import json

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
- Prefer adding 'auto_fix_patch' when safe.
"""

# === Ollama configuration ===
OLLAMA_API_URL = os.getenv("OLLAMA_API_URL", "http://localhost:11434/api/generate")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.1:8b")

def ask_ollama(prompt: str) -> str:
    """Call the Ollama API (local or remote)."""
    payload = {
        "model": OLLAMA_MODEL,
        "prompt": prompt,
        "stream": False
    }
    try:
        resp = requests.post(OLLAMA_API_URL, json=payload, timeout=60)
        resp.raise_for_status()
        data = resp.json()
        return data.get("response") or data.get("text") or str(data)
    except requests.exceptions.Timeout:
        return "[ERROR] Ollama request timed out."
    except requests.exceptions.RequestException as e:
        return f"[ERROR] Ollama request failed: {e}"

def review_hunks(hunks, rules, max_findings=50):
    """Send each diff hunk to Ollama for review."""
    guidelines = "\n".join(f"- {r['id']}: {r['description']}" for r in rules)
    all_findings = []
    summaries, efforts = [], []

    for h in hunks:
        prompt = PROMPT_TEMPLATE.format(
            guidelines=guidelines,
            hunk="\n".join(h["raw"])
        )
        raw = ask_ollama(prompt).strip()

        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            start, end = raw.find("{"), raw.rfind("}")
            if start != -1 and end != -1:
                data = json.loads(raw[start:end+1])
            else:
                data = {"summary": "parse_error", "findings": []}

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
