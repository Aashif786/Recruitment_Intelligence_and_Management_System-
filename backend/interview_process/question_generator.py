from app.services.ai_client import ai_client
import random
from typing import List, Dict
import json
import re
import logging
from .config import SKILL_CATEGORIES, MODEL_NAME

logger = logging.getLogger(__name__)

class QuestionGenerator:
    def _get_varied_fallbacks(self, category: str, difficulty: str, needed: int, exclude: List[str] = None) -> List[str]:
        """Generate a variety of fallback questions to avoid repetition."""
        if exclude is None:
            exclude = []
            
        if "scenario" in difficulty or "deep" in difficulty:
            templates = [
                f"Can you describe a real-world scenario where you applied your knowledge of {category}?",
                f"Walk me through a complex problem you solved using {category}.",
                f"What is the most challenging project you've handled involving {category}?",
                f"How would you approach a critical failure or bottleneck in a {category} system?",
                f"Describe a time you had to optimize the performance of a {category} implementation."
            ]
        else:
            templates = [
                f"Can you explain a fundamental concept related to {category}?",
                f"What are the core principles or best practices when working with {category}?",
                f"How do you handle common issues or errors in {category}?",
                f"Explain the role and importance of {category} in a modern development stack.",
                f"What are the key advantages and disadvantages of using {category}?"
            ]
            
        # Filter out already present questions
        available = [t for t in templates if t not in exclude]
        if not available:
            available = templates # Restart if all excluded
            
        result = []
        import random
        random.shuffle(available)
        
        while len(result) < needed:
            result.append(available[len(result) % len(available)])
            
        return result

    def __init__(self):
        self.ai_client = ai_client
        self.client = ai_client  # Fallback for old attribute checks

    # 1️⃣ FIRST QUESTION (GENERIC)
    def generate_general_intro_question(self) -> str:
        return (
            "Please describe your professional background, key skills, tools you use, "
            "and the type of projects you have worked on."
        )

    async def generate_initial_skill_questions(
        self, skill_category: str, candidate_level: str = "mid"
    ) -> List[str]:
        # Async Groq call (no asyncio.run) so FastAPI's event loop is not nested inside thread pools.
        skills = SKILL_CATEGORIES.get(skill_category, [])
        skills_text = ", ".join(skills[:6]) if skills else skill_category

        prompt = f"""
        You are an interviewer.

        Candidate level: {candidate_level}
        Domain: {skill_category}
        Key skills: {skills_text}

        Generate:
        - 2 fundamental questions
        - 2 practical questions
        - 1 scenario-based question

        Each must be strictly related to the domain.
        
        IMPORTANT: Vary the questions. Do not use the same standard questions every time.
        Focus on: {random.choice(['performance and optimization', 'security and best practices', 'architecture and design', 'debugging and troubleshooting', 'modern features and updates'])}
        """

        try:
            content = await self.ai_client.generate(prompt=prompt, system_instr="You are an interviewer.", model=MODEL_NAME)

            if not content or content == "AI_DISABLED":
                logger.warning(f"AI returned empty content for {skill_category}. Using fallbacks.")
                return self._fallback(skill_category)

            import re
            # Clean up leading numbers (1. Question -> Question) and filter only questions
            cleaned_questions = []
            for q in content.split("\n"):
                q = q.strip()
                if q.endswith("?"):
                    # Remove markdown bolding and leading numbering
                    clean = re.sub(r'^\d+[\.\)]\s*', '', q)
                    clean = re.sub(r'\*\*+', '', clean)
                    if clean:
                        cleaned_questions.append(clean)
            
            # Prevent duplicate questions within the batch
            unique_questions = []
            for q in cleaned_questions:
                if q not in unique_questions:
                    unique_questions.append(q)

            if len(unique_questions) >= 5:
                return unique_questions[:5]
            
            logger.warning(f"AI returned only {len(unique_questions)} unique questions. Filling with fallbacks.")
            return unique_questions + self._get_varied_fallbacks(skill_category, "basic", 5 - len(unique_questions), exclude=unique_questions)

        except Exception as e:
            logger.error(f"Error in generate_initial_skill_questions: {e}")
            return self._fallback(skill_category)

    def generate_behavioral_question_ai(
        self,
        candidate_background: dict,
        context: list | None = None
    ) -> str:
        """
        Generate a behavioral question based on candidate background.
        Context is optional and used for future adaptive behavior.
        """

        domain = candidate_background.get("primary_skill", "general")

        if domain == "bim":
            return (
                "Tell me about a time you identified a coordination or clash issue "
                "that was outside your assigned scope in a BIM project. "
                "How did you handle it and what was the outcome?"
            )

        return (
            "Tell me about a time when you faced an unexpected challenge at work. "
            "How did you take ownership of the situation and resolve it?"
        )


    def _fallback(self, category: str) -> List[str]:
        skills = SKILL_CATEGORIES.get(category, [])
        if not skills:
            return [
                "Explain a core concept in your domain?",
                "Describe a real-world problem you solved?",
                "How do you stay updated in your field?"
            ]

        return [
            f"Explain a core concept in {skills[0]}?",
            f"How do you use {skills[1] if len(skills) > 1 else skills[0]}?",
            f"What challenges do you face with {skills[-1]}?"
        ]

    # ── METHODS FROM IMPROVED VERSION ────────────────────────────────────────

    async def generate_specific_questions(
        self,
        skill_category: str,
        count: int,
        difficulty: str = "basic",
        extracted_skills_list: List[str] = None,
        job_title: str = "",
        job_description: str = "",
    ) -> List[str]:
        """Backward-compatible wrapper that returns only question texts."""
        meta = await self.generate_specific_questions_with_meta(
            skill_category=skill_category,
            count=count,
            difficulty=difficulty,
            extracted_skills_list=extracted_skills_list,
            job_title=job_title,
            job_description=job_description,
        )
        return meta.get("questions", [])[:count]

    def _build_specific_prompt(
        self,
        skill_category: str,
        count: int,
        difficulty: str,
        extracted_skills_list: List[str] = None,
        job_title: str = "",
        job_description: str = "",
    ) -> str:
        if extracted_skills_list:
            skills_text = f"Candidate's exact matching skills: {', '.join(extracted_skills_list)}"
        else:
            skills = SKILL_CATEGORIES.get(skill_category, [])
            skills_text = ", ".join(skills[:8]) if skills else skill_category

        if difficulty == "basic":
            prompt_difficulty = "fundamental, simple definitions, core conceptual knowledge, very basic questions. Do NOT ask scenario-based questions. Keep them short and simple."
        else:
            prompt_difficulty = "scenario-based, follow-up style, detailed implementation, 'how would you handle X', practical problem solving"

        return f"""
        You are an expert technical interviewer assessing a candidate.
        Domain: {skill_category}
        Job Title: {job_title}
        Job Description:
        {job_description}
        {skills_text}

        Generate exactly {count} {difficulty} interview questions.
        Focus: {prompt_difficulty}

        CRITICAL INSTRUCTION:
        If skill_category is not 'general', strictly ask questions related to the Candidate's exact matching skills listed above that are highly relevant to the {skill_category} domain.
        If skill_category is 'general', infer the relevant domain/technologies from Job Title and Job Description and generate job-relevant questions (avoid generic/unfocused questions).
        
        DO NOT ask about generic office software (e.g., MS Office, Word, Excel).
        DO NOT ask about soft skills or leadership here.
        
        IMPORTANT:
        - When skill_category is not 'general', do not ask about technologies outside the {skill_category} domain.
        - When skill_category is 'general', use the job narrative to decide the in-scope technologies.
        
        If no relevant specific technologies are found in the skills list, ask about standard architectural concepts, industry best practices, or fundamentals of {skill_category}.

        Return valid JSON array of strings, e.g. ["Question 1", "Question 2"]
        """

    def _clean_ai_response(self, content: str) -> str:
        if not content:
            return ""
        cleaned = re.sub(r"```json", "", content, flags=re.IGNORECASE)
        cleaned = re.sub(r"```", "", cleaned).strip()
        return cleaned

    def _parse_questions_from_json(self, cleaned: str) -> List[str]:
        if not cleaned:
            return []
        # Try direct parse first
        try:
            data = json.loads(cleaned)
            if isinstance(data, list):
                return [str(q).strip() for q in data if str(q).strip()]
        except Exception:
            pass

        # Try extracting wrapped JSON array from prose
        start = cleaned.find("[")
        end = cleaned.rfind("]")
        if start != -1 and end != -1 and end > start:
            try:
                data = json.loads(cleaned[start : end + 1])
                if isinstance(data, list):
                    return [str(q).strip() for q in data if str(q).strip()]
            except Exception:
                pass
        return []

    def _parse_questions_from_lines(self, cleaned: str) -> List[str]:
        questions: List[str] = []
        if not cleaned:
            return questions
        for line in cleaned.split("\n"):
            line = line.strip()
            if "?" not in line:
                continue
            q = re.sub(r"^\s*[-*]?\s*\d*[\.\)]?\s*", "", line).strip()
            if q and q not in questions:
                questions.append(q)
        return questions

    async def _call_specific_questions_ai(self, prompt: str) -> tuple[str, str]:
        """
        Returns (content, failure_reason).
        failure_reason in: AI_FAILURE, TIMEOUT, AI_DISABLED, EMPTY_RESPONSE
        """
        try:
            content = await self.ai_client.generate(
                prompt=prompt,
                system_instr="You are an expert technical interviewer assessing a candidate.",
                model=MODEL_NAME,
            )
        except TimeoutError:
            return "", "TIMEOUT"
        except Exception as e:
            logger.error(f"AI_FAILURE while generating specific questions: {e}")
            return "", "AI_FAILURE"

        if content == "AI_DISABLED":
            return "", "AI_DISABLED"
        if not content or not str(content).strip():
            return "", "EMPTY_RESPONSE"
        return str(content), ""

    async def generate_specific_questions_with_meta(
        self,
        skill_category: str,
        count: int,
        difficulty: str = "basic",
        extracted_skills_list: List[str] = None,
        job_title: str = "",
        job_description: str = "",
    ) -> Dict:
        """
        Strict decision flow with explicit source tagging.
        source: ai | fallback_internal | fallback_hard
        """
        if not self.client:
            return {
                "questions": [f"Tell me about your {difficulty} experience with {skill_category}."] * count,
                "source": "fallback_internal",
                "reason": "AI_DISABLED",
                "partial": False,
            }

        prompt = self._build_specific_prompt(
            skill_category=skill_category,
            count=count,
            difficulty=difficulty,
            extracted_skills_list=extracted_skills_list,
            job_title=job_title,
            job_description=job_description,
        )

        # Retry AI call once on AI_FAILURE/TIMEOUT/AI_DISABLED/EMPTY_RESPONSE
        last_reason = "AI_FAILURE"
        for attempt in range(2):
            content, failure_reason = await self._call_specific_questions_ai(prompt)
            if failure_reason:
                last_reason = failure_reason
                logger.warning(
                    f"Question generation AI failure attempt={attempt+1}/2 reason={failure_reason} skill={skill_category}"
                )
                continue

            cleaned = self._clean_ai_response(content)
            parsed = self._parse_questions_from_json(cleaned)

            # AI_RESPONSE_INVALID: attempt recovery before fallback
            if not parsed:
                parsed = self._parse_questions_from_lines(cleaned)
                if parsed:
                    logger.warning(
                        f"Question generation recovered from AI_RESPONSE_INVALID via line parsing skill={skill_category}"
                    )

            parsed = [q for q in parsed if q and q.strip()]
            if len(parsed) >= count:
                return {
                    "questions": parsed[:count],
                    "source": "ai",
                    "reason": "",
                    "partial": False,
                }

            # Explicit partial response (no silent padding)
            if parsed:
                last_reason = "PARTIAL_RESPONSE"
                logger.warning(
                    f"Question generation partial attempt={attempt+1}/2 got={len(parsed)} expected={count} skill={skill_category}"
                )
                # Retry once before returning partial/fallback
                if attempt == 0:
                    continue
                return {
                    "questions": parsed[:count],
                    "source": "ai",
                    "reason": "PARTIAL_RESPONSE",
                    "partial": True,
                }

            last_reason = "PARSE_FAILED"
            logger.warning(
                f"Question generation parse failed attempt={attempt+1}/2 skill={skill_category} cleaned_len={len(cleaned)}"
            )

        # Fallback only after retries exhausted
        logger.error(
            f"Question generation falling back to internal templates reason={last_reason} skill={skill_category} count={count}"
        )
        return {
            "questions": self._get_varied_fallbacks(skill_category, difficulty, count, exclude=[]),
            "source": "fallback_internal",
            "reason": last_reason,
            "partial": False,
        }

    @staticmethod
    def _hardcoded_aptitude_questions() -> List[dict]:
        """Deterministic MCQs when Groq fails (avoids recursive self-calls)."""
        return [
            {"question": "If a train travels 60 km/h for 2 hours, how far does it go?", "options": ["120 km", "100 km", "140 km", "80 km"], "answer": 0},
            {"question": "A bat and a ball cost $1.10 in total. The bat costs $1.00 more than the ball. How much does the ball cost?", "options": ["$0.10", "$0.05", "$0.15", "$0.01"], "answer": 1},
            {"question": "What is the next number in the sequence: 2, 4, 8, 16, ...?", "options": ["32", "24", "48", "64"], "answer": 0},
            {"question": "If it takes 5 machines 5 minutes to make 5 widgets, how long would it take 100 machines to make 100 widgets?", "options": ["5 minutes", "100 minutes", "20 minutes", "50 minutes"], "answer": 0},
            {"question": "If you have a 3-liter jug and a 5-liter jug, how do you measure exactly 4 liters?", "options": ["Fill 5L, pour into 3L, empty 3L, pour remaining 2L into 3L, fill 5L, pour into 3L until full.", "Fill 3L, pour into 5L, fill 3L, pour into 5L until full.", "Fill 5L, pour into 3L.", "None of the above"], "answer": 0},
        ]

    async def generate_behavioral_questions_batch(self, count: int, behavioral_role: str = "general", job_title: str = "", job_description: str = "") -> List[str]:
        """Generate a batch of behavioral questions based on role level"""
        if not self.client:
            return ["Tell me about a time you worked in a team."] * count

        role_focus = ""
        if behavioral_role == "junior":
            role_focus = "Focus on: Learning, Adaptability, Following instructions, Teamwork, and Proactive communication."
        elif behavioral_role == "mid":
            role_focus = "Focus on: Ownership, Conflict Resolution, Independent Problem Solving, Mentoring juniors, and Cross-functional collaboration."
        elif behavioral_role == "lead":
            role_focus = "Focus on: Leadership, System Design Trade-offs, Project Management, Stakeholder Management, Driving team culture, and Handling critical failures."
        else:
            role_focus = "Focus on: Teamwork, Adaptability, Ownership, Conflict Resolution, and Communication."

        job_context = f"\nJob Title: {job_title}\nJob Description: {job_description}\n" if job_title or job_description else ""

        prompt = f"""
        You are an HR manager. Generate exactly {count} behavioral interview questions for a {behavioral_role} candidate.
        {role_focus}
        {job_context}
        Tailor the scenarios to match the realities of the specified job role if provided.

        Return valid JSON array of strings.
        """

        try:
            import json
            import re

            content = await self.ai_client.generate(prompt=prompt, system_instr="You are an HR manager.", model=MODEL_NAME)

            if not content or content == "AI_DISABLED":
                return [f"Tell me about a challenge you faced as a {behavioral_role}."] * count

            content = re.sub(r"```json", "", content)
            content = re.sub(r"```", "", content).strip()

            try:
                if content.startswith("["):
                    questions = json.loads(content)
                    if isinstance(questions, list):
                        while len(questions) < count:
                            questions.append(f"Can you tell me about a time you faced a relevant challenge as a {behavioral_role}?")
                        return questions[:count]
            except:
                pass

            questions = []
            for line in content.split('\n'):
                if '?' in line:
                    clean = re.sub(r'^\d+[\.\\)]\s*', '', line.strip())
                    questions.append(clean)

            while len(questions) < count:
                questions.append(f"Can you tell me about a time you faced a relevant challenge as a {behavioral_role}?")
            return questions[:count]

        except Exception:
            return [f"Tell me about a challenge you faced as a {behavioral_role}."] * count

    async def generate_aptitude_questions(self, count: int) -> List[dict]:
        """Generate a batch of AI aptitude questions with MCQ options"""
        if not self.client:
            return self._hardcoded_aptitude_questions()[: max(0, count)]

        prompt = f"""
        You are an assessment expert creating an aptitude test.
        Generate exactly {count} logical reasoning, basic math, or analytical aptitude questions.
        
        Each question must be an object with:
        - "question": The problem statement string.
        - "options": A list of exactly 4 plausible option strings.
        - "answer": The index (0-3) of the correct option.
        
        Return valid JSON array of objects.
        """
        
        fallback = self._hardcoded_aptitude_questions()[: max(0, count)]
        try:
            import json
            import re

            content = await self.ai_client.generate(prompt=prompt, system_instr="You are an assessment expert creating an aptitude test.", model=MODEL_NAME)

            if not content or content == "AI_DISABLED":
                logger.warning("Aptitude generation unavailable (empty or AI_DISABLED); using hardcoded fallback.")
                return fallback

            match = re.search(r'\[.*\]', content, re.DOTALL)
            if match:
                content = match.group(0)

            try:
                questions = json.loads(content)
                if isinstance(questions, list) and questions:
                    return questions[:count]
            except Exception:
                pass

            return fallback

        except Exception as e:
            logger.error("Aptitude AI generation failed: %s", e)
            return fallback
