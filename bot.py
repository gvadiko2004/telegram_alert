import os
import time
import requests

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException

from telethon import TelegramClient, events

# ==============================
# 🔑 НАСТРОЙКИ
# ==============================

# === 2captcha ключ ===
API_KEY_2CAPTCHA = "898059857fb8c709ca5c9613d44ffae4"  # 👉 сюда вставь свой ключ от 2captcha

# === Данные для Telegram (получишь в my.telegram.org) ===
api_id = 21882740   # 👉 вставь сюда свой api_id
api_hash = "c80a68894509d01a93f5acfeabfdd922"
phone = "+380634646075"  # 👉 свой номер

# === Настройки браузера Chrome ===
chrome_options = Options()
chrome_options.add_argument("--no-sandbox")
chrome_options.add_argument("--disable-dev-shm-usage")
chrome_options.add_argument("--disable-blink-features=AutomationControlled")
chrome_options.add_argument("--headless")  # 👉 если нужно без интерфейса

driver = webdriver.Chrome(service=Service("/usr/local/bin/chromedriver"), options=chrome_options)



# ==============================
# 🔹 ФУНКЦИИ ДЛЯ РАБОТЫ С КАПЧЕЙ
# ==============================

def solve_recaptcha_v2(sitekey, url):
    """
    Отправляем задачу на 2captcha и получаем токен
    """
    print("[INFO] Отправляем задачу на 2captcha...")

    resp = requests.post(
        "http://2captcha.com/in.php",
        data={
            "key": API_KEY_2CAPTCHA,
            "method": "userrecaptcha",
            "googlekey": sitekey,   # sitekey берется из кода страницы
            "pageurl": url,
            "json": 1
        }
    ).json()

    if resp["status"] != 1:
        print("[ERROR] Не удалось отправить задачу:", resp)
        return None

    request_id = resp["request"]

    # Ждём решения
    for i in range(20):
        time.sleep(5)
        res = requests.get(
            f"http://2captcha.com/res.php?key={API_KEY_2CAPTCHA}&action=get&id={request_id}&json=1"
        ).json()

        if res["status"] == 1:
            print("[INFO] Капча решена!")
            return res["request"]

    print("[ERROR] Время ожидания вышло!")
    return None


def bypass_captcha(site_url):
    """
    Универсальная функция для обхода капчи
    """
    try:
        # Находим sitekey капчи (в HTML-коде страницы)
        sitekey = driver.find_element(By.CLASS_NAME, "g-recaptcha").get_attribute("data-sitekey")
        token = solve_recaptcha_v2(sitekey, site_url)

        if token:
            # Записываем токен в textarea reCAPTCHA
            driver.execute_script(
                f'document.getElementById("g-recaptcha-response").style.display="";'
                f'document.getElementById("g-recaptcha-response").value="{token}";'
            )
            print("[INFO] Токен вставлен в форму")
        else:
            print("[ERROR] Капча не решена!")

    except Exception as e:
        print("[INFO] Капча не найдена или ошибка:", e)


# ==============================
# 🔹 ЛОГИКА БОТА
# ==============================

# Пример: открываем сайт и обходим капчу
def open_site_and_login():
    url = "https://freelancehunt.com/ua/profile/login"  # 👉 сюда свой сайт
    driver.get(url)

    try:
        # Ждём появления формы
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.ID, "login-form"))
        )
        print("[INFO] Форма логина найдена")

        # Пример: заполняем поля
        driver.find_element(By.ID, "username").send_keys("мой_логин")
        driver.find_element(By.ID, "password").send_keys("мой_пароль")

        # Если есть капча — решаем
        bypass_captcha(url)

        # Жмём кнопку входа
        driver.find_element(By.ID, "login-button").click()
        print("[INFO] Логин выполнен!")

    except TimeoutException:
        print("[ERROR] Форма логина не найдена!")


# ==============================
# 🔹 TELEGRAM
# ==============================
client = TelegramClient("session_name", api_id, api_hash)

@client.on(events.NewMessage)
async def handler(event):
    text = event.message.message
    print(f"[TG] Новое сообщение: {text}")

    if "#зайти" in text:
        open_site_and_login()
        await event.reply("✅ Попытка входа выполнена!")


# ==============================
# 🔹 ЗАПУСК
# ==============================
def main():
    print("[START] Бот запущен...")
    with client:
        client.run_until_disconnected()


if __name__ == "__main__":
    main()
