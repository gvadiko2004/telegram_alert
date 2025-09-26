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

# ===== Настройки Telegram =====
api_id = 21882740
api_hash = "c80a68894509d01a93f5acfeabfdd922"
ALERT_BOT_TOKEN = "6566504110:AAFK9hA4jxZ0eA7KZGhVvPe8mL2HZj2tQmE"
ALERT_CHAT_ID = 1168962519  # твой Telegram ID

from telegram import Bot
alert_bot = Bot(token=ALERT_BOT_TOKEN)

# ===== Ключевые слова и текст заявки =====
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

PROFILE_PATH = "/home/user/chrome_profile"
COOKIES_FILE = "fh_cookies.pkl"
LOGIN_URL = "https://freelancehunt.com/profile/login"
LOGIN_DATA = {"login": "Vlari", "password": "Gvadiko_2004"}

# ---------------- Функции ----------------
def extract_links(text: str):
    return [link for link in re.findall(r"https?://[^\s]+", text)
            if link.startswith("https://freelancehunt.com/")]

def save_cookies(driver):
    with open(COOKIES_FILE, "wb") as f:
        pickle.dump(driver.get_cookies(), f)
    print("[INFO] Cookies сохранены.")

def login_if_needed(driver):
    if os.path.exists(COOKIES_FILE):
        print("[INFO] Cookies найдены, пропускаем авторизацию.")
        return

    driver.get(LOGIN_URL)
    wait = WebDriverWait(driver, 30)
    wait.until(EC.presence_of_element_located((By.ID, "login-0")))
    driver.execute_script(f'document.getElementById("login-0").value="{LOGIN_DATA["login"]}";')
    driver.execute_script(f'document.getElementById("password-0").value="{LOGIN_DATA["password"]}";')
    js_click_login = "const btn=document.querySelector('#save-0');if(btn){btn.click();}"
    driver.execute_script(js_click_login)
    time.sleep(5)
    save_cookies(driver)

# ---------------- Отправка уведомлений ----------------
async def send_alert(message: str):
    try:
        await alert_bot.send_message(chat_id=ALERT_CHAT_ID, text=message)
    except Exception as e:
        print(f"[ERROR] Не удалось отправить уведомление: {e}")

# ---------------- Функция ставок ----------------
async def make_bid(url):
    chrome_options = Options()
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument(f"--user-data-dir={PROFILE_PATH}")
    chrome_options.add_argument("--start-minimized")
    chrome_options.add_argument("--disable-extensions")
    chrome_options.add_argument("--disable-gpu")

    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=chrome_options)
    wait = WebDriverWait(driver, 30)

    try:
        login_if_needed(driver)
        driver.get(url)
        wait.until(lambda d: d.execute_script("return document.readyState") == "complete")
        print(f"[INFO] Страница проекта загружена: {url}")

        wait_short = WebDriverWait(driver, 5)
        try:
            bid_btn = wait_short.until(EC.element_to_be_clickable((By.ID, "add-bid")))
            driver.execute_script("arguments[0].click();", bid_btn)
            print("[INFO] Нажата кнопка 'Сделать ставку'")
        except TimeoutException:
            try:
                alert_div = driver.find_element(By.CSS_SELECTOR, "div.alert.alert-info")
                print(f"[ALERT] {alert_div.text.strip()}")
                await send_alert(f"❌ Не удалось сделать ставку: {alert_div.text.strip()}\nСсылка: {url}")
                return
            except NoSuchElementException:
                print("[WARNING] Нет кнопки 'Сделать ставку'")
                await send_alert(f"⚠️ Не удалось найти кнопку 'Сделать ставку' для проекта: {url}")
                return

        time.sleep(1)
        try:
            price_span = wait.until(EC.presence_of_element_located((
                By.CSS_SELECTOR, "span.text-green.bold.pull-right.price.with-tooltip.hidden-xs"
            )))
            price = re.sub(r"[^\d]", "", price_span.text) or "1111"
        except Exception:
            price = "1111"

        driver.find_element(By.ID, "amount-0").send_keys(price)
        driver.find_element(By.ID, "days_to_deliver-0").send_keys("3")
        driver.execute_script(f"document.getElementById('comment-0').value = `{COMMENT_TEXT}`;")
        js_click_code = """
        const addButton = document.querySelector('#add-0');
        if (addButton) {
            const rect = addButton.getBoundingClientRect();
            const evt = new MouseEvent('click',{bubbles:true, clientX:rect.left+rect.width/2, clientY:rect.top+rect.height/2});
            addButton.dispatchEvent(evt);
        }
        """
        driver.execute_script(js_click_code)
        print("[SUCCESS] Ставка отправлена через JS")
        await send_alert(f"✅ Ставка успешно отправлена!\nСсылка: {url}\nСумма: {price}")

    except Exception as e:
        print(f"[ERROR] Ошибка при отправке заявки: {e}")
        await send_alert(f"❌ Ошибка при отправке ставки: {e}\nСсылка: {url}")

    print("[INFO] Браузер оставлен открытым для проверки.")

# ---------------- Телеграм ----------------
client = TelegramClient("session", api_id, api_hash)

@client.on(events.NewMessage)
async def handler(event):
    text = (event.message.text or "").lower()
    links = extract_links(text)
    if any(k in text for k in KEYWORDS) and links:
        print(f"[INFO] Подходит ссылка: {links[0]}")
        await make_bid(links[0])
        print("[INFO] Готов к следующему проекту")

# ---------------- Запуск ----------------
async def main():
    print("[INFO] Запуск бота уведомлений через @iliarchie_bot...")
    await alert_bot.initialize()  # инициализация Bot API
    print("[INFO] Бот уведомлений запущен.")
    await client.start()
    print("[INFO] Telegram бот запущен. Ожидаем новые проекты...")
    await client.run_until_disconnected()

if __name__ == "__main__":
    asyncio.run(main())
