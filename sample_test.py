# Sample file with intentional issues for testing
import subprocess
import os

def bad_function():
    # Security issue - shell=True
    subprocess.run("ls -la", shell=True)
    
    # Performance issue - O(n^2) loop
    items = list(range(1000))
    result = []
    for i in items:
        for j in items:
            if i == j:
                result.append(i)
    
    # Style issue - inconsistent naming
    myVariable = "test"
    another_var = "test2"
    
    # Missing type hints
    def helper(x, y):
        return x + y
    
    return result

# Unused import and variable
import json
unused_var = "not used"
