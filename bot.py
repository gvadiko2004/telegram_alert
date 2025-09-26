#!/usr/bin/env python3
# coding: utf-8
"""
Минимальный Selenium + Telegram бот для VPS.
Открывает freelancehunt.com в headless режиме.
"""

import os
import time
import asyncio
import pickle
import random
import re

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

HEADLESS = True  # VPS без GUI
COOKIES_FILE = "/tmp/fh_cookies.pkl"

LOGIN_URL = "https://freelancehunt.com/ua/profile/login"
LOGIN_DATA = {"login": "Vlari", "password": "Gvadiko_2004"}

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
    opts.add_argument("--dns-prefetch-disable")
    opts.add_argument("--remote-debugging-port=9222")
    opts.add_argument("--host-resolver-rules=MAP * ~NOTFOUND , EXCLUDE 127.0.0.1")
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

# ---------------- Login ----------------
def login_if_needed():
    driver.get(LOGIN_URL)
    wait_for_body()
    load_cookies()
    try:
        login_input = driver.find_element(By.ID, "login-0")
        pwd_input = driver.find_element(By.ID, "password-0")
        btn = driver.find_element(By.ID, "save-0")
        login_input.send_keys(LOGIN_DATA["login"])
        pwd_input.send_keys(LOGIN_DATA["password"])
        driver.execute_script("arguments[0].click();", btn)
        time.sleep(2)
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
    try:
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
        await send_alert(f"✅ Ready to bid: {url}")
    except Exception as e:
        await send_alert(f"❌ Error opening {url}: {e}")

# ---------------- Telegram ----------------
def extract_links(event):
    links = []
    if event.message.buttons:
        for row in event.message.buttons:
            for btn in row:
                url = getattr(btn, "url", None)
                if url and "freelancehunt.com" in url:
                    links.append(url)
    text = (event.message.text or "").lower()
    return links, text

@tg_client.on(events.NewMessage)
async def on_msg(event):
    links, text = extract_links(event)
    KEYWORDS = ["#html_и_css_верстка", "#веб_программирование",
                "#cms", "#интернет_магазины_и_электронная_коммерция",
                "#создание_сайта_под_ключ", "#дизайн_сайтов"]
    if links and any(k.lower() in text for k in KEYWORDS):
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
