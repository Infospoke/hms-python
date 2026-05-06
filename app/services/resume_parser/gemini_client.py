import logging
import time
from typing import Dict, Any
from concurrent.futures import ThreadPoolExecutor, TimeoutError
import app.core.config as consts
from app.core.exceptions import GeminiAPIException

try:
    from google import genai
    from google.genai import types
except ImportError:
    genai = None
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

GEMINI_REQUEST_TIMEOUT_SECONDS = 90


# --- GEMINI CLIENT ---


class GeminiClient:

    def __init__(self, model: str = consts.GEMINI_MODEL):
        if genai is None:
            raise ImportError(consts.GENAI_IMPORT_ERROR)
        try:
            self.client = genai.Client(api_key=consts.GOOGLE_API_KEY)
            self.model_name = model
            logger.info(f"Gemini client initialized successfully for model: {model}")
        except Exception as e:
            logger.error(f"Failed to initialize Gemini client: {str(e)}")
            raise GeminiAPIException(consts.GEMINI_INIT_ERROR(model, e), 500, e)

    def generate_response(
        self, prompt: str, system_prompt: str = None
    ) -> Dict[str, Any]:
        if not prompt or not isinstance(prompt, str):
            logger.warning("Invalid prompt provided")
            raise ValueError(consts.EMPTY_STRING_ERROR)
        if system_prompt:
            final_prompt = system_prompt + "\n\n" + prompt
        else:
            final_prompt = prompt
        try:
            start_time = time.time()
            with ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(
                    self.client.models.generate_content,
                    model=self.model_name,
                    contents=final_prompt,
                    config=types.GenerateContentConfig(
                        temperature=0.0,
                        automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True)
                    )
                )
                response = future.result(timeout=GEMINI_REQUEST_TIMEOUT_SECONDS)
            end_time = time.time()
            processing_time = end_time - start_time
            response_content = response.text
            logger.info(
                f"Gemini API response generated successfully in {processing_time:.2f}s"
            )
            return {
                "success": True,
                "response": response_content,
                "processing_time": processing_time,
                "model": self.model_name,
                "prompt_tokens": len(prompt.split()),
                "error": None,
            }
        except TimeoutError as e:
            raise GeminiAPIException(
                f"Gemini request timeout after {GEMINI_REQUEST_TIMEOUT_SECONDS} seconds",
                504,
                e,
            )
        except ValueError as e:
            logger.error(f"Gemini API returned invalid response: {str(e)}")
            raise GeminiAPIException(consts.GEMINI_API_VALIDATION_ERROR(e), 422, e)
        except Exception as e:
            logger.error(f"Gemini API error: {str(e)}")
            raise GeminiAPIException(consts.GEMINI_API_CALL_FAILED(e), 503, e)

    def count_tokens(self, text: str) -> int:
        try:
            return self.client.models.count_tokens(
                model=self.model_name,
                contents=text
            ).total_tokens
        except Exception as e:
            logger.error(f"Error counting tokens: {e}")
            return len(text) // 4
