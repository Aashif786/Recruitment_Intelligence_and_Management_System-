import os
import sys
import subprocess
import time
from datetime import datetime, timezone

# ANSI colors for nice console logs
GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
CYAN = "\033[96m"
RESET = "\033[0m"
BOLD = "\033[1m"

def log_info(msg):
    print(f"{CYAN}[INFO] {msg}{RESET}")

def log_success(msg):
    print(f"{GREEN}[SUCCESS] {msg}{RESET}")

def log_warning(msg):
    print(f"{YELLOW}[WARNING] {msg}{RESET}")

def log_error(msg):
    print(f"{RED}[ERROR] {msg}{RESET}")

def run_command(name, cmd_args, cwd=None):
    print(f"\n{BOLD}Running: {name}...{RESET}")
    print(f"Command: {' '.join(cmd_args)}")
    
    # Configure PYTHONPATH to include backend root directory
    env = os.environ.copy()
    if cwd:
        env["PYTHONPATH"] = os.path.abspath(cwd)
    else:
        env["PYTHONPATH"] = os.path.dirname(os.path.abspath(__file__))
    
    start_time = time.time()
    result = subprocess.run(
        cmd_args,
        capture_output=True,
        text=True,
        cwd=cwd,
        env=env
    )
    elapsed = time.time() - start_time
    
    success = (result.returncode == 0)
    
    if success:
        log_success(f"{name} completed successfully in {elapsed:.2f}s")
    else:
        log_error(f"{name} failed in {elapsed:.2f}s with exit code {result.returncode}")
        
    return {
        "name": name,
        "success": success,
        "elapsed": elapsed,
        "stdout": result.stdout,
        "stderr": result.stderr,
        "returncode": result.returncode
    }

