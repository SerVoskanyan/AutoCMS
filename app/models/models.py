from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, Text, Boolean
from app.db.session import Base

class User(Base):
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True, nullable=False)
    password_hash = Column(String, nullable=False)
    role = Column(String, default="Manager") # Admin / Manager
    created_at = Column(DateTime, default=datetime.utcnow)

class Setting(Base):
    __tablename__ = "settings"
    
    id = Column(Integer, primary_key=True, index=True)
    setting_key = Column(String, unique=True, index=True, nullable=False)
    setting_value = Column(Text, nullable=True) # Usually JSON stored as Text
    description = Column(String, nullable=True)

class ShedevrumTask(Base):
    __tablename__ = "shedevrum_tasks"

    id = Column(Integer, primary_key=True, index=True)
    
    # Original Scraped Fields
    source_id = Column(String, index=True, nullable=True) 
    prompt = Column(Text, nullable=True)
    model = Column(String, nullable=True)
    author = Column(String, nullable=True)
    likes = Column(String, nullable=True)
    views = Column(String, nullable=True)
    url = Column(String, nullable=True)
    image_url = Column(String, nullable=True)
    date = Column(String, nullable=True)
    
    # AI Generated Fields
    prompt_ai = Column(Text, nullable=True)
    model_ai = Column(String, nullable=True)
    author_ai = Column(String, nullable=True)
    likes_ai = Column(String, nullable=True)
    views_ai = Column(String, nullable=True)
    url_ai = Column(String, nullable=True)
    image_url_ai = Column(String, nullable=True)
    date_ai = Column(String, nullable=True)
    
    # System Status Fields
    status = Column(String, default="pending")
    aspect_ratio = Column(String, nullable=True)
    attempt_count = Column(Integer, default=0)
    error_log = Column(Text, nullable=True)
    
    # Process Context
    scraping_period = Column(String, nullable=True) # Day/Week/All
    api_key_used = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f"<ShedevrumTask(id={self.id}, status='{self.status}')>"
