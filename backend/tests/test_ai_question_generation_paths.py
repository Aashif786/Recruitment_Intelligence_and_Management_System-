import asyncio
import unittest

from interview_process.question_generator import QuestionGenerator


class QuestionGenerationPathTests(unittest.TestCase):
    def test_ai_success_json_list_no_fallback(self):
        qg = QuestionGenerator()

        async def fake_generate(*, prompt: str, system_instr: str = "", model: str = "") -> str:
            return '["Q1?","Q2?","Q3?"]'

        qg.ai_client.generate = fake_generate  # type: ignore

        async def run():
            return await qg.generate_specific_questions(
                skill_category="backend",
                count=3,
                difficulty="basic",
                extracted_skills_list=["python", "fastapi"],
                job_title="Backend Engineer",
                job_description="Build APIs",
            )

        out = asyncio.run(run())
        self.assertEqual(len(out), 3)
        self.assertTrue(all(isinstance(q, str) and q.strip() for q in out))
        self.assertEqual(out[0], "Q1?")

    def test_ai_malformed_json_falls_back_to_regex_split(self):
        qg = QuestionGenerator()

        async def fake_generate(*, prompt: str, system_instr: str = "", model: str = "") -> str:
            return "1) What is REST?\n2) How would you design an API rate limiter?\n3) Explain database indexing?"

        qg.ai_client.generate = fake_generate  # type: ignore

        async def run():
            return await qg.generate_specific_questions(
                skill_category="backend",
                count=3,
                difficulty="basic",
                extracted_skills_list=["python"],
                job_title="Backend Engineer",
                job_description="Build APIs",
            )

        out = asyncio.run(run())
        self.assertEqual(len(out), 3)
        self.assertTrue(out[0].endswith("?"))

    def test_ai_empty_response_triggers_internal_fallback(self):
        qg = QuestionGenerator()

        async def fake_generate(*, prompt: str, system_instr: str = "", model: str = "") -> str:
            return ""

        qg.ai_client.generate = fake_generate  # type: ignore

        async def run():
            return await qg.generate_specific_questions(
                skill_category="backend",
                count=4,
                difficulty="basic",
                extracted_skills_list=["python"],
                job_title="Backend Engineer",
                job_description="Build APIs",
            )

        out = asyncio.run(run())
        self.assertEqual(len(out), 4)
        self.assertTrue(all(isinstance(q, str) and q.strip() for q in out))

    def test_ai_timeout_exception_triggers_internal_fallback(self):
        qg = QuestionGenerator()

        async def fake_generate(*, prompt: str, system_instr: str = "", model: str = "") -> str:
            raise TimeoutError("simulated timeout")

        qg.ai_client.generate = fake_generate  # type: ignore

        async def run():
            return await qg.generate_specific_questions(
                skill_category="backend",
                count=2,
                difficulty="basic",
                extracted_skills_list=["python"],
                job_title="Backend Engineer",
                job_description="Build APIs",
            )

        out = asyncio.run(run())
        self.assertEqual(len(out), 2)
        self.assertTrue(all(isinstance(q, str) and q.strip() for q in out))


if __name__ == "__main__":
    unittest.main()
