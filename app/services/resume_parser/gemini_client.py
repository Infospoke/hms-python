import logging
import time
from typing import Dict, Any
from concurrent.futures import ThreadPoolExecutor, TimeoutError
import app.core.config as consts
from app.core.exceptions import GeminiAPIException

try:
    import google.generativeai as genai
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
            genai.configure(api_key=consts.GOOGLE_API_KEY)
            self.model = genai.GenerativeModel(
                model_name=model, generation_config={"temperature": 0.0}
            )
            logger.info(f"Gemini model initialized successfully: {model}")
        except Exception as e:
            logger.error(f"Failed to initialize Gemini model: {str(e)}")
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
                future = executor.submit(self.model.generate_content, final_prompt)
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
                "model": str(self.model),
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
            return self.model.count_tokens(text).total_tokens
        except Exception as e:
            logger.error(f"Error counting tokens: {e}")
            return len(text) // 4
