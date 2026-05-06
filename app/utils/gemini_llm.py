import re
import json
from google import genai
from google.genai import types
from fastapi import HTTPException
from app.core import config as consts

_client = None

def get_client() -> genai.Client:
    global _client
    if _client is None:
        _client = genai.Client(api_key=consts.GOOGLE_API_KEY)
    return _client

async def call_llm(prompt: str) -> dict:
    if not consts.GOOGLE_API_KEY:
        raise HTTPException(status_code=500, detail="GOOGLE_API_KEY is not configured.")

    client = get_client()

    response = await client.aio.models.generate_content(
        model=consts.GEMINI_MODEL,
        contents=prompt,
        config=types.GenerateContentConfig(
            temperature=0.0,
            automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True)
        )
    )

    raw = response.text.strip()

    raw = re.sub(r"^```(?:json)?", "", raw).strip()
    raw = re.sub(r"```$", "", raw).strip()

    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", raw, re.DOTALL)
        if match:
            return json.loads(match.group())
        raise HTTPException(
            status_code=500, detail=f"LLM returned non-JSON response: {raw}"
        )