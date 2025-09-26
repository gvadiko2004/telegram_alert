#!/usr/bin/env python3
# coding: utf-8

import os
import pickle
import re
import time
import random
import asyncio
import requests
from twocaptcha import TwoCaptcha

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

# ----------------- CONFIG -----------------
api_id = 21882740
api_hash = "c80a68894509d01a93f5acfeabfdd922"
ALERT_BOT_TOKEN = "6566504110:AAFK9hA4jxZ0eA7KZGhVvPe8mL2HZj2tQmE"
ALERT_CHAT_ID = 1168962519
CAPTCHA_API_KEY = "898059857fb8c709ca5c9613d44ffae4"

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
KEYWORDS = [kw.lower() for kw in KEYWORDS]

COMMENT_TEXT = (
    "Доброго дня! Готовий виконати роботу якісно.\n"
    "Портфоліо робіт у моєму профілі.\n"
    "Заздалегідь дякую!"
)

# ----------------- Telegram -----------------
alert_bot = Bot(token=ALERT_BOT_TOKEN)
client = TelegramClient("session", api_id, api_hash)

# ----------------- 2Captcha -----------------
solver = TwoCaptcha(CAPTCHA_API_KEY)

# ----------------- Selenium -----------------
def create_chrome_driver():
    chrome_options = Options()
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--window-size=1920,1080")
    # chrome_options.add_argument("--headless=new")  # если хочешь видеть браузер, отключи headless
    chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
    chrome_options.add_experimental_option("useAutomationExtension", False)

    driver_path = ChromeDriverManager().install()
    svc = Service(driver_path)
    driver = webdriver.Chrome(service=svc, options=chrome_options)
    driver.set_page_load_timeout(60)
    return driver

driver = create_chrome_driver()
print("[STEP] Chrome запущен.")
time.sleep(1)

# ----------------- Utils -----------------
def extract_links(text: str):
    return [link for link in re.findall(r"https?://[^\s]+", text) if "freelancehunt.com" in link]

def save_cookies():
    try:
        with open(COOKIES_FILE, "wb") as f:
            pickle.dump(driver.get_cookies(), f)
        print("[STEP] Cookies сохранены.")
    except Exception as e:
        print(f"[ERROR] Не удалось сохранить куки: {e}")

def load_cookies():
    if os.path.exists(COOKIES_FILE):
        try:
            with open(COOKIES_FILE, "rb") as f:
                cookies = pickle.load(f)
            for c in cookies:
                try:
                    driver.add_cookie(c)
                except Exception:
                    pass
            print("[STEP] Cookies загружены.")
            return True
        except Exception as e:
            print(f"[WARNING] Ошибка загрузки кук: {e}")
    return False

def wait_for_page_load(timeout=20):
    try:
        WebDriverWait(driver, timeout).until(EC.presence_of_element_located((By.TAG_NAME, "body")))
        time.sleep(1)
    except TimeoutException:
        print("[WARNING] Таймаут ожидания загрузки страницы.")

def human_typing(el, text, delay_range=(0.04, 0.12)):
    for ch in text:
        el.send_keys(ch)
        time.sleep(random.uniform(*delay_range))

def page_contains_captcha_text():
    try:
        body = driver.find_element(By.TAG_NAME, "body").text.lower()
        if "капча" in body or "captcha" in body:
            return True
    except Exception:
        pass
    return False

def find_recaptcha_sitekey():
    try:
        elems = driver.find_elements(By.CSS_SELECTOR, "[data-sitekey]")
        for e in elems:
            key = e.get_attribute("data-sitekey")
            if key:
                return key
    except Exception:
        pass
    return None

def solve_recaptcha():
    sitekey = find_recaptcha_sitekey()
    if not sitekey:
        return None
    try:
        result = solver.recaptcha(sitekey=sitekey, url=driver.current_url)
        token = result.get("code")
        return token
    except Exception as e:
        print(f"[ERROR] 2Captcha solve failed: {e}")
        return None

