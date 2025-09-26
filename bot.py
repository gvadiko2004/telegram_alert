#!/usr/bin/env python3
"""
Telegram+Selenium bot:
- requests rotating/residential proxy from 2captcha Proxy API
- launches Chrome with that proxy
- if proxy has credentials user:pass@host:port -> tries to add Proxy-Authorization via CDP
- solves reCAPTCHA via official twocaptcha client
- logs into freelancehunt and places a bid
- notifies via Telegram bot
"""

import os
import pickle
import re
import time
import random
import base64
import json
import traceback
import asyncio
from functools import partial

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

# ======================
# === CONFIG SECTION ===
# ======================

# Telegram (already from your data)
TELEGRAM_API_ID = 21882740
TELEGRAM_API_HASH = "c80a68894509d01a93f5acfeabfdd922"
ALERT_BOT_TOKEN = "6566504110:AAFK9hA4jxZ0eA7KZGhVvPe8mL2HZj2tQmE"
ALERT_CHAT_ID = 1168962519
alert_bot = Bot(token=ALERT_BOT_TOKEN)

# Freelancehunt login
FH_LOGIN = "Vlari"
FH_PASSWORD = "Gvadiko_2004"
LOGIN_URL = "https://freelancehunt.com/ua/profile/login"
LOGIN_BUTTON_SELECTOR = "a.inline-block.link-no-underline"

# 2Captcha (solver) API key (from you)
CAPTCHA_API_KEY = "898059857fb8c709ca5c9613d44ffae4"
solver = TwoCaptcha(CAPTCHA_API_KEY)

# 2Captcha Proxy API key (same key is used for proxies)
PROXY_API_KEY = CAPTCHA_API_KEY
PROXY_API_ENDPOINT = "https://api.2captcha.com/proxy"

# Save cookies locally
COOKIES_FILE = "fh_cookies.pkl"

# Bot behaviour
VISIBLE = True        # True -> visible Chrome (requires X11); False -> headless
KEYWORDS = [
    "#html_и_css_верстка",
    "#веб_программирование",
    "#cms",
    "#интернет_магазины_и_электронная_коммерция",
    "#создание_сайта_под_ключ",
    "#дизайн_сайтов"
]
KEYWORDS = [k.lower() for k in KEYWORDS]

COMMENT_TEXT = """Доброго дня! Готовий виконати роботу якісно.
Портфоліо робіт у моєму профілі.
Заздалегідь дякую!
"""

# ======================
# ==== Utilities =======
# ======================

def sync_send_alert(text: str):
    try:
        alert_bot.send_message(chat_id=ALERT_CHAT_ID, text=text)
        print("[ALERT] sent:", text[:200])
    except Exception as e:
        print("[ALERT ERR]", e)

async def send_alert(text: str):
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, partial(sync_send_alert, text))

def human_typing(element, text, min_delay=0.04, max_delay=0.16):
    for ch in text:
        element.send_keys(ch)
        time.sleep(random.uniform(min_delay, max_delay))

def extract_links(text: str):
    return [link for link in re.findall(r"https?://[^\s]+", text) if "freelancehunt.com" in link]

# ======================
# === 2Captcha Proxy ===
# ======================

def request_2captcha_proxy():
    """
    Request proxy info from 2captcha proxy endpoint.
    Returns dict with proxy info or None.
    We attempt to parse common response shapes.
    """
    try:
        url = f"{PROXY_API_ENDPOINT}?key={PROXY_API_KEY}"
        print("[PROXY] Requesting proxy from", url)
        r = requests.get(url, timeout=30)
        r.raise_for_status()
        data = r.json() if r.text else {}
        print("[PROXY] Raw response:", data if isinstance(data, dict) else r.text[:500])
    except Exception as e:
        print("[PROXY] Request failed:", e)
        return None

    # Try to parse common shapes
    # Example from docs: {"status": "OK", "data": {"username": "u2135p...", ...}}
    if isinstance(data, dict):
        if data.get("status") and data.get("data"):
            d = data["data"]
            # if d contains 'proxy' or 'proxies' use that
            if isinstance(d, dict):
                if "proxy" in d:
                    return {"proxy": d["proxy"], **d}
                # some APIs return username + host + port
                if "username" in d and "port" in d and "host" in d:
                    up = f"{d.get('username')}:{d.get('password','')}@{d.get('host')}:{d.get('port')}"
                    return {"proxy": up, **d}
                # sometimes username is actually whole user:pass@host:port in username
                if "username" in d and isinstance(d.get("username"), str) and "@" in d.get("username"):
                    return {"proxy": d["username"], **d}
            # if data contains list of proxies
            if isinstance(data.get("data"), list) and data["data"]:
                return {"proxy": data["data"][0], "raw": data}
        # fallback: if response is {"proxy":"host:port"}:
        if "proxy" in data:
            return {"proxy": data["proxy"]}
    # if response is plain string like "user:pass@host:port" or "host:port"
    txt = r.text.strip() if 'r' in locals() else ""
    if txt and (":" in txt):
        return {"proxy": txt}
    print("[PROXY] Could not parse proxy response.")
    return None

