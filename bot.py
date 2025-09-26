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

# ===== Telegram =====
api_id = 21882740
api_hash = "c80a68894509d01a93f5acfeabfdd922"
ALERT_BOT_TOKEN = "6566504110:AAFK9hA4jxZ0eA7KZGhVvPe8mL2HZj2tQmE"
ALERT_CHAT_ID = 1168962519
alert_bot = Bot(token=ALERT_BOT_TOKEN)

# ===== Настройки Freelancehunt =====
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
LOGIN_BUTTON_SELECTOR = "a.inline-block.link-no-underline"
LOGIN_DATA = {"login": "Vlari", "password": "Gvadiko_2004"}

# ===== Функции =====
def extract_links(text: str):
    return [link for link in re.findall(r"https?://[^\s]+", text)
            if link.startswith("https://freelancehunt.com/")]

def save_cookies(driver):
    with open(COOKIES_FILE, "wb") as f:
        pickle.dump(driver.get_cookies(), f)
    print("[STEP] Cookies сохранены.")

def load_cookies(driver):
    if os.path.exists(COOKIES_FILE):
        with open(COOKIES_FILE, "rb") as f:
            cookies = pickle.load(f)
        for cookie in cookies:
            driver.add_cookie(cookie)
        print("[STEP] Cookies загружены.")
        return True
    return False

def create_driver():
    chrome_options = Options()
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--window-size=1920,1080")

    # Используем ваш заранее созданный профиль с расширением
    user_data_dir = os.path.join(os.getcwd(), "chrome_profile")
    os.makedirs(user_data_dir, exist_ok=True)
    chrome_options.add_argument(f"--user-data-dir={user_data_dir}")

    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=chrome_options)
    print("[INFO] Chrome запущен с профилем, где установлено расширение.")
    return driver

def wait_for_page_load(driver, timeout=15):
    try:
        WebDriverWait(driver, timeout).until(EC.presence_of_element_located((By.TAG_NAME, "body")))
        time.sleep(2)
    except TimeoutException:
        print("[WARNING] Таймаут ожидания загрузки страницы.")

def human_typing(element, text, delay_range=(0.05, 0.15)):
    for char in text:
        element.send_keys(char)
        time.sleep(random.uniform(*delay_range))

def check_captcha(driver):
    try:
        body_text = driver.find_element(By.TAG_NAME, "body").text
        if "капча" in body_text.lower() or "captcha" in body_text.lower():
            print("[WARNING] На странице обнаружена капча!")
            return True
    except Exception:
        pass
    return False

def login(driver):
    try:
        login_btn = driver.find_element(By.CSS_SELECTOR, LOGIN_BUTTON_SELECTOR)
        driver.execute_script("arguments[0].click();", login_btn)
        time.sleep(3)
    except NoSuchElementException:
        pass

    driver.get(LOGIN_URL)
    wait_for_page_load(driver)

    try:
        login_input = driver.find_element(By.ID, "login-0")
        password_input = driver.find_element(By.ID, "password-0")
        login_submit = driver.find_element(By.ID, "save-0")

        human_typing(login_input, LOGIN_DATA["login"])
        human_typing(password_input, LOGIN_DATA["password"])
        driver.execute_script("arguments[0].click();", login_submit)
        time.sleep(5)
        wait_for_page_load(driver)

        if check_captcha(driver):
            raise Exception("Капча обнаружена после логина!")

        save_cookies(driver)
    except NoSuchElementException:
        raise Exception("Поля логина/пароля не найдены!")

async def send_alert(message: str):
    try:
        await alert_bot.send_message(chat_id=ALERT_CHAT_ID, text=message)
    except Exception as e:
        print(f"[ERROR] Не удалось отправить уведомление: {e}")

async def make_bid(url):
    driver = create_driver()
    try:
        driver.get(url)
        wait_for_page_load(driver)

        if not load_cookies(driver):
            login(driver)
            driver.get(url)
            wait_for_page_load(driver)

        if check_captcha(driver):
            await send_alert(f"⚠️ Капча на странице: {url}")
            driver.quit()
            return

        # Клик по кнопке "Сделать ставку"
        try:
            bid_btn = WebDriverWait(driver, 15).until(
                EC.element_to_be_clickable((By.ID, "add-bid"))
            )
            bid_btn.click()
        except TimeoutException:
            await send_alert(f"⚠️ Кнопка 'Сделать ставку' не найдена: {url}")
            driver.quit()
            return

        # Заполнение формы
        try:
            human_typing(driver.find_element(By.ID, "amount-0"), "1111")
            human_typing(driver.find_element(By.ID, "days_to_deliver-0"), "3")
            human_typing(driver.find_element(By.ID, "comment-0"), COMMENT_TEXT, delay_range=(0.02,0.08))
            driver.find_element(By.ID, "add-0").click()
            await send_alert(f"✅ Ставка отправлена!\nСсылка: {url}")
        except Exception as e:
            await send_alert(f"❌ Ошибка при заполнении формы: {e}\nСсылка: {url}")

    except Exception as e:
        await send_alert(f"❌ Ошибка при обработке проекта: {e}\nСсылка: {url}")
    finally:
        driver.quit()

# ===== Telegram =====
client = TelegramClient("session", api_id, api_hash)

@client.on(events.NewMessage)
async def handler(event):
    text = (event.message.text or "").lower()
    links = extract_links(text)
    if any(k in text for k in KEYWORDS) and links:
        await make_bid(links[0])

# ===== Запуск =====
async def main():
    await alert_bot.initialize()
    await client.start()
    await client.run_until_disconnected()

if __name__ == "__main__":
    asyncio.run(main())