def inject_recaptcha_token_and_submit(token):
    try:
        driver.execute_script("""
        (function(token){
            var el = document.getElementById('g-recaptcha-response');
            if(!el){
                el = document.createElement('textarea');
                el.id = 'g-recaptcha-response';
                el.name = 'g-recaptcha-response';
                el.style.display = 'none';
                document.body.appendChild(el);
            }
            el.innerHTML = token;
        })(arguments[0]);
        """, token)
        try:
            btn = driver.find_element(By.CSS_SELECTOR, "form button[type='submit'], form input[type='submit']")
            driver.execute_script("arguments[0].click();", btn)
        except Exception:
            driver.execute_script("document.querySelectorAll('form').forEach(f => f.submit());")
        return True
    except Exception as e:
        print(f"[ERROR] Inject token failed: {e}")
        return False

# ----------------- Login -----------------
def login_if_needed():
    driver.get(LOGIN_URL)
    wait_for_page_load()
    if load_cookies():
        driver.refresh()
        wait_for_page_load()
    try:
        login_input = driver.find_element(By.ID, "login-0")
        password_input = driver.find_element(By.ID, "password-0")
        login_btn = driver.find_element(By.ID, "save-0")
        human_typing(login_input, LOGIN_DATA["login"])
        human_typing(password_input, LOGIN_DATA["password"])
        driver.execute_script("arguments[0].click();", login_btn)
        time.sleep(3)
        if page_contains_captcha_text():
            token = solve_recaptcha()
            if token:
                inject_recaptcha_token_and_submit(token)
        save_cookies()
    except NoSuchElementException:
        print("[INFO] Уже залогинен или поля не найдены.")

# ----------------- Main logic -----------------
async def send_alert(msg: str):
    try:
        await alert_bot.send_message(chat_id=ALERT_CHAT_ID, text=msg)
    except Exception:
        pass

async def make_bid(url: str):
    driver.get(url)
    wait_for_page_load()
    load_cookies()
    try:
        driver.find_element(By.CSS_SELECTOR, "a[href='/profile']")
    except NoSuchElementException:
        login_if_needed()
        driver.get(url)
        wait_for_page_load()

    if page_contains_captcha_text():
        token = solve_recaptcha()
        if token:
            inject_recaptcha_token_and_submit(token)

    try:
        bid_btn = WebDriverWait(driver, 12).until(EC.element_to_be_clickable((By.ID, "add-bid")))
        driver.execute_script("arguments[0].scrollIntoView(true);", bid_btn)
        driver.execute_script("arguments[0].click();", bid_btn)
    except TimeoutException:
        await send_alert(f"⚠️ Кнопка 'Сделать ставку' не найдена: {url}")
        return

    try:
        amount = WebDriverWait(driver, 8).until(EC.presence_of_element_located((By.ID, "amount-0")))
        days = driver.find_element(By.ID, "days_to_deliver-0")
        comment = driver.find_element(By.ID, "comment-0")
        human_typing(amount, "1111")
        human_typing(days, "3")
        human_typing(comment, COMMENT_TEXT, delay_range=(0.02,0.07))
        add_btn = driver.find_element(By.ID, "add-0")
        driver.execute_script("arguments[0].click();", add_btn)
        await send_alert(f"✅ Ставка отправлена: {url}")
    except Exception as e:
        await send_alert(f"❌ Ошибка при заполнении формы: {e}\n{url}")

# ----------------- Telegram -----------------
@client.on(events.NewMessage)
async def handler(event):
    text = (event.message.text or "").lower()
    links = extract_links(text)
    if links and any(k in text for k in KEYWORDS):
        await make_bid(links[0])

# ----------------- Main -----------------
async def main():
    await alert_bot.initialize()
    login_if_needed()
    await client.start()
    await client.run_until_disconnected()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    finally:
        try:
            driver.quit()
        except Exception:
            pass
