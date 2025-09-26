#!/usr/bin/env python3
# coding: utf-8
"""
Telegram + Selenium bot for Freelancehunt (VPS-ready)
- headless Chrome
- temporary unique profile per run
- 2Captcha reCAPTCHA v2
- Telegram notifications
"""

import os
import time
import random
import pickle
import re
import asyncio
import socket
from pathlib import Path

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

# ---------------- CONFIG ----------------
API_ID = 21882740
API_HASH = "c80a68894509d01a93f5acfeabfdd922"
ALERT_BOT_TOKEN = "6566504110:AAFK9hA4jxZ0eA7KZGhVvPe8mL2HZj2tQmE"
ALERT_CHAT_ID = 1168962519
CAPTCHA_API_KEY = os.getenv("TWOCAPTCHA_API_KEY", "898059857fb8c709ca5c9613d44ffae4")
HEADLESS = True

LOGIN_URL = "https://freelancehunt.com/ua/profile/login"
LOGIN_DATA = {"login": "Vlari", "password": "Gvadiko_2004"}
COOKIES_FILE = "fh_cookies.pkl"

KEYWORDS = [
    "#html_и_css_верстка",
    "#веб_программирование",
    "#cms",
    "#интернет_магазины_и_электронная_коммерция",
    "#создание_сайта_под_ключ",
    "#дизайн_сайтов"
]
KEYWORDS = [k.lower() for k in KEYWORDS]

COMMENT_TEXT = (
    "Доброго дня! Готовий виконати роботу якісно.\n"
    "Портфоліо робіт у моєму профілі.\n"
    "Заздалегідь дякую!"
)

# ---------------- Init Telegram / 2Captcha ----------------
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

# ---------------- Helpers ----------------
def ensure_dns(name="freelancehunt.com", timeout=5):
    try:
        socket.setdefaulttimeout(timeout)
        ip = socket.gethostbyname(name)
        print(f"[NET] DNS ok: {name} -> {ip}")
        return True
    except Exception as e:
        print(f"[NET WARN] DNS resolve failed for {name}: {e}")
        return False

def make_tmp_profile():
    tmp = os.path.join("/tmp", f"chrome-temp-{int(time.time())}-{random.randint(0,9999)}")
    Path(tmp).mkdir(parents=True, exist_ok=True)
    return tmp

def create_chrome_driver():
    tmp_profile = make_tmp_profile()
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
    opts.add_argument("--log-level=3")

    svc = Service(ChromeDriverManager().install())
    try:
        driver = webdriver.Chrome(service=svc, options=opts)
        driver.set_page_load_timeout(60)
        print(f"[STEP] Chrome ready. HEADLESS={HEADLESS}. Temp profile: {tmp_profile}")
        return driver
    except WebDriverException as e:
        print("[ERROR] creating Chrome WebDriver:", e)
        raise

driver = None
try:
    driver = create_chrome_driver()
except Exception as e:
    print("[FATAL] Could not start Chrome driver:", e)
    raise SystemExit(1)

def wait_for_body(timeout=20):
    try:
        WebDriverWait(driver, timeout).until(EC.presence_of_element_located((By.TAG_NAME, "body")))
        time.sleep(0.5)
    except TimeoutException:
        print("[WARN] page load timeout")

def save_cookies():
    try:
        with open(COOKIES_FILE, "wb") as f:
            pickle.dump(driver.get_cookies(), f)
        print("[STEP] Cookies saved.")
    except Exception as e:
        print("[ERROR] save_cookies:", e)

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
        print("[WARN] load_cookies:", e)
        return False

def human_typing(el, text, delay=(0.04,0.12)):
    for ch in text:
        el.send_keys(ch)
        time.sleep(random.uniform(*delay))

def human_scroll_and_move():
    try:
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight * 0.3);")
        time.sleep(random.uniform(0.2, 0.6))
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight * 0.6);")
        time.sleep(random.uniform(0.2, 0.6))
        ActionChains(driver).move_by_offset(random.randint(1,50), random.randint(1,50)).perform()
        time.sleep(0.2)
    except Exception:
        pass

# ---------------- Main Bot Logic ----------------
# Весь твой блок login_if_needed, make_bid, recaptcha handling и Telegram обработчики остаются как в твоём коде

# ---------------- Main ----------------
async def main():
    print("[STEP] Starting bot. Pre-check DNS...")
    ensure_dns()
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

    await tg_client.start()
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
