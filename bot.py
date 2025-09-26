#!/usr/bin/env python3
# coding: utf-8

import os
import re
import time
import random
import pickle
import asyncio
import socket
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

# ---------------- CONFIG ----------------
API_ID = 21882740
API_HASH = "c80a68894509d01a93f5acfeabfdd922"
ALERT_BOT_TOKEN = "6566504110:AAFK9hA4jxZ0eA7KZGhVvPe8mL2HZj2tQmE"
ALERT_CHAT_ID = 1168962519

CAPTCHA_API_KEY = "898059857fb8c709ca5c9613d44ffae4"

HEADLESS = False  # видимый Chrome

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
solver = TwoCaptcha(CAPTCHA_API_KEY)

# ---------------- Helpers ----------------
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
    opts.add_argument("--window-size=1280,900")
    if HEADLESS:
        opts.add_argument("--headless=new")
    opts.add_argument(f"--user-data-dir={tmp_profile}")
    opts.add_experimental_option("excludeSwitches", ["enable-automation"])
    opts.add_experimental_option("useAutomationExtension", False)
    svc = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=svc, options=opts)
    driver.set_page_load_timeout(60)
    print(f"[STEP] Chrome ready. HEADLESS={HEADLESS}. Temp profile: {tmp_profile}")
    return driver

driver = create_chrome_driver()

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
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight * 0.3);")
        time.sleep(random.uniform(0.2, 0.6))
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight * 0.6);")
        time.sleep(random.uniform(0.2, 0.6))
        ActionChains(driver).move_by_offset(random.randint(1,50), random.randint(1,50)).perform()
        time.sleep(0.2)
    except Exception:
        pass

def page_has_captcha_text() -> bool:
    try:
        body = driver.find_element(By.TAG_NAME, "body").text.lower()
        return "captcha" in body or "капча" in body or "protection" in body
    except Exception:
        return False

def find_recaptcha_sitekey() -> Optional[str]:
    try:
        elems = driver.find_elements(By.CSS_SELECTOR, "[data-sitekey]")
        for e in elems:
            sk = e.get_attribute("data-sitekey")
            if sk:
                return sk
    except Exception:
        pass
    return None

def solve_recaptcha(sitekey: str, pageurl: str) -> Optional[str]:
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
        return True
    except Exception as e:
        print("[inject token error]", e)
        return False

# ---------------- Login ----------------
def login_if_needed() -> bool:
    try:
        driver.get("https://freelancehunt.com/")
        wait_for_body()
        load_cookies()
        driver.refresh()
        wait_for_body()
        # Проверка, авторизован ли
        try:
            driver.find_element(By.CSS_SELECTOR, "a[href='/profile']")
            print("[LOGIN] already logged in")
            return True
        except NoSuchElementException:
            driver.get(LOGIN_URL)
            wait_for_body()
            login_input = driver.find_element(By.ID, "login-0")
            pwd_input = driver.find_element(By.ID, "password-0")
            btn = driver.find_element(By.ID, "save-0")
            human_typing(login_input, LOGIN_DATA["login"])
            human_typing(pwd_input, LOGIN_DATA["password"])
            human_scroll_and_move()
            driver.execute_script("arguments[0].click();", btn)
            time.sleep(2)
            wait_for_body()
            if page_has_captcha_text() and find_recaptcha_sitekey():
                token = solve_recaptcha(find_recaptcha_sitekey(), driver.current_url)
                if token:
                    inject_recaptcha_token(token)
            save_cookies()
            return True
    except Exception as e:
        print("[LOGIN ERROR]", e)
        return False

# ---------------- Bidding ----------------
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

        # Всегда логинимся перед открытием проекта
        login_if_needed()
        driver.get(url)
        wait_for_body()

        if page_has_captcha_text() and find_recaptcha_sitekey():
            token = solve_recaptcha(find_recaptcha_sitekey(), driver.current_url)
            if token:
                inject_recaptcha_token(token)

        # Найти и нажать кнопку "Сделать ставку"
        submit_btn = WebDriverWait(driver, 12).until(
            EC.element_to_be_clickable((By.ID, "btn-submit-0"))
        )
        driver.execute_script("arguments[0].scrollIntoView({block:'center'});", submit_btn)
        time.sleep(0.3)

        # Заполняем поля
        amount = WebDriverWait(driver, 8).until(EC.presence_of_element_located((By.ID, "amount-0")))
        days = driver.find_element(By.ID, "days_to_deliver-0")
        comment = driver.find_element(By.ID, "comment-0")

        human_typing(amount, "1111")
        human_typing(days, "3")
        human_typing(comment, COMMENT_TEXT, delay=(0.02, 0.07))
        time.sleep(0.4)

        # Нажимаем кнопку
        driver.execute_script("arguments[0].click();", submit_btn)
        await send_alert(f"✅ Ставка отправлена: {url}")
        save_cookies()
    except Exception as e:
        await send_alert(f"❌ Ошибка: {e}\n{url}")
        print("[ERROR] make_bid:", e)

# ---------------- Telegram ----------------
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
        asyncio.create_task(make_bid(url))

# ---------------- MAIN ----------------
async def main():
    print("[STEP] Starting bot. Pre-check DNS...")
    ensure_dns()
    try:
        await tg_client.start()
    except Exception as e:
        print("[WARN] Telethon start failed:", e)
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
