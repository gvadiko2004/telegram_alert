#!/usr/bin/env python3
# coding: utf-8
"""
Telegram+Selenium bot for Freelancehunt:
- uses one persistent Chrome profile (extensions + API keys are stored there)
- tries extension first (assumes Anti-Captcha extension is installed in profile)
- fallback: uses 2captcha API when reCAPTCHA v2 is detected
- keeps browser open for the whole bot lifetime
"""

import os
import pickle
import re
import time
import random
import asyncio
import requests

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException

from webdriver_manager.chrome import ChromeDriverManager
from telethon import TelegramClient, events
from telegram import Bot

# ---------------- CONFIG (заполни свои данные) ----------------
# Telegram (оставь свои значения)
API_ID = 21882740
API_HASH = "c80a68894509d01a93f5acfeabfdd922"
ALERT_BOT_TOKEN = "6566504110:AAFK9hA4jxZ0eA7KZGhVvPe8mL2HZj2tQmE"
ALERT_CHAT_ID = 1168962519

# 2captcha: запасной план (если расширение не помогло)
CAPTCHA_API_KEY = "898059857fb8c709ca5c9613d44ffae4"   # <-- здесь твой 2captcha ключ

# Профиль/кеш Chrome — туда устанавливается расширение и хранится ключ
# Если у тебя локально профиль из MobaXterm, распакуй его в этот путь на VPS.
CHROME_PROFILE_DIR = "/root/chrome-profile"  # <-- при переносе профиля укажи реальный путь

# Если True — браузер запускается в headless (на VPS без X11). Для ручной установки расширения установи False.
HEADLESS = False

# Сайт / логин
LOGIN_URL = "https://freelancehunt.com/ua/profile/login"
LOGIN_DATA = {"login": "Vlari", "password": "Gvadiko_2004"}

# Cookies файл
COOKIES_FILE = "fh_cookies.pkl"

# Ключевые слова для триггера
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
# ----------------------------------------------------------------

# Telegram objects
alert_bot = Bot(token=ALERT_BOT_TOKEN)
tg_client = TelegramClient("session", API_ID, API_HASH)

# ---------------- Selenium driver (один на весь бот) ----------------
def create_chrome_driver():
    opts = Options()
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--disable-gpu")
    opts.add_argument("--window-size=1366,900")
    if HEADLESS:
        opts.add_argument("--headless=new")
    # use persistent profile so extension + API key remain between runs
    opts.add_argument(f"--user-data-dir={CHROME_PROFILE_DIR}")
    # stealth-ish options
    opts.add_experimental_option("excludeSwitches", ["enable-automation"])
    opts.add_experimental_option("useAutomationExtension", False)
    # don't block images (default)
    driver_path = ChromeDriverManager().install()
    svc = Service(driver_path)
    driver = webdriver.Chrome(service=svc, options=opts)
    driver.set_page_load_timeout(60)
    return driver

# Try to create driver; if the profile is locked/in-use, fallback to a temp profile
try:
    driver = create_chrome_driver()
except Exception as e:
    print(f"[WARNING] Не удалось открыть профиль {CHROME_PROFILE_DIR}: {e}")
    # fallback: use temporary profile to let bot run (but extension won't be present)
    tmp_profile = os.path.join("/tmp", f"chrome-temp-{int(time.time())}")
    os.makedirs(tmp_profile, exist_ok=True)
    CHROME_PROFILE_DIR_TMP = tmp_profile
    print(f"[INFO] Буду использовать временный профиль: {CHROME_PROFILE_DIR_TMP}")
    # recreate driver with tmp profile
    def create_tmp_driver():
        opts = Options()
        opts.add_argument("--no-sandbox")
        opts.add_argument("--disable-dev-shm-usage")
        opts.add_argument("--disable-gpu")
        opts.add_argument("--window-size=1366,900")
        if HEADLESS:
            opts.add_argument("--headless=new")
        opts.add_argument(f"--user-data-dir={CHROME_PROFILE_DIR_TMP}")
        opts.add_experimental_option("excludeSwitches", ["enable-automation"])
        opts.add_experimental_option("useAutomationExtension", False)
        svc = Service(ChromeDriverManager().install())
        d = webdriver.Chrome(service=svc, options=opts)
        d.set_page_load_timeout(60)
        return d
    driver = create_tmp_driver()

