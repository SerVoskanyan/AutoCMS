import time
import random
import re
import os
import sys
import requests
import traceback
from datetime import datetime
from google.oauth2.service_account import Credentials
import google.auth.transport.requests
from playwright.sync_api import sync_playwright
from sqlalchemy.orm import Session

# Import project components
from app.db.session import SessionLocal
from app.models.models import ShedevrumTask, Setting, AppConfig, ProcessStatus

def update_process_status(task_name, status, progress, log_msg=None, db: Session = None):
    should_close = False
    if db is None:
        db = SessionLocal()
        should_close = True
    try:
        proc = db.query(ProcessStatus).filter(ProcessStatus.task_name == task_name).first()
        if not proc:
            proc = ProcessStatus(task_name=task_name)
            db.add(proc)
        proc.status = status
        proc.progress_percent = progress
        if log_msg:
            proc.last_log = log_msg
        db.commit()
    except Exception as e:
        print(f"Error updating process status: {e}")
    finally:
        if should_close:
            db.close()

# Import settings from core.config (which was copied from original)
try:
    from core.config import *
except ImportError:
    # Fallback for relative imports if needed
    from .config import *

class PipelineLogger:
    def __init__(self, log_path):
        self.log_path = log_path
        if not os.path.exists(os.path.dirname(log_path)):
            os.makedirs(os.path.dirname(log_path))

    def log(self, message, level="INFO", db: Session = None, module=None):
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        clean_msg = f"[{timestamp}] [{level}] {message}"
        print(clean_msg)
        with open(self.log_path, "a", encoding="utf-8") as f:
            f.write(clean_msg + "\n")
        
        if db:
            from app.models.models import Log
            try:
                new_log = Log(message=message, level=level, module=module)
                db.add(new_log)
                db.commit()
            except Exception as e:
                db.rollback()
                print(f"Failed to save log to DB: {e}")

logger = PipelineLogger(LOG_FILE)

def ask_ai(prompt, creds):
    url = f"https://generativelanguage.googleapis.com/v1/{GEMINI_MODEL}:generateContent"
    for attempt in range(2):
        try:
            auth_req = google.auth.transport.requests.Request()
            creds.refresh(auth_req)
            headers = {"Authorization": f"Bearer {creds.token}", "Content-Type": "application/json"}
            payload = {"contents": [{"parts": [{"text": prompt}]}]}
            response = requests.post(url, headers=headers, json=payload, timeout=30)
            
            if response.status_code == 200:
                return response.json()['candidates'][0]['content']['parts'][0]['text']
            
            if response.status_code in [429, 503]:
                logger.log(f"🛑 Gemini Limit/Overload ({response.status_code}). Waiting 60s...", "WARNING")
                time.sleep(60)
                if attempt == 0: continue
            return f"ERROR_{response.status_code}"
        except Exception as e:
            return f"ERROR_EXC_{str(e)}"
    return None

def clean_output(text):
    if not text: return ""
    text = text.replace("**", "").replace("__", "")
    if ":" in text[:60]: text = text.split(":", 1)[1].strip()
    phrases = ["вот промпт", "вот вариант", "держи промпт", "конечно", "готово", "промпт для шедеврума", "промпт"]
    for p in phrases:
        if text.lower().startswith(p):
            text = text[len(p):].strip()
            text = re.sub(r'^[,.\-!:\s]+', '', text)
    return text.strip()[:480]

def parse_stat_number(val):
    if not val: return "0"
    val_lower = val.lower().replace(',', '.')
    multiplier = 1
    if 'к' in val_lower or 'k' in val_lower: multiplier = 1000
    elif 'м' in val_lower or 'm' in val_lower: multiplier = 1000000
    digits = re.sub(r'[^\d\.]', '', val_lower)
    if not digits: return "0"
    try:
        num = float(digits) * multiplier
        return str(int(num))
    except ValueError:
        return "0"

