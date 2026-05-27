import re
import json
from google import genai
from google.genai import types
from fastapi import HTTPException
from app.core import config as consts
from groq import AsyncGroq
import logging

logger = logging.getLogger(__name__)

_client = None
_groq_client = None

def get_client() -> genai.Client:
    global _client
    if _client is None:
        _client = genai.Client(api_key=consts.GOOGLE_API_KEY)
    return _client

def get_groq_client() -> AsyncGroq:
    global _groq_client
    if _groq_client is None:
        if not consts.GROQ_API_KEY:
            raise HTTPException(status_code=500, detail="GROQ_API_KEY is not configured.")
        _groq_client = AsyncGroq(api_key=consts.GROQ_API_KEY)
    return _groq_client

async def call_llm(prompt: str, model_name: str = None) -> dict:
    # 1. Use Groq as the primary model for ultra-fast generation
    try:
        groq_client = get_groq_client()
        groq_model = (
            model_name or 
            consts.GROQ_MODEL_FOR_JOB_DESCRIPTION or 
            consts.GROQ_MODEL or 
            "llama-3.3-70b-versatile"
        )
        logger.info(f"Using ultra-fast Groq model '{groq_model}' for JSON generation...")
        
        chat_completion = await groq_client.chat.completions.create(
            messages=[{"role": "user", "content": prompt}],
            model=groq_model,
            temperature=0.0,
            response_format={"type": "json_object"}
        )
        raw = chat_completion.choices[0].message.content.strip()
        
        # Clean JSON string (remove markdown block wrappers if present)
        raw_cleaned = re.sub(r"^```(?:json)?\n", "", raw, flags=re.IGNORECASE)
        raw_cleaned = re.sub(r"\n```$", "", raw_cleaned).strip()
        
        try:
            parsed = json.loads(raw_cleaned)
            logger.info("Groq JSON generation success!")
            return parsed
        except Exception as json_err:
            logger.error(f"Failed to parse Groq response as JSON: {json_err}. Raw output: {raw}")
            # Fallthrough to Gemini if JSON parsing failed
    except Exception as groq_err:
        logger.error(f"Groq API call failed: {groq_err}. Falling back to Gemini...")

    # 2. Gemini fallback flow
    if not consts.GOOGLE_API_KEY:
        raise HTTPException(status_code=500, detail="GOOGLE_API_KEY is not configured.")

    client = get_client()
    model_to_use = consts.GEMINI_MODEL or "gemini-3.5-flash"
    
    # Gemma models do not support response_mime_type="application/json" and throw 500 INTERNAL.
    # We dynamically fallback to a standard model (gemini-3.5-flash) for JSON requests.
    if model_to_use and ("gemma" in model_to_use.lower() or "gemini-1.5-flash" in model_to_use.lower()):
        logger.warning(f"Configured model '{model_to_use}' does not support JSON response mode. Falling back to 'gemini-3.5-flash'.")
        model_to_use = "gemini-3.5-flash"

    logger.info(f"Using Gemini model '{model_to_use}' for JSON generation...")
    response = await client.aio.models.generate_content(
        model=model_to_use,
        contents=prompt,
        config=types.GenerateContentConfig(
            temperature=0.0,
            response_mime_type="application/json",
            automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True)
        )
    )

    raw = response.text.strip()
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