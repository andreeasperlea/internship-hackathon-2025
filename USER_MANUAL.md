# RevAI - AI Code Review Assistant 🤖

## User Manual & Command Reference

**RevAI** is an AI-powered code review tool that analyzes your staged Git changes using local Ollama LLM and static analysis tools. Get instant feedback on code quality, security, performance, and style.

---

## 🚀 Quick Start

### 1. Prerequisites
```bash
# Install Ollama (if not already installed)
curl -fsSL https://ollama.ai/install.sh | sh

# Pull the required model
ollama pull llama3.1:8b

# Start Ollama server
ollama serve
```

### 2. Install Dependencies
```bash
pip install rich pyyaml requests
```

### 3. Basic Usage
```bash
# Stage some files for review
git add your_file.py

# Run AI review
python cli.py
```

---

## 📖 Command Line Interface

### Basic Commands

#### **Default Review**
```bash
python cli.py
```
- Analyzes staged Git changes
- Uses default configuration from `review_config.yaml`
- Outputs markdown and JSON reports
- Autofix disabled by default

#### **Help**
```bash
python cli.py --help
```
Shows all available options and their descriptions.

---

## 🔧 Configuration Options

### Command Line Arguments

| Argument | Description | Example |
|----------|-------------|---------|
| `--config CONFIG` | Path to config file | `--config my_config.yaml` |
| `--rules RULES` | Path to rules file | `--rules custom_rules.yaml` |
| `--apply-fixes` | Enable autofix (overrides config) | `--apply-fixes` |
| `--no-apply-fixes` | Disable autofix (overrides config) | `--no-apply-fixes` |
| `--format {md,json,sarif}` | Output formats | `--format json --format sarif` |
| `--display {compact,detailed,summary}` | Display mode | `--display compact` |

### Display Modes

#### **Detailed Mode** (Default)
```bash
python cli.py --display detailed
```
- Full startup banner with configuration
- File tree of changed files
- Summary table of findings
- Detailed findings with recommendations
- Performance statistics

#### **Summary Mode**
```bash
python cli.py --display summary
```
- Startup banner and configuration
- File tree of changes  
- Summary table only
- Quick performance stats

#### **Compact Mode**
```bash
python cli.py --display compact
```
- Minimal output
- One line per finding
- Perfect for CI/CD pipelines

---

## ⚙️ Configuration Files

### `review_config.yaml` - Main Configuration

```yaml
# AI Backend Configuration
backend: ollama                    # Currently only ollama supported
model_ollama: llama3.1:8b         # Ollama model to use
model_gpt: gpt-4o-mini            # Future GPT support
ollama_url: http://localhost:11434/api/generate  # Ollama server URL

# Review Settings
max_findings: 50                   # Maximum findings to report
severity_threshold: info           # Minimum severity (info|warn|error)

# Auto-fix Configuration  
enable_autofix: false             # Default: disabled for safety
                                  # Use --apply-fixes to enable for single run
                                  # Use --no-apply-fixes to disable for single run

# Output Settings
formats: [md, json]               # Output formats (md|json|sarif)
use_only_staged: true             # Only analyze staged changes
```

### `rules.yaml` - Custom Review Guidelines

```yaml
guidelines:
  - id: PEP8
    description: Respectă PEP8 (naming, line length, imports).
  
  - id: SEC-BANDIT  
    description: Evită riscuri comune (subprocess shell=True, eval, pickle).
  
  - id: PERF
    description: Evită bucle O(n^2) inutile și conversii costisitoare în hot paths.
  
  - id: CUSTOM_RULE
    description: Your custom coding standards here.
```

---

## 🛠️ Auto-Fix System

### Safety First Approach
- **Disabled by default** for safety
- **Manual override** required for each run
- **Clear feedback** on what was applied

### Enabling Auto-Fix

#### **One-time Enable**
```bash
python cli.py --apply-fixes
```

#### **One-time Disable** (if enabled in config)
```bash
python cli.py --no-apply-fixes
```

#### **Enable in Config** (not recommended)
```yaml
# review_config.yaml
enable_autofix: true
```

### Auto-Fix Feedback
When auto-fix finds applicable patches:

**If Disabled:**
```
📝 Info: 3 auto-fixable issues found
Use --apply-fixes to automatically apply suggested fixes
```

**If Enabled:**
```
🛠️  Found 3 auto-fixable issues
🤖 Auto-fix is ENABLED - applying fixes automatically...
✅ Applied 2/3 auto-fix patches and staged them!
```

---

## 📊 Output Formats

### Markdown Report (`AI_REVIEW.md`)
```markdown
# AI Review Report

**Effort**: S

> Summary of findings

## Findings
- **ERROR** [SEC-BANDIT] file.py:15 — Security issue detected
  - Description of the problem
  - **Fix**: Recommended solution
```

### JSON Report (`ai_review.json`)  
```json
{
  "summary": "Brief overview",
  "effort": "S", 
  "findings": [
    {
      "file": "test.py",
      "line": 10,
      "rule": "PEP8", 
      "severity": "warn",
      "title": "Issue description",
      "description": "Detailed explanation",
      "recommendation": "How to fix",
      "auto_fix_patch": "unified diff patch"
    }
  ],
  "mypy": "MyPy output here"
}
```

### SARIF Report (`ai_review.sarif`)
Standard SARIF format for IDE integration and CI/CD pipelines.

---

## 🔍 Static Analysis Integration

