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

# ===== Настройки Telegram =====
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
LOGIN_URL = "https://freelancehunt.com/profile/login"
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
    # Важно: НЕ headless, чтобы видеть все действия
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=chrome_options)
    print("[STEP] Chrome запущен (видимый режим).")
    return driver

def wait_for_page_load(driver, timeout=15):
    """Ждем загрузки body и паузу, чтобы страница полностью прогрузилась."""
    try:
        WebDriverWait(driver, timeout).until(EC.presence_of_element_located((By.TAG_NAME, "body")))
        print("[STEP] Страница полностью загружена.")
        time.sleep(2)  # дополнительная пауза для всех JS элементов
    except TimeoutException:
        print("[WARNING] Таймаут ожидания загрузки страницы.")

def check_captcha(driver):
    try:
        text = driver.find_element(By.TAG_NAME, "body").text
        if "капча" in text.lower() or "captcha" in text.lower():
            print("[WARNING] На странице обнаружена капча!")
            return True
    except Exception:
        pass
    return False

def login(driver):
    driver.get(LOGIN_URL)
    print(f"[STEP] Переход на страницу логина: {LOGIN_URL}")
    wait_for_page_load(driver)

    try:
        login_input = driver.find_element(By.XPATH, "//label[contains(text(),'Логин')]/following-sibling::div//input")
        password_input = driver.find_element(By.XPATH, "//label[contains(text(),'Пароль')]/following-sibling::div//input")
        login_button = driver.find_element(By.ID, "save-0")

        print("[STEP] Найдены поля Логин, Пароль и кнопка Войти.")

        time.sleep(1)
        login_input.clear()
        login_input.send_keys(LOGIN_DATA["login"])
        print(f"[STEP] Ввели логин: {LOGIN_DATA['login']}")

        time.sleep(1)
        password_input.clear()
        password_input.send_keys(LOGIN_DATA["password"])
        print(f"[STEP] Ввели пароль.")

        time.sleep(1)
        login_button.click()
        print("[STEP] Нажата кнопка Войти.")

        time.sleep(5)
        wait_for_page_load(driver)

        if check_captcha(driver):
            raise Exception("Капча обнаружена после попытки логина.")

        save_cookies(driver)
        print("[STEP] Авторизация пройдена и куки сохранены.")

    except NoSuchElementException:
        raise Exception("Поля логина/пароля или кнопка не найдены — возможно капча.")

async def send_alert(message: str):
    try:
        await alert_bot.send_message(chat_id=ALERT_CHAT_ID, text=message)
        print(f"[STEP] Отправлено уведомление в Telegram: {message}")
    except Exception as e:
        print(f"[ERROR] Не удалось отправить уведомление: {e}")

async def make_bid(url):
    driver = create_driver()
    try:
        driver.get(url)
        print(f"[STEP] Перешли на страницу проекта: {url}")
        wait_for_page_load(driver)

        if not load_cookies(driver):
            print("[STEP] Cookies нет, нужна авторизация.")
            login(driver)
            driver.get(url)
            wait_for_page_load(driver)
            print(f"[STEP] Вернулись на страницу проекта после логина: {url}")

        try:
            driver.find_element(By.CSS_SELECTOR, "a[href='/profile']")
            print("[STEP] Уже авторизован на сайте.")
        except NoSuchElementException:
            await send_alert(f"❌ Авторизация не прошла на {url}")
            driver.quit()
            return

        if check_captcha(driver):
            await send_alert(f"⚠️ Обнаружена капча на странице: {url}")
            driver.quit()
            return

        try:
            bid_btn = WebDriverWait(driver, 15).until(EC.element_to_be_clickable((By.ID, "add-bid")))
            time.sleep(1)
            bid_btn.click()
            print("[STEP] Нажата кнопка 'Сделать ставку'")
        except TimeoutException:
            await send_alert(f"⚠️ Кнопка 'Сделать ставку' не найдена: {url}")
            driver.quit()
            return

        try:
            time.sleep(1)
            driver.find_element(By.ID, "amount-0").send_keys("1111")
            driver.find_element(By.ID, "days_to_deliver-0").send_keys("3")
            driver.find_element(By.ID, "comment-0").send_keys(COMMENT_TEXT)
            time.sleep(1)
            driver.find_element(By.ID, "add-0").click()
            print("[STEP] Форма ставки заполнена и отправлена.")
            await send_alert(f"✅ Ставка успешно отправлена!\nСсылка: {url}")
        except Exception as e:
            await send_alert(f"❌ Ошибка при заполнении формы ставки: {e}\nСсылка: {url}")

    except Exception as e:
        await send_alert(f"❌ Ошибка при обработке проекта: {e}\nСсылка: {url}")
    finally:
        driver.quit()
        print("[STEP] Браузер закрыт.")

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
    await alert_bot.initialize()
    print("[INFO] Бот уведомлений запущен.")
    await client.start()
    print("[INFO] Telegram бот запущен. Ожидаем новые проекты...")
    await client.run_until_disconnected()

if __name__ == "__main__":
    asyncio.run(main())
