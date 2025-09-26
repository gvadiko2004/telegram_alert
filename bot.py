#!/usr/bin/env python3
# coding: utf-8

import os
import pickle
import re
import time
import random
import asyncio
import json
import requests

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

# ----------------- CONFIG (вставь свои данные здесь) -----------------
# Telegram (оставь как есть или замени)
api_id = 21882740
api_hash = "c80a68894509d01a93f5acfeabfdd922"
ALERT_BOT_TOKEN = "6566504110:AAFK9hA4jxZ0eA7KZGhVvPe8mL2HZj2tQmE"
ALERT_CHAT_ID = 1168962519

# 2captcha API key (вставь свой ключ сюда)
CAPTCHA_API_KEY = "898059857fb8c709ca5c9613d44ffae4"  # <-- Твой 2captcha ключ

# Сайт и логин
LOGIN_URL = "https://freelancehunt.com/ua/profile/login"
LOGIN_DATA = {"login": "Vlari", "password": "Gvadiko_2004"}

# Сохранение куки и профиль хрома
COOKIES_FILE = "fh_cookies.pkl"
CHROME_PROFILE_DIR = "/root/chrome-profile"   # <-- путь к профилю (используется для бэкапа/переноса)
HEADLESS = False  # Если тестируешь в MobaXterm — False. На VPS обычно True, но расширения/видимость могут пострадать.

# Ключевые слова поиска
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
# ----------------------------------------------------------------------

# Telegram bot object
alert_bot = Bot(token=ALERT_BOT_TOKEN)

# Telethon client
client = TelegramClient("session", api_id, api_hash)

# ----------------- Selenium driver (один на весь процесс) -----------------
def create_chrome_driver():
    chrome_options = Options()
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--window-size=1920,1080")
    if HEADLESS:
        chrome_options.add_argument("--headless=new")
    # профиль пользователя сохраняет расширения, куки и настройки
    chrome_options.add_argument(f"--user-data-dir={CHROME_PROFILE_DIR}")
    # дополнительные опции (по необходимости)
    chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
    chrome_options.add_experimental_option('useAutomationExtension', False)

    driver_path = ChromeDriverManager().install()
    svc = Service(driver_path)
    driver = webdriver.Chrome(service=svc, options=chrome_options)
    driver.set_page_load_timeout(60)
    return driver

driver = create_chrome_driver()
print(f"[STEP] Chrome запущен. HEADLESS={HEADLESS}. Профиль: {CHROME_PROFILE_DIR}")
time.sleep(1)

# ----------------- Утилиты -----------------
def extract_links(text: str):
    return [link for link in re.findall(r"https?://[^\s]+", text)
            if "freelancehunt.com" in link]

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
        if "капча" in body or "captcha" in body or "protection" in body:
            return True
    except Exception:
        pass
    return False

# ----------------- 2captcha helpers (reCAPTCHA v2) -----------------
def find_recaptcha_sitekey():
    """Пытаемся найти sitekey на странице (data-sitekey или iframe)"""
    try:
        # 1) поиск элементов с data-sitekey
        elems = driver.find_elements(By.CSS_SELECTOR, "[data-sitekey]")
        for e in elems:
            key = e.get_attribute("data-sitekey")
            if key:
                return key
    except Exception:
        pass
    try:
        # 2) iframe с src содержащим 'sitekey='
        iframes = driver.find_elements(By.TAG_NAME, "iframe")
        for f in iframes:
            src = f.get_attribute("src") or ""
            if "sitekey=" in src:
                m = re.search(r"sitekey=([\w-_]+)", src)
                if m:
                    return m.group(1)
    except Exception:
        pass
    return None

def submit_2captcha_recaptcha(sitekey, pageurl, api_key, poll_interval=5, timeout=180):
    """
    Отправляем задачу на 2captcha для userrecaptcha, ждём результата.
    Возвращает токен (string) или None.
    """
    in_url = "http://2captcha.com/in.php"
    res_url = "http://2captcha.com/res.php"

    payload = {
        "key": api_key,
        "method": "userrecaptcha",
        "googlekey": sitekey,
        "pageurl": pageurl,
        "json": 1,
        # "invisible": 1,  # можно добавить, если это invisible
    }
    try:
        r = requests.post(in_url, data=payload, timeout=30)
        j = r.json()
    except Exception as e:
        print(f"[ERROR] 2captcha in request failed: {e}")
        return None

    if j.get("status") != 1:
        print(f"[ERROR] 2captcha returned error on in.php: {j}")
        return None

    task_id = j.get("request")
    print(f"[STEP] 2captcha task created, id={task_id}. Жду решение...")

    waited = 0
    while waited < timeout:
        time.sleep(poll_interval)
        waited += poll_interval
        try:
            r = requests.get(res_url, params={"key": api_key, "action": "get", "id": task_id, "json": 1}, timeout=30)
            j = r.json()
        except Exception as e:
            print(f"[WARNING] Ошибка при опросе 2captcha: {e}")
            continue
        if j.get("status") == 1:
            print("[STEP] 2captcha вернул токен.")
            return j.get("request")
        elif j.get("request") == "CAPCHA_NOT_READY":
            print("[STEP] 2captcha: ещё не готово...")
            continue
        else:
            print(f"[ERROR] 2captcha returned error: {j}")
            return None
    print("[ERROR] 2captcha: таймаут ожидания решения.")
    return None