# ======================
# === Selenium setup ===
# ======================

def create_driver_with_proxy(proxy_str=None, visible=True):
    opts = Options()
    if not visible:
        opts.add_argument("--headless=new")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--window-size=1920,1080")
    opts.add_argument("--disable-gpu")
    # prevent webdriver detection a bit
    opts.add_experimental_option("excludeSwitches", ["enable-automation"])
    opts.add_experimental_option('useAutomationExtension', False)

    if proxy_str:
        # proxy_str can be host:port or user:pass@host:port
        if "@" in proxy_str:
            hostport = proxy_str.split("@",1)[1]
            opts.add_argument(f"--proxy-server=http://{hostport}")
        else:
            opts.add_argument(f"--proxy-server=http://{proxy_str}")

    print("[STEP] Launching Chrome (visible=%s) with proxy=%s" % (visible, proxy_str))
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=opts)

    # Try to set Proxy-Authorization header via CDP if credentials present
    if proxy_str and "@" in proxy_str:
        try:
            auth = proxy_str.split("@",1)[0]  # user:pass
            b64 = base64.b64encode(auth.encode()).decode()
            # Enable Network and set header
            driver.execute_cdp_cmd("Network.enable", {})
            driver.execute_cdp_cmd("Network.setExtraHTTPHeaders", {"headers": {"Proxy-Authorization": "Basic " + b64}})
            print("[STEP] Set Proxy-Authorization header via CDP (Basic).")
        except Exception as e:
            print("[WARN] Could not set Proxy-Authorization via CDP:", e)
    # Minor anti-detect tweaks
    try:
        driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
    except Exception:
        pass

    return driver

# ======================
# === Cookie helpers ===
# ======================

def save_cookies(driver):
    try:
        with open(COOKIES_FILE, "wb") as f:
            pickle.dump(driver.get_cookies(), f)
        print("[STEP] Cookies saved.")
    except Exception as e:
        print("[WARN] Save cookies failed:", e)

def load_cookies_if_exists(driver):
    if not os.path.exists(COOKIES_FILE):
        return False
    try:
        with open(COOKIES_FILE, "rb") as f:
            cookies = pickle.load(f)
        for c in cookies:
            # remove SameSite if present (selenium compatibility)
            c.pop("sameSite", None)
            try:
                driver.add_cookie(c)
            except Exception:
                pass
        print("[STEP] Cookies loaded into browser.")
        return True
    except Exception as e:
        print("[WARN] Load cookies failed:", e)
        return False

def wait_for_ready(driver, timeout=20):
    try:
        WebDriverWait(driver, timeout).until(lambda d: d.execute_script("return document.readyState") == "complete")
        time.sleep(1.0)
        return True
    except TimeoutException:
        return False

# ======================
# === CAPTCHA solver ===
# ======================

def find_recaptcha_sitekey(driver):
    # try common selectors
    try:
        el = driver.find_element(By.CSS_SELECTOR, "div.g-recaptcha, div[data-sitekey]")
        sk = el.get_attribute("data-sitekey") or el.get_attribute("sitekey")
        if sk:
            return sk
    except Exception:
        pass
    # try iframes src
    try:
        iframes = driver.find_elements(By.CSS_SELECTOR, "iframe[src*='recaptcha']")
        for iframe in iframes:
            src = iframe.get_attribute("src") or ""
            m = re.search(r"k=([^&]+)", src)
            if m:
                return m.group(1)
    except Exception:
        pass
    return None

