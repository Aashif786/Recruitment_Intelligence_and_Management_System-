"""
Startup migration helper - safely adds missing columns to existing tables.
Works with both SQLite and PostgreSQL.
Called from main.py AFTER Base.metadata.create_all().
"""
import logging
from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine

from app.domain.constants import CandidateState

logger = logging.getLogger(__name__)


_REQUIRED_COLUMNS = [
    ("jobs", "aptitude_questions_file", "VARCHAR(500)"),
    ("applications", "resume_file_path", "VARCHAR(500)"),
    ("jobs", "job_id", "VARCHAR(50)"),
    ("interview_questions", "question_options", "TEXT"),
    ("interview_questions", "correct_option", "INTEGER"),
    ("resume_extractions", "summary", "TEXT"),
    ("jobs", "interview_token", "VARCHAR(50)"),
    ("interviews", "test_id", "VARCHAR(50)"),
    # Resume parsing lifecycle tracking (HR gating + retry UI)
    ("applications", "resume_status", "VARCHAR(32) DEFAULT 'pending'"),
    ("applications", "resume_score", "FLOAT"),
    ("applications", "aptitude_score", "FLOAT"),
    ("applications", "interview_score", "FLOAT"),
    ("applications", "composite_score", "FLOAT"),
    ("applications", "recommendation", "VARCHAR(50)"),
    # Resume parsing persistence fields (may be missing on legacy DBs)
    ("applications", "candidate_phone_raw", "TEXT"),
    ("applications", "resume_file_name", "VARCHAR(255)"),
    ("applications", "candidate_photo_path", "TEXT"),
    ("applications", "hr_notes", "TEXT"),
    ("applications", "hr_id", "INTEGER REFERENCES users(id)"),
    ("interview_answers", "ai_used", "BOOLEAN DEFAULT FALSE"),
    ("interview_answers", "fallback_used", "BOOLEAN DEFAULT FALSE"),
    ("interview_answers", "confidence_score", "FLOAT"),
    ("interview_reports", "ai_used", "BOOLEAN DEFAULT FALSE"),
    ("interview_reports", "fallback_used", "BOOLEAN DEFAULT FALSE"),
    ("interview_reports", "confidence_score", "FLOAT"),
    # Onboarding
    ("applications", "offer_sent", "BOOLEAN DEFAULT FALSE"),
    ("applications", "offer_sent_date", "TIMESTAMP"),
    ("applications", "joining_date", "TIMESTAMP"),
    ("applications", "notification_sent", "BOOLEAN DEFAULT FALSE"),
    ("applications", "onboarding_approval_status", "VARCHAR(20) DEFAULT 'pending'"),
    # Enhanced Onboarding V2
    ("applications", "offer_approval_status", "VARCHAR(20) DEFAULT 'pending'"),
    ("applications", "offer_approved_by", "INTEGER REFERENCES users(id)"),
    ("applications", "offer_approved_at", "TIMESTAMP"),
    ("applications", "offer_response_status", "VARCHAR(20) DEFAULT 'pending'"),
    ("applications", "offer_response_date", "TIMESTAMP"),
    ("applications", "offer_token", "VARCHAR(100)"),
    ("applications", "offer_short_id", "VARCHAR(20)"),
    ("applications", "offer_token_expiry", "TIMESTAMP WITH TIME ZONE"),
    ("applications", "offer_token_used", "BOOLEAN DEFAULT FALSE"),
    ("applications", "offer_template_snapshot", "TEXT"),
    ("applications", "offer_pdf_path", "VARCHAR(500)"),
    ("applications", "offer_accepted_ip", "VARCHAR(50)"),
    ("applications", "offer_accepted_user_agent", "TEXT"),
    ("applications", "offer_email_status", "VARCHAR(20) DEFAULT 'pending'"),
    ("applications", "offer_email_retry_count", "INTEGER DEFAULT 0"),
    ("applications", "reminder_sent_at", "TIMESTAMP"),
    ("applications", "email_sent_at", "TIMESTAMP"),
    ("applications", "email_status", "VARCHAR(20) DEFAULT 'pending'"),
    # Missing ResumeExtraction columns
    ("resume_extractions", "candidate_name", "VARCHAR(255)"),
    ("resume_extractions", "email", "VARCHAR(255)"),
    ("resume_extractions", "phone_number", "VARCHAR(50)"),
    ("resume_extractions", "reasoning", "TEXT"), # Cast to JSONB happens in models/postgres if column exists
    # Missing Interview columns
    ("interviews", "current_difficulty", "VARCHAR(20) DEFAULT 'medium'"),
    ("interviews", "questions_asked", "INTEGER DEFAULT 0"),
    ("interviews", "total_questions", "INTEGER DEFAULT 20"),
    ("interviews", "locked_skill", "VARCHAR(50)"),
    ("interviews", "started_at", "TIMESTAMP"),
    ("interviews", "completed_at", "TIMESTAMP"),
    ("interviews", "termination_reason", "VARCHAR(100)"),
    ("interviews", "report_generated", "BOOLEAN DEFAULT FALSE"),
    ("interviews", "candidate_id", "INTEGER REFERENCES users(id)"),
    # Repository question set FK columns on jobs — plain INTEGER first, FK added after table exists
    ("jobs", "aptitude_repo_set_id", "INTEGER"),
    ("jobs", "technical_repo_set_id", "INTEGER"),
    ("jobs", "behavioural_repo_set_id", "INTEGER"),
]


