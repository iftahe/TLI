from sqlalchemy import text
import logging

logger = logging.getLogger(__name__)

# Raw SQL migrations. Use portable types only:
#   - VARCHAR, BIGINT, INTEGER work on both SQLite and PostgreSQL
#   - Use TIMESTAMP (not DATETIME) for date/time columns — PostgreSQL
#     does not recognize DATETIME as a type
MIGRATIONS = [
    ("tasks", "recurrence", "ALTER TABLE tasks ADD COLUMN recurrence VARCHAR"),
    ("sub_categories", "chat_id", "ALTER TABLE sub_categories ADD COLUMN chat_id BIGINT"),
    ("tasks", "is_shared", "ALTER TABLE tasks ADD COLUMN is_shared INTEGER DEFAULT 0"),
    ("tasks", "completed_at", "ALTER TABLE tasks ADD COLUMN completed_at TIMESTAMP"),
]

def migrate():
    from src.database.core import SessionLocal, DATABASE_URL
    is_postgres = not DATABASE_URL.startswith("sqlite")

    for table, column, sql in MIGRATIONS:
        # PostgreSQL supports IF NOT EXISTS (avoids noisy error on existing columns)
        if is_postgres:
            sql = sql.replace("ADD COLUMN ", "ADD COLUMN IF NOT EXISTS ")

        session = SessionLocal()
        try:
            session.execute(text(sql))
            session.commit()
            logger.info(f"Migration OK: '{column}' on '{table}'")
        except Exception as e:
            session.rollback()
            logger.info(f"Migration skipped: '{column}' on '{table}': {e}")
        finally:
            session.close()

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    migrate()
