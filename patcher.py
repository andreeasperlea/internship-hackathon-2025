import subprocess, tempfile

def apply_unified_patch(patch_text: str) -> bool:
    if not patch_text or "@@ " not in patch_text:
        return False
    with tempfile.NamedTemporaryFile("w", delete=False, suffix=".patch") as f:
        f.write(patch_text.strip() + "\n")
        path = f.name
    try:
        subprocess.run(["git","apply","--index", path], check=True)
        return True
    except subprocess.CalledProcessError:
        return False
