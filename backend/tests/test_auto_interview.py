import os
import time
import json
import sys
from io import BytesIO
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse, unquote

import requests
import psycopg2
from dotenv import load_dotenv
from passlib.context import CryptContext
from jose import jwt as jose_jwt

try:
    # Ensure prints are flushed to the terminal log immediately.
    sys.stdout.reconfigure(line_buffering=True, write_through=True)
except Exception:
    pass


def _load_env():
    # .env lives next to this script (rims/backend/.env)
    dotenv_path = os.path.join(os.path.dirname(__file__), ".env")
    if not os.path.exists(dotenv_path):
        dotenv_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env")
    load_dotenv(dotenv_path=dotenv_path)


def _parse_db_url(db_url: str):
    if not db_url:
        raise RuntimeError("DATABASE_URL missing from .env")
    parsed = urlparse(db_url)
    return {
        "dbname": parsed.path[1:],
        "user": unquote(parsed.username) if parsed.username else None,
        "password": unquote(parsed.password) if parsed.password else None,
        "host": parsed.hostname,
        "port": parsed.port or 5432,
    }


def _get_conn(db_params: dict):
    return psycopg2.connect(
        dbname=db_params["dbname"],
        user=db_params["user"],
        password=db_params["password"],
        host=db_params["host"],
        port=db_params["port"],
    )


def _hr_headers_from_super_admin(db_conn, jwt_secret: str, jwt_algorithm: str = "HS256"):
    # We forge a valid HR JWT using the server's JWT_SECRET.
    # This avoids needing the super-admin password (the test environment may not expose it).
    cur = db_conn.cursor()
    cur.execute(
        """
        SELECT id, email, full_name, role
        FROM users
        WHERE role IN ('super_admin', 'hr')
          AND approval_status = 'approved'
          AND is_active = TRUE
        ORDER BY id DESC
        LIMIT 1
        """
    )
    row = cur.fetchone()
    cur.close()
    if not row:
        raise RuntimeError("No approved active HR/super_admin user found in DB.")

    user_id, email, full_name, role = row
    now = datetime.now(timezone.utc)
    exp = now + timedelta(minutes=120)  # matches default jwt_expiration_minutes

    payload = {
        "sub": str(user_id),
        "email": email,
        "role": role,
        "full_name": full_name,
        "exp": exp,
    }
    token = jose_jwt.encode(payload, jwt_secret, algorithm=jwt_algorithm)
    return {"Authorization": f"Bearer {token}"}


def _bcrypt_hash(context: CryptContext, raw: str) -> str:
    return context.hash(raw)


def _api_post(session: requests.Session, url: str, *, json_body=None, headers=None, timeout=120):
    last_err = None
    for attempt in range(3):
        try:
            return session.post(url, json=json_body, headers=headers, timeout=timeout)
        except requests.exceptions.RequestException as e:
            last_err = e
            time.sleep(2 * (attempt + 1))
    raise last_err


def _api_put(session: requests.Session, url: str, *, json_body=None, headers=None, timeout=120):
    last_err = None
    for attempt in range(3):
        try:
            return session.put(url, json=json_body, headers=headers, timeout=timeout)
        except requests.exceptions.RequestException as e:
            last_err = e
            time.sleep(2 * (attempt + 1))
    raise last_err


def _api_get(session: requests.Session, url: str, *, headers=None, timeout=120):
    last_err = None
    for attempt in range(3):
        try:
            return session.get(url, headers=headers, timeout=timeout)
        except requests.exceptions.RequestException as e:
            last_err = e
            time.sleep(2 * (attempt + 1))
    raise last_err


