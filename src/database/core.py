import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from src.database.models import Base, SubCategory

# Get DB URL from env or use sqlite local fallback
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./tasks.db")

# Fix for some cloud providers (like Heroku/Render) that use 'postgres://' instead of 'postgresql://'
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

connect_args = {}
engine_kwargs = {}

if DATABASE_URL.startswith("sqlite"):
    connect_args = {"check_same_thread": False}
else:
    # PostgreSQL (Neon serverless) resilience
    connect_args = {"connect_timeout": 10}
    engine_kwargs = {
        "pool_pre_ping": True,    # test connection before use — auto-reconnects stale ones
        "pool_recycle": 300,      # recycle every 5 min (before Neon idle timeout)
        "pool_size": 5,
        "pool_timeout": 30,
    }

engine = create_engine(DATABASE_URL, connect_args=connect_args, **engine_kwargs)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Configure JobStore for APScheduler
jobstores = {
    'default': SQLAlchemyJobStore(engine=engine)
}

DEFAULT_CATEGORIES = [
    # Home
    ("קניות 🛒", "home"),
    ("תחזוקה 🔧", "home"),
    ("ניקיון 🧹", "home"),
    ("אחר 📂", "home"),
    # Work
    ("מיילים 📧", "work"),
    ("פגישות 📅", "work"),
    ("פרויקטים 📊", "work"),
    ("אחר 📂", "work"),
]

SHARED_HOME_CATEGORIES = [
    ("קניות 🛒", "home"),
    ("תחזוקה 🔧", "home"),
    ("ניקיון 🧹", "home"),
    ("אחר 📂", "home"),
]

def init_db():
    Base.metadata.create_all(bind=engine)
    session = SessionLocal()
    try:
        ensure_shared_categories(session)
    finally:
        session.close()

def ensure_user_categories(session, chat_id: int):
    """Seeds default categories for a user if they have none yet."""
    count = session.query(SubCategory).filter(SubCategory.chat_id == chat_id).count()
    if count == 0:
        defaults = [
            SubCategory(name=name, parent=parent, chat_id=chat_id, is_active=1)
            for name, parent in DEFAULT_CATEGORIES
        ]
        session.add_all(defaults)
        session.commit()

def ensure_shared_categories(session):
    """Seeds shared Home sub-categories (chat_id=0 sentinel) if they don't exist yet."""
    count = session.query(SubCategory).filter(SubCategory.chat_id == 0).count()
    if count == 0:
        defaults = [
            SubCategory(name=name, parent=parent, chat_id=0, is_active=1)
            for name, parent in SHARED_HOME_CATEGORIES
        ]
        session.add_all(defaults)
        session.commit()