print(f"[STEP] Chrome ready. HEADLESS={HEADLESS}. Profile: {CHROME_PROFILE_DIR}")

# ---------------- Utilities ----------------
def wait_for_body(timeout=20):
    try:
        WebDriverWait(driver, timeout).until(EC.presence_of_element_located((By.TAG_NAME, "body")))
        time.sleep(0.6)
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

def human_scroll_and_move():
    # simple human-like scrolls and tiny mouse move
    try:
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight * 0.3);")
        time.sleep(random.uniform(0.2, 0.6))
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight * 0.6);")
        time.sleep(random.uniform(0.2, 0.6))
        # move mouse a bit using ActionChains
        a = ActionChains(driver)
        a.move_by_offset(random.randint(1,50), random.randint(1,50)).perform()
        time.sleep(0.2)
        # move back to (0,0) - selenium's move_by_offset is relative and might fail depending on platform,
        # in many environments this is best-effort.
    except Exception:
        pass

def page_has_captcha_text():
    try:
        body = driver.find_element(By.TAG_NAME, "body").text.lower()
        if "captcha" in body or "капча" in body or "protection" in body:
            return True
    except Exception:
        pass
    return False

# ---------------- 2captcha helpers (reCAPTCHA v2) ----------------
def find_recaptcha_sitekey():
    # try data-sitekey
    try:
        elems = driver.find_elements(By.CSS_SELECTOR, "[data-sitekey]")
        for e in elems:
            sk = e.get_attribute("data-sitekey")
            if sk:
                return sk
    except Exception:
        pass
    # try iframes src
    try:
        iframes = driver.find_elements(By.TAG_NAME, "iframe")
        for f in iframes:
            src = f.get_attribute("src") or ""
            if "sitekey=" in src:
                m = re.search(r"sitekey=([a-zA-Z0-9_-]+)", src)
                if m:
                    return m.group(1)
    except Exception:
        pass
    return None

def submit_2captcha(sitekey, pageurl, poll=5, timeout=180):
    # uses 2captcha API (simple polling). Returns token or None.
    try:
        in_url = "http://2captcha.com/in.php"
        res_url = "http://2captcha.com/res.php"
        payload = {
            "key": CAPTCHA_API_KEY,
            "method": "userrecaptcha",
            "googlekey": sitekey,
            "pageurl": pageurl,
            "json": 1
        }
        r = requests.post(in_url, data=payload, timeout=30).json()
        if r.get("status") != 1:
            print(f"[2CAPTCHA ERROR] in.php: {r}")
            return None
        task_id = r.get("request")
        waited = 0
        print(f"[2CAPTCHA] task {task_id} created")
        while waited < timeout:
            time.sleep(poll)
            waited += poll
            r2 = requests.get(res_url, params={"key": CAPTCHA_API_KEY, "action": "get", "id": task_id, "json": 1}, timeout=30).json()
            if r2.get("status") == 1:
                print("[2CAPTCHA] got token")
                return r2.get("request")
            elif r2.get("request") == "CAPCHA_NOT_READY":
                continue
            else:
                print(f"[2CAPTCHA ERROR] {r2}")
                return None
        print("[2CAPTCHA] timeout")
        return None
    except Exception as e:
        print(f"[2CAPTCHA EX] {e}")
        return None

def inject_recaptcha_token(token):
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
        time.sleep(0.8)
        # try submit any nearby form submit
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
        print(f"[inject token error] {e}")
        return False

