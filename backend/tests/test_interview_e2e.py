import requests
import time

BASE_URL = "http://localhost:10000"

# --- Credentials (replace with the latest from your database) ---
# You can get these by approving a candidate for an interview and checking the `interviews` table.
email = "b8mcfkeplz@bwmyga.com"
access_key = "tABjyboTbS0b3xdt3mYR1w"

print(f"--- Starting E2E Interview Test for {email} ---")

# Step 1: Access the interview to get a session token
print("\n1. Accessing interview...")
access_res = requests.post(f"{BASE_URL}/api/interviews/access", json={
    "email": email,
    "access_key": access_key
})

if access_res.status_code != 200:
    print(f"  [FAIL] Access failed with status {access_res.status_code}: {access_res.text}")
    exit()

access_data = access_res.json()
token = access_data.get("access_token")
interview_id = access_data.get("interview_id")
headers = {"Authorization": f"Bearer {token}"}

print(f"  [SUCCESS] Got token and interview_id: {interview_id}")

# Step 2: Poll for the first question until it's ready
print("\n2. Fetching first question (polling if necessary)...")
question_data = None
for i in range(10): # Poll for up to 30 seconds
    question_res = requests.get(f"{BASE_URL}/api/interviews/{interview_id}/current-question", headers=headers)
    if question_res.status_code == 200:
        question_data = question_res.json()
        if question_data and question_data.get("id"):
            print(f"  [SUCCESS] Received question: {question_data.get('question_text')[:50]}...")
            break
    elif question_res.status_code == 202:
        print(f"  [INFO] Questions not ready yet (202), waiting 3s... (Attempt {i+1}/10)")
        time.sleep(3)
    else:
        print(f"  [FAIL] Failed to get question. Status: {question_res.status_code}, Response: {question_res.text}")
        exit()

if not question_data or not question_data.get("id"):
    print("  [FAIL] Timed out waiting for questions to be generated.")
    exit()

# Step 3: Submit an answer to the first question
print("\n3. Submitting answer...")
question_id = question_data.get("id")
answer_payload = {
    "question_id": question_id,
    "answer_text": "I have over 5 years of experience in backend development, primarily using Python with frameworks like FastAPI and Django. I am also proficient in Java and have worked with Spring Boot."
}

answer_res = requests.post(f"{BASE_URL}/api/interviews/{interview_id}/answer", headers=headers, json=answer_payload)

if answer_res.status_code == 200:
    print(f"  [SUCCESS] Answer submitted successfully.")
    print("  Response:", answer_res.json())
else:
    print(f"  [FAIL] Answer submission failed with status {answer_res.status_code}: {answer_res.text}")

print("\n--- Test Complete ---")
