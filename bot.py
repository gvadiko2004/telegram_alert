import os
import time
import pickle
import random
import asyncio
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException, UnexpectedAlertPresentException
from webdriver_manager.chrome import ChromeDriverManager
from telegram import Bot

# ===== Настройки Telegram =====
ALERT_BOT_TOKEN = "6566504110:AAFK9hA4jxZ0eA7KZGhVvPe8mL2HZj2tQmE"
ALERT_CHAT_ID = 1168962519
alert_bot = Bot(token=ALERT_BOT_TOKEN)

# ===== Настройки 2Captcha =====
API_KEY_2CAPTCHA = "898059857fb8c709ca5c9613d44ffae4"

# ===== Настройки Chrome =====
PROFILE_DIR = os.path.join(os.getcwd(), "chrome_profile")  # Папка для профиля браузера
EXTENSION_URL = "https://chrome.google.com/webstore/detail/anti-captcha-blocker-exte/bnmifaggmbajabmgbgolcapebogbejkn"

def create_driver_with_extension(headless=False):
    chrome_options = Options()
    chrome_options.add_argument(f"--user-data-dir={PROFILE_DIR}")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--window-size=1920,1080")
    if headless:
        chrome_options.add_argument("--headless=new")
    
    # Устанавливаем Chrome
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=chrome_options)
    return driver

def setup_extension(driver):
    driver.get(EXTENSION_URL)
    time.sleep(5)

    try:
        # Нажимаем кнопку "Установить"
        install_btn = driver.find_element(By.XPATH, "//span[text()='Установить']/..")
        driver.execute_script("arguments[0].click();", install_btn)
        print("[STEP] Нажата кнопка 'Установить' расширение")
        time.sleep(3)

        # Подтверждаем алерт установки
        try:
            alert = driver.switch_to.alert
            alert.accept()
            print("[STEP] Алерт подтверждён")
        except Exception:
            pass

        # Ждём, пока расширение загрузится
        time.sleep(5)
    except Exception as e:
        print(f"[INFO] Возможно, расширение уже установлено: {e}")

    # Открываем вкладку расширения для ввода API ключа
    driver.get("chrome-extension://bnmifaggmbajabmgbgolcapebogbejkn/popup.html")  # Пример, возможно надо проверить реальный путь
    time.sleep(2)

    try:
        input_field = driver.find_element(By.CSS_SELECTOR, "input[name='apiKey']")
        input_field.clear()
        input_field.send_keys(API_KEY_2CAPTCHA)
        submit_btn = driver.find_element(By.CSS_SELECTOR, "button[type='submit']")
        submit_btn.click()
        print("[STEP] API ключ введён и подтверждён")
        time.sleep(2)
    except Exception as e:
        print(f"[WARNING] Не удалось ввести API ключ (возможно уже введён): {e}")

async def send_alert(message: str):
    try:
        await alert_bot.send_message(chat_id=ALERT_CHAT_ID, text=message)
        print(f"[ALERT] {message}")
    except Exception as e:
        print(f"[ERROR] Telegram уведомление не отправлено: {e}")

async def main():
    print("[INFO] Запуск Selenium с расширением Anti-Captcha...")
    driver = create_driver_with_extension(headless=False)
    setup_extension(driver)
    print("[INFO] Расширение готово к работе.")
    
    # Здесь ваш основной цикл Freelancehunt
    # Например: login(driver), make_bid(...)

    driver.quit()

if __name__ == "__main__":
    asyncio.run(main())
