from playwright.sync_api import sync_playwright
import time
import random
import re
import gspread
from datetime import datetime
import os
import sys

# Ensure project root is in path for app imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app.db.session import SessionLocal
from app.models.models import Log, AppConfig, ProcessStatus

def log_to_db(message, level="INFO"):
    db = SessionLocal()
    try:
        new_log = Log(message=message, level=level, module="Scraper")
        db.add(new_log)
        
        # Update process status
        proc = db.query(ProcessStatus).filter(ProcessStatus.task_name == "Scraper").first()
        if not proc:
            proc = ProcessStatus(task_name="Scraper")
            db.add(proc)
        proc.status = "Running" if level == "INFO" else "Error"
        proc.last_log = message
        
        db.commit()
    except Exception as e:
        print(f"Error logging to DB: {e}")
    finally:
        db.close()

# ЛИМИТ СБОРА: сколько новых/обновляемых постов обрабатывать за раз
MAX_POSTS = 5

def is_valid_prompt(prompt, author):
    if not prompt:
        return False
        
    prompt_lower = prompt.strip().lower()
    
    if prompt_lower == author.strip().lower():
        return False
        
    forbidden_phrases = ["pro", "скрыт", "промпт виден только", "только друзьям"]
    if any(phrase in prompt_lower for phrase in forbidden_phrases):
        return False
        
    words = prompt_lower.split()
    non_hashtags = [w for w in words if not w.startswith('#')]
    
    text_without_hashtags = " ".join(non_hashtags)
    cleaned = re.sub(r'[^\w\s]', '', text_without_hashtags).replace('_', '').strip()
    
    if not cleaned: 
        return False
        
    return True

def parse_stat_number(val):
    if not val:
        return "0"
        
    val_lower = val.lower().replace(',', '.')
    multiplier = 1
    
    if 'к' in val_lower or 'k' in val_lower:
        multiplier = 1000
    elif 'м' in val_lower or 'm' in val_lower:
        multiplier = 1000000
        
    digits = re.sub(r'[^\d\.]', '', val_lower)
    if not digits:
        return "0"
        
    try:
        num = float(digits) * multiplier
        return str(int(num))
    except ValueError:
        return "0"

def simulate_human_behavior(page):
    """Имитирует действия реального пользователя на странице поста."""
    print("🤖 Имитирую поведение человека...")
    try:
        # 1. Рандомные движения мыши
        for _ in range(random.randint(3, 7)):
            x = random.randint(100, 1000)
            y = random.randint(100, 700)
            page.mouse.move(x, y)
            time.sleep(random.uniform(0.1, 0.4))
            
        # 2. Плавный скролл туда-обратно
        scroll_amount = random.randint(200, 500)
        page.evaluate(f"window.scrollBy(0, {scroll_amount})")
        time.sleep(random.uniform(0.5, 1.5))
        page.evaluate(f"window.scrollBy(0, {-random.randint(100, 300)})")
        
        # 3. Имитация чтения: выделение текста (если промпт виден)
        prompt_el = page.locator("span.prompt").first
        if prompt_el.is_visible(timeout=1000):
            prompt_el.dblclick(delay=200)
            time.sleep(0.5)
            # Убираем выделение кликом в пустое место
            page.mouse.click(10, 10)
            
        # 4. Рандомная пауза "на подумать"
        time.sleep(random.uniform(1.0, 4.0))
    except Exception as e:
        print(f"⚠️ Ошибка при имитации поведения: {e}")

