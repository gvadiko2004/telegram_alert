import os
import pickle
import re
import time
import random
import asyncio

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

# ===== Telegram Настройки =====
api_id = 21882740
api_hash = "c80a68894509d01a93f5acfeabfdd922"
ALERT_BOT_TOKEN = "6566504110:AAFK9hA4jxZ0eA7KZGhVvPe8mL2HZj2tQmE"
ALERT_CHAT_ID = 1168962519
alert_bot = Bot(token=ALERT_BOT_TOKEN)

# ===== Настройки сайта =====
KEYWORDS = [
    "#html_и_css_верстка",
    "#веб_программирование",
    "#cms",
    "#интернет_магазины_и_электронная_коммерция",
    "#создание_сайта_под_ключ",
    "#дизайн_сайтов"
]
KEYWORDS = [kw.lower() for kw in KEYWORDS]

COMMENT_TEXT = """Доброго дня! Готовий виконати роботу якісно.
Портфоліо робіт у моєму профілі.
Заздалегідь дякую!
"""

COOKIES_FILE = "fh_cookies.pkl"
LOGIN_URL = "https://freelancehunt.com/ua/profile/login"
LOGIN_DATA = {"login": "Vlari", "password": "Gvadiko_2004"}

# ===== Selenium драйвер (headless для VPS) =====
chrome_options = Options()
chrome_options.add_argument("--headless")  # Headless режим
chrome_options.add_argument("--no-sandbox")
chrome_options.add_argument("--disable-dev-shm-usage")
chrome_options.add_argument("--disable-gpu")
chrome_options.add_argument("--window-size=1920,1080")
# Унікальний профіль для кожного запуску
chrome_options.add_argument(f"--user-data-dir=/root/chrome-profile-{int(time.time())}")

driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=chrome_options)

print("[STEP] Chrome запущен (headless режим).")

# ===== Функції =====
def extract_links(text: str):
    return [link for link in re.findall(r"https?://[^\s]+", text)
            if link.startswith("https://freelancehunt.com/")]

def save_cookies():
    with open(COOKIES_FILE, "wb") as f:
        pickle.dump(driver.get_cookies(), f)
    print("[STEP] Cookies сохранены.")

def load_cookies():
    if os.path.exists(COOKIES_FILE):
        with open(COOKIES_FILE, "rb") as f:
            cookies = pickle.load(f)
        for cookie in cookies:
            driver.add_cookie(cookie)
        print("[STEP] Cookies загружены.")
        return True
    return False

def wait_for_page_load(timeout=15):
    try:
        WebDriverWait(driver, timeout).until(EC.presence_of_element_located((By.TAG_NAME, "body")))
        time.sleep(2)
    except TimeoutException:
        print("[WARNING] Таймаут ожидания загрузки страницы.")

def human_typing(element, text, delay_range=(0.05, 0.15)):
    for char in text:
        element.send_keys(char)
        time.sleep(random.uniform(*delay_range))

def login():
    driver.get(LOGIN_URL)
    wait_for_page_load()
    try:
        login_input = driver.find_element(By.ID, "login-0")
        password_input = driver.find_element(By.ID, "password-0")
        login_submit = driver.find_element(By.ID, "save-0")
        print("[STEP] Поля логин/пароль найдены.")
        human_typing(login_input, LOGIN_DATA["login"])
        human_typing(password_input, LOGIN_DATA["password"])
        driver.execute_script("arguments[0].click();", login_submit)
        print("[STEP] Нажата кнопка 'Увійти'")
        time.sleep(5)
        wait_for_page_load()
        save_cookies()
    except NoSuchElementException:
        print("[INFO] Поля логина не найдены, возможно уже залогинены.")

async def send_alert(message: str):
    try:
        await alert_bot.send_message(chat_id=ALERT_CHAT_ID, text=message)
        print(f"[STEP] Уведомление отправлено: {message}")
    except Exception as e:
        print(f"[ERROR] Не удалось отправить уведомление: {e}")

async def make_bid(url):
    driver.get(url)
    wait_for_page_load()

    if not load_cookies():
        login()
        driver.get(url)
        wait_for_page_load()

    try:
        bid_btn = WebDriverWait(driver, 15).until(
            EC.element_to_be_clickable((By.ID, "add-bid"))
        )
        bid_btn.click()
        print("[STEP] Нажата кнопка 'Сделать ставку'")
    except TimeoutException:
        await send_alert(f"⚠️ Кнопка 'Сделать ставку' не найдена: {url}")
        return

    # Заполняем форму
    try:
        human_typing(driver.find_element(By.ID, "amount-0"), "1111")
        human_typing(driver.find_element(By.ID, "days_to_deliver-0"), "3")
        human_typing(driver.find_element(By.ID, "comment-0"), COMMENT_TEXT, delay_range=(0.02,0.08))
        driver.find_element(By.ID, "add-0").click()
        print("[STEP] Форма ставки заполнена и отправлена.")
        await send_alert(f"✅ Ставка успешно отправлена!\nСсылка: {url}")
    except Exception as e:
        await send_alert(f"❌ Ошибка при заполнении формы: {e}\nСсылка: {url}")

# ===== Telegram =====
client = TelegramClient("session", api_id, api_hash)

@client.on(events.NewMessage)
async def handler(event):
    text = (event.message.text or "").lower()
    links = extract_links(text)
    if any(k in text for k in KEYWORDS) and links:
        print(f"[INFO] Подходит ссылка: {links[0]}")
        await make_bid(links[0])
        print("[INFO] Готов к следующему проекту")

# ===== Запуск =====
async def main():
    print("[INFO] Запуск бота уведомлений...")
    await client.start()
    print("[INFO] Telegram бот запущен. Ожидаем новые проекты...")
    await client.run_until_disconnected()

if __name__ == "__main__":
    login()  # Вход в аккаунт при старте
    asyncio.run(main())
