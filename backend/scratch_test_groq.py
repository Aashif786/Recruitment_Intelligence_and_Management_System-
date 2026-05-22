import asyncio
import os
import sys

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.services.ai_client import ai_client
from interview_process.config import MODEL_NAME

async def main():
    print(f"Disabled status: {ai_client.disabled}")
    print(f"API key loaded: {ai_client.api_key[:10]}...{ai_client.api_key[-5:] if ai_client.api_key else ''}")
    print(f"Model configured: {MODEL_NAME}")
    
    prompt = "Hello! Please reply with 'Test OK' if you can read this."
    system_instr = "You are a test runner."
    
    print("\n--- Testing default model llama-3.1-8b-instant ---")
    try:
        res = await ai_client.generate(prompt=prompt, system_instr=system_instr, model="llama-3.1-8b-instant")
        print(f"Response: {res}")
    except Exception as e:
        print(f"Error: {e}")
        
    print(f"\n--- Testing configured model {MODEL_NAME} ---")
    try:
        res = await ai_client.generate(prompt=prompt, system_instr=system_instr, model=MODEL_NAME)
        print(f"Response: {res}")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(main())
