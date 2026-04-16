import os
from datetime import datetime, timedelta
from typing import List, Optional

from fastapi import FastAPI, Depends, HTTPException, status, BackgroundTasks
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from fastapi.middleware.cors import CORSMiddleware
from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db.session import engine, get_db, SessionLocal
from app.models import models
from app.models.models import Base, User, ShedevrumTask, Setting

# Initialize Database
Base.metadata.create_all(bind=engine)

# Security
SECRET_KEY = os.getenv("SECRET_KEY", "super-secret-key-for-autocms")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 * 7 # 1 week

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="api/auth/login")

app = FastAPI(title="AutoCMS API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Admin Creation on startup
def create_admin():
    db = SessionLocal()
    admin = db.query(User).filter(User.username == "admin").first()
    if not admin:
        hashed_password = pwd_context.hash("admin")
        new_admin = User(username="admin", password_hash=hashed_password, role="Admin")
        db.add(new_admin)
        db.commit()
    db.close()

create_admin()

# Schemas
class Token(BaseModel):
    access_token: str
    token_type: str

class SettingUpdate(BaseModel):
    key: str
    value: str
    description: Optional[str] = None

class TaskSchema(BaseModel):
    id: int
    source_id: Optional[str] = None
    prompt: Optional[str] = None
    model: Optional[str] = None
    author: Optional[str] = None
    likes: Optional[str] = None
    views: Optional[str] = None
    url: Optional[str] = None
    image_url: Optional[str] = None
    date: Optional[str] = None
    prompt_ai: Optional[str] = None
    model_ai: Optional[str] = None
    author_ai: Optional[str] = None
    likes_ai: Optional[str] = None
    views_ai: Optional[str] = None
    url_ai: Optional[str] = None
    image_url_ai: Optional[str] = None
    date_ai: Optional[str] = None
    status: str
    aspect_ratio: Optional[str] = None
    attempt_count: Optional[int] = 0
    error_log: Optional[str] = None
    scraping_period: Optional[str] = None
    api_key_used: Optional[str] = None
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True

class TaskUpdate(BaseModel):
    source_id: Optional[str] = None
    prompt: Optional[str] = None
    model: Optional[str] = None
    author: Optional[str] = None
    likes: Optional[str] = None
    views: Optional[str] = None
    url: Optional[str] = None
    image_url: Optional[str] = None
    date: Optional[str] = None
    prompt_ai: Optional[str] = None
    model_ai: Optional[str] = None
    author_ai: Optional[str] = None
    likes_ai: Optional[str] = None
    views_ai: Optional[str] = None
    url_ai: Optional[str] = None
    image_url_ai: Optional[str] = None
    date_ai: Optional[str] = None
    status: Optional[str] = None
    aspect_ratio: Optional[str] = None
    attempt_count: Optional[int] = None
    error_log: Optional[str] = None
    scraping_period: Optional[str] = None
    api_key_used: Optional[str] = None

    class Config:
        from_attributes = True

# Auth Helper
def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception
    user = db.query(User).filter(User.username == username).first()
    if user is None:
        raise credentials_exception
    return user

# Core Logic Wrapper
def run_pipeline_task():
    print(f"[{datetime.now()}] Starting AutoCMS Pipeline...")
    try:
        from core.pipeline import run_pipeline
        run_pipeline()
    except Exception as e:
        print(f"Error in pipeline: {e}")

# Endpoints
@app.post("/api/auth/login", response_model=Token)
async def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username ==form_data.username).first()
    if not user or not pwd_context.verify(form_data.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = jwt.encode(
        {"sub": user.username}, SECRET_KEY, algorithm=ALGORITHM
    )
    return {"access_token": access_token, "token_type": "bearer"}

@app.post("/api/tasks/start")
async def start_task(background_tasks: BackgroundTasks, current_user: User = Depends(get_current_user)):
    background_tasks.add_task(run_pipeline_task)
    return {"status": "started", "message": "Pipeline execution started in background"}

@app.get("/api/tasks", response_model=List[TaskSchema])
async def get_tasks(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    tasks = db.query(models.ShedevrumTask).order_by(models.ShedevrumTask.created_at.desc()).all()
    return tasks

@app.patch("/api/tasks/{task_id}", response_model=TaskSchema)
async def update_task(task_id: int, task_update: TaskUpdate, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    db_task = db.query(models.ShedevrumTask).filter(models.ShedevrumTask.id == task_id).first()
    if not db_task:
        raise HTTPException(status_code=404, detail="Task not found")
    
    update_data = task_update.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(db_task, key, value)
    
    db.commit()
    db.refresh(db_task)
    return db_task

@app.patch("/api/settings")
async def update_settings(setting: SettingUpdate, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    db_setting = db.query(Setting).filter(Setting.setting_key == setting.key).first()
    if not db_setting:
        db_setting = Setting(setting_key=setting.key, setting_value=setting.value, description=setting.description)
        db.add(db_setting)
    else:
        db_setting.setting_value = setting.value
        if setting.description:
            db_setting.description = setting.description
    db.commit()
    return {"status": "success", "message": f"Setting {setting.key} updated"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
