#!/usr/bin/env python3
# coding: utf-8

import os, time, random, pickle, asyncio, re
from pathlib import Path
from twocaptcha import TwoCaptcha
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
from webdriver_manager.chrome import ChromeDriverManager
from telethon import TelegramClient, events
from telegram import Bot

API_ID, API_HASH = 21882740, "c80a68894509d01a93f5acfeabfdd922"
ALERT_BOT_TOKEN, ALERT_CHAT_ID = "6566504110:AAFK9hA4jxZ0eA7KZGhVvPe8mL2HZj2tQmE", 1168962519
CAPTCHA_API_KEY = "898059857fb8c709ca5c9613d44ffae4"
HEADLESS = False
LOGIN_URL = "https://freelancehunt.com/ua/profile/login"
LOGIN_DATA = {"login": "Vlari", "password": "Gvadiko_2004"}
COOKIES_FILE = "fh_cookies.pkl"
COMMENT_TEXT = ("Доброго дня! Готовий виконати роботу якісно.\n"
                "Портфоліо робіт у моєму профілі.\n"
                "Заздалегідь дякую!")
KEYWORDS = [k.lower() for k in [
    "#html_и_css_верстка","#веб_программирование","#cms",
    "#интернет_магазины_и_электронная_коммерция","#создание_сайта_под_ключ","#дизайн_сайтов"
]]
url_regex = re.compile(r"https?://[^\s\)\]\}]+", re.IGNORECASE)

alert_bot = Bot(token=ALERT_BOT_TOKEN)
tg_client = TelegramClient("session", API_ID, API_HASH)
solver = None
driver = None

def log(msg: str):
    print(f"[ЛОГ] {msg}")

def make_tmp_profile() -> str:
    tmp = os.path.join("/tmp", f"chrome-temp-{int(time.time())}-{random.randint(0,9999)}")
    Path(tmp).mkdir(parents=True, exist_ok=True)
    return tmp

def create_driver() -> webdriver.Chrome:
    opts = Options()
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--window-size=1366,900")
    if HEADLESS: opts.add_argument("--headless=new")
    opts.add_argument(f"--user-data-dir={make_tmp_profile()}")
    opts.add_experimental_option("excludeSwitches", ["enable-automation"])
    opts.add_experimental_option("useAutomationExtension", False)
    svc = Service(ChromeDriverManager().install())
    d = webdriver.Chrome(service=svc, options=opts)
    d.set_page_load_timeout(60)
    log(f"Chrome готов, HEADLESS={HEADLESS}")
    return d

def wait_body(timeout=20):
    try:
        WebDriverWait(driver, timeout).until(EC.presence_of_element_located((By.TAG_NAME, "body")))
        time.sleep(0.3)
    except TimeoutException:
        log("Таймаут загрузки страницы (wait_body)")

def human_type(el, text, delay=(0.04,0.12)):
    try:
        for ch in text: el.send_keys(ch); time.sleep(random.uniform(*delay))
    except: pass

def human_scroll_and_move():
    try:
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight*0.3);")
        time.sleep(random.uniform(0.15,0.4))
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight*0.6);")
        ActionChains(driver).move_by_offset(random.randint(1,50), random.randint(1,50)).perform()
    except: pass

def save_cookies():
    try:
        with open(COOKIES_FILE, "wb") as f: pickle.dump(driver.get_cookies(), f)
        log("Куки сохранены")
    except: pass

def load_cookies():
    if os.path.exists(COOKIES_FILE):
        try:
            for c in pickle.load(open(COOKIES_FILE,"rb")):
                try: driver.add_cookie(c)
                except: pass
            log("Куки загружены")
        except: pass

def is_logged_in() -> bool:
    try: driver.find_element(By.CSS_SELECTOR, "a[href='/profile']"); return True
    except: return False

def login_if_needed() -> bool:
    driver.get(LOGIN_URL)
    wait_body()
    load_cookies()
    if is_logged_in(): log("Уже авторизован"); return True
    try:
        login_field = WebDriverWait(driver, 6).until(EC.presence_of_element_located((By.NAME, "login")))
        passwd_field = driver.find_element(By.NAME, "password")
        submit_btn = driver.find_element(By.CSS_SELECTOR, "button[type='submit']")
        human_type(login_field, LOGIN_DATA["login"])
        human_type(passwd_field, LOGIN_DATA["password"])
        try: submit_btn.click()
        except: driver.execute_script("arguments[0].click();", submit_btn)
        time.sleep(2); wait_body()
        if is_logged_in(): save_cookies(); log("Авторизация успешна"); return True
        log("Авторизация неуспешна"); return False
    except Exception as e: log(f"Ошибка при логине: {e}"); return False

def init_captcha():
    global solver
    if CAPTCHA_API_KEY:
        try: solver = TwoCaptcha(CAPTCHA_API_KEY); log("Анти-капча инициализирована")
        except Exception as e: solver = None; log(f"Ошибка 2captcha: {e}")

