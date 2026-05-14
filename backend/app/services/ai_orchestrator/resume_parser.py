import json
import logging
from app.services.ai_client import ai_client, clean_json

logger = logging.getLogger(__name__)

async def parse_resume(text: str) -> dict:
    """Extracts structured fields from raw resume text."""
    logger.info("Parsing resume with AI Orchestrator")
    
    prompt = f"Analyze the following resume text and extract structured information.\n\nResume Text:\n{text}"
    system_instr = "You are an expert technical recruiter. Parse the resume and return a JSON object with: 'skills' (list of strings), 'years_of_experience' (float), 'education' (list of objects), 'previous_roles' (list of objects with 'title', 'company', 'duration'), 'summary' (string). Return ONLY valid JSON."
    
    try:
        response = await ai_client.generate(prompt, system_instr, model="llama-3.3-70b-versatile")
        return json.loads(clean_json(response))
    except Exception as e:
        logger.error(f"Failed to parse resume: {str(e)}", exc_info=True)
        # Fallback mechanism
        return {"skills": [], "years_of_experience": 0, "education": [], "previous_roles": [], "summary": "Failed to parse."}