def _safe_rollback(conn) -> None:
    """Clear aborted transactions so later migrations can continue."""
    try:
        conn.rollback()
    except Exception:
        pass


def column_exists(conn, table_name: str, column_name: str) -> bool:
    """Check if a column exists in a table (PostgreSQL/SQLite compatible)."""
    # Use inspector for broad compatibility
    from sqlalchemy import inspect
    inspector = inspect(conn)
    if table_name not in inspector.get_table_names():
        return False
    columns = [c["name"] for c in inspector.get_columns(table_name)]
    return column_name in columns


def update_role_constraint(conn):
    """Safely update the role constraint to include 'pending_hr' and 'super_admin'."""
    try:
        # Check if we are on PostgreSQL
        if "postgresql" in str(conn.engine.url):
            conn.execute(text("ALTER TABLE users DROP CONSTRAINT IF EXISTS check_users_role"))
            conn.execute(text("""
                ALTER TABLE users ADD CONSTRAINT check_users_role 
                CHECK (role IN ('super_admin', 'hr', 'recruiter', 'pending_hr', 'candidate'))
            """))
            logger.info("Migration completed: updated check_users_role constraint")
        else:
            logger.info("Skipping constraint update: not on PostgreSQL")
    except Exception as exc:
        logger.warning(f"Migration failed to update role constraint: {exc}")


