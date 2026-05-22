import asyncio
import os
import sys

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from interview_process.response_analyzer import ResponseAnalyzer
from app.services.ai_client import ai_client

async def main():
    print("Initializing ResponseAnalyzer...")
    analyzer = ResponseAnalyzer()
    
    question = "Walk me through a complex problem you solved using backend."
    # The answer in the DB has double quotes inside single quotes: '"How do you handle common issues or errors in backend?"'
    # Wait, let's try evaluating it.
    answer = '"How do you handle common issues or errors in backend?"'
    question_type = "technical"
    
    print(f"\nEvaluating Answer:\nQuestion: {question}\nAnswer: {answer}\n")
    
    try:
        # We call evaluate_answer directly
        result = await analyzer.evaluate_answer(question, answer, question_type)
        print("\nEvaluation Result:")
        import pprint
        pprint.pprint(result)
    except Exception as e:
        print(f"\nError occurred: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main())
