import requests
import time

BASE_URL = "http://localhost:10000"

# --- Credentials (replace with the latest from your database) ---
email = "b8mcfkeplz@bwmyga.com"
access_key = "tABjyboTbS0b3xdt3mYR1w"

print("=" * 60)
print("FULL INTERVIEW SIMULATION")
print("=" * 60)

# Step 1: Access interview
print("\n1. Accessing interview...")
res = requests.post(f"{BASE_URL}/api/interviews/access", json={
    "email": email, "access_key": access_key
})

if res.status_code != 200:
    print(f"  [FAIL] Access failed: {res.status_code} {res.text}")
    exit()

data = res.json()
token = data.get("access_token")
interview_id = data.get("interview_id")
headers = {"Authorization": f"Bearer {token}"}
print(f"  [SUCCESS] Accessed Interview ID: {interview_id}")

# Step 2: Get ALL questions
print("\n2. Fetching all questions...")
questions = []
for attempt in range(10):
    res = requests.get(f"{BASE_URL}/api/interviews/{interview_id}/questions", headers=headers)
    if res.status_code == 200:
        questions = res.json()
        if questions and len(questions) > 0:
            break
    print(f"  [INFO] Waiting for questions... attempt {attempt+1}")
    time.sleep(3)

if not questions:
    print("  [FAIL] Could not fetch questions.")
    exit()

print(f"  [SUCCESS] Fetched {len(questions)} questions.")
print("=" * 60)

# Step 3: Answer every question
print("\n3. Answering all questions...")
sample_answers = [
    "I have over 5 years of experience working with Java, React, and Docker in enterprise environments. I focus on writing clean, scalable code and building robust CI/CD pipelines.",
    "I approach problems by first understanding the core requirements, then breaking them down into smaller, manageable parts. I test each component individually before integrating them.",
    "I use a combination of version control with Git, mandatory code reviews for all new features, and a comprehensive suite of unit and integration tests to maintain high code quality.",
    "I believe in proactive communication. I communicate blockers as soon as they arise, provide regular status updates, and document my work thoroughly to ensure the team is always aligned.",
    "I prioritize tasks based on their impact on the project goals and the urgency of the deadline. I use agile methodologies like Scrum to stay organized and adapt to changing requirements.",
]

for i, question in enumerate(questions):
    question_text = question.get('question_text', question.get('text', ''))
    print(f"\nQ{i+1}: {question_text}")
    
    answer = sample_answers[i % len(sample_answers)]
    print(f"  A: {answer}")
    
    res = requests.post(
        f"{BASE_URL}/api/interviews/{interview_id}/answer",
        headers=headers,
        json={"question_id": question["id"], "answer_text": answer}
    )
    
    if res.status_code == 200:
        print(f"    -> Status: {res.status_code} - {res.json().get('message', res.json())}")
    else:
        print(f"    -> [FAIL] Status: {res.status_code} - {res.text}")
    time.sleep(1)

print("\n" + "=" * 60)
print("INTERVIEW COMPLETE")
print("=" * 60)

# Step 4: Get final status
print("\n4. Fetching final interview status...")
res = requests.get(f"{BASE_URL}/api/interviews/{interview_id}/stage", headers=headers)

if res.status_code == 200:
    print(f"  [SUCCESS] Final Stage: {res.json()}")
else:
    print(f"  [FAIL] Could not fetch final status: {res.status_code} {res.text}")
