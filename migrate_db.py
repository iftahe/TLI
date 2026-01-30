from src.database.core import engine
from sqlalchemy import text
import logging

logger = logging.getLogger(__name__)

MIGRATIONS = [
    ("tasks", "recurrence", "ALTER TABLE tasks ADD COLUMN recurrence VARCHAR"),
    ("sub_categories", "chat_id", "ALTER TABLE sub_categories ADD COLUMN chat_id BIGINT"),
]

def migrate():
    with engine.connect() as conn:
        for table, column, sql in MIGRATIONS:
            try:
                conn.execute(text(sql))
                conn.commit()
                logger.info(f"Added '{column}' column to '{table}'.")
            except Exception as e:
                logger.info(f"Column '{column}' on '{table}' already exists or migration skipped: {e}")

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    migrate()
