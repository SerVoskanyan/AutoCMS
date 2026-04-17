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

class PromptTemplate(Base):
    __tablename__ = "prompt_templates"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, nullable=False)
    content = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

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

class Log(Base):
    __tablename__ = "logs"
    
    id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(DateTime, default=datetime.utcnow)
    message = Column(Text, nullable=False)
    level = Column(String, default="INFO") # INFO / ERROR
    module = Column(String, nullable=True) # e.g., "Scraper", "Generator"

class RunHistory(Base):
    __tablename__ = "run_history"
    
    id = Column(Integer, primary_key=True, index=True)
    start_time = Column(DateTime, default=datetime.utcnow)
    module_name = Column(String, nullable=False)
    status = Column(String, default="Running") # Running / Success / Failed
    result_summary = Column(String, nullable=True)

class AppConfig(Base):
    __tablename__ = "app_config"
    key = Column(String, primary_key=True)
    value = Column(Text, nullable=True)

class ProcessStatus(Base):
    __tablename__ = "process_status"
    task_name = Column(String, primary_key=True)
    status = Column(String, default="Idle")
    progress_percent = Column(Integer, default=0)
    last_log = Column(Text, nullable=True)