# ---------------- Login flow ----------------
def login_if_needed():
    # go to login page, try to find login fields and enter credentials
    driver.get(LOGIN_URL)
    wait_for_body()
    # try cookies preloaded
    load_cookies()
    time.sleep(0.6)
    try:
        login_input = driver.find_element(By.ID, "login-0")
        pwd_input = driver.find_element(By.ID, "password-0")
        btn = driver.find_element(By.ID, "save-0")
        human_typing(login_input, LOGIN_DATA["login"])
        human_typing(pwd_input, LOGIN_DATA["password"])
        human_scroll_and_move()
        driver.execute_script("arguments[0].click();", btn)
        time.sleep(2)
        wait_for_body()
        # if captcha present, try extension (extension normally catches and solves). If not, fallback to 2captcha
        if page_has_captcha_text() or find_recaptcha_sitekey():
            print("[WARN] captcha detected after login attempt")
            sitekey = find_recaptcha_sitekey()
            if sitekey and CAPTCHA_API_KEY:
                token = submit_2captcha(sitekey, driver.current_url)
                if token:
                    inject_recaptcha_token(token)
        save_cookies()
        return True
    except NoSuchElementException:
        # fields not found -> likely already logged in
        return True
    except Exception as e:
        print(f"[login_if_needed error] {e}")
        return False

# ---------------- Main job: place bid ----------------
async def send_alert(msg):
    try:
        await alert_bot.send_message(chat_id=ALERT_CHAT_ID, text=msg)
        print("[TG] " + msg)
    except Exception as e:
        print("[TGERROR] " + str(e))

async def make_bid(url):
    print(f"[JOB] processing: {url}")
    try:
        # load page
        driver.get(url)
        wait_for_body()
        # load cookies (if exist) to keep session
        load_cookies()
        time.sleep(0.5)
        # check login by presence of profile link
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

        # if captcha on page - try extension (automatic) else fallback to 2captcha
        if page_has_captcha_text() or find_recaptcha_sitekey():
            print("[INFO] captcha detected on project page")
            # allow some time for extension to solve (if extension present in profile it usually auto-solves)
            time.sleep(5)
            # check again
            if page_has_captcha_text() or find_recaptcha_sitekey():
                sk = find_recaptcha_sitekey()
                if sk and CAPTCHA_API_KEY:
                    token = submit_2captcha(sk, driver.current_url)
                    if token:
                        inject_recaptcha_token(token)
                else:
                    await send_alert(f"⚠️ Captcha on {url} — manual intervention may be required.")
                    return

        # find and click "Сделать ставку" (wait clickable)
        try:
            bid_btn = WebDriverWait(driver, 12).until(EC.element_to_be_clickable((By.ID, "add-bid")))
            driver.execute_script("arguments[0].scrollIntoView(true);", bid_btn)
            time.sleep(0.2)
            human_scroll_and_move()
            driver.execute_script("arguments[0].click();", bid_btn)
            time.sleep(0.8)
        except TimeoutException:
            await send_alert(f"⚠️ Кнопка 'Сделать ставку' не найдена: {url}")
            return

        # fill form
        try:
            amount = WebDriverWait(driver, 8).until(EC.presence_of_element_located((By.ID, "amount-0")))
            days = driver.find_element(By.ID, "days_to_deliver-0")
            comment = driver.find_element(By.ID, "comment-0")

            human_typing(amount, "1111")
            human_typing(days, "3")
            human_typing(comment, COMMENT_TEXT, delay=(0.02,0.07))
            time.sleep(0.3)
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
def extract_links(text):
    return [ln for ln in re.findall(r"https?://[^\s]+", text) if "freelancehunt.com" in ln]

@tg_client.on(events.NewMessage)
async def on_msg(event):
    text = (event.message.text or "").lower()
    links = extract_links(text)
    if links and any(k in text for k in KEYWORDS):
        url = links[0]
        print("[TG] got link:", url)
        await make_bid(url)

# ---------------- Main ----------------
async def main():
    print("[STEP] Starting bot. Chrome profile:", CHROME_PROFILE_DIR)
    # pre-load cookies if exist (open domain to allow adding cookies)
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
        # optional initial login: uncomment if you want login at start
        # login_if_needed()
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Exiting by user")
    finally:
        try:
            driver.quit()
        except Exception:
            pass
