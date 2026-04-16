import gspread
import time
import random
import traceback
import re
from datetime import datetime
from playwright.sync_api import sync_playwright

# Настройки
SERVICE_ACCOUNT_FILE = 'service_account.json'
SHEET_NAME = 'Shedevrum_Trends'
CHROME_PROFILE_PATH = './shedevrum_session'

def handle_ads(page):
    """Улучшенный Анти-рекламный модуль (быстрый)"""
    ad_selectors = [
        '[data-fullscreen-element-name="close-btn"]',
        'button[aria-label*="Закрыть"]',
        'button[aria-label*="Close"]',
        'text="Закрыть"',
        'text="Понятно"',
        'text="✕"',
        '.close-button',
        '.modal-close'
    ]
    
    for sel in ad_selectors:
        try:
            element = page.locator(sel).first
            if element.is_visible(timeout=500):
                print(f"⚠️ Реклама ({sel}) найдена, закрываю...")
                element.click(force=True)
                time.sleep(1)
        except: continue

def run_poster():
    # 1. Авторизация и поиск Очереди
    try:
        print("📊 Подключение к Google Sheets...")
        gc = gspread.service_account(filename=SERVICE_ACCOUNT_FILE)
        sheet = gc.open(SHEET_NAME).sheet1
        
        all_values = sheet.get_all_values()
        headers = [col.strip() for col in all_values[0]]
        col = {name: i for i, name in enumerate(headers)}
        
        target_rows = []
        for i, row in enumerate(all_values):
            if i == 0: continue
            row_padded = row + [''] * (len(headers) - len(row))
            if "Generated" in row_padded[col["Status"]]:
                target_rows.append({
                    "row_idx": i + 1,
                    "prompt": row_padded[col["Prompt_AI"]].strip(),
                    "model": row_padded[col["Model_AI"]].strip(),
                    "aspect_ratio": row_padded[col["Aspect_Ratio"]].strip() if "Aspect_Ratio" in col else "1:1"
                })
        
        if not target_rows:
            print("❌ Очередь пуста.")
            return
        print(f"🎯 Найдено {len(target_rows)} постов.")
        
    except Exception as e:
        print(f"❌ Ошибка Sheets: {e}")
        return

    p = None
    browser = None
    
    try:
        print("\n🌐 Запуск Playwright (slow_mo=1500)...")
        p = sync_playwright().start()
        browser = p.chromium.launch_persistent_context(
            user_data_dir=CHROME_PROFILE_PATH,
            headless=False,
            channel="chrome",
            slow_mo=1500,
            viewport={'width': 1280, 'height': 800},
            args=['--disable-blink-features=AutomationControlled']
        )
        page = browser.pages[0] if browser.pages else browser.new_page()
        
        print("➡️ Открываю shedevrum.ai...")
        page.goto('https://shedevrum.ai/', timeout=60000)
        print("\n🛑 Boss, залогинься и нажми ENTER здесь!")
        input()
        
        # --- ЦИКЛ ОБРАБОТКИ ---
        for entry in target_rows[:10]:
            target_row_idx = entry["row_idx"]
            ai_prompt = entry["prompt"]
            ai_model = entry["model"]
            target_ratio = entry["aspect_ratio"] or "1:1"
            
            print(f"\n🚀--- Пост из строки {target_row_idx} ---")
            
            try:
                page.goto('https://shedevrum.ai/text-to-image/', timeout=60000)
                page.wait_for_load_state("networkidle")
                page.wait_for_timeout(2000)
                
                # Реклама ПЕРЕД настройками
                handle_ads(page)

                # 1. Выбор Модели (ИСПРАВЛЕНО: Mapping + PRO Safety)
                if ai_model:
                    try:
                        # Карта соответствия (Model Mapping)
                        short_version = ai_model
                        if "Alice AI v.1.0" in ai_model: short_version = "v.1.0"
                        elif "v2.5" in ai_model or "v.2.5" in ai_model: short_version = "v.2.5"
                        elif "v2.7" in ai_model or "v.2.7" in ai_model: short_version = "v.2.7"
                        
                        print(f"🔍 Настройка модели: {ai_model} ➔ {short_version}")
                        
                        # Открытие меню: ищем кнопку с текущей версией
                        model_menu_btn = page.locator('div[aria-haspopup="true"] >> div.cursor-pointer').filter(has_text=re.compile(r"v\d\.|✨|v\.\d", re.IGNORECASE)).first
                        if model_menu_btn.is_visible(timeout=5000):
                            model_menu_btn.click(force=True)
                            page.wait_for_timeout(1000)
                            
                            # Поиск в открытом диалоге
                            target_li = page.locator('dialog[open] li').filter(has_text=short_version).first
                            if target_li.is_visible(timeout=3000):
                                # Проверка на доступность (для ПРО моделей ✨)
                                is_disabled = target_li.get_attribute("aria-disabled") == "true" or "disabled" in (target_li.get_attribute("class") or "").lower()
                                
                                if is_disabled:
                                    print(f"⚠️ Модель ПРО ({short_version}) недоступна, оставляю текущую.")
                                    page.mouse.click(10, 10) # Закрыть меню кликом в сторону
                                else:
                                    target_li.click(force=True)
                                    print(f"✅ Модель {short_version} выбрана успешно.")
                            else:
                                print(f"ℹ️ {short_version} не найдена в диалоге. Закрываю.")
                                page.mouse.click(10, 10)
                        else:
                            print("ℹ️ Кнопка переключения моделей не видна.")
                    except Exception as e_m:
                        print(f"ℹ️ Ошибка выбора модели: {e_m}")

                # 2. Выбор Ratio (Силовой клик)
                try:
                    print(f"📐 Выбор формата {target_ratio}...")
                    handle_ads(page)
                    ratio_btn = page.get_by_text(target_ratio, exact=True).first
                    if ratio_btn.is_visible(timeout=3000):
                        ratio_btn.locator("..").click(force=True) # ПРОЛОМ СЛОЕВ
                        print(f"✅ Соотношение {target_ratio} выбрано.")
                except: print("ℹ️ Ошибка выбора Ratio.")

                # 3. Силовой ввод промпта (Fix "Not Editable")
                print("✍️ Силовой ввод промпта...")
                textarea = page.locator('textarea#prompt, [contenteditable="true"]').first
                textarea.click(force=True)
                # Очистка через JS
                page.evaluate("document.querySelector('#prompt') ? document.querySelector('#prompt').value = '' : null")
                page.wait_for_timeout(500)
                # Посимвольный набор (имитация клавиатуры)
                textarea.press_sequentially(ai_prompt, delay=50)
                page.wait_for_timeout(1000)
                
                # 4. Нажатие финальной кнопки 'Создать'
                handle_ads(page)
                create_btn = page.locator('form button, button').filter(has_text=re.compile(r"^Создать$|^generate$", re.IGNORECASE)).last
                create_btn.click(force=True) # ПРОЛОМ СЛОЕВ
                
                # --- ЭТАП: УМНОЕ ОЖИДАНИЕ + ТАЙМАУТ (Smart Timeout) ---
                print("🛡 Ожидание результата (лимит 60 сек)...")
                is_posted = False
                error_msg = "Цензура Яндекса: промпт отклонен"
                is_timeout = False
                
                start_time = time.time()
                while time.time() - start_time < 60:
                    handle_ads(page) # Реклама может выскочить в любой момент
                    
                    # Проверка на успех: кнопка Опубликовать
                    publish_btn = page.locator('button:has-text("Опубликовать"), button:has-text("Publish")').first
                    if publish_btn.is_visible(timeout=500):
                        print("📸 Генерация завершена! Нажимаю Опубликовать (силой)...")
                        publish_btn.click(force=True)
                        
                        # Проверка редиректа (Retry Logic для публикации)
                        for _ in range(5): # 5 секунд ждем URL
                            if "/post/" in page.url:
                                is_posted = True
                                break
                            time.sleep(1)
                        
                        if is_posted: break
                        else:
                            print("ℹ️ URL не сменился, нажимаю Опубликовать еще раз...")
                            publish_btn.click(force=True)
                    
                    # Проверка на неудачу (Цензура)
                    if time.time() - start_time > 7:
                        if create_btn.is_visible(timeout=500) and not publish_btn.is_visible(timeout=500):
                            if create_btn.is_enabled():
                                print("🛑 ОБНАРУЖЕНА ЦЕНЗУРА ПЛОЩАДКИ!")
                                is_posted = False
                                break
                    
                    time.sleep(1.5)
                else:
                    # Цикл while завершился по времени (60 секунд истекло)
                    print("⌛ ТАЙМАУТ: Генерация идет слишком долго (>60 сек).")
                    is_timeout = True
                
                # --- ЛОГИКА СБРОСА ПРИ ТАЙМАУТЕ ---
                if is_timeout:
                    try:
                        # 1. Нажатие Отмена
                        cancel_btn = page.locator('button:has-text("Отмена"), [aria-label*="Отмена"], [aria-label*="Cancel"], .close-button').first
                        if cancel_btn.is_visible(timeout=2000):
                            cancel_btn.click(force=True)
                            print("🚫 Генерация отменена.")
                        
                        # 2. Очистка поля промпта
                        textarea = page.locator('textarea#prompt, [contenteditable="true"]').first
                        textarea.click(force=True)
                        textarea.fill("") # Жесткая очистка
                        print("🧹 Поле ввода очищено.")
                        
                        # 3. Парковка в таблицу
                        sheet.update_cell(target_row_idx, col["Status"] + 1, "⏳ Pending_Later")
                        if "Error_Log" in col:
                            sheet.update_cell(target_row_idx, col["Error_Log"] + 1, "[Timeout] > 1 мин. Отложено.")
                        
                        continue # Переход к следующему посту
                    except Exception as e_reset:
                        print(f"⚠️ Ошибка при сбросе таймаута: {e_reset}")
                        continue
                
                if not is_posted:
                    sheet.update_cell(target_row_idx, col["Status"] + 1, "🛠 Redo_Requested")
                    if "Error_Log" in col:
                        sheet.update_cell(target_row_idx, col["Error_Log"] + 1, error_msg)
                    
                    # Обновление счетчика попыток (колонка T)
                    if "Attempt_Count" in col:
                        try:
                            # Считываем текущее значение напрямую из ячейки для точности
                            current_val = sheet.cell(target_row_idx, col["Attempt_Count"] + 1).value
                            attempts = int(current_val) if current_val and str(current_val).isdigit() else 0
                        except:
                            attempts = 0
                        
                        new_attempts = attempts + 1
                        sheet.update_cell(target_row_idx, col["Attempt_Count"] + 1, new_attempts)
                        print(f"📊 Попытка №{new_attempts} для этого поста зафиксирована.")
                        
                    continue

                # 5. Фиксация результата
                final_url = page.url
                final_img = ""
                try: final_img = page.locator('article img, main img').first.get_attribute("src") or ""
                except: pass
                
                sheet.update(values=[[final_url, final_img, datetime.now().strftime("%d.%m.%Y %H:%M"), "🚀 Posted"]], range_name=f"O{target_row_idx}:R{target_row_idx}")
                if "Error_Log" in col: sheet.update_cell(target_row_idx, col["Error_Log"] + 1, "")
                print(f"✅ Пост {target_row_idx} опубликован!")
                
            except Exception as e:
                print(f"❌ Ошибка на строке {target_row_idx}: {e}")
                continue

    except Exception as e:
        print(f"❌ Критическая ошибка: {e}")
        traceback.print_exc()
    finally:
        if browser: browser.close()
        if p: p.stop()
        print("\n🏁 Очередь завершена.")

if __name__ == '__main__':
    run_poster()
