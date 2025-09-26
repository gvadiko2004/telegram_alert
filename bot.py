#!/usr/bin/env python3
# coding: utf-8

"""
Freelancehunt bidding bot:
- Telegram listener
- Selenium + headless Chrome
- Login + Cookies
- reCAPTCHA solving via 2Captcha
"""

import os
import re
import time
import random
import pickle
import asyncio
from pathlib import Path

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException

from webdriver_manager.chrome import ChromeDriverManager
from twocaptcha import TwoCaptcha
from telethon import TelegramClient, events
from telegram import Bot

# ---------------- CONFIG ----------------
API_ID = 21882740
API_HASH = "c80a68894509d01a93f5acfeabfdd922"
ALERT_BOT_TOKEN = "YOUR_TELEGRAM_BOT_TOKEN"
ALERT_CHAT_ID = 1168962519

CAPTCHA_API_KEY = "YOUR_2CAPTCHA_KEY"

LOGIN_URL = "https://freelancehunt.com/ua/profile/login"
LOGIN_DATA = {"login": "YOUR_LOGIN", "password": "YOUR_PASSWORD"}

COOKIES_FILE = "cookies.pkl"
HEADLESS = True

COMMENT_TEXT = "Доброго дня! Готовий виконати роботу якісно.\nПортфоліо робіт у моєму профілі.\nЗаздалегідь дякую!"

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
tg_client = TelegramClient("session", API_ID, API_HASH)
alert_bot = Bot(token=ALERT_BOT_TOKEN)
solver = TwoCaptcha(CAPTCHA_API_KEY)

def make_driver():
    opts = Options()
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--disable-gpu")
    opts.add_argument("--window-size=1366,900")
    if HEADLESS:
        opts.add_argument("--headless=new")
    return webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=opts)

driver = make_driver()

# ---------------- HELPERS ----------------
def wait_body(timeout=20):
    WebDriverWait(driver, timeout).until(EC.presence_of_element_located((By.TAG_NAME, "body")))
    time.sleep(0.5)

def save_cookies():
    with open(COOKIES_FILE, "wb") as f:
        pickle.dump(driver.get_cookies(), f)

def load_cookies():
    if not os.path.exists(COOKIES_FILE): return
    with open(COOKIES_FILE, "rb") as f:
        for c in pickle.load(f):
            try: driver.add_cookie(c)
            except: pass

def find_sitekey():
    try:
        elem = driver.find_element(By.CSS_SELECTOR, "[data-sitekey]")
        return elem.get_attribute("data-sitekey")
    except: return None

def solve_captcha(sitekey, url):
    try:
        result = solver.recaptcha(sitekey=sitekey, url=url)
        return result.get("code")
    except Exception as e:
        print("2Captcha error:", e)
        return None

def inject_token(token):
    driver.execute_script("""
    var el=document.getElementById('g-recaptcha-response');
    if(!el){
      el=document.createElement('textarea');
      el.id='g-recaptcha-response';
      el.name='g-recaptcha-response';
      el.style.display='none';
      document.body.appendChild(el);
    }
    el.value=arguments[0];
    """, token)
    time.sleep(2)

async def send_alert(msg):
    await alert_bot.send_message(chat_id=ALERT_CHAT_ID, text=msg)
    print("[ALERT]", msg)

# ---------------- LOGIN ----------------
def login():
    driver.get(LOGIN_URL)
    wait_body()
    load_cookies()
    try:
        login_input = driver.find_element(By.ID, "login-0")
        pwd_input = driver.find_element(By.ID, "password-0")
        btn = driver.find_element(By.ID, "save-0")
        login_input.send_keys(LOGIN_DATA["login"])
        pwd_input.send_keys(LOGIN_DATA["password"])
        btn.click()
        wait_body()
        sk = find_sitekey()
        if sk:
            token = solve_captcha(sk, driver.current_url)
            if token: inject_token(token)
        save_cookies()
    except NoSuchElementException:
        print("Already logged in")

# ---------------- BID ----------------
async def make_bid(url):
    print("Processing:", url)
    driver.get(url)
    wait_body()
    load_cookies()
    driver.refresh()
    wait_body()

    sk = find_sitekey()
    if sk:
        token = solve_captcha(sk, driver.current_url)
        if token: inject_token(token)

    try:
        bid_btn = WebDriverWait(driver, 15).until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, "#add-bid, #add-0, button[name='add']"))
        )
        bid_btn.click()
        time.sleep(1)
    except TimeoutException:
        await send_alert(f"⚠️ Кнопка 'Сделать ставку' не найдена: {url}")
        return

    try:
        driver.find_element(By.ID, "amount-0").send_keys("1111")
        driver.find_element(By.ID, "days_to_deliver-0").send_keys("3")
        driver.find_element(By.ID, "comment-0").send_keys(COMMENT_TEXT)
        driver.find_element(By.ID, "add-0").click()
        await send_alert(f"✅ Ставка отправлена: {url}")
        save_cookies()
    except Exception as e:
        await send_alert(f"❌ Ошибка при заполнении формы: {e}\n{url}")

# ---------------- TELEGRAM ----------------
def extract_links(text):
    return [ln for ln in re.findall(r"https?://[^\s]+", text) if "freelancehunt.com" in ln]

@tg_client.on(events.NewMessage)
async def on_msg(event):
    text = (event.message.text or "").lower()
    links = extract_links(text)
    if links and any(k in text for k in KEYWORDS):
        await make_bid(links[0])

# ---------------- MAIN ----------------
async def main():
    login()
    await tg_client.start()
    print("Bot is running...")
    await tg_client.run_until_disconnected()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        driver.quit()
