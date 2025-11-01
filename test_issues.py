import subprocess
import os
import json  # Unused import - will trigger Ruff

def security_issue():
    # This will trigger Bandit security warning
    subprocess.run("echo hello", shell=True)
    
def style_issue():  
    # This line is too long and will trigger Ruff style warning
    very_long_variable_name_that_definitely_exceeds_the_pep8_recommended_line_length_of_79_characters = "test"
    return very_long_variable_name_that_definitely_exceeds_the_pep8_recommended_line_length_of_79_characters

def undocumented_function():
    # Missing docstring - may trigger AI or static analysis
    return "no documentation"