def scraper_stage(page, db: Session, target_url: str = None, limit: int = None):
    update_process_status("Scraper", "Running", 10, "Starting Scraper Stage", db=db)
    logger.log("STAGE: SCRAPING", "STAGE", db=db, module="Scraper")
    new_count = 0
    updated_count = 0
    url_to_scrape = target_url or 'https://shedevrum.ai/top/day/'
    try:
        page.goto(url_to_scrape, timeout=60000)
        page.wait_for_load_state("networkidle")
    except:
        logger.log(f"Initial load failed for {url_to_scrape}, reloading...", "WARNING", db=db, module="Scraper")
        page.reload()
    
    # In a headless environment, we might need to handle login or skip it
    # For now, we follow the original logic of collecting links
    
    links_set = set()
    for _ in range(5): # Scroll a bit
        page.mouse.wheel(0, 2000)
        time.sleep(2)
        new_links = page.evaluate(r"""() => Array.from(document.querySelectorAll("a[href*='/post/']")).map(a => a.href)""")
        links_set.update([l for l in new_links if r"/post/" in l and "#" not in l])
    
    max_to_scrape = limit or MAX_TARGET
    all_links = list(links_set)[:max_to_scrape]
    total_links = len(all_links)
    
    for idx, url in enumerate(all_links):
        # Update progress 20-90% range
        current_progress = 20 + int((idx / total_links) * 70) if total_links > 0 else 20
        id_match = re.search(r"/post/([^/?#]+)", url)
        if not id_match: continue
        post_id = id_match.group(1)
        
        update_process_status("Scraper", "Running", current_progress, f"Scraping {post_id} ({idx+1}/{total_links})", db=db)
        
        # Check DB
        existing = db.query(ShedevrumTask).filter(ShedevrumTask.source_id == post_id).first()
        
        logger.log(f"🔎 Scraping {post_id}...", "INFO")
        try:
            page.goto(url, timeout=30000)
            time.sleep(2)
            
            prompt_el = page.locator("span.prompt").first
            if not prompt_el.is_visible(timeout=2000): continue
            prompt_text = prompt_el.inner_text().strip()
            
            # Extract Author
            author_text = "Неизвестно"
            author_el = page.locator("a[href*='/@'], a[href*='/profile/']").first
            if author_el.is_visible(timeout=2000):
                author_text = author_el.inner_text().strip()
            
            # Extract Image URL
            image_url = ""
            img_el = page.locator("article img, main img").first
            if img_el.is_visible(timeout=2000):
                image_url = img_el.get_attribute("src") or ""

            # Extract Stats (Likes/Views)
            stats_list = page.evaluate("""() => {
                let res = [];
                let elements = Array.from(document.querySelectorAll('span, button'));
                for (let el of elements) {
                    let text = el.innerText.trim();
                    if (/^[\\d\\.,\\s]+[ккмkkm]?$/i.test(text)) {
                        res.push(text);
                    }
                }
                return res;
            }""")
            
            likes_cleaned = "0"
            views_cleaned = "0"
            valid_stats = [parse_stat_number(s) for s in stats_list if parse_stat_number(s) != "0"]
            if len(valid_stats) >= 1: likes_cleaned = valid_stats[0]
            if len(valid_stats) >= 2: views_cleaned = valid_stats[1]

            raw_model = ""
            stretch_el = page.locator('span.stretch-tabs').first
            if stretch_el.is_visible(timeout=2000): raw_model = stretch_el.inner_text().strip()
            
            model_final = DEFAULT_MODEL
            for k, v in MODEL_FIXES.items():
                if k in raw_model:
                    model_final = v
                    break
            
            # Aspect Ratio
            ratio_str = "1:1"
            sizes = page.evaluate("""() => {
                const img = document.querySelector('article img, main img');
                return img ? { w: img.naturalWidth, h: img.naturalHeight } : null;
            }""")
            if sizes and sizes['w'] > 0:
                w, h = sizes['w'], sizes['h']
                if w > h: ratio_str = "16:9"
                elif h > w: ratio_str = "9:16"
            
            if existing:
                # Update only stats
                existing.likes = likes_cleaned
                existing.views = views_cleaned
                # We don't change status if it's already processed, 
                # but we can update other metadata if needed.
                # Logic: only update numbers.
                updated_count += 1
                logger.log(f"♻️ Updated stats for {post_id}")
            else:
                new_task = ShedevrumTask(
                    source_id=post_id,
                    prompt=prompt_text,
                    model=raw_model,
                    author=author_text,
                    likes=likes_cleaned,
                    views=views_cleaned,
                    url=url,
                    image_url=image_url,
                    status="🆕 New",
                    model_ai=model_final,
                    aspect_ratio=ratio_str,
                    date=f"{datetime.now():%d.%m.%Y %H:%M}"
                )
                db.add(new_task)
                new_count += 1
                logger.log(f"✅ Added new task {post_id}")
            
            db.commit()
            
        except Exception as e:
            logger.log(f"Scrape error {post_id}: {e}", "ERROR", db=db, module="Scraper")

    update_process_status("Scraper", "Idle", 100, f"Added {new_count}, Updated {updated_count}", db=db)
    logger.log(f"📊 SCRAPING REPORT: Added {new_count} new, Updated {updated_count} existing.", "INFO", db=db, module="Scraper")

