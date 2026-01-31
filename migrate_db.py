from sqlalchemy import text
import logging

logger = logging.getLogger(__name__)

MIGRATIONS = [
    ("tasks", "recurrence", "ALTER TABLE tasks ADD COLUMN recurrence VARCHAR"),
    ("sub_categories", "chat_id", "ALTER TABLE sub_categories ADD COLUMN chat_id BIGINT"),
    ("tasks", "is_shared", "ALTER TABLE tasks ADD COLUMN is_shared INTEGER DEFAULT 0"),
    ("tasks", "completed_at", "ALTER TABLE tasks ADD COLUMN completed_at DATETIME"),
]

def migrate():
    from src.database.core import SessionLocal
    for table, column, sql in MIGRATIONS:
        session = SessionLocal()
        try:
            session.execute(text(sql))
            session.commit()
            logger.info(f"Added '{column}' column to '{table}'.")
        except Exception as e:
            session.rollback()
            logger.info(f"Column '{column}' on '{table}' already exists or migration skipped: {e}")
        finally:
            session.close()

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    migrate()
