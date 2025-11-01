# cli.py
import subprocess
import sys
import argparse
import os
from review import review_code

def ensure_api_key():
    if not os.getenv("OPENAI_API_KEY"):
        print("❌ Missing OpenAI API key. Please set it like this:")
        print('   export OPENAI_API_KEY="sk-your-key"')
        sys.exit(1)

def get_git_diff() -> str:
    """Get staged changes."""
    try:
        result = subprocess.run(
            ["git", "diff", "--cached"],
            capture_output=True, text=True, check=True
        )
        return result.stdout.strip() or "No changes staged."
    except subprocess.CalledProcessError as e:
        return f"[ERROR] Could not get git diff: {e}"

def main():
    parser = argparse.ArgumentParser(description="AI Code Review CLI")
    parser.add_argument("--backend", choices=["ollama", "gpt"], default="ollama",
                        help="Choose AI backend: ollama (local) or gpt (OpenAI API)")
    parser.add_argument("--prompt", type=str, default="Review my code",
                        help="Prompt to send to the AI model")
    args = parser.parse_args()

    if args.backend == "gpt":
        ensure_api_key()

    print(f"🤖 AI Code Review Assistant [{args.backend.upper()} mode]")
    diff = get_git_diff()
    if not diff or "No changes" in diff:
        print("No staged changes found.")
        sys.exit(0)

    print("\n🔍 Sending code to AI for review...\n")
    response = review_code(args.prompt, diff, backend=args.backend)

    print("\n=== 💬 AI Review Feedback ===\n")
    print(response)
    print("\n==============================\n")

if __name__ == "__main__":
    main()
