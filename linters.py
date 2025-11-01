import subprocess, json

def run_ruff(paths=None):
    cmd = ["ruff","check","--quiet","--output-format","json"]
    if paths: cmd += paths
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, check=True)
        return json.loads(r.stdout) if r.stdout else []
    except Exception:
        return []

def run_bandit(paths=None):
    cmd = ["bandit","-q","-r",".","-f","json"]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, check=True)
        return json.loads(r.stdout).get("results",[])
    except Exception:
        return []

def run_mypy(paths=None):
    cmd = ["mypy","--pretty","--hide-error-codes","--no-error-summary"]
    if paths: cmd += paths
    try:
        r = subprocess.run(cmd, capture_output=True, text=True)
        return r.stdout
    except Exception:
        return ""
