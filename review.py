# review.py
import os
import requests
from openai import OpenAI

OLLAMA_API_URL = "http://localhost:11434/api/generate"
OLLAMA_MODEL = "llama3.1:8b"
OPENAI_MODEL = "gpt-4o-mini"  # can be gpt-4-turbo or similar

def ask_ollama(prompt: str, diff: str) -> str:
    """Call local Ollama API."""
    payload = {
        "model": OLLAMA_MODEL,
        "prompt": f"{prompt}\n\nHere is the git diff:\n{diff}",
        "stream": False,
    }
    try:
        resp = requests.post(OLLAMA_API_URL, json=payload, timeout=120)
        resp.raise_for_status()
        return resp.json().get("response", "No response from model.")
    except requests.exceptions.RequestException as e:
        return f"[ERROR] Ollama API error: {e}"

def ask_openai(prompt: str, diff: str) -> str:
    """Call OpenAI GPT API."""
    client = OpenAI()
    full_prompt = f"{prompt}\n\nHere is the git diff:\n{diff}"
    try:
        resp = client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=[
                {"role": "system", "content": "You are an expert code reviewer."},
                {"role": "user", "content": full_prompt},
            ],
        )
        return resp.choices[0].message.content.strip()
    except Exception as e:
        return f"[ERROR] OpenAI API error: {e}"

def review_code(prompt: str, diff: str, backend: str = "ollama") -> str:
    """Unified entrypoint for either backend."""
    backend = backend.lower()
    if backend == "gpt" or backend == "openai":
        return ask_openai(prompt, diff)
    elif backend == "ollama":
        return ask_ollama(prompt, diff)
    else:
        return f"[ERROR] Unknown backend '{backend}'. Use 'ollama' or 'gpt'."
