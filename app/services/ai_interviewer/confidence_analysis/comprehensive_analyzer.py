import json
import logging
from app.core import config
from app.services.resume_parser.gemini_client import GeminiClient

logger = logging.getLogger(__name__)


class ComprehensiveAnalyzer(GeminiClient):
    def __init__(self, api_key=None):
        super().__init__(model=config.GEMINI_MODEL_FOR_AI_INTERVIEWER)
        logger.info(f"ComprehensiveAnalyzer initialized with model: {self.model}")

    def analyze(self, text):
        if not text:
            return None
        logger.info(f"Gemini analyzing text of length {len(text)}...")

        prompt = f"""
        Analyze this interview answer transcript.
        TRANSCRIPT: "{text}"
        
        Return a valid JSON object with these EXACT keys:
        - "assertiveness_score": (0-100)
        - "sentence_completeness": (0-100)
        - "clarity_index": (0-100)
        - "professionalism_rating": ("High", "Medium", "Low")
        - "key_phrases": (list of strong confidence markers)
        - "weakness_flags": (list of hedging words or red flags)
        
        JSON ONLY. No markdown.
        """
        try:
            result = self.generate_response(prompt)
            if not result.get("success"):
                logger.error(f"Gemini analysis failed: {result.get('error')}")
                return None

            response_content = result["response"]

            clean_json = (
                response_content.replace("```json", "").replace("```", "").strip()
            )
            return json.loads(clean_json)
        except Exception as e:
            logger.error(f"Error in comprehensive analysis: {e}")
            return None
