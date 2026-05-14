from app.infrastructure.database import SessionLocal
from sqlalchemy import text

db = SessionLocal()
try:
    result = db.execute(text("SELECT column_name FROM information_schema.columns WHERE table_name = 'applications'"))
    columns = [row[0] for row in result]
    print("Columns in 'applications' table:")
    for col in columns:
        print(f" - {col}")
finally:
    db.close()
