# RevAI - AI Code Review Assistant 🤖

**Intelligent code review powered by local Ollama LLM**

RevAI provides automated code review for your Git staged changes, combining AI analysis with static analysis tools for comprehensive code quality assessment.

## 🚀 Quick Start

```bash
# 1. Start Ollama server
ollama serve

# 2. Stage your changes  
git add your_file.py

# 3. Run AI review
python cli.py
```

## ✨ Key Features

- **🤖 AI-Powered Analysis** - Uses local Ollama LLM (llama3.1:8b)
- **🔍 Multi-Tool Integration** - Combines Ruff, Bandit, MyPy + AI insights
- **🛠️ Auto-Fix Capabilities** - Applies suggested fixes automatically (optional)
- **🎨 Beautiful CLI** - Rich terminal interface with progress indicators
- **📊 Multiple Output Formats** - Markdown, JSON, and SARIF reports
- **🔒 Privacy-First** - All analysis happens locally, no cloud APIs
- **⚡ Git Integration** - Pre-commit hooks and staged-change focus

## 📖 Documentation

| Document | Purpose |
|----------|---------|
| **[USER_MANUAL.md](USER_MANUAL.md)** | Complete documentation with examples |
| **[COMMANDS.md](COMMANDS.md)** | Quick reference and cheat sheet |

## 🎯 Quick Commands

```bash
# Basic review (autofix disabled by default)
python cli.py

# Enable auto-fix for this run
python cli.py --apply-fixes

# Compact output for CI/CD
python cli.py --display compact

# Multiple output formats
python cli.py --format json --format sarif

# Get help
python cli.py --help
```

## 🔧 Configuration

Edit `review_config.yaml` to customize:
- AI model and server settings
- Auto-fix behavior (disabled by default)
- Output formats and display modes
- Analysis thresholds

Edit `rules.yaml` to add custom coding guidelines.

## 🏗️ Architecture

```
Git Staged Changes → AI Analysis (Ollama) → Static Analysis (Ruff/Bandit/MyPy) → Reports + Auto-fixes
```

## 📊 Sample Output

```
╭────────────────────────────── 🤖 RevAI Results ──────────────────────────────╮
│ 🤖 AI Code Review Complete                                                    │
│ Summary: Found 3 issues requiring attention                                   │
│ Effort Estimate: S                                                            │
╰──────────────────────────────────────────────────────────────────────────────╯

┏━━━━━━━━━━━━┳━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓
┃ Severity   ┃ Rule          ┃ Location                  ┃ Issue                         ┃
┡━━━━━━━━━━━━╇━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┩
│ 🚨 ERROR   │ SEC-BANDIT    │ test.py:10                │ Use of subprocess with shell  │
│ ⚠️  WARN   │ PEP8          │ test.py:15                │ Line too long (89 > 88)      │
│ ℹ️  INFO   │ DOCS          │ test.py:5                 │ Missing function docstring    │
└────────────┴───────────────┴───────────────────────────┴───────────────────────────────┘
```

## 🏆 Benefits

- **Faster Code Reviews** - Instant feedback on code quality
- **Consistent Standards** - Enforces team coding guidelines  
- **Security Focus** - Catches security vulnerabilities early
- **Learning Tool** - Detailed explanations help developers improve
- **Integration Ready** - Works with existing Git workflows

## 🤝 Getting Help

1. Check **[USER_MANUAL.md](USER_MANUAL.md)** for comprehensive documentation
2. See **[COMMANDS.md](COMMANDS.md)** for quick command reference
3. Run `python cli.py --help` for CLI options
4. Verify Ollama server status with `ollama serve`

---

**Start reviewing smarter, not harder! 🚀**
