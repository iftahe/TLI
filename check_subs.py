from src.database.core import SessionLocal
from src.database.models import Task, SubCategory
from sqlalchemy import func

session = SessionLocal()
try:
    # Check what sub_categories exist
    results = session.query(Task.sub_category, func.count(Task.id)).group_by(Task.sub_category).all()
    print("Existing Sub Categories:")
    for sub, count in results:
        print(f"'{sub}': {count}")
        
    print("-" * 20)
    
    # Check if 'sub_maintenance' exists in SubCategory table?
    subs = session.query(SubCategory).all()
    print("Defined Sub Categories:")
    for s in subs:
        print(f"ID: {s.id}, Name: {s.name}, Parent: {s.parent}")
        
finally:
    session.close()
