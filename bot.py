#!/usr/bin/env python3
# coding: utf-8
"""
Visible Chrome Freelancehunt bidding bot
- Telethon listener
- Selenium (VISIBLE Chrome via X11 forwarding)
- reCAPTCHA solve via 2Captcha
- Uses your existing API keys / login from provided code
"""

import os
import re
import time
import random
import pickle
import asyncio
import socket
import sqlite3
from pathlib import Path
from typing import Optional

from twocaptcha import TwoCaptcha
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException, WebDriverException

from webdriver_manager.chrome import ChromeDriverManager
from telethon import TelegramClient, events
from telegram import Bot

# ---------------- CONFIG (взято из твоего кода) ----------------
API_ID = 21882740
API_HASH = "c80a68894509d01a93f5acfeabfdd922"
ALERT_BOT_TOKEN = "6566504110:AAFK9hA4jxZ0eA7KZGhVvPe8mL2HZj2tQmE"
ALERT_CHAT_ID = 1168962519

CAPTCHA_API_KEY = "898059857fb8c709ca5c9613d44ffae4"

# Важно: VISIBLE Chrome
HEADLESS = False

LOGIN_URL = "https://freelancehunt.com/ua/profile/login"
LOGIN_DATA = {"login": "Vlari", "password": "Gvadiko_2004"}

COOKIES_FILE = "fh_cookies.pkl"

COMMENT_TEXT = (
    "Доброго дня! Готовий виконати роботу якісно.\n"
    "Портфоліо робіт у моєму профілі.\n"
    "Заздалегідь дякую!"
)

KEYWORDS = [
    "#html_и_css_верстка",
    "#веб_программирование",
    "#cms",
    "#интернет_магазины_и_электронная_коммерция",
    "#создание_сайта_под_ключ",
    "#дизайн_сайтов"
]
KEYWORDS = [k.lower() for k in KEYWORDS]

# ---------------- INIT ----------------
alert_bot = Bot(token=ALERT_BOT_TOKEN)
tg_client = TelegramClient("session", API_ID, API_HASH)
solver = None
if CAPTCHA_API_KEY:
    try:
        solver = TwoCaptcha(CAPTCHA_API_KEY)
        print("[STEP] 2Captcha client initialized.")
    except Exception as e:
        print("[WARN] 2Captcha init error:", e)
else:
    print("[WARN] No 2Captcha API key provided.")

# ---------------- Utilities ----------------
def ensure_dns(name="freelancehunt.com", timeout=5) -> bool:
    try:
        socket.setdefaulttimeout(timeout)
        ip = socket.gethostbyname(name)
        print(f"[NET] DNS ok: {name} -> {ip}")
        return True
    except Exception as e:
        print(f"[NET WARN] DNS resolve failed for {name}: {e}")
        return False

def make_tmp_profile() -> str:
    tmp = os.path.join("/tmp", f"chrome-temp-{int(time.time())}-{random.randint(0,9999)}")
    Path(tmp).mkdir(parents=True, exist_ok=True)
    return tmp

def create_chrome_driver() -> webdriver.Chrome:
    tmp_profile = make_tmp_profile()
    opts = Options()
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    # убираем --disable-gpu т.к. для видимого режима иногда мешает
    opts.add_argument("--window-size=1280,900")
    if HEADLESS:
        opts.add_argument("--headless=new")
    # используем отдельный профиль чтобы не мешать другому процессу
    opts.add_argument(f"--user-data-dir={tmp_profile}")
    # не скрывать окно при X11
    opts.add_experimental_option("excludeSwitches", ["enable-automation"])
    opts.add_experimental_option("useAutomationExtension", False)
    svc = Service(ChromeDriverManager().install())
    try:
        driver = webdriver.Chrome(service=svc, options=opts)
        driver.set_page_load_timeout(60)
        print(f"[STEP] Chrome ready. HEADLESS={HEADLESS}. Temp profile: {tmp_profile}")
        return driver
    except WebDriverException as e:
        print("[ERROR] creating Chrome WebDriver:", e)
        raise

driver = create_chrome_driver()

def wait_for_body(timeout=20):
    try:
        WebDriverWait(driver, timeout).until(EC.presence_of_element_located((By.TAG_NAME, "body")))
        time.sleep(0.4)
    except TimeoutException:
        print("[WARN] page load timeout")

def save_cookies():
    try:
        with open(COOKIES_FILE, "wb") as f:
            pickle.dump(driver.get_cookies(), f)
        print("[STEP] Cookies saved.")
    except Exception as e:
        print("[ERROR] save_cookies:", e)

