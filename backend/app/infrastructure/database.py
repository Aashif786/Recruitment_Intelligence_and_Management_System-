from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from app.core.config import get_settings

settings = get_settings()

# Create database engine
engine = create_engine(
    settings.database_url,
    pool_pre_ping=True,
    pool_size=10,         # Scalable pool size
    max_overflow=20,
    pool_recycle=300,    # Recycle connections every 5 minutes (ideal for Supabase/PG poolers)
    echo=settings.debug
)


# Create session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Base class for models
Base = declarative_base()

def get_db():
    """Dependency for FastAPI to get database session"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def set_db_identity(db: Session, user_id: int):
    """
    Set PostgreSQL session variable for Row Level Security (RLS).
    Policies in Phase 2 rely on 'app.current_user_id'. (Phase 2 Fix)
    """
    from sqlalchemy import text
    try:
        # RLS is only supported/needed on PostgreSQL (Phase 2 Fix)
        if "postgresql" in str(db.get_bind().url).lower():
            db.execute(text("SET LOCAL app.current_user_id = :uid"), {"uid": str(user_id)})
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(f"Failed to set RLS identity: {e}")
