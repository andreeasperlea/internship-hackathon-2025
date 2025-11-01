# 🧪 Feedback System Testing Guide

## Manual Testing Scenarios

### **Scenario 1: Basic Feedback Workflow**

#### Step 1: Generate Findings (Even Without Ollama)
```bash
# Create a test file with intentional issues
echo 'import subprocess
def bad_function():
    subprocess.run("ls", shell=True)  # Security issue
    very_long_line = "this line exceeds 79 characters and should trigger a style warning from ruff linter tool"' > test_issues.py

# Stage the file
git add test_issues.py

# Run review (static analysis will still work without Ollama)
python cli.py --display detailed
```

#### Step 2: List Generated Findings
```bash
# See all findings with their IDs
python cli.py --feedback list
```

#### Step 3: Interact with Findings
```bash
# Copy a finding ID from the list output, then:

# Add a comment
python cli.py --feedback comment --finding-id FINDING_ID_HERE --message "I'm investigating this issue"

# Mark as resolved
python cli.py --feedback resolve --finding-id FINDING_ID_HERE --message "Fixed by removing shell=True"

# Mark as false positive
python cli.py --feedback false-positive --finding-id FINDING_ID_HERE --message "This is intentional for our use case"

# Mark as will fix later
python cli.py --feedback will-fix-later --finding-id FINDING_ID_HERE --message "Technical debt - will fix in v2.0"
```

### **Scenario 2: Direct Feedback Testing (Without Review)**

If you want to test feedback commands without running a full review:

#### Create Mock Feedback Data
```bash
# First, create a simple test file and run review to populate the feedback system
echo 'def test(): pass' > simple_test.py
git add simple_test.py
python cli.py  # This creates the feedback database

# Now you can test feedback commands directly
```

### **Scenario 3: Comprehensive Workflow Testing**

```bash
# 1. Create test file with multiple issues
cat > comprehensive_test.py << 'EOF'
import subprocess
import os

def security_issue():
    # Security: shell=True vulnerability
    subprocess.run("echo hello", shell=True)
    
def style_issue():
    # Style: line too long
    very_long_variable_name_that_exceeds_the_recommended_line_length_limit = "test"
    return very_long_variable_name_that_exceeds_the_recommended_line_length_limit

# Missing docstring
def undocumented_function():
    return "no docs"

# Unused import will be caught by static analysis
import json
EOF

# 2. Stage and review
git add comprehensive_test.py
python cli.py --display detailed

# 3. Test all feedback operations
python cli.py --feedback list
python cli.py --feedback stats
python cli.py --feedback search --query "security"

# 4. Copy finding IDs from output and test interactions
# python cli.py --feedback comment --finding-id <ID> --message "Working on this"
# python cli.py --feedback resolve --finding-id <ID> --message "Fixed"

# 5. Check updated statistics
python cli.py --feedback stats
```

## Testing Commands Reference

### **List Operations**
```bash
# List all findings
python cli.py --feedback list

# List only resolved findings
python cli.py --feedback list --status resolved

# List only open findings  
python cli.py --feedback list --status open
```

### **Detailed View**
```bash
# Show complete discussion for a finding
python cli.py --feedback show --finding-id <FINDING_ID>
```

### **Status Changes**
```bash
# Mark as resolved
python cli.py --feedback resolve --finding-id <ID> --message "Fixed in commit abc123"

# Mark as false positive
python cli.py --feedback false-positive --finding-id <ID> --message "Expected behavior"

# Mark as will fix later
python cli.py --feedback will-fix-later --finding-id <ID> --message "Planned for v2.0"
```

### **Comments**
```bash
# Add a discussion comment
python cli.py --feedback comment --finding-id <ID> --message "Investigating root cause"

# Add another comment
python cli.py --feedback comment --finding-id <ID> --message "Found the issue - will fix tomorrow"
```

### **Search & Statistics**
```bash
# Search findings by keyword
python cli.py --feedback search --query "subprocess"
python cli.py --feedback search --query "security"
python cli.py --feedback search --query "style"

# View overall statistics
python cli.py --feedback stats
```

## Expected Outputs

### **After First Review**
You should see findings displayed with:
- ✅ **Feedback Status**: Shows as "🔓 Open" initially
- ✅ **Finding IDs**: 12-character identifiers like `a1b2c3d4e5f6`
- ✅ **Feedback Summary**: Panel showing total findings and resolution rate

### **After Adding Comments**
```bash
python cli.py --feedback show --finding-id <ID>
```
Should show:
- Finding details
- Complete discussion history
- All status changes
- Timestamps and authors

### **After Status Changes**
```bash
python cli.py --feedback list
```
Should show updated status icons:
- 🔓 Open
- ✅ Done (resolved)
- 🚫 FP (false positive) 
- ⏳ Later (will fix later)

## Troubleshooting

### **No Findings Generated**
If you don't see any findings:
```bash
# Check what's staged
git status

# Make sure static analysis tools are working
python -c "from linters import run_ruff; print(run_ruff())"

# Run with verbose static analysis
python cli.py --display detailed
```

### **Finding IDs Not Working**
If feedback commands fail:
```bash
# Check the feedback database exists
ls -la .ai_review_feedback.json

# List all findings to get valid IDs
python cli.py --feedback list

# Verify ID format (should be 12 characters)
```

### **No Static Analysis Results**
If no static findings are generated:
```bash
# Install required tools
pip install ruff bandit mypy

# Test tools directly
ruff check test_issues.py
bandit -r test_issues.py
mypy test_issues.py
```

## Testing Checklist

- [ ] Generate findings with static analysis (Ruff, Bandit, MyPy)
- [ ] List findings and copy IDs
- [ ] Add comments to findings
- [ ] Change finding status (resolve, false positive, will fix later)
- [ ] View detailed finding information
- [ ] Search findings by keywords
- [ ] Check statistics and resolution rates
- [ ] Verify persistent storage (.ai_review_feedback.json)
- [ ] Test filtering by status
- [ ] Confirm feedback appears in review output

The feedback system works completely independently of the AI analysis, so you can test all functionality even with Ollama offline! 🚀
