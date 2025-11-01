# AI Review Report

**Effort**: XS

> Potential security issue with subprocess

## Findings

- **ERROR** [SEC-BANDIT] path/to/file.py:1 — Avoid subprocess shell=True for security reasons
  - Using `shell=True` with subprocess can lead to command injection attacks. Consider using the `args` parameter instead.
  - **Fix**: Replace `subprocess.run('ls', shell=True)` with `subprocess.run(['ls'])` or use the `args` parameter
