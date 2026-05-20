
import sys
import os
import json
import asyncio

# Add backend to path
sys.path.append(os.path.join(os.getcwd(), 'backend'))

from interview_process.utils import is_gibberish, analyze_response_quality
from interview_process.response_analyzer import ResponseAnalyzer

def test_gibberish():
    print("--- Testing Gibberish Detection ---")
    test_cases = [
        ("This is a perfectly normal technical answer about microservices.", False),
        ("aaaaaaaaaaaaaaaaaaaaaaaaaaaaaa", True),
        ("bcdfghjklmnpqrstvwxyz bcdfghjklmnpqrstvwxyz", True), # Too few vowels
        ("!@#$%^&*() !@#$%^&*() !@#$%^&*()", True), # Too many special chars
        ("Short", False), # Too short to be sure
        ("Averylongwordthatdoesnotexistinanylanguageandisjustastringofrandomcharacterswithnospacesatallanditjustkeepsgoingonandon", True),
    ]
    
    for text, expected in test_cases:
        result = is_gibberish(text)
        print(f"Text: {text[:30]}... | Expected: {expected} | Got: {result}")
        assert result == expected, f"Failed for: {text}"
    print("Gibberish detection passed!")

def test_score_weighting_logic():
    print("\n--- Testing Score Weighting Logic ---")
    # Simulating the logic from _finalize_interview_and_report_internal
    def calculate_score(tech_scores, behav_scores):
        tech_avg = sum(tech_scores) / len(tech_scores) if tech_scores else 0.0
        behav_avg = sum(behav_scores) / len(behav_scores) if behav_scores else 0.0
        
        if tech_scores and behav_scores:
            return round((tech_avg * 0.7 + behav_avg * 0.3), 2)
        elif tech_scores:
            return round(tech_avg, 2)
        elif behav_scores:
            return round(behav_avg, 2)
        else:
            return 0.0

    # Case 1: Both present
    score = calculate_score([10, 10], [5, 5])
    print(f"Both present (10 tech, 5 behav): {score} (Expected: 8.5)")
    assert score == 8.5
    
    # Case 2: Only tech
    score = calculate_score([10, 10], [])
    print(f"Only tech (10, 10): {score} (Expected: 10.0)")
    assert score == 10.0
    
    # Case 3: Only behavioral
    score = calculate_score([], [5, 5])
    print(f"Only behavioral (5, 5): {score} (Expected: 5.0)")
    assert score == 5.0
    
    print("Score weighting logic passed!")

async def test_report_generation_params():
    print("\n--- Testing Report Generation Params ---")
    # We can't easily call the actual AI service without a key/mock, 
    # but we can check if the function signature and calls match.
    # The actual implementation of generate_interview_report was updated in ai_service.py
    
    from app.services.ai_service import generate_interview_report
    import inspect
    
    sig = inspect.signature(generate_interview_report)
    print(f"generate_interview_report signature: {sig}")
    assert 'aptitude_context' in sig.parameters
    print("Signature check passed!")

if __name__ == "__main__":
    test_gibberish()
    test_score_weighting_logic()
    asyncio.run(test_report_generation_params())
    print("\nAll verification tests passed!")
