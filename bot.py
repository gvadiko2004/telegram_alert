#!/usr/bin/env python3
# coding: utf-8

import os, time, random, pickle, asyncio, socket, re
from pathlib import Path
from twocaptcha import TwoCaptcha
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from webdriver_manager.chrome import ChromeDriverManager
from telethon import TelegramClient, events
from telegram import Bot

# -------- CONFIG --------
API_ID, API_HASH = 21882740, "c80a68894509d01a93f5acfeabfdd922"
ALERT_BOT_TOKEN, ALERT_CHAT_ID = "6566504110:AAFK9hA4jxZ0eA7KZGhVvPe8mL2HZj2tQmE", 1168962519
CAPTCHA_API_KEY = "898059857fb8c709ca5c9613d44ffae4"
HEADLESS = False
LOGIN_URL = "https://freelancehunt.com/ua/profile/login"
LOGIN_DATA = {"login": "Vlari", "password": "Gvadiko_2004"}
COOKIES_FILE = "fh_cookies.pkl"
COMMENT_TEXT = ("Доброго дня! Готовий виконати роботу якісно.\n"
                "Портфоліо робіт у моєму профілі.\nЗаздалегідь дякую!")
KEYWORDS = [k.lower() for k in [
    "#html_и_css_верстка","#веб_программирование","#cms",
    "#интернет_магазины_и_электронная_коммерция","#создание_сайта_под_ключ","#дизайн_сайтов"
]]

# -------- INIT --------
alert_bot = Bot(token=ALERT_BOT_TOKEN)
tg_client = TelegramClient("session", API_ID, API_HASH)
solver = None

# -------- UTILS --------
def log(msg): print(f"[ЛОГ] {msg}")

def ensure_dns(host="freelancehunt.com"):
    try:
        ip = socket.gethostbyname(host)
        log(f"DNS OK: {host} -> {ip}")
        return True
    except: log(f"DNS НЕУДАЛОСЬ: {host}"); return False

def tmp_profile():
    tmp = f"/tmp/chrome-{int(time.time())}-{random.randint(0,9999)}"
    Path(tmp).mkdir(parents=True, exist_ok=True)
    return tmp

def driver_create():
    opts = Options()
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--window-size=1280,900")
    if HEADLESS: opts.add_argument("--headless=new")
    opts.add_argument(f"--user-data-dir={tmp_profile()}")
    opts.add_experimental_option("excludeSwitches", ["enable-automation"])
    opts.add_experimental_option("useAutomationExtension", False)
    drv = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=opts)
    drv.set_page_load_timeout(60)
    log(f"Chrome готов, HEADLESS={HEADLESS}")
    return drv

driver = driver_create()

def wait_body(timeout=20):
    try: WebDriverWait(driver, timeout).until(EC.presence_of_element_located((By.TAG_NAME,"body"))); time.sleep(0.3)
    except: pass

def human_type(el, txt, delay=(0.04,0.12)):
    for ch in txt: el.send_keys(ch); time.sleep(random.uniform(*delay))

def human_scroll():
    try:
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight*0.3);")
        time.sleep(random.uniform(0.2,0.4))
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight*0.6);")
        ActionChains(driver).move_by_offset(random.randint(1,50), random.randint(1,50)).perform()
    except: pass

def save_cookies():
    try:
        with open(COOKIES_FILE,"wb") as f: pickle.dump(driver.get_cookies(),f)
    except: pass

def load_cookies():
    if not os.path.exists(COOKIES_FILE): return False
    try:
        with open(COOKIES_FILE,"rb") as f:
            for c in pickle.load(f):
                try: driver.add_cookie(c)
                except: pass
    except: return False
    return True

def logged_in():
    try: driver.find_element(By.CSS_SELECTOR,"a[href='/profile']"); return True
    except: return False

def login():
    driver.get(LOGIN_URL)
    wait_body()
    load_cookies()
    if logged_in(): return True
    try:
        login_field = WebDriverWait(driver,10).until(EC.presence_of_element_located((By.NAME,"login")))
        pass_field = driver.find_element(By.NAME,"password")
        login_field.send_keys(LOGIN_DATA["login"])
        pass_field.send_keys(LOGIN_DATA["password"])
        driver.find_element(By.CSS_SELECTOR,"button[type='submit']").click()
        WebDriverWait(driver,5).until(lambda d: logged_in())
        save_cookies()
        log("Авторизация успешна")
        return True
    except: log("Не удалось авторизоваться"); return False