def solve_recaptcha(driver):
    sk = find_recaptcha_sitekey(driver)
    if not sk:
        raise Exception("sitekey not found")
    page = driver.current_url
    print("[CAPTCHA] sitekey:", sk, "page:", page)
    print("[CAPTCHA] sending to 2captcha...")
    res = solver.recaptcha(sitekey=sk, url=page)
    token = res.get("code") or res.get("captchaSolve") or res.get("request")
    if not token:
        raise Exception("no token from solver: " + str(res))
    print("[CAPTCHA] got token (len=%d)" % (len(token)))
    # inject token to g-recaptcha-response
    inject_js = """
    (function(token){
      var el = document.getElementById('g-recaptcha-response');
      if(!el){
        el = document.createElement('textarea');
        el.id = 'g-recaptcha-response';
        el.name = 'g-recaptcha-response';
        el.style.display = 'none';
        document.body.appendChild(el);
      }
      el.value = token;
      el.innerHTML = token;
      var ev = document.createEvent('HTMLEvents');
      ev.initEvent('change', true, true);
      el.dispatchEvent(ev);
    })(arguments[0]);
    """
    driver.execute_script(inject_js, token)
    time.sleep(1.0)
    return token

# ======================
# === Main workflow ===
# ======================

def perform_make_bid_sync(project_url: str):
    """
    Full synchronous worker that:
      - requests proxy
      - starts driver (with proxy)
      - navigates, logs in (solving captcha if needed), makes bid
    """
    driver = None
    proxy_info = None
    try:
        # 1) Request a proxy from 2captcha
        proxy_info = request_2captcha_proxy()
        proxy_str = proxy_info.get("proxy") if proxy_info else None
        print("[PROXY] Using proxy:", proxy_str)

        # 2) Start Chrome with proxy
        driver = create_driver_with_proxy(proxy_str, visible=VISIBLE)
        wait_for_ready(driver, timeout=20)

        # 3) Open project page
        print("[STEP] Opening project page:", project_url)
        driver.get(project_url)
        wait_for_ready(driver, timeout=20)
        time.sleep(1.0)

        # 4) Load cookies if we have them (first page load needed to set domain)
        if os.path.exists(COOKIES_FILE):
            try:
                load_cookies_if_exists(driver)
                driver.get(project_url)
                wait_for_ready(driver)
                print("[STEP] Re-opened after loading cookies.")
            except Exception as e:
                print("[WARN] cookie reload problem:", e)

        # 5) Check login status
        logged = False
        try:
            driver.find_element(By.CSS_SELECTOR, "a[href='/profile']")
            logged = True
            print("[INFO] Already logged in (profile link found).")
        except NoSuchElementException:
            logged = False
            print("[INFO] Not logged in.")

        # 6) If not logged -> login flow
        if not logged:
            # click Вхід if exists
            try:
                btn = driver.find_element(By.CSS_SELECTOR, LOGIN_BUTTON_SELECTOR)
                driver.execute_script("arguments[0].click();", btn)
                print("[STEP] clicked 'Вхід' link.")
                time.sleep(1.0)
            except Exception:
                pass
            # navigate to login page explicitly
            driver.get(LOGIN_URL)
            wait_for_ready(driver)

            # solve captcha on login page if present
            if driver.find_elements(By.CSS_SELECTOR, "iframe[src*='recaptcha']") or "captcha" in driver.page_source.lower():
                print("[INFO] Captcha on login page detected -> solving")
                try:
                    solve_recaptcha(driver)
                    print("[INFO] login-captcha solved")
                except Exception as e:
                    print("[ERROR] login-captcha solve failed:", e)
                    raise

            # fill credentials
            try:
                login_input = WebDriverWait(driver, 8).until(EC.presence_of_element_located((By.ID, "login-0")))
                password_input = driver.find_element(By.ID, "password-0")
                submit_btn = driver.find_element(By.ID, "save-0")
                human_typing(login_input, FH_LOGIN)
                time.sleep(0.4)
                human_typing(password_input, FH_PASSWORD)
                time.sleep(0.4)
                driver.execute_script("arguments[0].click();", submit_btn)
                print("[STEP] clicked login submit")
                time.sleep(3.0)
                wait_for_ready(driver)
            except Exception as e:
                print("[ERROR] login inputs not found or failed:", e)
                raise

            # after click, if captcha appears again - solve
            if driver.find_elements(By.CSS_SELECTOR, "iframe[src*='recaptcha']") or "captcha" in driver.page_source.lower():
                print("[INFO] Captcha after submit -> solving")
                solve_recaptcha(driver)
                time.sleep(2.0)
                wait_for_ready(driver)

            # final login check
            try:
                driver.find_element(By.CSS_SELECTOR, "a[href='/profile']")
                print("[INFO] Login appears successful.")
                save_cookies(driver)
            except Exception:
                raise Exception("Login failed - profile link not found after login")

        # 7) Back to project page (ensure fresh)
        driver.get(project_url)
        wait_for_ready(driver)
        time.sleep(0.8)

        # 8) If captcha on project page -> solve
        if driver.find_elements(By.CSS_SELECTOR, "iframe[src*='recaptcha']") or "captcha" in driver.page_source.lower():
            print("[INFO] Captcha on project page -> solving")
            solve_recaptcha(driver)
            time.sleep(1.0)
            wait_for_ready(driver)

        # 9) Find 'add-bid' button and click
        try:
            bid_btn = WebDriverWait(driver, 10).until(EC.element_to_be_clickable((By.ID, "add-bid")))
            driver.execute_script("arguments[0].scrollIntoView(true);", bid_btn)
            time.sleep(0.4)
            bid_btn.click()
            print("[STEP] Clicked add-bid.")
        except TimeoutException:
            # fallback find by button text
            try:
                el = driver.find_element(By.XPATH, "//button[contains(text(),'Сделать ставку') or contains(text(),'Зробити ставку') or contains(text(),'Відправити') or contains(text(),'Надіслати')]")
                driver.execute_script("arguments[0].click();", el)
                print("[STEP] Clicked alternative bid button.")
            except Exception as e:
                raise Exception("Bid button not found: " + str(e))

        time.sleep(1.0)
        # 10) Fill form
        try:
            amount = driver.find_element(By.ID, "amount-0")
            days = driver.find_element(By.ID, "days_to_deliver-0")
            comment = driver.find_element(By.ID, "comment-0")
            human_typing(amount, "1111")
            time.sleep(0.2)
            human_typing(days, "3")
            time.sleep(0.2)
            human_typing(comment, COMMENT_TEXT, min_delay=0.01, max_delay=0.06)
            time.sleep(0.3)
            add_btn = driver.find_element(By.ID, "add-0")
            driver.execute_script("arguments[0].click();", add_btn)
            print("[SUCCESS] Bid submitted")
            sync_send_alert = sync_send_alert if False else None  # noop so linter ok
            # send async alert via blocking wrapper
            sync_send_alert = lambda t: alert_bot.send_message(chat_id=ALERT_CHAT_ID, text=t)
            try:
                sync_send_alert(f"✅ Ставка отправлена: {project_url}")
            except Exception:
                print("[WARN] Could not send success alert")
        except Exception as e:
            raise Exception("Filling bid form failed: " + str(e))

    except Exception as e:
        tb = traceback.format_exc()
        print("[FATAL] Worker error:", e)
        print(tb)
        try:
            alert_bot.send_message(chat_id=ALERT_CHAT_ID, text=f"❌ Ошибка при обработке {project_url}: {e}\n{tb[:800]}")
        except Exception:
            pass
    finally:
        if driver:
            try:
                driver.quit()
            except Exception:
                pass
        print("[STEP] Worker finished (driver closed).")

# ======================
# ==== Telethon loop ===
# ======================

client = TelegramClient("session", TELEGRAM_API_ID, TELEGRAM_API_HASH)

@client.on(events.NewMessage)
async def handler(event):
    text = (event.message.message or "").lower()
    links = extract_links(text)
    if not links:
        return
    if any(k in text for k in KEYWORDS):
        project = links[0]
        print("[INFO] Received project:", project)
        # run blocking worker in background to not block telethon
        await asyncio.to_thread(perform_make_bid_sync, project)
        print("[INFO] Worker done for:", project)

async def main():
    print("[INFO] Starting bot...")
    await client.start()
    print("[INFO] Telegram client started.")
    await client.run_until_disconnected()

if __name__ == "__main__":
    asyncio.run(main())
