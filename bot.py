#!/usr/bin/env python3
# coding: utf-8
"""
Telegram + Selenium bot for Freelancehunt on VPS
- Headless Chrome
- Inline button URL extraction
- 2captcha support for reCAPTCHA v2
"""

import os
import time
import random
import asyncio
import pickle
import re
import requests

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException

from webdriver_manager.chrome import ChromeDriverManager
from telethon import TelegramClient, events
from telegram import Bot

# ---------------- CONFIG ----------------
API_ID = 21882740
API_HASH = "c80a68894509d01a93f5acfeabfdd922"
ALERT_BOT_TOKEN = "YOUR_BOT_TOKEN"
ALERT_CHAT_ID = 1168962519
CAPTCHA_API_KEY = "YOUR_2CAPTCHA_KEY"

HEADLESS = True  # VPS без X11
COOKIES_FILE = "/tmp/fh_cookies.pkl"

LOGIN_URL = "https://freelancehunt.com/ua/profile/login"
LOGIN_DATA = {"login": "Vlari", "password": "Gvadiko_2004"}

KEYWORDS = [k.lower() for k in [
    "#html_и_css_верстка",
    "#веб_программирование",
    "#cms",
    "#интернет_магазины_и_электронная_коммерция",
    "#создание_сайта_под_ключ",
    "#дизайн_сайтов"
]]
COMMENT_TEXT = "Доброго дня! Готовий виконати роботу якісно.\nПортфоліо робіт у моєму профілі.\nЗаздалегідь дякую!"

# ---------------- Telegram ----------------
alert_bot = Bot(token=ALERT_BOT_TOKEN)
tg_client = TelegramClient("session", API_ID, API_HASH)

# ---------------- Selenium driver ----------------
def create_chrome_driver():
    tmp_profile = f"/tmp/chrome-temp-{int(time.time())}"
    os.makedirs(tmp_profile, exist_ok=True)

    opts = Options()
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--disable-gpu")
    opts.add_argument("--window-size=1366,900")
    if HEADLESS:
        opts.add_argument("--headless=new")
    opts.add_argument(f"--user-data-dir={tmp_profile}")
    opts.add_experimental_option("excludeSwitches", ["enable-automation"])
    opts.add_experimental_option("useAutomationExtension", False)

    svc = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=svc, options=opts)
    driver.set_page_load_timeout(60)
    return driver

driver = create_chrome_driver()
print(f"[STEP] Chrome ready. HEADLESS={HEADLESS}")

# ---------------- Utilities ----------------
def wait_for_body(timeout=20):
    try:
        WebDriverWait(driver, timeout).until(EC.presence_of_element_located((By.TAG_NAME, "body")))
        time.sleep(0.5)
    except TimeoutException:
        print("[WARNING] page load timeout")

def save_cookies():
    try:
        with open(COOKIES_FILE, "wb") as f:
            pickle.dump(driver.get_cookies(), f)
        print("[STEP] Cookies saved.")
    except Exception as e:
        print(f"[ERROR] save_cookies: {e}")

def load_cookies():
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
        print(f"[WARNING] load_cookies: {e}")
        return False

def human_typing(el, text, delay=(0.04,0.12)):
    for ch in text:
        el.send_keys(ch)
        time.sleep(random.uniform(*delay))

def page_has_captcha_text():
    try:
        body = driver.find_element(By.TAG_NAME, "body").text.lower()
        if "captcha" in body or "капча" in body or "protection" in body:
            return True
    except Exception:
        pass
    return False

def find_recaptcha_sitekey():
    try:
        elems = driver.find_elements(By.CSS_SELECTOR, "[data-sitekey]")
        for e in elems:
            sk = e.get_attribute("data-sitekey")
            if sk:
                return sk
    except Exception:
        pass
    return None