def load_cookies() -> bool:
    if not os.path.exists(COOKIES_FILE):
        return False
    try:
        with open(COOKIES_FILE, "rb") as f:
            cookies = pickle.load(f)
        for c in cookies:
            try:
                driver.add_cookie(c)
            except Exception:
                pass
        print("[STEP] Cookies loaded.")
        return True
    except Exception as e:
        print("[WARN] load_cookies:", e)
        return False

def human_typing(el, text, delay=(0.04,0.12)):
    for ch in text:
        el.send_keys(ch)
        time.sleep(random.uniform(*delay))

def human_scroll_and_move():
    try:
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight * 0.25);")
        time.sleep(random.uniform(0.15, 0.4))
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight * 0.6);")
        time.sleep(random.uniform(0.15, 0.4))
        ActionChains(driver).move_by_offset(random.randint(1,50), random.randint(1,50)).perform()
    except Exception:
        pass

def page_has_captcha_text() -> bool:
    try:
        body = driver.find_element(By.TAG_NAME, "body").text.lower()
        return "captcha" in body or "капча" in body or "protection" in body
    except Exception:
        return False

def find_recaptcha_sitekey() -> Optional[str]:
    # data-sitekey
    try:
        elems = driver.find_elements(By.CSS_SELECTOR, "[data-sitekey]")
        for e in elems:
            sk = e.get_attribute("data-sitekey")
            if sk:
                return sk
    except Exception:
        pass
    # iframe src
    try:
        iframes = driver.find_elements(By.TAG_NAME, "iframe")
        for f in iframes:
            src = f.get_attribute("src") or ""
            if "sitekey=" in src:
                m = re.search(r"sitekey=([A-Za-z0-9_-]+)", src)
                if m:
                    return m.group(1)
            # google recaptcha anchor pattern ?k=SITEKEY
            m2 = re.search(r"[?&]k=([A-Za-z0-9_-]+)", src)
            if m2:
                return m2.group(1)
    except Exception:
        pass
    return None

def solve_recaptcha(sitekey: str, pageurl: str, timeout:int=180) -> Optional[str]:
    if solver is None:
        print("[2CAPTCHA] Solver not initialized.")
        return None
    try:
        print("[2CAPTCHA] submitting recaptcha task...")
        res = solver.recaptcha(sitekey=sitekey, url=pageurl, invisible=0)
        token = None
        if isinstance(res, dict):
            token = res.get("code") or res.get("request")
        elif isinstance(res, str):
            token = res
        print("[2CAPTCHA] got token:", bool(token))
        return token
    except Exception as e:
        print("[2CAPTCHA ERROR]", e)
        return None

def inject_recaptcha_token(token: str) -> bool:
    try:
        driver.execute_script("""
        (function(t){
            var el = document.getElementById('g-recaptcha-response');
            if(!el){
                el = document.createElement('textarea');
                el.id='g-recaptcha-response';
                el.name='g-recaptcha-response';
                el.style.display='none';
                document.body.appendChild(el);
            }
            el.innerHTML = t;
        })(arguments[0]);
        """, token)
        time.sleep(1)
        # пробуем сабмитнуть ближайшую форму
        try:
            btn = driver.find_element(By.CSS_SELECTOR, "form button[type='submit'], form input[type='submit']")
            driver.execute_script("arguments[0].click();", btn)
            return True
        except Exception:
            try:
                driver.execute_script("document.querySelectorAll('form').forEach(f=>f.submit());")
                return True
            except Exception:
                return False
    except Exception as e:
        print("[inject token error]", e)
        return False

# ---------------- Login and bidding ----------------
def login_if_needed() -> bool:
    try:
        driver.get(LOGIN_URL)
        wait_for_body()
        load_cookies()
        time.sleep(0.6)
        # если уже залогинен, поле не будет найдено
        login_input = driver.find_element(By.ID, "login-0")
        pwd_input = driver.find_element(By.ID, "password-0")
        btn = driver.find_element(By.ID, "save-0")
        human_typing(login_input, LOGIN_DATA["login"])
        human_typing(pwd_input, LOGIN_DATA["password"])
        human_scroll_and_move()
        driver.execute_script("arguments[0].click();", btn)
        time.sleep(2)
        wait_for_body()
        # капча при логине
        if page_has_captcha_text() or find_recaptcha_sitekey():
            sk = find_recaptcha_sitekey()
            if sk:
                token = solve_recaptcha(sk, driver.current_url)
                if token:
                    inject_recaptcha_token(token)
        save_cookies()
        print("[LOGIN] login attempt done")
        return True
    except NoSuchElementException:
        print("[LOGIN] login fields not found — maybe already logged in")
        return True
    except Exception as e:
        print("[LOGIN ERROR]", e)
        return False

async def send_alert(msg: str):
    try:
        await alert_bot.send_message(chat_id=ALERT_CHAT_ID, text=msg)
        print("[TG ALERT]", msg)
    except Exception as e:
        print("[TGERROR]", e)