RevAI integrates multiple static analysis tools:

### **Ruff** - Python Linting
- Style checking (PEP8)
- Import sorting
- Code complexity analysis
- Automatic fixing of simple issues

### **Bandit** - Security Analysis  
- Security vulnerability detection
- Common security antipatterns
- Risk assessment (HIGH/MEDIUM/LOW)

### **MyPy** - Type Checking
- Static type analysis
- Type hint validation
- Generic type checking

---

## 🚦 Git Integration

### Pre-commit Hook
Install the pre-commit hook for automatic reviews:

```bash
# Copy the hook
cp git/hooks/pre-commit .git/hooks/

# Make it executable  
chmod +x .git/hooks/pre-commit
```

The hook will:
- Run on every commit attempt
- Block commits if critical issues found
- Provide immediate feedback

### Manual Git Integration
```bash
# Stage files for review
git add file1.py file2.py

# Run review on staged changes
python cli.py

# Apply any manual fixes
# Re-run review if needed
python cli.py

# Commit when satisfied
git commit -m "Your commit message"
```

---

## 🎯 Common Usage Patterns

### **Development Workflow**
```bash
# 1. Make code changes
vim myfile.py

# 2. Stage changes
git add myfile.py  

# 3. Review changes
python cli.py --display detailed

# 4. Apply fixes if needed
python cli.py --apply-fixes

# 5. Commit
git commit -m "Add feature X"
```

### **CI/CD Pipeline**
```bash
# Minimal output for automation
python cli.py --display compact --format json

# Check exit code
if [ $? -ne 0 ]; then
  echo "Review failed"
  exit 1
fi
```

### **Team Code Review**
```bash
# Generate comprehensive reports
python cli.py --format md --format json --format sarif --display detailed

# Share AI_REVIEW.md with team
# Import ai_review.sarif into IDE
# Use ai_review.json for further processing
```

---

## 🐛 Troubleshooting

### **Ollama Connection Issues**

**Problem:** `❌ Ollama server not reachable`

**Solutions:**
1. Check if Ollama is running: `ollama serve`
2. Verify model is available: `ollama list`
3. Pull model if missing: `ollama pull llama3.1:8b`
4. Check URL in config: `ollama_url: http://localhost:11434/api/generate`

### **No Staged Changes**

**Problem:** `⚠️ No staged changes found`

**Solution:**
```bash
# Stage files first
git add .
# or specific files  
git add myfile.py
```

### **Auto-fix Not Working**

**Problem:** Patches not applying

**Possible Causes:**
1. Conflicting changes in working directory
2. Invalid patch format from AI
3. File permissions issues

**Solutions:**
```bash
# Ensure clean working directory
git status

# Try manual review first
python cli.py --no-apply-fixes
```

### **AI Parsing Errors**

**Problem:** `parse_error` or `LLM returned non-JSON response`

**Solutions:**
```bash
# 1. Check Ollama server status
ollama serve

# 2. Verify model is available
ollama list

# 3. Test Ollama directly
ollama run llama3.1:8b "Hello"

# 4. Clear cache and retry
rm -rf .ai_review_cache/
python cli.py

# 5. Check debug file
cat .ai_review_cache/last_failed_response.txt
```

### **Performance Issues**

**Problem:** Slow analysis

**Solutions:**
1. Reduce `max_findings` in config
2. Use `--display compact` for faster output
3. Check Ollama server performance
4. Ensure sufficient system resources

---

## 📈 Performance Optimization

### **Caching**
- AI responses are cached in `.ai_review_cache/`
- Identical diffs reuse cached results
- Clear cache: `rm -rf .ai_review_cache/`

### **Batch Processing**  
- Multiple hunks sent in single AI request
- Reduces API calls and latency
- Configured automatically

### **Resource Monitoring**
```bash
# Check resource usage
python cli.py --display detailed
# Look for "📊 Performance" section at the end
```

---

## 🔐 Security Considerations

### **Local AI Processing**
- Uses local Ollama server (no cloud APIs)
- Code never leaves your machine
- Full privacy and security control

### **Auto-fix Safety**
- Disabled by default
- Requires explicit enable per run
- Only applies safe, validated patches
- All changes are staged (easily revertible)

### **Configuration Security**
- Store sensitive configs outside repository
- Use environment variables for URLs
- Review auto-generated patches before committing

---

## 📚 Advanced Usage

### **Custom Rules**
Create domain-specific rules in `rules.yaml`:

```yaml
guidelines:
  - id: API_SECURITY
    description: API endpoints must validate all input parameters
  
  - id: PERFORMANCE  
    description: Database queries should use proper indexing
  
  - id: DOCUMENTATION
    description: Public functions must have docstrings
```

### **Remote Ollama Server**
```yaml
# review_config.yaml
ollama_url: http://your-server:11434/api/generate
```

### **Multiple Configurations**
```bash
# Development config
python cli.py --config dev_config.yaml

# Production config  
python cli.py --config prod_config.yaml
```

---

## 🆘 Support & Contributing

### **Getting Help**
1. Check this manual first
2. Review error messages carefully
3. Check Ollama server status
4. Verify Git staging status

### **Feature Requests**
- Suggest new static analysis tools
- Request additional output formats
- Propose new display modes
- Add custom rule categories

### **Bug Reports**
Include:
- Command used
- Configuration files
- Error messages
- Git status
- System information

---

**Happy Coding! 🚀**

*RevAI - Making code review intelligent, fast, and local.*
