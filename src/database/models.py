from sqlalchemy import Column, Integer, String, DateTime, BigInteger, func
from sqlalchemy.orm import declarative_base

Base = declarative_base()

class Task(Base):
    __tablename__ = "tasks"

    id = Column(Integer, primary_key=True, autoincrement=True)
    chat_id = Column(BigInteger, nullable=False, index=True)
    text = Column(String, nullable=False)
    priority = Column(String, nullable=False)  # 'urgent', 'normal', 'low'
    parent_category = Column(String, nullable=False)  # 'home', 'work'
    sub_category = Column(String, nullable=True)
    reminder_time = Column(DateTime, nullable=True)
    status = Column(String, default='pending')  # 'pending', 'done'
    recurrence = Column(String, nullable=True) # 'daily', 'weekly', 'monthly'
    is_shared = Column(Integer, default=0)  # 1=shared (visible to all users), 0=personal
    created_at = Column(DateTime, default=func.now())
    completed_at = Column(DateTime, nullable=True)

class SubCategory(Base):
    __tablename__ = "sub_categories"

    id = Column(Integer, primary_key=True, autoincrement=True)
    chat_id = Column(BigInteger, nullable=True, index=True)
    name = Column(String, nullable=False)
    parent = Column(String, nullable=False)  # 'home' or 'work'
    is_active = Column(Integer, default=1)  # 1=True, 0=False
