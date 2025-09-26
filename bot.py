import os
import pickle
import re
import time
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

# ===== Telegram =====
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

COOKIES_FILE = "/root/chrome_profile/fh_cookies.pkl"
LOGIN_URL = "https://freelancehunt.com/profile/login"
LOGIN_DATA = {"login": "Vlari", "password": "Gvadiko_2004"}
PROFILE_PATH = "/root/chrome_profile"

# ===== Функции =====
def extract_links(text: str):
    return [link for link in re.findall(r"https?://[^\s]+", text)
            if link.startswith("https://freelancehunt.com/")]

def save_cookies(driver):
    os.makedirs(PROFILE_PATH, exist_ok=True)
    with open(COOKIES_FILE, "wb") as f:
        pickle.dump(driver.get_cookies(), f)
    print("[INFO] Cookies сохранены.")

def load_cookies(driver):
    if os.path.exists(COOKIES_FILE):
        with open(COOKIES_FILE, "rb") as f:
            cookies = pickle.load(f)
        for cookie in cookies:
            driver.add_cookie(cookie)
        print("[INFO] Cookies загружены.")
        return True
    return False

def create_driver():
    print("[STEP] Запуск виртуального Chrome...")
    chrome_options = Options()
    chrome_options.add_argument("--headless=new")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--window-size=1920,1080")
    chrome_options.add_argument(f"--user-data-dir={PROFILE_PATH}")
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=chrome_options)
    print("[STEP] Chrome запущен.")
    return driver

def login(driver):
    print(f"[STEP] Переход на страницу логина: {LOGIN_URL}")
    driver.get(LOGIN_URL)
    wait = WebDriverWait(driver, 20)
    
    try:
        # Ищем label с текстом "Логин" и берём соседний input
        login_label = driver.find_element(By.XPATH, "//label[contains(text(), 'Логин')]")
        login_input = login_label.find_element(By.XPATH, "./following-sibling::div//input")
        login_input.send_keys(LOGIN_DATA["login"])
        print("[STEP] Ввели логин.")

        # Ищем label с текстом "Пароль" и берём соседний input
        password_label = driver.find_element(By.XPATH, "//label[contains(text(), 'Пароль')]")
        password_input = password_label.find_element(By.XPATH, "./following-sibling::div//input")
        password_input.send_keys(LOGIN_DATA["password"])
        print("[STEP] Ввели пароль.")

        # Кнопка "Увійти"
        submit_btn = driver.find_element(By.XPATH, "//button[contains(text(),'Увійти')]")
        submit_btn.click()
        print("[STEP] Нажата кнопка 'Увійти'")

        time.sleep(5)
        save_cookies(driver)
        print("[INFO] Авторизация пройдена и куки сохранены.")
    except TimeoutException:
        print("[ERROR] Не удалось найти поля логина/пароля — возможно капча.")
        raise Exception("Авторизация не удалась")
    except Exception as e:
        print(f"[ERROR] Ошибка при авторизации: {e}")
        raise e

async def send_alert(message: str):
    try:
        alert_bot.send_message(chat_id=ALERT_CHAT_ID, text=message)
    except Exception as e:
        print(f"[ERROR] Не удалось отправить уведомление: {e}")

async def make_bid(url):
    driver = create_driver()
    wait = WebDriverWait(driver, 20)
    try:
        print(f"[STEP] Переход на страницу проекта: {url}")
        driver.get(url)
        time.sleep(3)

        # Загружаем куки если есть
        if not load_cookies(driver):
            print("[STEP] Cookies нет, нужна авторизация.")
            login(driver)
            driver.get(url)
            time.sleep(3)

        # Проверка авторизации
        try:
            driver.find_element(By.CSS_SELECTOR, "a[href='/profile']")
            print("[INFO] Уже авторизован.")
        except NoSuchElementException:
            print("[INFO] Авторизация не прошла.")
            await send_alert(f"❌ Авторизация не прошла на {url}")
            driver.quit()
            return

        # Ищем кнопку "Сделать ставку"
        try:
            bid_btn = wait.until(EC.element_to_be_clickable((By.ID, "add-bid")))
            bid_btn.click()
            print("[STEP] Нажата кнопка 'Сделать ставку'")
        except TimeoutException:
            print("[WARNING] Кнопка 'Сделать ставку' не найдена — возможно капча или проект закрыт")
            await send_alert(f"⚠️ Кнопка 'Сделать ставку' не найдена: {url}")
            driver.quit()
            return

        # Заполнение формы
        try:
            driver.find_element(By.ID, "amount-0").send_keys("1111")
            driver.find_element(By.ID, "days_to_deliver-0").send_keys("3")
            driver.find_element(By.ID, "comment-0").send_keys(COMMENT_TEXT)
            driver.find_element(By.ID, "add-0").click()
            print("[SUCCESS] Ставка отправлена")
            await send_alert(f"✅ Ставка успешно отправлена!\nСсылка: {url}")
        except Exception as e:
            print(f"[ERROR] Не удалось заполнить форму ставки: {e}")
            await send_alert(f"❌ Ошибка при отправке ставки: {e}\nСсылка: {url}")

    except Exception as e:
        print(f"[ERROR] Ошибка при обработке проекта: {e}")
        await send_alert(f"❌ Ошибка при обработке проекта: {e}\nСсылка: {url}")

    finally:
        driver.quit()
        print("[INFO] Браузер закрыт.")

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
    asyncio.run(main())