# -------- CAPTCHA --------
def init_captcha():
    global solver
    if CAPTCHA_API_KEY:
        solver = TwoCaptcha(CAPTCHA_API_KEY)
        log("Анти-капча инициализирована и готова к работе")
    else: solver = None; log("Ключ API не задан, капча отключена")

def solve_captcha():
    if not solver: return False
    try:
        for f in driver.find_elements(By.TAG_NAME,"iframe"):
            src = f.get_attribute("src") or ""
            if "recaptcha" in src:
                sitekey = re.search(r"sitekey=([a-zA-Z0-9_-]+)",src)
                if not sitekey: return False
                sitekey = sitekey.group(1)
                result = solver.recaptcha(sitekey=sitekey, url=driver.current_url)
                code = result.get("code")
                driver.execute_script(f'document.getElementById("g-recaptcha-response").innerHTML="{code}";')
                driver.execute_script('___grecaptcha_cfg.clients[0].R.R.callback(arguments[0]);',code)
                log("Капча решена")
                return True
        log("Капча на странице не найдена")
        return False
    except: return False

async def send_alert(msg):
    try: await alert_bot.send_message(chat_id=ALERT_CHAT_ID,text=msg); log(f"TG ALERT: {msg}")
    except: pass

# -------- BID --------
async def make_bid(url):
    try:
        if not ensure_dns(): await send_alert(f"DNS не удалось {url}"); return
        driver.get(url)
        wait_body()
        load_cookies()
        if not logged_in(): login(); driver.get(url); wait_body()
        solve_captcha()

        # --- Проверка "ставка уже сделана" ---
        try:
            alert_el = driver.find_element(By.CSS_SELECTOR,"div.alert.alert-info")
            if alert_el:
                log(f"Ставка уже сделана или закрыта: {alert_el.text}")
                await send_alert(f"⚠️ Ставка уже сделана или закрыта: {url}")
                return
        except: pass

        # --- Клик "Сделать ставку" ---
        try: WebDriverWait(driver,5).until(EC.element_to_be_clickable((By.ID,"add-bid"))).click(); time.sleep(0.5); human_scroll()
        except: pass

        # --- Определяем сумму ---
        try: span = driver.find_element(By.CSS_SELECTOR,"span.text-green.bold.pull-right.price"); amount = re.sub(r"[^\d\.]","",span.text)
        except: amount = "1111"

        # --- Заполняем форму ---
        try: human_type(driver.find_element(By.ID,"amount-0"),amount)
        except: pass
        try: human_type(driver.find_element(By.ID,"days_to_deliver-0"),"3")
        except: pass
        try: human_type(driver.find_element(By.ID,"comment-0"),COMMENT_TEXT,(0.02,0.07))
        except: pass
        time.sleep(0.4)

        # --- Финальный клик "Добавить" ---
        try: driver.find_element(By.ID,"btn-submit-0").click()
        except: pass

        await send_alert(f"✅ Ставка отправлена: {url}")
        save_cookies()
    except: pass

# -------- TELEGRAM --------
def extract_links(msg):
    links = []
    # текст
    for word in (msg.text or "").split():
        if "freelancehunt.com" in word: links.append(word)
    # кнопки inline
    try:
        for row in getattr(msg,"buttons",[]) or []:
            for btn in row:
                url = getattr(btn,"url",None)
                if url and "freelancehunt.com" in url: links.append(url)
    except: pass
    return list(set(links))

@tg_client.on(events.NewMessage)
async def on_msg(event):
    txt = (event.message.text or "").lower()
    links = extract_links(event.message)
    if links and any(k in txt for k in KEYWORDS):
        asyncio.create_task(make_bid(links[0]))

# -------- MAIN --------
async def main():
    ensure_dns()
    init_captcha()
    if os.path.exists(COOKIES_FILE):
        driver.get("https://freelancehunt.com")
        wait_body()
        load_cookies()
        driver.refresh()
        wait_body()
    await tg_client.start()
    log("Telegram клиент запущен")
    await tg_client.run_until_disconnected()

if __name__=="__main__":
    try: asyncio.run(main())
    except KeyboardInterrupt: log("Завершение работы"); driver.quit()