def main():
    _load_env()

    BASE_URL = os.getenv("BASE_URL", "http://localhost:10000")

    db_url = os.getenv("DATABASE_URL")
    jwt_secret = os.getenv("JWT_SECRET") or os.getenv("jwt_secret")
    jwt_algorithm = os.getenv("JWT_ALGORITHM", "HS256")

    if not jwt_secret:
        raise RuntimeError("JWT_SECRET missing from .env")

    db_params = _parse_db_url(db_url)

    print("\n" + "=" * 80)
    print("FULL AUTO INTERVIEW TEST - FROM SCRATCH")
    print("=" * 80)

    # --- Step 0: Schema inspection (must run) ---
    conn = _get_conn(db_params)
    cur = conn.cursor()

    cur.execute(
        """
        SELECT column_name
        FROM information_schema.columns
        WHERE table_name = 'interviews'
        ORDER BY ordinal_position
        """
    )
    interview_cols = [r[0] for r in cur.fetchall()]
    print(f"\nInterviews table columns: {interview_cols}")

    cur.execute(
        """
        SELECT column_name
        FROM information_schema.columns
        WHERE table_name = 'jobs'
        ORDER BY ordinal_position
        """
    )
    job_cols = [r[0] for r in cur.fetchall()]
    print(f"Jobs table columns: {job_cols}")

    cur.execute(
        """
        SELECT column_name
        FROM information_schema.columns
        WHERE table_name = 'applications'
        ORDER BY ordinal_position
        """
    )
    app_cols = [r[0] for r in cur.fetchall()]
    print(f"Applications table columns: {app_cols}")

    # Determine the "access key" column we can poll/override.
    access_key_col = None
    for col in interview_cols:
        c = col.lower()
        if ("raw" in c) and ("key" in c):
            access_key_col = col
            break
    if not access_key_col:
        for col in interview_cols:
            c = col.lower()
            if "access" in c and "key" in c:
                access_key_col = col
                break
    if not access_key_col:
        for col in interview_cols:
            c = col.lower()
            if "key" in c and ("token" in c or "code" in c or "access" in c):
                access_key_col = col
                break
    print(f"\nUsing access key column: '{access_key_col}'")

    if not access_key_col:
        raise RuntimeError("Could not locate an access key column in interviews table.")

    cur.close()
    conn.close()

    # --- Step 1: Forge HR auth and create a Job via API ---
    session = requests.Session()

    conn = _get_conn(db_params)
    cur = conn.cursor()
    # Pick JWT for HR role (super admin / hr) from DB.
    hr_headers = _hr_headers_from_super_admin(conn, jwt_secret, jwt_algorithm=jwt_algorithm)
    cur.close()
    conn.close()

    print("\n[1] Creating job...")
    job_payload = {
        "title": "Senior Python Backend Engineer",
        "description": (
            "We are looking for a Senior Python Backend Engineer to join our core platform team. "
            "You will design and build scalable microservices, own API development, "
            "and collaborate with cross-functional teams on high-impact products."
        ),
        "experience_level": "senior",
        "location": "Remote",
        "mode_of_work": "Remote",
        "job_type": "Full-Time",
        "domain": "Engineering",
        "primary_evaluated_skills": [
            "Python",
            "REST API Design",
            "PostgreSQL",
            "Docker",
            "Kubernetes",
            "AWS",
            "Testing",
        ],
        "aptitude_enabled": False,
        "first_level_enabled": True,
        "interview_mode": "ai",
        "behavioral_role": "general",
        "duration_minutes": 60,
    }

    job_res = _api_post(session, f"{BASE_URL}/api/jobs", json_body=job_payload, headers=hr_headers)
    print(f"  Status: {job_res.status_code}")
    if job_res.status_code not in (200, 201):
        raise RuntimeError(f"Job creation failed: {job_res.status_code} {job_res.text}")
    job_data = job_res.json()
    job_db_id = job_data.get("id") or job_data.get("job_id") or job_data.get("data", {}).get("id")
    if not job_db_id:
        raise RuntimeError(f"Could not resolve created job id from response: {job_data}")
    print(f"  Created Job ID (DB): {job_db_id}")

    # --- Step 2: Submit application via API (multipart) ---
    print("\n[2] Submitting application...")
    candidate_email = f"autotest_{int(time.time())}@testcandidate.com"
    candidate_name = "Alex Rivera"
    # Endpoint requires digits-only, length 10-15. Make it dynamic.
    candidate_phone = f"1555{int(time.time()) % 10000000:07d}"

    resume_text = (
        "Alex Rivera - Senior Software Engineer\n"
        "6 years building Python/Django REST APIs and React frontends.\n"
        "Led migration of monolith to microservices at a FinTech startup (2M daily txns).\n"
        "Strong in AWS (ECS, Lambda, RDS), Docker, Kubernetes, and CI/CD pipelines.\n"
        "Open source contributor. B.Sc. Computer Science, UT Austin.\n"
        f"Unique Run Reference ID: {time.time()}\n"
    )

    # Minimal PNG header + padding is sufficient for the backend (it only saves bytes).
    photo_bytes = b"\x89PNG\r\n\x1a\n" + (b"\x00" * 256)

    # Generate a real .docx file containing the resume text using python-docx
    import docx
    doc = docx.Document()
    for line in resume_text.split("\n"):
        doc.add_paragraph(line)
    resume_stream = BytesIO()
    doc.save(resume_stream)
    resume_bytes = resume_stream.getvalue()

    apply_url = f"{BASE_URL}/api/applications/apply"
    apply_data = {
        "job_id": str(job_db_id),
        "candidate_name": candidate_name,
        "candidate_email": candidate_email,
        "candidate_phone": candidate_phone,
    }
    apply_files = {
        "resume_file": ("resume.docx", resume_bytes, "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
        "photo_file": ("photo.png", photo_bytes, "image/png"),
    }

    apply_res = session.post(apply_url, data=apply_data, files=apply_files, timeout=180)
    print(f"  Status: {apply_res.status_code}")
    if apply_res.status_code not in (200, 201):
        raise RuntimeError(f"Application submission failed: {apply_res.status_code} {apply_res.text}")

    app_data = apply_res.json()
    app_id = app_data.get("id") or app_data.get("application_id") or app_data.get("data", {}).get("id")
    if not app_id:
        raise RuntimeError(f"Could not resolve application id from response: {app_data}")
    print(f"  Application ID: {app_id} | Candidate: {candidate_email}")

    # --- Step 2.5: Wait for resume screening background task ---
    print("\n[2.5] Waiting for resume screening background task...")
    for attempt in range(60):
        conn = _get_conn(db_params)
        cur = conn.cursor()
        cur.execute(
            "SELECT resume_status, failure_reason FROM applications WHERE id = %s",
            (app_id,)
        )
        row = cur.fetchone()
        cur.close()
        conn.close()
        if row:
            res_status, fail_reason = row
            if res_status in ("parsed", "failed"):
                print(f"  [OK] Resume screening complete: resume_status={res_status}, failure_reason={fail_reason}")
                if res_status == "failed":
                    raise RuntimeError(f"Resume parsing failed: {fail_reason}")
                break
        print(f"  Waiting... attempt {attempt+1}/60")
        time.sleep(5)

    # --- Step 3: Trigger interview creation via HR API ---
    print("\n[3] Triggering interview creation...")
    trigger_res = _api_put(
        session,
        f"{BASE_URL}/api/applications/{app_id}/status",
        json_body={"action": "approve_for_interview", "hr_notes": "Automated E2E approval."},
        headers=hr_headers,
    )
    print(f"  Status: {trigger_res.status_code}")
    if trigger_res.status_code not in (200, 201):
        raise RuntimeError(f"Interview trigger failed: {trigger_res.status_code} {trigger_res.text}")

    # --- Step 4/5: Poll DB until interview exists + access key populated ---
    print("\n[4] Polling DB for interview access key & interview readiness...")

    interview_id = None
    last_status = None
    for attempt in range(60):  # up to ~5 minutes
        conn = _get_conn(db_params)
        cur = conn.cursor()
        cur.execute(
            f"""
            SELECT i.id, i.{access_key_col}, i.status, i.interview_stage
            FROM interviews i
            JOIN applications a ON i.application_id = a.id
            WHERE a.candidate_email = %s
            ORDER BY i.id DESC
            LIMIT 1
            """,
            (candidate_email,),
        )
        row = cur.fetchone()

        interview_count = 0
        # Also compute question count; it becomes >0 only after we access the interview.
        cur.execute(
            """
            SELECT COUNT(*) FROM interview_questions
            WHERE interview_id = %s
            """,
            (row[0] if row else None,),
        )
        q_count_row = cur.fetchone()
        q_count = q_count_row[0] if q_count_row else 0

        cur.close()
        conn.close()

        if row and row[0] and row[1] is not None:
            interview_id = row[0]
            last_status = row[2]
            print(f"  [OK] Interview row found: interview_id={interview_id}, status={last_status}, current_questions={q_count}")
            break

        print(f"  Waiting... attempt {attempt+1}/60 (interview row not ready yet)")
        time.sleep(5)

    if not interview_id:
        raise RuntimeError("Timed out waiting for interview access key to be populated.")

    # Generate a raw access key via the new TEST-ONLY endpoint.
    print("\n[5] Generating raw interview access key (test-only endpoint)...")
    token_res = _api_post(
        session,
        f"{BASE_URL}/api/interviews/{interview_id}/generate-test-token",
        json_body={},
        headers=hr_headers,
        timeout=60,
    )
    print(f"  Status: {token_res.status_code}")
    if token_res.status_code != 200:
        raise RuntimeError(f"Test token generation failed: {token_res.status_code} {token_res.text}")
    raw_access_key = token_res.json().get("access_key")
    if not raw_access_key:
        raise RuntimeError(f"Test token generation response missing access_key: {token_res.text}")

    # --- Step 6: Access interview using candidate email + access key ---
    print("\n[6] Accessing interview...")
    access_res = _api_post(
        session,
        f"{BASE_URL}/api/interviews/access",
        json_body={"email": candidate_email, "access_key": raw_access_key},
        headers=None,
        timeout=60,
    )
    print(f"  Status: {access_res.status_code}")
    if access_res.status_code != 200:
        raise RuntimeError(f"Access failed: {access_res.status_code} {access_res.text}")

    access_data = access_res.json()
    token = access_data.get("access_token")
    interview_id_from_access = access_data.get("interview_id")
    if not token:
        raise RuntimeError(f"Access response missing access_token: {access_data}")
    if interview_id_from_access and int(interview_id_from_access) != int(interview_id):
        print(f"  [WARN] interview_id mismatch: db={interview_id} api={interview_id_from_access}")
        interview_id = int(interview_id_from_access)

    interview_headers = {"Authorization": f"Bearer {token}"}
    print(f"  [OK] Interview accessed: interview_id={interview_id}")

    # --- Step 7: Poll until AI-generated questions exist; fetch all questions ---
    print("\n[7] Fetching all interview questions (poll until available)...")
    questions = None
    for attempt in range(90):  # up to ~7.5 minutes
        questions_res = _api_get(
            session,
            f"{BASE_URL}/api/interviews/{interview_id}/questions",
            headers=interview_headers,
            timeout=90,
        )
        if questions_res.status_code == 200:
            data = questions_res.json()
            # endpoint returns list[]
            if isinstance(data, list) and len(data) > 0:
                questions = data
                break
        elif questions_res.status_code == 202:
            pass
        else:
            print(f"  [WARN] Questions fetch status={questions_res.status_code} body={questions_res.text[:200]}")

        print(f"  Waiting... attempt {attempt+1}/90")
        time.sleep(5)

    if not questions:
        raise RuntimeError("Questions never became available (timed out).")

    print(f"  [OK] Got {len(questions)} questions.")

    # --- Step 8: Answer all questions with realistic responses ---
    print("\n[8] Answering all questions...")

    technical_template = (
        "In my experience, I approach backend design by starting with clear requirements and "
        "then selecting a pragmatic architecture. I build REST APIs with strong input validation, "
        "idempotency where it matters, and well-defined error handling. For persistence, I use "
        "PostgreSQL effectively (indexes, query plans, migrations, and safe transaction boundaries). "
        "I containerize services with Docker, deploy with Kubernetes, and use AWS primitives (ECS/EKS, "
        "RDS, Lambda where appropriate) while maintaining reliability through observability (structured logs, "
        "metrics, and alerting)."
    )

    behavioral_template = (
        "I use a structured approach to behavioral questions: I identify the context, define the goal, "
        "explain the actions I took, and share measurable outcomes. I collaborate proactively, keep stakeholders "
        "aligned with concise updates, and escalate risks early. When conflict arises, I focus on shared objectives, "
        "listen carefully, and negotiate trade-offs with evidence and clear next steps."
    )

    aptitude_template = (
        "The correct answer is 0. Explanation: Based on the provided option set, selecting the first option."
    )

    def build_answer(q):
        q_type = (q.get("question_type") or "").lower()
        q_text = (q.get("question_text") or "").lower()

        # Keep it realistic but generic; the AI evaluation will grade qualitatively anyway.
        if "behavior" in q_type:
            return behavioral_template
        if q_type == "technical" or "technical" in q_text:
            return technical_template
        if q_type == "aptitude":
            return aptitude_template

        # Default
        if any(k in q_text for k in ["explain", "design", "api", "database", "distributed"]):
            return technical_template
        return behavioral_template

    answered = 0
    submit_delay_seconds = float(os.getenv("SUBMIT_DELAY_SECONDS", "7"))
    for i, q in enumerate(questions, start=1):
        q_text = q.get("question_text") or ""
        q_id = q.get("id")
        q_type = q.get("question_type")

        print(f"  Q{i}/{len(questions)} (type={q_type}): {q_text[:60]}...")
        answer_text = build_answer(q)

        # Send a mock monitoring event to keep proctoring alive
        try:
            session.post(
                f"{BASE_URL}/api/interviews/{interview_id}/monitoring-events",
                json={"event_type": "normal", "confidence_score": 1.0},
                headers=interview_headers,
                timeout=10,
            )
        except Exception as me_err:
            print(f"    [WARN] Failed to send mock monitoring event: {me_err}")

        submit_res = session.post(
            f"{BASE_URL}/api/interviews/{interview_id}/submit-answer",
            json={"question_id": q_id, "answer_text": answer_text},
            headers=interview_headers,
            timeout=120,
        )
        if submit_res.status_code == 429:
            # Rate limited; wait and retry once.
            retry_after = submit_res.headers.get("Retry-After")
            wait_s = int(retry_after) if retry_after and retry_after.isdigit() else 30
            print(f"    [WARN] Rate limited (429). Waiting {wait_s}s and retrying question_id={q_id}...")
            time.sleep(wait_s)
            submit_res = session.post(
                f"{BASE_URL}/api/interviews/{interview_id}/submit-answer",
                json={"question_id": q_id, "answer_text": answer_text},
                headers=interview_headers,
                timeout=120,
            )

        if submit_res.status_code != 200:
            raise RuntimeError(f"Answer submit failed for question_id={q_id}: {submit_res.status_code} {submit_res.text}")
        answered += 1

        time.sleep(submit_delay_seconds)

    print(f"  [OK] Submitted answers for {answered} questions.")

    # --- Wait for async evaluations to populate answer_score/evaluated_at ---
    # This is not strictly required for completion, but it makes the final score accurate.
    print("\n[9] Waiting for AI evaluations to finish (polling DB)...")
    start = time.time()
    total_questions = len(questions)
    while time.time() - start < 300:  # 5 minutes
        conn = _get_conn(db_params)
        cur = conn.cursor()
        cur.execute(
            """
            SELECT COUNT(*)
            FROM interview_answers
            WHERE interview_id = %s
              AND evaluated_at IS NOT NULL
            """,
            (interview_id,),
        )
        evaluated = cur.fetchone()[0]
        cur.close()
        conn.close()

        if evaluated >= total_questions:
            print(f"  [OK] Evaluations completed: evaluated={evaluated}/{total_questions}")
            break
        print(f"  Evaluations pending: evaluated={evaluated}/{total_questions}")
        time.sleep(5)

    # --- Complete interview and print final report ---
    print("\n[10] Completing interview...")
    end_res = session.post(
        f"{BASE_URL}/api/interviews/{interview_id}/end",
        headers=interview_headers,
        timeout=180,
    )
    print(f"  Status: {end_res.status_code}")
    if end_res.status_code not in (200, 201):
        raise RuntimeError(f"Interview end failed: {end_res.status_code} {end_res.text}")
    end_data = end_res.json()
    print(f"  Interview completion response: {end_data}")

    # Candidate-visible stage
    stage_res = _api_get(
        session,
        f"{BASE_URL}/api/interviews/{interview_id}/stage",
        headers=interview_headers,
        timeout=60,
    )
    if stage_res.status_code == 200:
        print(f"\nStage summary:\n{json.dumps(stage_res.json(), indent=2, default=str)}")
    else:
        print(f"\n[WARN] stage fetch failed: {stage_res.status_code} {stage_res.text}")

    # HR-only report
    print("\n[11] Fetching final HR report (polling until available)...")
    report = None
    report_res = None
    for attempt in range(12):
        report_res = _api_get(
            session,
            f"{BASE_URL}/api/interviews/{interview_id}/report",
            headers=hr_headers,
            timeout=120,
        )
        print(f"  Attempt {attempt+1}: Status={report_res.status_code}")
        if report_res.status_code == 200:
            report = report_res.json()
            break
        elif report_res.status_code == 404:
            print("    Report not yet ready, waiting...")
        else:
            print(f"    Unexpected response: {report_res.text}")
        time.sleep(5)

    if not report:
        raise RuntimeError(f"Report fetch failed: {report_res.status_code} {report_res.text if report_res else 'No response'}")

    report = report_res.json()
    # Avoid printing encrypted blobs; report is expected to be decrypted by the backend types.
    print("\nFINAL REPORT")
    print("=" * 80)
    print(json.dumps(report, indent=2, default=str))
    print("=" * 80)
    print("END-TO-END TEST COMPLETE!")


if __name__ == "__main__":
    main()