def run_startup_migrations(engine: Engine):
    """Check for missing columns and add them safely using PostgreSQL-friendly DDL."""
    inspector = inspect(engine)

    # 0. Create question_sets table FIRST — must exist before FK columns on jobs are added
    with engine.connect() as conn:
        try:
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS question_sets (
                    id SERIAL PRIMARY KEY,
                    title VARCHAR(255) NOT NULL,
                    round_type VARCHAR(50) NOT NULL,
                    job_roles TEXT,
                    questions TEXT NOT NULL DEFAULT '[]',
                    topic_tags TEXT,
                    hr_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                )
            """))
            conn.commit()
            logger.info("Ensured question_sets table exists")
        except Exception as e:
            _safe_rollback(conn)
            logger.warning(f"Failed to create question_sets table: {e}")

    # Refresh inspector after table creation
    inspector = inspect(engine)

    # 1. Ensure columns exist first
    with engine.connect() as conn:
        for table, column, col_type in _REQUIRED_COLUMNS:
            if table not in inspector.get_table_names():
                logger.info(f"Skipping column {column} — table {table} does not exist yet.")
                continue
            
            try:
                # Check existence to provide better logging
                if not column_exists(conn, table, column):
                    logger.info(f"Applying migration: Adding column {table}.{column} ({col_type})...")
                    # PostgreSQL supports 'IF NOT EXISTS' for columns, but SQLite does not.
                    if "postgresql" in str(conn.engine.url):
                        conn.execute(text(f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {column} {col_type}"))
                    else:
                        conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {col_type}"))
                    conn.commit()
                    logger.info(f"Migration SUCCESS: Column {table}.{column} added.")
                else:
                    logger.debug(f"Column {table}.{column} already exists.")
            except Exception as e:
                _safe_rollback(conn)
                logger.error(f"Migration FAILED for {table}.{column}: {e}")
                # For critical updates, we might want to raise, but for baseline, we log and continue
                # unless it's a manual migration script.

        # Ensure approval_status exists on users (crucial for HR flow)
        try:
            if not column_exists(conn, "users", "approval_status"):
                if "postgresql" in str(engine.url):
                    conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS approval_status VARCHAR(20) DEFAULT 'pending'"))
                else:
                    conn.execute(text("ALTER TABLE users ADD COLUMN approval_status VARCHAR(20) DEFAULT 'pending'"))
                conn.commit()
                logger.info("Ensured users.approval_status exists")
        except Exception as e:
            _safe_rollback(conn)
            logger.warning(f"Failed to add users.approval_status: {e}")

        # Backfill resume_status from existing resume_extractions (metadata sync)
        try:
            if (
                column_exists(conn, "applications", "resume_status")
                and "resume_extractions" in inspector.get_table_names()
            ):
                conn.execute(text("""
                    UPDATE applications
                    SET resume_status = 'parsed'
                    WHERE (resume_status = 'pending' OR resume_status IS NULL)
                      AND EXISTS (
                        SELECT 1
                        FROM resume_extractions re
                        WHERE re.application_id = applications.id
                      )
                """))
                conn.commit()
                logger.info("Backfilled applications.resume_status from resume_extractions")
        except Exception as e:
            _safe_rollback(conn)
            logger.warning(f"Failed to backfill applications.resume_status: {e}")

        # 1c. Ensure status constraint is updated for 'offer_sent' and 'onboarded'
        try:
            if "postgresql" in str(engine.url):
                conn.execute(text("ALTER TABLE applications DROP CONSTRAINT IF EXISTS check_applications_status"))
                conn.execute(text("""
                    ALTER TABLE applications ADD CONSTRAINT check_applications_status 
                    CHECK (status IN ('applied', 'screened', 'aptitude_round', 'ai_interview', 'interview_scheduled', 'interview_completed', 'hired', 'pending_approval', 'offer_sent', 'accepted', 'rejected', 'onboarded', 'physical_interview', 'review_later', 'permanent_failure'))
                """))
                conn.commit()
                logger.info("Updated check_applications_status constraint")
        except Exception as e:
            _safe_rollback(conn)
            logger.warning(f"Failed to update application status constraint: {e}")

        # 1d. Create global_settings table if not exists
        try:
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS global_settings (
                    id SERIAL PRIMARY KEY,
                    key VARCHAR(100) UNIQUE NOT NULL,
                    value TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """))
            conn.commit()
            logger.info("Ensured global_settings table exists")
        except Exception as e:
            _safe_rollback(conn)
            logger.warning(f"Failed to create global_settings table: {e}")

        # 1e. (question_sets table is created in step 0 above)

        # 1f. Ensure interview_feedbacks table exists (added after initial DB creation)
        try:
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS interview_feedbacks (
                    id SERIAL PRIMARY KEY,
                    interview_id INTEGER NOT NULL UNIQUE REFERENCES interviews(id) ON DELETE CASCADE,
                    ui_ux_rating INTEGER,
                    feedback_text TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """))
            conn.commit()
            logger.info("Ensured interview_feedbacks table exists")
        except Exception as e:
            _safe_rollback(conn)
            logger.warning(f"Failed to create interview_feedbacks table: {e}")

    # 2. Update Role Constraints
    with engine.connect() as conn:
        try:
            conn.execute(text("ALTER TABLE users DROP CONSTRAINT IF EXISTS check_users_role"))
            conn.execute(text("""
                ALTER TABLE users ADD CONSTRAINT check_users_role 
                CHECK (role IN ('super_admin', 'hr', 'recruiter', 'pending_hr', 'candidate'))
            """))
            conn.commit()
            logger.info("Updated check_users_role constraint")
        except Exception as exc:
            _safe_rollback(conn)
            logger.warning(f"Error updating role constraint: {exc}")

    # 3. Data normalization and Super Admin promotion
    with engine.connect() as conn:
        if column_exists(conn, "users", "approval_status"):
            try:
                # Normalize legacy roles
                conn.execute(text("""
                    UPDATE users
                    SET role = CASE
                        WHEN role IN ('admin', 'hr_manager', 'recruiter') AND approval_status = 'approved' THEN 'hr'
                        WHEN role IN ('admin', 'hr_manager', 'recruiter', 'hr') AND approval_status != 'approved' THEN 'pending_hr'
                        ELSE role
                    END
                    WHERE role NOT IN ('super_admin', 'candidate')
                """))
                
                # Promote specific user to super_admin
                from app.core.config import get_settings
                settings = get_settings()
                admin_email = (settings.super_admin_email or '').lower().strip()
                if admin_email:
                    conn.execute(text("""
                        UPDATE users 
                        SET role = 'super_admin', approval_status = 'approved'
                        WHERE email = :email
                    """), {"email": admin_email})
                else:
                    logger.warning("No super_admin_email configured. Skipping database super_admin role promotion.")
                
                # Ensure existing staff are approved
                conn.execute(text("""
                    UPDATE users 
                    SET approval_status = 'approved' 
                    WHERE role IN ('super_admin', 'hr') AND approval_status IS NULL
                """))
                
                conn.commit()
                logger.info("Migration completed: normalized roles and promoted super admin")
            except Exception as exc:
                _safe_rollback(conn)
                logger.warning(f"Migration failed to normalize roles: {exc}")
        
        # Populate Application.hr_id
        try:
            if column_exists(conn, "applications", "hr_id") and column_exists(conn, "jobs", "hr_id"):
                conn.execute(text("""
                    UPDATE applications
                    SET hr_id = (SELECT hr_id FROM jobs WHERE jobs.id = applications.job_id)
                    WHERE hr_id IS NULL
                """))
                conn.commit()
                logger.info("Migration completed: populated Application.hr_id")
        except Exception as exc:
            _safe_rollback(conn)
            logger.warning(f"Migration failed to populate hr_id: {exc}")

    # 4. Constraints/Indexes
    required_constraints = [
        (
            "applications",
            "uq_application_job_email",
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_application_job_email ON applications(job_id, candidate_email)",
        ),
        (
            "interview_answers",
            "uq_answer_per_question",
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_answer_per_question ON interview_answers(question_id)",
        ),
        (
            "interviews",
            "uq_interview_application_id",
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_interview_application_id ON interviews(application_id)",
        ),
    ]

    with engine.connect() as conn:
        for table, constraint_name, create_sql in required_constraints:
            if table not in inspector.get_table_names():
                continue
            try:
                conn.execute(text(create_sql))
                conn.commit()
                logger.info(f"Migration completed: ensured index {constraint_name}")
            except Exception as exc:
                _safe_rollback(conn)
                logger.warning(f"Migration skipped index {constraint_name}: {exc}")


def validate_enum_parity(engine: Engine):
    """
    Verify that the CandidateState enum in code matches the DB constraint.
    """
    from sqlalchemy import inspect, text
    inspector = inspect(engine)
    
    # We only check this on PostgreSQL
    if "postgresql" not in str(engine.url):
        return

    expected_states = {s.value for s in CandidateState}
    
    with engine.connect() as conn:
        try:
            # Query the constraint from PG catalog
            result = conn.execute(text("""
                SELECT conkey, pg_get_constraintdef(oid) 
                FROM pg_constraint 
                WHERE conname = 'check_applications_status'
            """)).fetchone()
            
            if result:
                def_str = result[1]
                # Extract values from "CHECK (status IN ('state1', 'state2'))"
                import re
                found_states = set(re.findall(f"'(.*?)'", def_str))
                
                missing = expected_states - found_states
                if missing:
                    error_msg = f"CRITICAL ENUM MISMATCH: Database constraint 'check_applications_status' is missing states: {missing}"
                    logger.critical(error_msg)
                    raise RuntimeError(error_msg)
            else:
                logger.warning("Constraint 'check_applications_status' not found for verification.")
        except Exception as e:
            if isinstance(e, RuntimeError): raise
            logger.warning(f"Enum parity check skipped/failed: {e}")

def validate_required_columns(engine: Engine):
    """
    Validation-only check that stops app startup if critical columns are missing.
    Does NOT attempt to migrate.
    """
    from sqlalchemy import inspect
    inspector = inspect(engine)
    
    # Critical columns that MUST exist for the app to function safely
    CRITICAL = [
        ("applications", "email_sent_at"),
        ("applications", "email_status"),
        ("applications", "resume_status"),
        ("interviews", "test_id"),
    ]
    
    missing = []
    with engine.connect() as conn:
        for table, col in CRITICAL:
            if not column_exists(conn, table, col):
                missing.append(f"{table}.{col}")
    
    if missing:
        error_msg = f"CRITICAL DATABASE ERROR: The following columns are missing from the database: {', '.join(missing)}. Please run 'python scripts/migrate.py' to fix the schema."
        logger.critical(error_msg)
        raise RuntimeError(error_msg)
    
    # Run enum parity check
    validate_enum_parity(engine)
    
    logger.info("Database schema and Enum validation passed.")
