import os
import logging
import re
from groq import AsyncGroq
import time

logger = logging.getLogger(__name__)


def is_ai_unavailable_response(content: str | None) -> bool:
    """
    True when the chat layer did not return usable model text (disabled API, error, or empty).
    Safe repair: central guard so json.loads never runs on AI_DISABLED / empty — use route-specific fallbacks.
    """
    if content is None:
        return True
    c = str(content).strip()
    return c == "" or c == "AI_DISABLED"


from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type, before_sleep_log
# Bleach is not installed - using native regex for sanitization (see sanitize_content)

def sanitize_content(text: str) -> str:
    """Removes potential scripts or malicious HTML from AI responses."""
    if not text:
        return ""
    # Remove script tags and common event handlers
    clean = re.sub(r'<script.*?>.*?</script>', '', text, flags=re.DOTALL | re.IGNORECASE)
    clean = re.sub(r'on\w+=".*?"', '', clean, flags=re.IGNORECASE)
    return clean

class AIClient:
    def __init__(self):
        # Safe repair — unified Groq key
        self.api_key = ""
        try:
            from app.core.config import get_settings
            keys = get_settings().groq_keys
            if keys:
                self.api_key = keys[0]
        except Exception as e:
            logger.debug("Groq key from Settings unavailable: %s", e)
        if not self.api_key:
            self.api_key = (os.getenv("GROQ_API_KEY", "") or "").strip()

        self.disabled = False
        self.client = None

        if not self.api_key:
            logger.warning("AI features disabled - GROQ_API_KEY not set in environment.")
            self.disabled = True
        else:
            try:
                timeout_s = float(os.getenv("AI_TIMEOUT_SECONDS", "45") or "45")
                self.client = AsyncGroq(api_key=self.api_key, timeout=timeout_s)
            except Exception as e:
                logger.warning(f"Failed to initialize Groq client: {e}. AI features disabled.")
                self.disabled = True

    @retry(
        retry=retry_if_exception_type((Exception)), # We filter inside or keep generic for LLM volatility
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        before_sleep=before_sleep_log(logger, logging.INFO),
        reraise=True
    )
    async def _generate_with_retry(self, prompt: str, system_instr: str, model: str) -> str:
        """Internal method for tenacity to wrap."""
        response = await self.client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_instr},
                {"role": "user", "content": prompt}
            ],
            temperature=0.7,
            max_tokens=2000,
        )
        return response.choices[0].message.content

    async def generate(self, prompt: str, system_instr: str = "You are a helpful assistant", model: str = "llama-3.1-8b-instant") -> str:
        """Centralized generator with resilience and safety."""
        if self.disabled:
            logger.warning("AI Disabled - Returning graceful fallback response.")
            return "AI_DISABLED"
            
        t0 = time.perf_counter()
        try:
            raw = await self._generate_with_retry(prompt, system_instr, model)
            if raw is None or not str(raw).strip():
                logger.warning("Groq returned empty message content.")
                return "AI_DISABLED"
            
            content = sanitize_content(str(raw).strip())
            
            elapsed_ms = (time.perf_counter() - t0) * 1000.0
            logger.debug("AI generate ok", extra={"elapsed_ms": elapsed_ms, "len": len(content)})
            return content
        except Exception as e:
            elapsed_ms = (time.perf_counter() - t0) * 1000.0
            logger.error(f"AI Final Failure after retries: {e}", extra={"elapsed_ms": elapsed_ms})
            return "AI_DISABLED"

# Singleton instance to be imported globally
ai_client = AIClient()

def clean_json(text: str) -> str:
    """Clean markdown code blocks from JSON string and extract first JSON object"""
    # Remove markdown code blocks
    text = text.replace("```json", "").replace("```", "").strip()
    
    # Try to find JSON object with regex if it's not clean
    match = re.search(r'(\{.*\})', text, re.DOTALL)
    if match:
        return match.group(1)
        
    match_list = re.search(r'(\[.*\])', text, re.DOTALL)
    if match_list:
        return match_list.group(1)

    return text
