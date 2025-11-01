import subprocess, re
from typing import List, Dict

def get_staged_diff(unified_context: int = 0) -> str:
    res = subprocess.run(["git","diff","--cached", f"-U{unified_context}"],
                         capture_output=True, text=True, check=True)
    return res.stdout

HUNK_RE = re.compile(r"^@@ -(\d+),?(\d+)? \+(\d+),?(\d+)? @@")

def split_into_hunks(diff_text: str) -> List[Dict]:
    files, current = [], None
    filename = None
    for line in diff_text.splitlines():
        if line.startswith("+++ b/"):
            filename = line[6:]
        if line.startswith("@@"):
            m = HUNK_RE.match(line)
            if m:
                if current: files.append(current)
                current = {
                    "file": filename,
                    "header": line,
                    "added": [],
                    "raw": [line],
                }
            continue
        if current:
            current["raw"].append(line)
            if line.startswith("+") and not line.startswith("+++"):
                current["added"].append(line[1:])
    if current: files.append(current)
    # păstrăm doar hunks cu linii adăugate
    return [h for h in files if h["added"]]
