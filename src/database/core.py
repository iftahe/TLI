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
if DATABASE_URL.startswith("sqlite"):
    connect_args = {"check_same_thread": False}

engine = create_engine(DATABASE_URL, connect_args=connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Configure JobStore for APScheduler
jobstores = {
    'default': SQLAlchemyJobStore(engine=engine)
}

def init_db():
    Base.metadata.create_all(bind=engine)
    
    # Seed default categories if empty
    session = SessionLocal()
    try:
        count = session.query(SubCategory).count()
        if count == 0:
            defaults = [
                # Home
                SubCategory(name="קניות 🛒", parent="home"),
                SubCategory(name="תחזוקה 🔧", parent="home"),
                SubCategory(name="ניקיון 🧹", parent="home"),
                SubCategory(name="אחר 📂", parent="home"),
                # Work
                SubCategory(name="מיילים 📧", parent="work"),
                SubCategory(name="פגישות 📅", parent="work"),
                SubCategory(name="פרויקטים 📊", parent="work"),
                SubCategory(name="אחר 📂", parent="work"),
            ]
            session.add_all(defaults)
            session.commit()
            print("Seeded default categories.")
    except Exception as e:
        print(f"Error seeding DB: {e}")
    finally:
        session.close()
