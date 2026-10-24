"""Shared LLM client for HW5. Every AI call goes through Portkey using PORTKEY_API_KEY."""

import os
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI

HW5_DIR = Path(__file__).resolve().parent
# The key lives in "AI for managers/.env"; hw5/.env holds non-secret settings (model).
load_dotenv(HW5_DIR.parent / ".env")
load_dotenv(HW5_DIR / ".env")

PORTKEY_BASE_URL = os.environ.get("PORTKEY_BASE_URL", "https://api.portkey.ai/v1")
# Every HW5 agent uses this one model (keeps multi-agent token use down).
REQUIRED_MODEL = "gpt-6-luna"


def portkey_settings() -> tuple[str, str]:
    """Return (api_key, model) for Portkey. No fallback to other keys or models."""
    api_key = os.environ.get("PORTKEY_API_KEY")
    if not api_key:
        raise RuntimeError("PORTKEY_API_KEY not found (expected in 'AI for managers/.env').")
    model = os.environ.get("PORTKEY_MODEL")
    if not model:
        raise RuntimeError("PORTKEY_MODEL must be set (see hw5/.env).")
    if model != REQUIRED_MODEL:
        raise RuntimeError(f"HW5 agents must use {REQUIRED_MODEL}, not {model!r}.")
    return api_key, model


def get_client() -> tuple[OpenAI, str]:
    """Return (client, model) routed through Portkey."""
    api_key, model = portkey_settings()
    return OpenAI(api_key=api_key, base_url=PORTKEY_BASE_URL), model


if __name__ == "__main__":
    client, model = get_client()
    reply = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": "Reply with the single word: ok"}],
    )
    print(f"Portkey OK — model={model} reply={reply.choices[0].message.content!r}")