def inject_recaptcha_token_and_submit(token):
    """
    Вставляем токен в textarea#g-recaptcha-response и отправляем форму.
    Это общая попытка, может потребоваться адаптация под конкретную форму.
    """
    try:
        # Создаём/вставляем textarea с нужным id
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
            // если есть grecaptcha, попытаемся вызвать callback
            if(window.grecaptcha && window.grecaptcha.getResponse){
                // нет прямого способа вызвать внутренний callback, поэтому просто ставим ответ
            }
        })(arguments[0]);
        """, token)
        time.sleep(1)
        print("[STEP] Токен injected в g-recaptcha-response.")
        # Пытаемся найти кнопку submit формы рядом с капчей
        try:
            # ищем кнопку типа submit в пределах формы
            btn = driver.find_element(By.CSS_SELECTOR, "form button[type='submit'], form input[type='submit']")
            driver.execute_script("arguments[0].click();", btn)
            print("[STEP] Нажата кнопка submit формы после вставки токена.")
            return True
        except Exception:
            # альтернативно - триггер события на форме
            driver.execute_script("document.querySelectorAll('form').forEach(f => f.submit());")
            print("[STEP] Попытка submit всех форм на странице.")
            return True
    except Exception as e:
        print(f"[ERROR] Ошибка при inject token: {e}")
    return False

# ----------------- Login flow -----------------
def login_if_needed():
    """Переход на login_page и ввод логина/пароля, сохранение куки"""
    try:
        driver.get(LOGIN_URL)
        wait_for_page_load()
        # попробуем загрузить куки (если сохранены) — но для корректности лучше загружать до перехода
        # далее проверим наличие полей
        try:
            login_input = driver.find_element(By.ID, "login-0")
            password_input = driver.find_element(By.ID, "password-0")
            login_btn = driver.find_element(By.ID, "save-0")
            print("[STEP] Поля логина/пароля найдены на странице login.")
            human_typing(login_input, LOGIN_DATA["login"])
            human_typing(password_input, LOGIN_DATA["password"])
            driver.execute_script("arguments[0].click();", login_btn)
            print("[STEP] Клик по кнопке входа выполнен.")
            time.sleep(4)
            wait_for_page_load()
            # после логина проверить капчу
            if page_contains_captcha_text() or find_recaptcha_sitekey():
                print("[WARNING] После логина обнаружена капча.")
                # если reCAPTCHA v2 — запустить 2captcha
                sitekey = find_recaptcha_sitekey()
                if sitekey and CAPTCHA_API_KEY:
                    print(f"[STEP] Найден sitekey={sitekey}, отправляю задачу в 2captcha...")
                    token = submit_2captcha_recaptcha(sitekey, driver.current_url, CAPTCHA_API_KEY)
                    if token:
                        inject_recaptcha_token_and_submit(token)
                        time.sleep(3)
                # в любом случае завершаем попытку логина
            save_cookies()
            return True
        except NoSuchElementException:
            print("[INFO] Поля логина не найдены — возможно уже залогинен или другая страница.")
            return True
    except Exception as e:
        print(f"[ERROR] Ошибка в login_if_needed: {e}")
        return False

# ----------------- Основной цикл ставок -----------------
async def send_alert(msg: str):
    try:
        # TeleBot send (await)
        await alert_bot.send_message(chat_id=ALERT_CHAT_ID, text=msg)
        print(f"[STEP] Уведомление отправлено: {msg}")
    except Exception as e:
        print(f"[ERROR] Не удалось отправить уведомление: {e}")

async def make_bid(url: str):
    print(f"[INFO] Начинаю обработку: {url}")
    try:
        driver.get(url)
        wait_for_page_load()
        # Загружаем куки (если есть) — лучше делать ДО первого get, но оставляю здесь для стабильности
        load_cookies()
        time.sleep(1)
        # Проверка авторизации: ищем ссылку на профиль
        try:
            driver.find_element(By.CSS_SELECTOR, "a[href='/profile']")  # если есть — залогинен
            print("[STEP] Авторизация подтверждена (есть ссылка /profile).")
        except NoSuchElementException:
            print("[STEP] Не найден профиль — делаем логин...")
            # переходим на логин и логинимся
            ok = login_if_needed()
            if not ok:
                await send_alert(f"❌ Не удалось выполнить логин на {url}")
                return
            driver.get(url)
            wait_for_page_load()

        # Проверка капчи на странице проекта
        if page_contains_captcha_text() or find_recaptcha_sitekey():
            print("[WARNING] На странице проекта есть капча.")
            sitekey = find_recaptcha_sitekey()
            if sitekey and CAPTCHA_API_KEY:
                token = submit_2captcha_recaptcha(sitekey, driver.current_url, CAPTCHA_API_KEY)
                if token:
                    injected = inject_recaptcha_token_and_submit(token)
                    if injected:
                        time.sleep(3)
                        wait_for_page_load()
            else:
                await send_alert(f"⚠️ Обнаружена капча на {url} — ручное вмешательство нужно.")
                return

        # Ищем кнопку "Сделать ставку"
        try:
            bid_btn = WebDriverWait(driver, 12).until(
                EC.element_to_be_clickable((By.ID, "add-bid"))
            )
            driver.execute_script("arguments[0].scrollIntoView(true);", bid_btn)
            time.sleep(0.3)
            driver.execute_script("arguments[0].click();", bid_btn)
            print("[STEP] Нажата кнопка 'Сделать ставку'.")
        except TimeoutException:
            await send_alert(f"⚠️ Кнопка 'Сделать ставку' не найдена: {url}")
            return

        # Заполняем форму
        try:
            amount = WebDriverWait(driver, 8).until(EC.presence_of_element_located((By.ID, "amount-0")))
            days = driver.find_element(By.ID, "days_to_deliver-0")
            comment = driver.find_element(By.ID, "comment-0")

            human_typing(amount, "1111")
            human_typing(days, "3")
            human_typing(comment, COMMENT_TEXT, delay_range=(0.02, 0.07))

            # Нажать кнопку отправки (add-0)
            add_btn = driver.find_element(By.ID, "add-0")
            driver.execute_script("arguments[0].click();", add_btn)
            print("[SUCCESS] Ставка отправлена (нажали add-0).")
            await send_alert(f"✅ Ставка отправлена: {url}")
            # не закрываем браузер, профиль сохраняется
            time.sleep(2)
        except Exception as e:
            await send_alert(f"❌ Ошибка при заполнении формы: {e}\n{url}")
            print(f"[ERROR] Заполнение формы: {e}")
    except Exception as e:
        await send_alert(f"❌ Ошибка при обработке проекта: {e}\n{url}")
        print(f"[ERROR] make_bid exception: {e}")

# ----------------- Telegram handlers -----------------
@client.on(events.NewMessage)
async def handler(event):
    text = (event.message.text or "").lower()
    links = extract_links(text)
    if links and any(k in text for k in KEYWORDS):
        url = links[0]
        print(f"[INFO] Подходит ссылка: {url}")
        await make_bid(url)
        print("[INFO] Готов к следующему проекту")

# ----------------- Main -----------------
async def main():
    print("[INFO] Запуск бота...")
    await alert_bot.initialize()
    print("[STEP] Telegram notify bot initialized.")
    # загружаем куки до старта (если есть)
    try:
        # если есть куки файл, заносим в профиль (нужно перед навигацией)
        if os.path.exists(COOKIES_FILE):
            # Открываем стартовую страницу чтобы можно было добавлять куки
            driver.get("https://freelancehunt.com/")
            wait_for_page_load()
            load_cookies()
            print("[STEP] Cookies загружены на старте.")
    except Exception as e:
        print(f"[WARNING] Ошибка загрузки кук на старте: {e}")

    await client.start()
    print("[INFO] Telegram client started. Waiting for new projects...")
    await client.run_until_disconnected()

if __name__ == "__main__":
    try:
        # При старте можно выполнить логин (если нужно)
        # login_if_needed()  # можно раскомментировать, если хочешь логинить при старте
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Exit by user")
    finally:
        try:
            driver.quit()
        except Exception:
            pass
