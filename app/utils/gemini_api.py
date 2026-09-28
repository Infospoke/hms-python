import re
import json
from google import genai
from google.genai import types
from fastapi import HTTPException
from app.core import config as consts
import logging

logger = logging.getLogger(__name__)

# google-genai makes a single attempt by default, so transient 429/5xx
# responses are retried before a request is reported as failed.
GEMINI_HTTP_OPTIONS = types.HttpOptions(
    timeout=90_000,
    retry_options=types.HttpRetryOptions(attempts=3),
)

_client = None

def get_client() -> genai.Client:
    global _client
    if _client is None:
        _client = genai.Client(api_key=consts.GOOGLE_API_KEY, http_options=GEMINI_HTTP_OPTIONS)
    return _client

async def call_llm(prompt: str, model_name: str = None) -> dict:
    if not consts.GOOGLE_API_KEY:
        raise HTTPException(status_code=500, detail="GOOGLE_API_KEY is not configured.")

    client = get_client()
    model_to_use = model_name or consts.GEMINI_MODEL_FOR_JOB_DESCRIPTION

    # No temperature override: Google advises keeping Gemini 3.x models at
    # their default sampling settings.
    logger.info(f"Using Gemini model '{model_to_use}' for JSON generation...")
    response = await client.aio.models.generate_content(
        model=model_to_use,
        contents=prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True)
        )
    )

    raw = (response.text or "").strip()
    raw_cleaned = re.sub(r"^```(?:json)?\n", "", raw, flags=re.IGNORECASE)
    raw_cleaned = re.sub(r"\n```$", "", raw_cleaned).strip()

    try:
        return json.loads(raw_cleaned)
    except json.JSONDecodeError:
        # Try to find JSON inside raw text using regex
        match = re.search(r"(\{.*\}|\[.*\])", raw_cleaned, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(0))
            except json.JSONDecodeError:
                pass

        raise HTTPException(
            status_code=500, detail=f"LLM returned non-JSON response or extra data: {raw}"
        )
