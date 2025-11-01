import argparse, os, json, hashlib
from diff_utils import get_staged_diff, split_into_hunks
from review import review_hunks
from patcher import apply_unified_patch
from linters import run_ruff, run_bandit, run_mypy
from cost import CostTracker
import yaml
from pathlib import Path

CACHE_DIR = Path(".ai_review_cache")
CACHE_DIR.mkdir(exist_ok=True)

import requests, os

def check_ollama_connection():
    url = os.getenv("OLLAMA_API_URL", "http://localhost:11434/api/generate")
    try:
        resp = requests.post(url, json={"model":"llama3.1:8b","prompt":"ping","stream":False}, timeout=10)
        if resp.status_code == 200:
            print(f"🔌 Connected to Ollama at {url}")
        else:
            print(f"⚠️ Ollama responded with status {resp.status_code}")
    except requests.exceptions.Timeout:
        print(f"❌ Ollama at {url} timed out.")
        raise SystemExit(1)
    except requests.exceptions.RequestException as e:
        print(f"❌ Could not reach Ollama: {e}")
        raise SystemExit(1)


def cache_key(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()

def load_yaml(p):
    with open(p) as f:
        return yaml.safe_load(f)

def main():
    parser = argparse.ArgumentParser(description="AI Code Review Assistant (Ollama Only)")
    parser.add_argument("--config", default="review_config.yaml", help="Path to config file")
    parser.add_argument("--rules", default="rules.yaml", help="Path to rules file")
    parser.add_argument("--apply-fixes", action="store_true", help="Apply AI suggested fixes")
    parser.add_argument("--format", choices=["md", "json", "sarif"], action="append",
                        help="Output formats")
    args = parser.parse_args()

    cfg = load_yaml(args.config) if os.path.exists(args.config) else {}
    rules = load_yaml(args.rules).get("guidelines", []) if os.path.exists(args.rules) else []
    formats = args.format or cfg.get("formats", ["md"])

    # Backend fixed to Ollama
    backend = "ollama"
    print(f"🤖 AI Code Review Assistant [OLLAMA]")

    diff = get_staged_diff(unified_context=0)
    if not diff.strip():
        print("No staged changes found.")
        return 0

    hunks = split_into_hunks(diff)
    tracker = CostTracker()

    key = cache_key(diff + backend)
    cache_file = CACHE_DIR / f"{key}.json"
    if cache_file.exists():
        report = json.loads(cache_file.read_text())
    else:
        report = review_hunks(hunks, rules, max_findings=50)
        cache_file.write_text(json.dumps(report, indent=2))

    # Linters
    ruff = run_ruff()
    bandit = run_bandit()
    mypy = run_mypy()

    findings = report.get("findings", [])
    for item in ruff:
        findings.append({
            "file": item["filename"],
            "line": item["location"]["row"],
            "rule": item["code"],
            "severity": "warn",
            "title": item["message"],
            "description": "ruff",
            "recommendation": "Conform to lint rule",
            "auto_fix_patch": ""
        })
    for item in bandit:
        findings.append({
            "file": item.get("filename"),
            "line": item.get("line_number"),
            "rule": f"BANDIT-{item.get('test_id')}",
            "severity": "error" if item.get("issue_severity") == "HIGH" else "warn",
            "title": item.get("issue_text"),
            "description": "bandit",
            "recommendation": "Refactor to mitigate security issue",
            "auto_fix_patch": ""
        })

    out = {
        "summary": report.get("summary", ""),
        "effort": report.get("effort", "S"),
        "findings": findings,
        "mypy": mypy
    }

    # Apply auto-fix patches if enabled
    applied = 0
    if args.apply_fixes or cfg.get("enable_autofix", False):
        for f in findings:
            patch = f.get("auto_fix_patch")
            if patch and apply_unified_patch(patch):
                applied += 1
        if applied:
            print(f"🛠  Applied {applied} auto-fix patches and staged them.")

    # --- Output files ---
    if "json" in formats:
        Path("ai_review.json").write_text(json.dumps(out, indent=2))
        print("💾 Wrote ai_review.json")

    if "md" in formats:
        md = ["# AI Review Report\n", f"**Effort**: {out['effort']}\n"]
        if out.get("summary"):
            md.append(f"> {out['summary']}\n")
        if out.get("mypy"):
            md.append("## mypy\n```\n" + out["mypy"] + "\n```\n")
        md.append("## Findings\n")
        for f in findings:
            md.append(f"- **{f['severity'].upper()}** [{f.get('rule','GEN')}] "
                      f"{f['file']}:{f.get('line','?')} — {f['title']}\n"
                      f"  - {f['description']}\n"
                      f"  - **Fix**: {f['recommendation']}\n")
        Path("AI_REVIEW.md").write_text("\n".join(md))
        print("💾 Wrote AI_REVIEW.md")

    # --- Concise summary ---
    if out.get("findings"):
        print("\n=== 💬 AI Review Summary ===\n")
        for f in out["findings"]:
            sev = f.get("severity", "info").upper()
            rule = f.get("rule", "GEN")
            file = f.get("file", "?")
            line = f.get("line", "?")
            title = f.get("title", "")
            rec = f.get("recommendation", "")
            print(f"• {sev} [{rule}] {file}:{line} — {title}")
            if rec:
                print(f"  ↳ {rec}")
        print("\n=============================\n")
    else:
        print("✅ No significant findings detected.")

    if "sarif" in formats:
        sarif = {
            "version": "2.1.0",
            "runs": [{
                "tool": {"driver": {"name": "AIReview", "informationUri": "local"}},
                "results": [{
                    "ruleId": f.get("rule", "AI"),
                    "message": {"text": f.get("title", "Issue")},
                    "level": {"info": "note", "warn": "warning", "error": "error"}[f.get("severity", "info")],
                    "locations": [{
                        "physicalLocation": {
                            "artifactLocation": {"uri": f.get("file", "")},
                            "region": {"startLine": f.get("line", 1)}
                        }
                    }]
                } for f in findings]
            }]
        }
        Path("ai_review.sarif").write_text(json.dumps(sarif, indent=2))
        print("💾 Wrote ai_review.sarif")
    
    if Path("AI_REVIEW.md").exists():
        print("\n=== 💬 AI Review Feedback Summary ===\n")
        lines = Path("AI_REVIEW.md").read_text().splitlines()
        for line in lines:
            if line.strip().startswith("- **"):
                print(line)
        print("\n📄 Full report saved to AI_REVIEW.md\n")

    stats = tracker.summary()
    print(f"⏱  Done. Elapsed≈{stats['elapsed_sec']}s")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
