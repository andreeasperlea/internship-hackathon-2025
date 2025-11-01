import subprocess
import os
import json

def new_function():
    # This should trigger context-aware suggestions based on existing patterns
    result = subprocess.run("ls -la", shell=True, capture_output=True)
    
    # Similar pattern exists in cli.py - should suggest consistency
    data = json.loads('{"test": "value"}')
    
    # This follows a different pattern than existing codebase
    print("Hello world!")
    return data

class NewFeature:
    def __init__(self):
        self.config = {}
    
    def process_data(self, input_data):
        try:
            result = subprocess.run(["echo", "test"], capture_output=True, text=True)
            return result.stdout
        except Exception as e:
            print(f"Error: {e}")
            return None