def submit_2captcha(sitekey, pageurl, poll=5, timeout=180):
    try:
        r = requests.post("http://2captcha.com/in.php", data={
            "key": CAPTCHA_API_KEY,
            "method": "userrecaptcha",
            "googlekey": sitekey,
            "pageurl": pageurl,
            "json": 1
        }, timeout=30).json()
        if r.get("status") != 1:
            print(f"[2CAPTCHA ERROR] {r}")
            return None
        task_id = r.get("request")
        waited = 0
        while waited < timeout:
            time.sleep(poll)
            waited += poll
            r2 = requests.get("http://2captcha.com/res.php", params={
                "key": CAPTCHA_API_KEY, "action": "get", "id": task_id, "json": 1
            }, timeout=30).json()
            if r2.get("status") == 1:
                return r2.get("request")
            elif r2.get("request") == "CAPCHA_NOT_READY":
                continue
            else:
                return None
        return None
    except Exception as e:
        print(f"[2CAPTCHA EX] {e}")
        return None

def inject_recaptcha_token(token):
    try:
        driver.execute_script("""
            (function(t){
                var el=document.getElementById('g-recaptcha-response');
                if(!el){el=document.createElement('textarea'); el.id='g-recaptcha-response';
                el.name='g-recaptcha-response'; el.style.display='none'; document.body.appendChild(el);}
                el.innerHTML=t;
            })(arguments[0]);
        """, token)
        time.sleep(0.8)
        try:
            btn = driver.find_element(By.CSS_SELECTOR, "form button[type='submit'], form input[type='submit']")
            driver.execute_script("arguments[0].click();", btn)
            return True
        except Exception:
            driver.execute_script("document.querySelectorAll('form').forEach(f=>f.submit());")
            return True
    except Exception as e:
        print(f"[inject token error] {e}")
        return False

# ---------------- Login ----------------
def login_if_needed():
    driver.get(LOGIN_URL)
    wait_for_body()
    load_cookies()
    try:
        login_input = driver.find_element(By.ID, "login-0")
        pwd_input = driver.find_element(By.ID, "password-0")
        btn = driver.find_element(By.ID, "save-0")
        human_typing(login_input, LOGIN_DATA["login"])
        human_typing(pwd_input, LOGIN_DATA["password"])
        driver.execute_script("arguments[0].click();", btn)
        time.sleep(2)
        wait_for_body()
        if page_has_captcha_text() or find_recaptcha_sitekey():
            sitekey = find_recaptcha_sitekey()
            if sitekey:
                token = submit_2captcha(sitekey, driver.current_url)
                if token:
                    inject_recaptcha_token(token)
        save_cookies()
        return True
    except NoSuchElementException:
        return True
    except Exception as e:
        print(f"[login_if_needed error] {e}")
        return False

# ---------------- Job ----------------
async def send_alert(msg):
    try:
        await alert_bot.send_message(chat_id=ALERT_CHAT_ID, text=msg)
        print("[TG] " + msg)
    except Exception as e:
        print("[TGERROR] " + str(e))

async def make_bid(url):
    driver.get(url)
    wait_for_body()
    load_cookies()
    try:
        driver.find_element(By.CSS_SELECTOR, "a[href='/profile']")
    except NoSuchElementException:
        ok = login_if_needed()
        if not ok:
            await send_alert(f"❌ Login failed for {url}")
            return
        driver.get(url)
        wait_for_body()
    # TODO: здесь добавь заполнение формы как у тебя в локальном скрипте
    await send_alert(f"✅ Ready to bid: {url}")

# ---------------- Telegram handlers ----------------
def extract_links_from_msg(event):
    links = []
    text = (event.message.text or "").lower()
    # ищем обычные ссылки в тексте
    links.extend([ln for ln in re.findall(r"https?://[^\s]+", text) if "freelancehunt.com" in ln])
    # ищем ссылки на кнопках
    if hasattr(event.message, "reply_markup") and event.message.reply_markup:
        for row in event.message.reply_markup.rows:
            for button in row.buttons:
                if getattr(button, "url", None):
                    if "freelancehunt.com" in button.url.lower():
                        links.append(button.url)
    return links

@tg_client.on(events.NewMessage)
async def on_msg(event):
    links = extract_links_from_msg(event)
    text = (event.message.text or "").lower()
    if links and any(k in text for k in KEYWORDS):
        url = links[0]
        await make_bid(url)

# ---------------- Main ----------------
async def main():
    await tg_client.start()
    print("[STEP] Telegram client started. Waiting for messages...")
    await tg_client.run_until_disconnected()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    finally:
        try:
            driver.quit()
        except Exception:
            pass