def main():
    print("=" * 60)
    print(f"{BOLD}{CYAN}RIMS PRODUCTION READINESS VERIFICATION SUITE{RESET}")
    print(f"Start Time: {datetime.now(timezone.utc).isoformat()}")
    print("=" * 60)
    
    backend_dir = os.path.dirname(os.path.abspath(__file__))
    python_path = os.path.join(backend_dir, "venv", "Scripts", "python.exe")
    if not os.path.exists(python_path):
        python_path = "python" # fallback to system python if venv not activated or present
        log_warning(f"Could not find virtualenv python path. Falling back to '{python_path}'")
    else:
        log_info(f"Using virtualenv Python: {python_path}")
        
    results = []
    
    # -------------------------------------------------------------
    # Tier 1: Core Test Suite (Pytest)
    # -------------------------------------------------------------
    pytest_res = run_command(
        "Tier 1: Core Pytest Suite",
        [python_path, "-m", "pytest", "--tb=short"],
        cwd=backend_dir
    )
    results.append(pytest_res)
    
    # -------------------------------------------------------------
    # Tier 2: Standalone Component & Logic Tests
    # -------------------------------------------------------------
    standalone_tests = [
        ("tests/run_adaptive_engine.py", "Adaptive Difficulty Engine"),
        ("tests/run_ai_client_resilience.py", "AI Client Resilience & Resolution"),
        ("tests/run_enterprise_validators.py", "Enterprise Schema & Signature Validators"),
        ("tests/run_idempotency_redis.py", "Idempotency & Ephemeral Replay Cache"),
        ("tests/run_ws_submit_idempotency.py", "WebSocket Submit Idempotency")
    ]
    
    for relative_path, name in standalone_tests:
        full_path = os.path.join(backend_dir, relative_path)
        if os.path.exists(full_path):
            test_res = run_command(
                f"Tier 2: {name}",
                [python_path, relative_path],
                cwd=backend_dir
            )
            results.append(test_res)
        else:
            log_warning(f"Standalone test script not found: {relative_path}")
            
    # -------------------------------------------------------------
    # Tier 3: Production Environment Smoke Tests
    # -------------------------------------------------------------
    smoke_script = os.path.join(backend_dir, "verify_production.py")
    if os.path.exists(smoke_script):
        smoke_res = run_command(
            "Tier 3: Production Smoke Verification",
            [python_path, "verify_production.py"],
            cwd=backend_dir
        )
        results.append(smoke_res)
    else:
        log_warning("verify_production.py not found.")
        
    # -------------------------------------------------------------
    # Summary & Report Generation
    # -------------------------------------------------------------
    print("\n" + "=" * 60)
    print(f"{BOLD}VERIFICATION SUMMARY{RESET}")
    print("=" * 60)
    
    all_passed = True
    total_time = 0.0
    for r in results:
        status_str = f"{GREEN}PASSED{RESET}" if r["success"] else f"{RED}FAILED{RESET}"
        print(f"- {r['name']:<50} : {status_str} ({r['elapsed']:.2f}s)")
        total_time += r["elapsed"]
        if not r["success"]:
            all_passed = False
            
    print("-" * 60)
    final_status = f"{GREEN}{BOLD}ALL SYSTEMS GO!{RESET}" if all_passed else f"{RED}{BOLD}VERIFICATION FAILED!{RESET}"
    print(f"Overall Status : {final_status}")
    print(f"Total Duration : {total_time:.2f}s")
    print("=" * 60)
    
    # Generate markdown verification report
    report_path = os.path.join(backend_dir, "verification_report.md")
    log_info(f"Generating detailed report: {report_path}")
    
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(f"# RIMS Production Readiness Verification Report\n\n")
        f.write(f"Generated at: `{datetime.now(timezone.utc).isoformat()}`\n\n")
        
        if all_passed:
            f.write("> [!NOTE]\n")
            f.write("> **SUCCESS**: All verification tests passed. RIMS backend is production-ready!\n\n")
        else:
            f.write("> [!WARNING]\n")
            f.write("> **FAILURE**: One or more verification suites failed. Review the detailed log outputs below before deploying.\n\n")
            
        f.write("## Execution Summary Table\n\n")
        f.write("| Verification Tier | Status | Duration | Exit Code |\n")
        f.write("| :--- | :---: | :---: | :---: |\n")
        for r in results:
            status_icon = "✅ PASSED" if r["success"] else "❌ FAILED"
            f.write(f"| {r['name']} | {status_icon} | `{r['elapsed']:.2f}s` | `{r['returncode']}` |\n")
        f.write(f"| **Total** | | **`{total_time:.2f}s`** | |\n\n")
        
        f.write("## Detailed Execution Logs\n\n")
        for r in results:
            f.write(f"### {r['name']}\n\n")
            f.write(f"- **Exit Code**: `{r['returncode']}`\n")
            f.write(f"- **Duration**: `{r['elapsed']:.2f}s`\n\n")
            
            if r["stdout"].strip():
                f.write("**Standard Output**:\n```text\n")
                # Clean up any potential sensitive strings if any (general practice)
                stdout_clean = r["stdout"]
                f.write(stdout_clean)
                f.write("\n```\n\n")
                
            if r["stderr"].strip():
                f.write("**Standard Error / Diagnostics**:\n```text\n")
                f.write(r["stderr"])
                f.write("\n```\n\n")
                
            f.write("---\n\n")
            
        # Add next steps / manual tests documentation
        f.write("## E2E Playwright Browser Testing Guide\n\n")
        f.write("To verify the frontend system and live interview integration interactively:\n")
        f.write("1. **Start backend server**:\n")
        f.write("   ```powershell\n")
        f.write("   cd backend\n")
        f.write("   .\\start.ps1 start\n")
        f.write("   ```\n")
        f.write("2. **Start frontend server**:\n")
        f.write("   ```bash\n")
        f.write("   cd frontend\n")
        f.write("   npm run dev\n")
        f.write("   ```\n")
        f.write("3. **Execute Playwright Tests**:\n")
        f.write("   ```bash\n")
        f.write("   cd frontend\n")
        f.write("   npx playwright test\n")
        f.write("   ```\n")
        
    log_success("Report successfully generated!")
    
    if not all_passed:
        sys.exit(1)

if __name__ == "__main__":
    main()
