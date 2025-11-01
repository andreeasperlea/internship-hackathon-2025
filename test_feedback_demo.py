# Test file for feedback system demo
import subprocess

def test_function():
    # This will trigger security issues
    subprocess.run("echo hello", shell=True)
    
    # This will trigger style issues  
    very_long_line_that_exceeds_the_pep8_recommended_line_length_of_79_characters = "test"
    
    return very_long_line_that_exceeds_the_pep8_recommended_line_length_of_79_characters

# Missing docstring will trigger documentation issues
def helper():
    return "test"
