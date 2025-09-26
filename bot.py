#!/usr/bin/env python3
# coding: utf-8

import asyncio
import re
import time
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
from telethon import TelegramClient, events
from telegram import Bot
from webdriver_manager.chrome import ChromeDriverManager

# ---------------- CONFIG ----------------
API_ID = 21882740
API_HASH = "c80a68894509d01a93f5acfeabfdd922"
ALERT_BOT_TOKEN = "6566504110:AAFK9hA4jxZ0eA7KZGhVvPe8mL2HZj2tQmE"
ALERT_CHAT_ID = 1168962519
HEADLESS = True

# ---------------- Telegram ----------------
alert_bot = Bot(token=ALERT_BOT_TOKEN)
tg_client = TelegramClient("session", API_ID, API_HASH)

# ---------------- Selenium ----------------
def create_driver():
    options = Options()
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    if HEADLESS:
        options.add_argument("--headless=new")
    options.add_argument("--window-size=1366,900")
    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=options)
    driver.set_page_load_timeout(30)
    print("[STEP] Chrome ready")
    return driver

driver = create_driver()

# ---------------- Helpers ----------------
def extract_links(text: str):
    text = text.replace("*", "")  # убираем звёздочки
    return [ln for ln in re.findall(r"https?://[^\s]+", text) if "freelancehunt.com" in ln]

async def send_alert(msg: str):
    safe_msg = msg.replace("*", "").replace("_", "").replace("`", "")
    try:
        await alert_bot.send_message(chat_id=ALERT_CHAT_ID, text=safe_msg, parse_mode=None)
        print("[TG ALERT]", safe_msg)
    except Exception as e:
        print("[TG ERROR]", e)

async def make_bid(url: str):
    try:
        print("[STEP] Opening URL:", url)
        driver.get(url)
        WebDriverWait(driver, 15).until(EC.presence_of_element_located((By.TAG_NAME, "body")))
        print("[STEP] Page loaded")
        await send_alert(f"✅ URL открыт: {url}")
    except TimeoutException:
        await send_alert(f"❌ Страница не загрузилась: {url}")
    except Exception as e:
        await send_alert(f"❌ Ошибка: {e}\n{url}")

# ---------------- Telegram Event ----------------
@tg_client.on(events.NewMessage)
async def on_msg(event):
    text = event.message.text or ""
    print("[TG MESSAGE]", text)
    links = extract_links(text)
    if links:
        await make_bid(links[0])

# ---------------- Main ----------------
async def main():
    print("[STEP] Starting bot...")
    await tg_client.start()
    print("[STEP] Telegram client ready. Waiting for messages...")
    await tg_client.run_until_disconnected()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Exiting by user")
    finally:
        try:
            driver.quit()
        except Exception:
            pass
