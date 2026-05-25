import requests
import time
import concurrent.futures
import statistics
import psycopg2
from urllib.parse import urlparse, unquote
from jose import jwt as jose_jwt
import os
from datetime import datetime, timedelta, timezone
from dotenv import load_dotenv

BASE_URL = "http://localhost:10000"

def get_hr_token():
    dotenv_path = os.path.join(os.path.dirname(__file__), "..", ".env")
    load_dotenv(dotenv_path=dotenv_path)

    db_url = os.getenv("DATABASE_URL")
    jwt_secret = os.getenv("JWT_SECRET") or os.getenv("jwt_secret")
    
    if not db_url or not jwt_secret:
        print("Missing DATABASE_URL or JWT_SECRET")
        return None

    parsed = urlparse(db_url)
    try:
        conn = psycopg2.connect(
            dbname=parsed.path[1:],
            user=unquote(parsed.username) if parsed.username else None,
            password=unquote(parsed.password) if parsed.password else None,
            host=parsed.hostname,
            port=parsed.port or 5432,
        )
        cur = conn.cursor()
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
        conn.close()

        if not row:
            print("No valid HR user found in DB")
            return None

        user_id, email, full_name, role = row
        now = datetime.now(timezone.utc)
        exp = now + timedelta(minutes=120)

        payload = {
            "sub": str(user_id),
            "email": email,
            "role": role,
            "full_name": full_name,
            "exp": exp,
        }
        return jose_jwt.encode(payload, jwt_secret, algorithm="HS256")
    except Exception as e:
        print(f"Error generating token: {e}")
        return None

def fetch_endpoint(url, token, thread_id):
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    start_time = time.time()
    try:
        res = requests.get(url, headers=headers, timeout=30)
        end_time = time.time()
        return {"status": res.status_code, "duration": end_time - start_time, "thread": thread_id, "url": url}
    except Exception as e:
        return {"status": "error", "error": str(e), "duration": time.time() - start_time, "thread": thread_id, "url": url}

def run_performance_test(endpoint, token, num_requests=50, max_workers=20):
    print(f"\n--- Starting performance test on {endpoint} ---")
    results = []
    start_total = time.time()
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [executor.submit(fetch_endpoint, f"{BASE_URL}{endpoint}", token, i) for i in range(num_requests)]
        for future in concurrent.futures.as_completed(futures):
            results.append(future.result())
            
    end_total = time.time()
    
    durations = [r["duration"] for r in results if r["status"] == 200]
    errors = [r for r in results if r["status"] != 200]
    
    print(f"Total time for {num_requests} requests: {end_total - start_total:.2f}s")
    print(f"Successful requests: {len(durations)}")
    print(f"Errors: {len(errors)}")
    
    if errors:
        print("Sample error:", errors[0])
        
    if durations:
        print(f"Min time: {min(durations):.3f}s")
        print(f"Max time: {max(durations):.3f}s")
        print(f"Avg time: {statistics.mean(durations):.3f}s")
        print(f"Median time: {statistics.median(durations):.3f}s")

if __name__ == "__main__":
    token = get_hr_token()
    if token:
        run_performance_test("/api/analytics/reports?limit=50", token, num_requests=30, max_workers=15)
        run_performance_test("/api/analytics/dashboard", token, num_requests=30, max_workers=15)
    else:
        print("Failed to get token, aborting test.")
