#!/usr/bin/env python3
# coding: utf-8

import os
import time
import random
import pickle
import asyncio
from pathlib import Path
import socket

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException, WebDriverException
from webdriver_manager.chrome import ChromeDriverManager

from telethon import TelegramClient, events
from telegram import Bot
from twocaptcha import TwoCaptcha

# ================= CONFIG =================
API_ID = 21882740
API_HASH = "c80a68894509d01a93f5acfeabfdd922"
ALERT_BOT_TOKEN = "6566504110:AAFK9hA4jxZ0eA7KZGhVvPe8mL2HZj2tQmE"
ALERT_CHAT_ID = 1168962519

TWOCAPTCHA_KEY = os.getenv("TWOCAPTCHA_API_KEY", "898059857fb8c709ca5c9613d44ffae4")
HEADLESS = True

LOGIN_URL = "https://freelancehunt.com/ua/profile/login"
LOGIN_DATA = {"login": "Vlari", "password": "Gvadiko_2004"}
COOKIES_FILE = "fh_cookies.pkl"

KEYWORDS = ["#дизайн_сайтов", "#html_и_css_верстка", "#cms"]
KEYWORDS = [k.lower() for k in KEYWORDS]

COMMENT_TEXT = "Доброго дня! Готовий виконати роботу якісно. Портфоліо у профілі. Дякую!"

# ================= INIT =================
tg_client = TelegramClient("session", API_ID, API_HASH)
alert_bot = Bot(token=ALERT_BOT_TOKEN)
solver = TwoCaptcha(TWOCAPTCHA_KEY) if TWOCAPTCHA_KEY else None

# ================= HELPERS =================
def ensure_dns(name="freelancehunt.com"):
    try:
        ip = socket.gethostbyname(name)
        print(f"[NET] DNS ok: {name} -> {ip}")
        return True
    except Exception as e:
        print(f"[NET WARN] DNS resolve failed for {name}: {e}")
        return False

def make_tmp_profile():
    tmp = os.path.join("/tmp", f"chrome-{int(time.time())}-{random.randint(0,9999)}")
    Path(tmp).mkdir(parents=True, exist_ok=True)
    return tmp

def create_driver():
    opts = Options()
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--disable-gpu")
    opts.add_argument("--window-size=1366,900")
    if HEADLESS:
        opts.add_argument("--headless=new")
    tmp_profile = make_tmp_profile()
    opts.add_argument(f"--user-data-dir={tmp_profile}")
    opts.add_experimental_option("excludeSwitches", ["enable-automation"])
    opts.add_experimental_option("useAutomationExtension", False)
    opts.add_argument("--log-level=3")

    svc = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=svc, options=opts)
    driver.set_page_load_timeout(60)
    print(f"[STEP] Chrome ready. HEADLESS={HEADLESS}. Profile: {tmp_profile}")
    return driver

driver = create_driver()

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
            except:
                pass
        print("[STEP] Cookies loaded.")
        return True
    except Exception as e:
        print("[WARN] load_cookies:", e)
        return False

def wait_for_body(timeout=20):
    try:
        WebDriverWait(driver, timeout).until(EC.presence_of_element_located((By.TAG_NAME, "body")))
        time.sleep(0.5)
    except TimeoutException:
        print("[WARN] page load timeout")

def human_typing(el, text, delay=(0.04,0.12)):
    for ch in text:
        el.send_keys(ch)
        time.sleep(random.uniform(*delay))

# ================= LOGIN =================
def login_if_needed():
    driver.get(LOGIN_URL)
    wait_for_body()
    load_cookies()
    time.sleep(0.5)
    try:
        login_input = driver.find_element(By.ID, "login-0")
        pwd_input = driver.find_element(By.ID, "password-0")
        btn = driver.find_element(By.ID, "save-0")
        human_typing(login_input, LOGIN_DATA["login"])
        human_typing(pwd_input, LOGIN_DATA["password"])
        btn.click()
        time.sleep(2)
        save_cookies()
        print("[LOGIN] done")
        return True
    except NoSuchElementException:
        print("[LOGIN] already logged in")
        return True
    except Exception as e:
        print("[LOGIN ERROR]", e)
        return False

# ================= MAKE BID =================
async def make_bid(url):
    print(f"[JOB] Processing: {url}")
    driver.get(url)
    wait_for_body()
    login_if_needed()
    print(f"[JOB] Ready to bid on {url}")
    # Тут можно добавить код для Selenium, чтобы делать ставку

# ================= TELEGRAM HANDLER =================
def extract_links(text):
    return [ln for ln in re.findall(r"https?://[^\s]+", text) if "freelancehunt.com" in ln]

@tg_client.on(events.NewMessage)
async def on_msg(event):
    text = (event.message.text or "").lower()
    print("[TG MESSAGE]", text)
    links = extract_links(text)
    if links and any(k in text for k in KEYWORDS):
        url = links[0]
        await make_bid(url)
        await event.reply("Бот обработал ссылку ✅")

# ================= MAIN =================
async def main():
    print("[STEP] Starting bot...")
    ensure_dns()
    if os.path.exists(COOKIES_FILE):
        driver.get("https://freelancehunt.com/")
        wait_for_body()
        load_cookies()
        driver.refresh()
        wait_for_body()
    await tg_client.start()
    print("[STEP] Telegram client ready.")
    await tg_client.run_until_disconnected()

# ================= RUN =================
if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Exiting by user")
    finally:
        try:
            driver.quit()
        except:
            pass
