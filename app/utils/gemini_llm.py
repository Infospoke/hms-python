import re
import json
import google.generativeai as genai
from fastapi import HTTPException
from app.core import config as consts

async def call_llm(prompt: str) -> dict:
    if not consts.GOOGLE_API_KEY:
        raise HTTPException(status_code=500, detail="GOOGLE_API_KEY is not configured.")

    genai.configure(api_key=consts.GOOGLE_API_KEY)

    model = genai.GenerativeModel(consts.GEMINI_MODEL)

    response = await model.generate_content_async(prompt)

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