def try_solve_recaptcha():
    if solver is None: return False
    try:
        iframes = driver.find_elements(By.TAG_NAME, "iframe")
        for f in iframes:
            src = f.get_attribute("src") or ""
            if "recaptcha" in src:
                m = re.search(r"sitekey=([A-Za-z0-9_-]+)", src)
                sitekey = m.group(1) if m else None
                if not sitekey:
                    try: sitekey = driver.find_element(By.CSS_SELECTOR, "[data-sitekey]").get_attribute("data-sitekey")
                    except: continue
                res = solver.recaptcha(sitekey=sitekey, url=driver.current_url)
                token = res.get("code") if isinstance(res, dict) else res
                driver.execute_script("""
                (function(token){
                    var el=document.getElementById('g-recaptcha-response');
                    if(!el){el=document.createElement('textarea');el.id='g-recaptcha-response';el.style.display='none';document.body.appendChild(el);}
                    el.innerHTML=token;
                })(arguments[0]);
                """, token)
                try: btn = driver.find_element(By.CSS_SELECTOR, "form button[type='submit'], form input[type='submit']"); driver.execute_script("arguments[0].click();", btn)
                except: pass
                log("Капча решена"); return True
    except: pass
    return False

def extract_links(message):
    found = []
    txt = getattr(message, "text", "") or getattr(message, "message", "")
    if txt: found += url_regex.findall(txt)
    buttons = getattr(message, "buttons", None)
    if buttons:
        for row in buttons:
            for btn in row:
                url = getattr(btn, "url", None)
                if url: found.append(url)
                else: btn_txt = getattr(btn, "text", "") or ""; found += url_regex.findall(btn_txt)
    uniq = []
    for u in found:
        if u not in uniq: uniq.append(u)
    return uniq

async def send_alert(msg: str):
    try: await alert_bot.send_message(chat_id=ALERT_CHAT_ID, text=msg); log(f"TG ALERT: {msg}")
    except: log(f"TG ALERT не отправлено: {msg}")

def page_has_already_bid():
    try: el = driver.find_element(By.CSS_SELECTOR, "div.alert.alert-info"); return True, el.text.strip() if el.text.strip() else ""
    except: return False, ""

async def attempt_bid_on_url(url: str):
    try:
        log(f"Открываю: {url}")
        driver.get(url); wait_body(); try_solve_recaptcha()
        already, text = page_has_already_bid()
        if already: log(f"Ставка уже сделана: {text}"); await send_alert(f"⚠️ Уже сделано: {url}\n{text}"); return False

        clicked = False
        try: btn = WebDriverWait(driver,6).until(EC.element_to_be_clickable((By.ID,"add-bid"))); driver.execute_script("arguments[0].click();", btn); clicked=True
        except:
            for c in driver.find_elements(By.CSS_SELECTOR, "a.btn, button.btn"):
                if "ставк" in (c.text or "").lower() or "сделать" in (c.text or "").lower():
                    try: driver.execute_script("arguments[0].click();", c); clicked=True; break
                    except: continue
        if not clicked: log("Кнопка 'Сделать ставку' не найдена"); return False

        human_scroll_and_move()

        try: amt_el = driver.find_element(By.ID, "amount-0"); amt_el.clear(); human_type(amt_el,"1111")
        except: pass
        try: days_el = driver.find_element(By.ID,"days_to_deliver-0"); days_el.clear(); human_type(days_el,"3")
        except: pass
        try: comment_el = driver.find_element(By.ID,"comment-0"); human_type(comment_el, COMMENT_TEXT, delay=(0.02,0.07))
        except: pass

        submitted=False
        try: submit_btn = driver.find_element(By.ID,"btn-submit-0"); driver.execute_script("arguments[0].click();",submit_btn); submitted=True
        except:
            for c in driver.find_elements(By.CSS_SELECTOR,"button.btn-primary, .btn-primary"):
                txt = (c.text or "").lower()
                if "добав" in txt or "додати" in txt:
                    try: driver.execute_script("arguments[0].click();", c); submitted=True; break
                    except: continue

        if submitted: await send_alert(f"✅ Ставка отправлена: {url}"); save_cookies(); return True
        log("Не удалось нажать кнопку 'Добавить'"); return False
    except Exception as e:
        log(f"Ошибка attempt_bid_on_url: {e}"); await send_alert(f"❌ Ошибка ставки: {e}\n{url}"); return False

@tg_client.on(events.NewMessage)
async def handler_newmsg(event):
    try:
        raw_text = (event.message.text or "").lower() if getattr(event,"message",None) else ""
        if any(k in raw_text for k in KEYWORDS):
            log("Ключевое слово найдено — собираем ссылки")
            links = extract_links(event.message)
            if not links: await send_alert("⚠️ Ключевое слово найдено, но ссылки не обнаружены."); return
            log(f"Найдено ссылок: {len(links)}")
            for u in links:
                ok = await attempt_bid_on_url(u)
                if ok: log(f"Ставка успешно отправлена по ссылке: {u}"); break
    except Exception as e: log(f"handler_newmsg: ошибка: {e}")

async def main():
    global driver
    driver = create_driver()
    init_captcha()
    if not login_if_needed(): log("❌ Не удалось авторизоваться — выходим"); return
    await tg_client.start(); log("Telegram клиент запущен, ожидаю сообщений...")
    await tg_client.run_until_disconnected()

if __name__=="__main__":
    try: asyncio.run(main())
    except KeyboardInterrupt: log("Завершение работы"); driver.quit()
