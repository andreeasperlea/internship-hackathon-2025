# RevAI Command Reference 🚀

## Quick Command Cheat Sheet

### 🎯 Essential Commands

```bash
# Basic review (autofix disabled)
python cli.py

# Review with autofix enabled
python cli.py --apply-fixes

# Compact output (for CI/CD)
python cli.py --display compact

# Multiple output formats
python cli.py --format json --format sarif --format md

# Custom config and rules
python cli.py --config my_config.yaml --rules my_rules.yaml

# Help
python cli.py --help
```

---

### 📋 All CLI Options

| Option | Short | Description | Example |
|--------|-------|-------------|---------|
| `--help` | `-h` | Show help message | `python cli.py -h` |
| `--config CONFIG` | | Custom config file | `--config dev.yaml` |
| `--rules RULES` | | Custom rules file | `--rules team_rules.yaml` |
| `--apply-fixes` | | Enable auto-fix (override config) | `--apply-fixes` |
| `--no-apply-fixes` | | Disable auto-fix (override config) | `--no-apply-fixes` |
| `--format FORMAT` | | Output format(s) | `--format json` |
| `--display MODE` | | Display mode | `--display summary` |

---

### 🎨 Display Modes

| Mode | Description | Use Case |
|------|-------------|----------|
| `detailed` | Full output with all panels | Development review |
| `summary` | Config + summary table only | Quick overview |
| `compact` | Minimal one-line findings | CI/CD pipelines |

---

### 📊 Output Formats

| Format | File | Description |
|--------|------|-------------|
| `md` | `AI_REVIEW.md` | Human-readable markdown |
| `json` | `ai_review.json` | Machine-readable data |
| `sarif` | `ai_review.sarif` | IDE/tool integration |

---

### 🔧 Configuration Files

#### `review_config.yaml`
```yaml
backend: ollama
model_ollama: llama3.1:8b
max_findings: 50
severity_threshold: info
enable_autofix: false  # Safe default
formats: [md, json]
use_only_staged: true
ollama_url: http://localhost:11434/api/generate
```

#### `rules.yaml`
```yaml
guidelines:
  - id: PEP8
    description: Follow PEP8 style guidelines
  - id: SEC-BANDIT
    description: Avoid common security risks
  - id: PERF
    description: Optimize performance bottlenecks
```

---

### ⚡ Quick Workflows

#### **Development Review**
```bash
git add myfile.py
python cli.py --display detailed
# Review findings, apply manual fixes
python cli.py --apply-fixes  # If auto-fixes available
git commit -m "Fix issues"
```

#### **CI/CD Integration**
```bash
python cli.py --display compact --format json
exit_code=$?
if [ $exit_code -ne 0 ]; then
  echo "Review failed"
  exit 1
fi
```

#### **Team Review**
```bash
python cli.py --format md --format sarif
# Share AI_REVIEW.md with team
# Import ai_review.sarif into IDE
```

#### **Pre-commit Hook**
```bash
# Install hook
cp git/hooks/pre-commit .git/hooks/
chmod +x .git/hooks/pre-commit

# Automatic review on every commit
git commit -m "Auto-reviewed code"
```

---

### 🛠️ Auto-Fix Control

| Setting | Method | Result |
|---------|--------|--------|
| Default | Config: `enable_autofix: false` | ❌ Disabled |
| Enable once | `--apply-fixes` | ✅ Enabled |
| Disable once | `--no-apply-fixes` | ❌ Disabled |
| Always enable | Config: `enable_autofix: true` | ⚠️ Not recommended |

---

### 🔍 Static Analysis Tools

| Tool | Purpose | Severity |
|------|---------|----------|
| **Ruff** | Python linting, style | warn |
| **Bandit** | Security vulnerabilities | error/warn |
| **MyPy** | Type checking | info |
| **AI Review** | Logic, architecture, docs | info/warn/error |

---

### 📈 Performance Tips

- **Use caching**: Identical diffs reuse cached AI results
- **Compact mode**: Faster output for automation
- **Limit findings**: Set `max_findings: 20` for speed
- **Local Ollama**: Keep server running for faster responses

---

### 🐛 Common Issues & Fixes

| Problem | Solution |
|---------|----------|
| `❌ Ollama server not reachable` | `ollama serve` |
| `⚠️ No staged changes found` | `git add <files>` |
| `Auto-fix not working` | Check clean working directory |
| `Slow performance` | Reduce `max_findings`, use local Ollama |

---

### 🎯 Examples by Use Case

#### **Security Review**
```bash
# Focus on security issues
python cli.py --display detailed
# Look for BANDIT-* rules in output
```

#### **Style Cleanup**
```bash
# Fix style issues automatically
python cli.py --apply-fixes --display compact
```

#### **Performance Check**
```bash
# Review for performance issues
# Check AI findings for PERF rules
python cli.py --display detailed
```

#### **Documentation Review**
```bash
# AI will suggest documentation improvements
python cli.py --display detailed
# Look for DOCS rule suggestions
```

---

*For full documentation, see [USER_MANUAL.md](USER_MANUAL.md)*