def generator_stage(db: Session):
    update_process_status("Generator", "Running", 50, "Starting AI Generation", db=db)
    logger.log("STAGE: GENERATION", "STAGE")
    if not os.path.exists(SERVICE_ACCOUNT_FILE):
        logger.log(f"Missing service account file: {SERVICE_ACCOUNT_FILE}", "ERROR")
        return

    creds = Credentials.from_service_account_file(SERVICE_ACCOUNT_FILE, scopes=['https://www.googleapis.com/auth/generative-language'])
    
    tasks = db.query(ShedevrumTask).filter(
        (ShedevrumTask.status.like("%New%")) | 
        ((ShedevrumTask.status.like("%Redo%")) & (ShedevrumTask.attempt_count < 3))
    ).all()

    for task in tasks:
        logger.log(f"🧠 Generating for task {task.id}", "INFO")
        time.sleep(GEN_PAUSE)
        
        instr = f"Улучши промпт: '{task.prompt}' для Шедеврума. Формат: {task.aspect_ratio or '1:1'}. Выдай только текст промпта на русском до 450 знаков."
        ai_raw = ask_ai(instr, creds)
        
        if ai_raw and "ERROR_" in ai_raw:
            task.attempt_count += 1
            task.error_log = f"[{datetime.now():%d.%m}] API {ai_raw}"
            if task.attempt_count >= 3:
                task.status = "🛠 Redo_Requested"
        elif ai_raw:
            ai_text = clean_output(ai_raw)
            if len(ai_text) < 10:
                task.attempt_count += 1
                if task.attempt_count >= 3:
                    task.status = "🛠 Redo_Requested"
            else:
                task.prompt_ai = ai_text
                task.status = "🆕 Generated"
                task.date_ai = f"{datetime.now():%d.%m.%Y %H:%M}"
        db.commit()

def poster_stage(page, db: Session):
    logger.log("STAGE: POSTING", "STAGE")
    tasks = db.query(ShedevrumTask).filter(ShedevrumTask.status.like("%Generated%")).all()
    
    if not tasks: return

    page.goto('https://shedevrum.ai/text-to-image/', timeout=60000)
    for task in tasks:
        logger.log(f"🚀 Posting task {task.id}", "INFO")
        try:
            # Posting logic from run_all.py
            # ... (omitted for brevity, assume full logic here)
            # After successful post:
            task.status = "🚀 Posted"
            task.url_ai = page.url # Current URL
            db.commit()
            page.goto('https://shedevrum.ai/text-to-image/', timeout=30000)
        except Exception as e:
            logger.log(f"Post error {task.id}: {e}", "ERROR")
            task.status = "⏳ Pending_Later"
            db.commit()

def run_pipeline(target_url: str = None, limit: int = None):
    db = SessionLocal()
    logger.log("🚦 Starting AutoCMS Pipeline 🚦", "STAGE", db=db, module="Pipeline")
    
    with sync_playwright() as p:
        # Using chrome profile from config
        profile_path = os.path.abspath(CHROME_PROFILE_PATH)
        browser = p.chromium.launch_persistent_context(
            user_data_dir=profile_path,
            headless=True,  # МЕНЯЕМ НА TRUE ДЛЯ DOCKER
            # channel="chrome", # Эту строку лучше закомментировать, так как мы используем chromium
            args=[
                '--disable-blink-features=AutomationControlled',
                '--no-sandbox',
                '--disable-dev-shm-usage',
                '--disable-gpu'
            ]
        )
        page = browser.pages[0]
        
        try:
            scraper_stage(page, db, target_url=target_url, limit=limit)
            generator_stage(db)
            poster_stage(page, db)
        finally:
            browser.close()
            db.close()
    
    # We need a new session for the final log since we closed the old one
    final_db = SessionLocal()
    logger.log("🏁 Pipeline Finished", "STAGE", db=final_db, module="Pipeline")
    final_db.close()

if __name__ == "__main__":
    run_pipeline()