def run(target_url=None, limit=None):
    import json
    posts_data = []
    
    # Load from AppConfig if not provided
    if target_url is None or limit is None:
        try:
            db = SessionLocal()
            configs = db.query(AppConfig).all()
            conf_dict = {c.key: c.value for c in configs}
            db.close()
            
            if target_url is None: target_url = conf_dict.get("url")
            if limit is None: 
                limit_raw = conf_dict.get("limit")
                if limit_raw: limit = int(limit_raw)
        except Exception as e:
            print(f"Error reading AppConfig in scraper: {e}")

    final_url = target_url or 'https://shedevrum.ai/top/day/'
    final_limit = limit or MAX_POSTS
    
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=False,
            slow_mo=1500,
            args=[
                '--no-sandbox',
                '--disable-setuid-sandbox',
                '--disable-dev-shm-usage',
                '--dns-prefetch-disable',
                '--disable-web-security',
                '--ignore-certificate-errors',
            ]
        )
        context = browser.new_context(
            viewport={'width': 1280, 'height': 800},
            ignore_https_errors=True,
        )
        page = context.new_page()
        
        log_to_db("🚀 Starting Scraper execution...")
        print(f"Переходим на {final_url} ...")
        
        # Retry-логика на случай проблем с DNS/сетью
        for attempt in range(3):
            try:
                page.goto(final_url, timeout=60000)
                break
            except Exception as nav_err:
                print(f"Попытка {attempt+1}/3 не удалась: {nav_err}")
                if attempt < 2:
                    print("Повторяем через 5 секунд...")
                    time.sleep(5)
                else:
                    raise
        
        print("Если появилась капча от Яндекса, пройди её в открывшемся окне.")
        input('Нажми Enter в терминале, когда пройдешь капчу...')
        
        # Предварительное получение ID из таблицы для избежания дублей при сборе параметров
        print("📊 Подключение к Google Sheets для получения существующих ID...")
        gc = gspread.service_account(filename='service_account.json')
        sh = gc.open('Shedevrum_Trends')
        worksheet = sh.sheet1
        all_records = worksheet.get_all_values()
        
        existing_ids = set()
        if all_records:
            existing_ids = {row[0] for row in all_records[1:] if row}
        
        seen_ids = set()
        print("\nНачинаем сбор и скроллинг ленты...")
        
        no_new_posts_count = 0
        
        for i in range(10):
            progress = 10 + (i * 5) # 10-60% during scrolling
            msg = f"Scroll {i+1}/10..."
            log_to_db(msg)
            
            # Manually update progress since log_to_db doesn't handle percentage
            db = SessionLocal()
            proc = db.query(ProcessStatus).filter(ProcessStatus.task_name == "Scraper").first()
            if proc:
                proc.progress_percent = progress
                db.commit()
            db.close()

            print(msg)
            page.mouse.wheel(0, 1000)
            time.sleep(2)
            
            if no_new_posts_count >= 3:
                print("Новые посты не появляются, пробуем найти кнопку 'Ещё'...")
                try:
                    more_btn = page.get_by_text('Ещё', exact=False).last
                    if more_btn.is_visible(timeout=1000):
                        more_btn.click(force=True)
                        time.sleep(2)
                except Exception:
                    pass
                no_new_posts_count = 0
                
            posts_info = page.evaluate(r"""
                () => {
                    let results = [];
                    let postLinks = Array.from(document.querySelectorAll("a[href*='/post/']"));
                    
                    for (let link of postLinks) {
                        try {
                            let url = link.href;
                            if (url.endsWith('/#comments') || url.includes('#')) continue;
                            
                            let idMatch = url.match(/\/post\/([^\/?#]+)/);
                            let id = idMatch ? idMatch[1] : null;
                            if (!id) continue;
                            
                            let container = link.closest('div.bg-gray-100') || link.closest('article') || link.closest('[class*="Card"]');
                            if (!container) {
                                container = link;
                                while (container && container.parentElement && container.offsetHeight < 400) {
                                    container = container.parentElement;
                                }
                            }
                            
                            let textContent = container.innerText || "";
                            
                            let promptSpan = container.querySelector("span.prompt");
                            let exactPrompt = promptSpan ? promptSpan.innerText.trim() : "";
                            
                            let altText = "";
                            let imgSrc = "";
                            let img = container.querySelector("img");
                            if (img) {
                                altText = img.getAttribute("alt") || "";
                                imgSrc = img.getAttribute("src") || "";
                            }
                            
                            // Фильтр ВИДЕО
                            if (imgSrc.includes('clip') || textContent.toLowerCase().includes('clip')) {
                                continue;
                            }
                            
                            let author = "Неизвестно";
                            let authorLinks = container.querySelectorAll("a[href*='/@'], a[href*='/profile/']");
                            for (let aLink of authorLinks) {
                                let t = aLink.innerText.trim();
                                if (t) { author = t; break; }
                            }
                            
                            if (author === "Неизвестно" && container.parentElement) {
                                let neighborLinks = container.parentElement.querySelectorAll("a[href*='/@']");
                                for (let nLink of neighborLinks) {
                                    let t = nLink.innerText.trim();
                                    if (t) { author = t; break; }
                                }
                            }
                            
                            if (author === "Неизвестно" || author === "") {
                                let avatars = container.querySelectorAll("img[src*='avatars']");
                                for (let av of avatars) {
                                    let avAlt = av.getAttribute("alt");
                                    if (avAlt && avAlt !== altText) {
                                        author = avAlt.trim();
                                        break;
                                    }
                                }
                            }
                            
                            let stats = [];
                            let statElements = container.querySelectorAll("button, span");
                            for (let el of statElements) {
                                let t = el.innerText.trim();
                                if (t && /^[\d\.,\s]+[ккмkkm]?$/i.test(t)) {
                                    stats.push(t);
                                }
                            }
                            let model = "";
                            let stretchEl = container.querySelector('span.stretch-tabs');
                            if (stretchEl) {
                                let modelText = stretchEl.innerText.trim();
                                if (modelText) {
                                    model = modelText;
                                }
                            }
                            
                            results.push({
                                id: id,
                                url: url,
                                exact_prompt: exactPrompt,
                                text: textContent,
                                alt: altText,
                                aria: link.getAttribute("aria-label") || "",
                                img_src: imgSrc,
                                author: author,
                                stats: stats,
                                model: model
                            });
                        } catch(e) { }
                    }
                    return results;
                }
            """)
            
            current_date = datetime.now().strftime("%d.%m.%Y %H:%M")
            new_this_round = 0
            
            for info in posts_info:
                post_id = info.get("id")
                if not post_id or post_id in seen_ids:
                    continue
                    
                url = info.get("url", "")
                text_content = info.get("text", "")
                alt_text = info.get("alt", "")
                aria_text = info.get("aria", "")
                author = info.get("author", "Неизвестно")
                img_src = info.get("img_src", "")
                stats = info.get("stats", [])
                
                prompt = info.get("exact_prompt", "").strip()
                            
                if not prompt:
                    if alt_text and len(alt_text) > 10:
                        prompt = alt_text
                    elif aria_text and len(aria_text) > 10:
                        prompt = aria_text
                        
                if prompt and is_valid_prompt(prompt, author):
                    # Проверяем, не набрали ли мы уже лимит final_limit
                    if len(posts_data) >= final_limit:
                        print(f"🛑 Достигнут лимит final_limit ({final_limit}).")
                        break
                        
                    is_new = post_id not in existing_ids and post_id not in seen_ids
                    is_existing = post_id in existing_ids and post_id not in seen_ids
                    
                    if not is_new and not is_existing:
                        continue
                        
                    seen_ids.add(post_id)
                    
                    # Update progress 60-95%
                    current_idx = len(posts_data)
                    scrape_progress = 60 + int((current_idx / final_limit) * 35) if final_limit > 0 else 60
                    
                    msg = f"🔎 Scraping {post_id} ({current_idx+1}/{final_limit})..."
                    
                    # Update status
                    db = SessionLocal()
                    proc = db.query(ProcessStatus).filter(ProcessStatus.task_name == "Scraper").first()
                    if proc:
                        proc.progress_percent = scrape_progress
                        proc.last_log = msg
                        db.commit()
                    db.close()

                    print(msg)
                    try:
                        detail_page = context.new_page()
                        detail_page.goto(url, timeout=30000)
                        detail_page.wait_for_timeout(2000) # Ждем прогрузки
                        
                        # Выполнение "человеческих" действий
                        simulate_human_behavior(detail_page)
                        
                        # Извлечение Aspect Ratio из атрибутов класса изображения
                        print("📐 Ищу Aspect Ratio в CSS-классах...")
                        html_content = detail_page.content()
                        # Ищем паттерн aspect-[9/16] и подобные
                        ratio_match = re.search(r'aspect-\[(\d+/\d+)\]', html_content)
                        if ratio_match:
                            aspect_raw = ratio_match.group(1) # например "9/16"
                            aspect_ratio = aspect_raw.replace('/', ':')
                            print(f"✅ Найдено: {aspect_ratio}")
                        else:
                            # Фолбэк на текстовый поиск если класс не найден
                            page_text = detail_page.locator("body").inner_text()
                            for r in ['1:1', '3:4', '4:3', '16:9', '9:16']:
                                if r in page_text:
                                    aspect_ratio = r
                                    break
                                
                        # Уточняем модель
                        stretch_el = detail_page.locator('span.stretch-tabs').first
                        if stretch_el.is_visible(timeout=2000):
                            m_text = stretch_el.inner_text().strip()
                            if m_text:
                                actual_model = m_text
                                
                        detail_page.close()
                    except Exception as e:
                        print(f"⚠️ Ошибка на странице поста {post_id}: {e}")
                    
                    likes_cleaned = "0"
                    views_cleaned = "0"
                    
                    valid_stats = [parse_stat_number(s) for s in stats if parse_stat_number(s) != "0"]
                    
                    if len(valid_stats) >= 1:
                        likes_cleaned = valid_stats[0]
                    if len(valid_stats) >= 2:
                        views_cleaned = valid_stats[1]
                        
                    posts_data.append({
                        "id": post_id,
                        "prompt": prompt,
                        "model": actual_model,
                        "author": author,
                        "likes": likes_cleaned,
                        "views": views_cleaned,
                        "url": url,
                        "image_url": img_src,
                        "date": current_date,
                        "aspect_ratio": aspect_ratio,
                        "is_new": is_new
                    })
                    new_this_round += 1
                
            if len(posts_data) >= final_limit:
                break
                
            if new_this_round == 0:
                no_new_posts_count += 1
            else:
                no_new_posts_count = 0

        msg = f"\nСобрано {len(posts_data)} постов. Начинаю синхронизацию с Google Sheets..."
        log_to_db(msg)
        print(msg)
        browser.close()

    if not posts_data:
        print("Нет данных для синхронизации.")
        return

    # Синхронизация с Google Sheets
    try:
        # Авторизуемся по сервисному аккаунту
        gc = gspread.service_account(filename='service_account.json')
        # Открываем таблицу
        sh = gc.open('Shedevrum_Trends')
        worksheet = sh.sheet1
        
        # Получаем все текущие записи для проверки дублей по ID
        all_records = worksheet.get_all_values()
        
        id_to_row = {}
        # Заполняем на основе уже существующих данных
        if len(all_records) == 0:
            headers = [
                "ID", "Prompt", "Model", "Author", "Likes", "Views", "URL", "Image_URL", "Date", 
                "Prompt_AI", "Model_AI", "Author_AI", "Likes_AI", "Views_AI", "URL_AI", "Image_URL_AI", "Date_AI", "Status",
                "Aspect_Ratio", "Attempt_Count", "Error_Log"
            ]
            worksheet.append_row(headers)
        else:
            for idx, row in enumerate(all_records):
                if idx == 0:
                    continue 
                if row and len(row) > 0:
                    id_to_row[row[0]] = idx + 1

        new_count = 0
        updated_count = 0
        
        cells_to_update = []
        new_rows = []
        
        for post in posts_data:
            post_id = post["id"]
            if not post["is_new"]:
                # ПОЛУ-ОБНОВЛЕНИЕ существующего поста
                row_idx = id_to_row[post_id]
                existing_row = all_records[row_idx - 1]
                
                # Колонки E/5 и F/6 - Likes и Views
                cells_to_update.append(gspread.Cell(row=row_idx, col=5, value=post["likes"]))
                cells_to_update.append(gspread.Cell(row=row_idx, col=6, value=post["views"]))
                
                # Колонка S/19 - Aspect_Ratio (обновляем только если была пуста или "Не удалось найти")
                current_aspect = existing_row[18] if len(existing_row) >= 19 else ""
                if not current_aspect or current_aspect == "Не удалось найти" or current_aspect == "1:1":
                    cells_to_update.append(gspread.Cell(row=row_idx, col=19, value=post["aspect_ratio"]))
                
                updated_count += 1
            else:
                # Новая строка: 21 колонка
                new_row = [
                    post["id"], 
                    post["prompt"], 
                    post["model"],
                    post["author"], 
                    post["likes"], 
                    post["views"], 
                    post["url"], 
                    post["image_url"], 
                    post["date"],
                    "", "", "", "", "", "", "", "", "🆕 New",
                    post["aspect_ratio"],
                    "0",
                    "None"
                ]
                new_rows.append(new_row)
                new_count += 1
                
        # Пакетное обновление с помощью update_cells (работает быстрее)
        if cells_to_update:
            worksheet.update_cells(cells_to_update)
            
        # Пакетное добавление новых постов
        if new_rows:
            worksheet.append_rows(new_rows)
            
        msg = f"Синхронизация завершена! Добавлено новых: {new_count}, обновлено: {updated_count}"
        log_to_db(msg)
        print(msg)

    except Exception as e:
        print(f"Ошибка при работе с Google Sheets: {e}")

if __name__ == '__main__':
    run()
