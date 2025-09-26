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
from twocaptcha import TwoCaptcha

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
LOGIN_URL = "https://freelancehunt.com/ua/profile/login"
LOGIN_BUTTON_SELECTOR = "a.inline-block.link-no-underline"
LOGIN_DATA = {"login": "Vlari", "password": "Gvadiko_2004"}

# ===== Настройки 2Captcha =====
CAPTCHA_API_KEY = "898059857fb8c709ca5c9613d44ffae4"
solver = TwoCaptcha(CAPTCHA_API_KEY)

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
            try:
                driver.add_cookie(cookie)
            except Exception:
                pass
        print("[STEP] Cookies загружены.")
        return True
    return False

def create_driver():
    chrome_options = Options()
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--window-size=1920,1080")
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=chrome_options)
    print("[STEP] Chrome запущен (видимый режим).")
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

def solve_recaptcha(driver):
    try:
        iframe = driver.find_element(By.CSS_SELECTOR, "iframe[src*='recaptcha']")
        driver.switch_to.frame(iframe)
        sitekey = iframe.get_attribute("src").split("k=")[1].split("&")[0]
        driver.switch_to.default_content()
        url = driver.current_url
        print("[STEP] Отправка капчи на 2Captcha...")
        result = solver.recaptcha(sitekey=sitekey, url=url)
        token = result['code']
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
        })(arguments[0]);
        """
        driver.execute_script(inject_js, token)
        time.sleep(1)
        print("[STEP] Капча решена и токен вставлен.")
    except Exception as e:
        print(f"[ERROR] Не удалось решить капчу: {e}")

def check_captcha(driver):
    try:
        if driver.find_elements(By.CSS_SELECTOR, "iframe[src*='recaptcha']"):
            print("[INFO] reCAPTCHA обнаружена.")
            solve_recaptcha(driver)
            return True
    except Exception:
        pass
    return False

def login(driver):
    try:
        login_btn = driver.find_element(By.CSS_SELECTOR, LOGIN_BUTTON_SELECTOR)
        driver.execute_script("arguments[0].click();", login_btn)
        time.sleep(2)
    except NoSuchElementException:
        pass
    driver.get(LOGIN_URL)
    wait_for_page_load(driver)
    try:
        login_input = driver.find_element(By.ID, "login-0")
        password_input = driver.find_element(By.ID, "password-0")
        submit_btn = driver.find_element(By.ID, "save-0")
        human_typing(login_input, LOGIN_DATA["login"])
        human_typing(password_input, LOGIN_DATA["password"])
        driver.execute_script("arguments[0].click();", submit_btn)
        time.sleep(5)
        wait_for_page_load(driver)
        check_captcha(driver)
        save_cookies(driver)
    except Exception as e:
        print(f"[ERROR] Ошибка логина: {e}")

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
        check_captcha(driver)
        try:
            bid_btn = WebDriverWait(driver, 15).until(EC.element_to_be_clickable((By.ID, "add-bid")))
            time.sleep(1)
            bid_btn.click()
        except TimeoutException:
            await send_alert(f"⚠️ Кнопка 'Сделать ставку' не найдена: {url}")
            return
        human_typing(driver.find_element(By.ID, "amount-0"), "1111")
        human_typing(driver.find_element(By.ID, "days_to_deliver-0"), "3")
        human_typing(driver.find_element(By.ID, "comment-0"), COMMENT_TEXT, delay_range=(0.02,0.08))
        time.sleep(1)
        driver.find_element(By.ID, "add-0").click()
        await send_alert(f"✅ Ставка успешно отправлена!\nСсылка: {url}")
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
