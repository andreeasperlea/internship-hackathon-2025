# AI Review Report

**Effort**: S

> Newly added code review

## Findings

- **WARN** [SEC-BANDIT] path/to/file.py:456 — Potential subprocess vulnerability
  - The use of `shell=True` in the `subprocess.call()` function can pose a security risk. Consider using `subprocess.run()` with `text=False` instead.
  - **Fix**: Replace `subprocess.call()` with `subprocess.run()` and set `text=False`
