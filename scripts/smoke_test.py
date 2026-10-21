"""Smoke test: verify that the OpenAI API key loads and authenticates."""

import os
import sys

from dotenv import load_dotenv
from openai import AuthenticationError, OpenAI

PLACEHOLDER = "sk-your-key-here"


def main() -> int:
    load_dotenv()
    key = os.getenv("OPENAI_API_KEY")

    if not key or key == PLACEHOLDER:
        print("OPENAI_API_KEY is missing or still the placeholder. Check your .env file.")
        return 1

    client = OpenAI()  # reads OPENAI_API_KEY from the environment

    try:
        models = client.models.list()
    except AuthenticationError:
        print("Authentication failed: OpenAI rejected the key.")
        return 1

    ids = sorted(m.id for m in models)
    print(f"Key OK. {len(ids)} models available to this key:")
    for model_id in ids:
        print(f"  {model_id}")
    return 0


if __name__ == "__main__":
    sys.exit(main())