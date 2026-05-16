"""
llm_client.py — Unified LLM abstraction for Still Point Engine.

Supports:
  - "local"  → Ollama (local, private, no cost)
  - "gemini" → Google Gemini API (cloud, requires GEMINI_API_KEY in config)

Usage:
    from llm_client import generate, embed

    text = generate(prompt, provider="gemini")
    vec  = embed(text)   # always local (Nomic)
"""
import re

from config import LLM_MODEL, GEMINI_API_KEY, GEMINI_MODEL


# ─── Ollama (local) ──────────────────────────────────────────────────────────

def _generate_ollama(prompt: str) -> str:
    import ollama
    res = ollama.generate(model=LLM_MODEL, prompt=prompt)
    return res["response"]


# ─── Gemini ───────────────────────────────────────────────────────────────────

def _generate_gemini(prompt: str, max_retries: int = 5) -> str:
    """
    Call Gemini generateContent REST API with exponential-backoff retry on 429.

    Free tier limits: 15 RPM / 1,500 RPD for gemini-2.0-flash.
    Retry schedule on 429: 5s → 15s → 30s → 60s → give up.
    """
    import urllib.request
    import urllib.error
    import json
    import time

    if not GEMINI_API_KEY:
        raise RuntimeError(
            "GEMINI_API_KEY is not set in config.py. "
            "Add your key or switch to the local LLM provider."
        )

    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"{GEMINI_MODEL}:generateContent?key={GEMINI_API_KEY}"
    )
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature":     0.85,
            "maxOutputTokens": 8192,
        },
    }
    data = json.dumps(payload).encode("utf-8")

    wait_secs = [5, 15, 30, 60]

    for attempt in range(max_retries):
        try:
            req  = urllib.request.Request(
                url, data=data,
                headers={"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=90) as resp:
                body = json.loads(resp.read())

            return body["candidates"][0]["content"]["parts"][0]["text"]

        except urllib.error.HTTPError as e:
            err_body = e.read().decode("utf-8")
            is_daily_quota = False
            detailed_msg = e.reason

            try:
                err_json = json.loads(err_body)
                detailed_msg = err_json.get("error", {}).get("message", e.reason)
                details = err_json.get("error", {}).get("details", [])
                for d in details:
                    if d.get("@type") == "type.googleapis.com/google.rpc.QuotaFailure":
                        for v in d.get("violations", []):
                            if "PerDay" in v.get("quotaId", ""):
                                is_daily_quota = True
                                detailed_msg += f" [Daily Quota Hit: limit {v.get('quotaValue')} requests/day]"
            except Exception:
                if "PerDay" in err_body:
                    is_daily_quota = True

            if e.code in (429, 500, 502, 503, 504) and attempt < max_retries - 1 and not is_daily_quota:
                wait = wait_secs[min(attempt, len(wait_secs) - 1)]
                print(f"[gemini] HTTP {e.code} — retrying in {wait}s "
                      f"(attempt {attempt+1}/{max_retries})")
                time.sleep(wait)
                continue

            # Re-raise anything else, or the final error
            if is_daily_quota:
                raise RuntimeError(
                    f"Gemini HTTP {e.code}: {detailed_msg}. "
                    "You have exhausted your Google API daily quota. Please switch to the Local LLM."
                ) from e
            else:
                raise RuntimeError(
                    f"Gemini HTTP {e.code}: {detailed_msg}. "
                    "If this keeps happening, switch to Local LLM or wait a minute."
                ) from e

    raise RuntimeError("Gemini: max retries exceeded (rate limit).")


# ─── Public API ───────────────────────────────────────────────────────────────

def generate(prompt: str, provider: str = "local") -> str:
    """
    Generate text from `prompt` using the chosen provider.

    Args:
        prompt:   The full prompt string.
        provider: "local" (Ollama) or "gemini" (Google Gemini API).

    Returns:
        Raw generated string.
    """
    if provider == "gemini":
        return _generate_gemini(prompt)
    return _generate_ollama(prompt)


def embed(text: str) -> list:
    """
    Always uses local Ollama Nomic embeddings (no cloud dependency).
    Embeddings are used for ChromaDB topic similarity — kept local for privacy.
    """
    import ollama
    from config import EMBED_MODEL
    return ollama.embeddings(model=EMBED_MODEL, prompt=text)["embedding"]