async def make_bid(url: str):
    print("[JOB] processing:", url)
    try:
        if not ensure_dns():
            await send_alert(f"⚠️ DNS resolving failed, cannot open {url}")
            return
        driver.get(url)
        wait_for_body()
        load_cookies()
        time.sleep(0.5)
        # проверим залогинен ли
        try:
            driver.find_element(By.CSS_SELECTOR, "a[href='/profile']")
            print("[STEP] already logged in")
        except NoSuchElementException:
            ok = login_if_needed()
            if not ok:
                await send_alert(f"❌ Login failed for {url}")
                return
            driver.get(url)
            wait_for_body()
        # запуск обработки капчи на странице проекта, если есть
        if page_has_captcha_text() or find_recaptcha_sitekey():
            print("[INFO] captcha detected on project page")
            time.sleep(3)
            sk = find_recaptcha_sitekey()
            if sk:
                token = solve_recaptcha(sk, driver.current_url)
                if token:
                    injected = inject_recaptcha_token(token)
                    if not injected:
                        await send_alert(f"⚠️ Не удалось инжектить токен на {url}")
                        return
                else:
                    await send_alert(f"⚠️ 2Captcha failed for {url}")
                    return
            else:
                await send_alert(f"⚠️ Captcha on {url} — manual intervention required.")
                return
        # универсальный поиск кнопки "Сделать ставку"
        selectors = ["#add-bid", "#add-0", "button[name='add']", "button[data-action='add-bid']", ".project-action .btn"]
        clicked = False
        for sel in selectors:
            try:
                btn = WebDriverWait(driver, 5).until(EC.element_to_be_clickable((By.CSS_SELECTOR, sel)))
                driver.execute_script("arguments[0].scrollIntoView({block:'center'});", btn)
                time.sleep(0.2)
                driver.execute_script("arguments[0].click();", btn)
                clicked = True
                break
            except TimeoutException:
                continue
            except Exception:
                continue
        if not clicked:
            await send_alert(f"⚠️ Кнопка 'Сделать ставку' не найдена: {url}")
            return
        time.sleep(0.8)
        # заполняем форму
        try:
            amount = WebDriverWait(driver, 8).until(EC.presence_of_element_located((By.ID, "amount-0")))
            days = driver.find_element(By.ID, "days_to_deliver-0")
            comment = driver.find_element(By.ID, "comment-0")
            human_typing(amount, "1111")
            human_typing(days, "3")
            human_typing(comment, COMMENT_TEXT, delay=(0.02, 0.07))
            time.sleep(0.4)
            submit_btn = driver.find_element(By.ID, "add-0")
            driver.execute_script("arguments[0].click();", submit_btn)
            await send_alert(f"✅ Ставка отправлена: {url}")
            save_cookies()
        except Exception as e:
            await send_alert(f"❌ Ошибка заполнения формы: {e}\n{url}")
    except Exception as e:
        await send_alert(f"❌ Ошибка обработки: {e}\n{url}")
        print("[ERROR] make_bid:", e)

# ---------------- Telegram handlers ----------------
def extract_links(text: str):
    return [ln for ln in re.findall(r"https?://[^\s]+", text) if "freelancehunt.com" in ln]

@tg_client.on(events.NewMessage)
async def on_msg(event):
    text = (event.message.text or "").lower()
    print("[TG MESSAGE]", text)
    links = extract_links(text)
    if links and any(k in text for k in KEYWORDS):
        url = links[0]
        print("[TG] got link:", url)
        # запустить задачу, не блокируя обработчик
        asyncio.create_task(make_bid(url))

# ---------------- MAIN ----------------
async def main():
    print("[STEP] Starting bot. Pre-check DNS...")
    ensure_dns()
    # preload cookies if exists (без авторизации Telethon)
    try:
        if os.path.exists(COOKIES_FILE):
            driver.get("https://freelancehunt.com/")
            wait_for_body()
            load_cookies()
            driver.refresh()
            wait_for_body()
            print("[STEP] cookies preloaded")
    except Exception as e:
        print("[WARNING] preload cookies error:", e)
    # start telethon client with safe retry on sqlite lock
    try:
        await tg_client.start()
    except (sqlite3.OperationalError, Exception) as e:
        print("[WARN] Telethon start failed:", e)
        # если sqlite locked — просигналим и попробуем удалить lock-файлы (осторожно)
        # Но не удаляем сессию автоматически, чтобы не сломать авторизацию.
        print("Если Telethon выдал sqlite 'database is locked' — убедись, что нет другого процесса бота.")
        raise
    print("[STEP] Telegram client started. Waiting for messages...")
    await tg_client.run_until_disconnected()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Exiting by user")
    finally:
        try:
            driver.quit()
        except Exception:
            pass
