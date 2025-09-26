#!/usr/bin/env python3
# coding: utf-8
"""
Visible Chrome Freelancehunt bidding bot
Полная русская отладка в терминале: этапы, капча (обнаружена/решена/не решена/заблокирована)
"""

import os
import re
import time
import random
import pickle
import asyncio
import socket
from pathlib import Path
from typing import Optional

from twocaptcha import TwoCaptcha
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException, WebDriverException

from webdriver_manager.chrome import ChromeDriverManager
from telethon import TelegramClient, events
from telegram import Bot

# ---------------------- КОНФИГ (взято из твоего кода) ----------------------
API_ID = 21882740
API_HASH = "c80a68894509d01a93f5acfeabfdd922"
ALERT_BOT_TOKEN = "6566504110:AAFK9hA4jxZ0eA7KZGhVvPe8mL2HZj2tQmE"
ALERT_CHAT_ID = 1168962519

CAPTCHA_API_KEY = "898059857fb8c709ca5c9613d44ffae4"

HEADLESS = False                # Видимый Chrome (чтобы было видно в MobaXterm / X11)
LOGIN_URL = "https://freelancehunt.com/ua/profile/login"
LOGIN_DATA = {"login": "Vlari", "password": "Gvadiko_2004"}

COOKIES_FILE = "fh_cookies.pkl"

COMMENT_TEXT = (
    "Доброго дня! Готовий виконати роботу якісно.\n"
    "Портфоліо робіт у моєму профілі.\n"
    "Заздалегідь дякую!"
)

KEYWORDS = [k.lower() for k in [
    "#html_и_css_верстка","#веб_программирование","#cms",
    "#интернет_магазины_и_электронная_коммерция","#создание_сайта_под_ключ","#дизайн_сайтов"
]]

# ---------------------- ИНИЦИАЛИЗАЦИЯ ----------------------
alert_bot = Bot(token=ALERT_BOT_TOKEN)
tg_client = TelegramClient("session", API_ID, API_HASH)
solver = None
if CAPTCHA_API_KEY:
    try:
        solver = TwoCaptcha(CAPTCHA_API_KEY)
        print("[STEP] 2Captcha инициализирован.")
    except Exception as e:
        solver = None
        print("[WARN] Не удалось инициализировать 2Captcha:", e)
else:
    print("[WARN] Ключ 2Captcha не задан.")

# ---------------------- УТИЛИТЫ / ДРАЙВЕР ----------------------
def ensure_dns(host="freelancehunt.com"):
    try:
        ip = socket.gethostbyname(host)
        print(f"[СЕТЬ] DNS: {host} -> {ip}")
        return True
    except Exception as e:
        print("[СЕТЬ] Ошибка DNS:", e)
        return False

def tmp_profile():
    p = f"/tmp/chrome-{int(time.time())}-{random.randint(0,9999)}"
    Path(p).mkdir(parents=True, exist_ok=True)
    return p

def make_driver():
    profile = tmp_profile()
    opts = Options()
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--window-size=1366,900")
    if HEADLESS:
        opts.add_argument("--headless=new")
    opts.add_argument(f"--user-data-dir={profile}")
    opts.add_experimental_option("excludeSwitches", ["enable-automation"])
    opts.add_experimental_option("useAutomationExtension", False)
    svc = Service(ChromeDriverManager().install())
    try:
        d = webdriver.Chrome(service=svc, options=opts)
        d.set_page_load_timeout(60)
        print(f"[STEP] Chrome готов. Видимый режим: {not HEADLESS}. Профиль: {profile}")
        return d
    except WebDriverException as e:
        print("[FATAL] Не удалось запустить Chrome:", e)
        raise

driver = make_driver()

def wait_for_body(timeout=20):
    try:
        WebDriverWait(driver, timeout).until(EC.presence_of_element_located((By.TAG_NAME, "body")))
        time.sleep(0.3)
    except TimeoutException:
        print("[WARN] Таймаут загрузки страницы (body).")

def save_cookies():
    try:
        with open(COOKIES_FILE, "wb") as f:
            pickle.dump(driver.get_cookies(), f)
        print("[COOKIE] Cookies сохранены.")
    except Exception as e:
        print("[COOKIE] Ошибка сохранения cookies:", e)

def load_cookies():
    if not os.path.exists(COOKIES_FILE):
        return False
    try:
        with open(COOKIES_FILE, "rb") as f:
            cookies = pickle.load(f)
        for c in cookies:
            try:
                driver.add_cookie(c)
            except Exception:
                pass
        print("[COOKIE] Cookies загружены.")
        return True
    except Exception as e:
        print("[COOKIE] Ошибка загрузки cookies:", e)
        return False

def human_type(el, text, delay=(0.04,0.12)):
    for ch in text:
        el.send_keys(ch)
        time.sleep(random.uniform(*delay))

def human_scroll_and_move():
    try:
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight * 0.3);")
        time.sleep(random.uniform(0.15,0.4))
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight * 0.6);")
        time.sleep(random.uniform(0.15,0.4))
        ActionChains(driver).move_by_offset(random.randint(1,50), random.randint(1,50)).perform()
    except Exception:
        pass

# ---------------------- CAPTCHA helpers ----------------------
def page_has_captcha_text():
    try:
        body = driver.find_element(By.TAG_NAME, "body").text.lower()
        return "captcha" in body or "капча" in body or "protection" in body or "проверка" in body
    except Exception:
        return False

def find_recaptcha_sitekey() -> Optional[str]:
    try:
        elems = driver.find_elements(By.CSS_SELECTOR, "[data-sitekey]")
        for e in elems:
            sk = e.get_attribute("data-sitekey")
            if sk:
                return sk
    except Exception:
        pass
    # Пробуем iframe src
    try:
        iframes = driver.find_elements(By.TAG_NAME, "iframe")
        for f in iframes:
            src = f.get_attribute("src") or ""
            if "sitekey=" in src:
                m = re.search(r"(?:sitekey|k)=([A-Za-z0-9_-]+)", src)
                if m:
                    return m.group(1)
    except Exception:
        pass
    return None

def solve_recaptcha_and_inject(sitekey, pageurl, poll_interval=5, timeout=180):
    if solver is None:
        print("[CAPTCHA] 2Captcha не инициализирован. Решение невозможно.")
        return False, "solver-missing"
    print("[CAPTCHA] Отправляю задание на 2Captcha...")
    try:
        res = solver.recaptcha(sitekey=sitekey, url=pageurl, invisible=0)
        token = None
        if isinstance(res, dict):
            token = res.get("code") or res.get("request")
        elif isinstance(res, str):
            token = res
        if not token:
            print("[CAPTCHA] 2Captcha вернула пустой токен.")
            return False, "no-token"
        # вставляем токен в g-recaptcha-response
        print("[CAPTCHA] Токен получен, инжектим в страницу...")
        driver.execute_script("""
            (function(t){
                var el = document.getElementById('g-recaptcha-response');
                if(!el){
                    el = document.createElement('textarea');
                    el.id='g-recaptcha-response';
                    el.name='g-recaptcha-response';
                    el.style.display='none';
                    document.body.appendChild(el);
                }
                el.innerHTML = t;
            })(arguments[0]);
            """, token)
        time.sleep(1)
        # пробуем сабмитнуть ближайшую форму
        try:
            btn = driver.find_element(By.CSS_SELECTOR, "form button[type='submit'], form input[type='submit']")
            driver.execute_script("arguments[0].click();", btn)
            print("[CAPTCHA] Нажали на кнопку отправки формы после инжекта токена.")
        except Exception:
            try:
                driver.execute_script("document.querySelectorAll('form').forEach(f=>f.submit());")
                print("[CAPTCHA] Отправили все формы через JS.submit().")
            except Exception:
                print("[CAPTCHA] Не удалось автоматически сабмитнуть форму после инжекта.")
        # даём время проверить, сработало ли
        time.sleep(2)
        # проверяем — ушла ли капча
        if page_has_captcha_text():
            print("[CAPTCHA] После инжекта токена страница всё ещё содержит текст 'captcha' -> возможно блокировка.")
            return False, "still-captcha"
        print("[CAPTCHA] Возможно успешно решено (страница не содержит 'captcha').")
        return True, "ok"
    except Exception as e:
        print("[CAPTCHA] Ошибка при работе с 2Captcha:", e)
        return False, "exception"

# ---------------------- LOGIN ----------------------
def is_logged():
    try:
        driver.find_element(By.CSS_SELECTOR, "a[href='/profile']")
        return True
    except NoSuchElementException:
        return False

def login_if_needed():
    print("[LOGIN] Проверяю авторизацию...")
    try:
        driver.get("https://freelancehunt.com/")
        wait_for_body()
        load_cookies()
        driver.refresh()
        wait_for_body()
    except Exception as e:
        print("[LOGIN] Ошибка при загрузке главной для cookies:", e)
    if is_logged():
        print("[LOGIN] Уже залогинен.")
        return True
    print("[LOGIN] Не залогинен — перехожу на страницу логина.")
    try:
        driver.get(LOGIN_URL)
        wait_for_body()
        # заполняем форму логина
        el_login = WebDriverWait(driver, 8).until(EC.presence_of_element_located((By.ID, "login-0")))
        el_pass = driver.find_element(By.ID, "password-0")
        el_btn = driver.find_element(By.ID, "save-0")
        human_type(el_login, LOGIN_DATA["login"])
        human_type(el_pass, LOGIN_DATA["password"])
        human_scroll_and_move()
        driver.execute_script("arguments[0].click();", el_btn)
        time.sleep(2)
        wait_for_body()
        # если появилась капча при логине
        if page_has_captcha_text() or find_recaptcha_sitekey():
            sk = find_recaptcha_sitekey()
            if sk:
                print("[LOGIN] reCAPTCHA обнаружена на странице логина. Пытаюсь решить...")
                ok, why = solve_recaptcha_and_inject(sk, driver.current_url)
                print(f"[LOGIN] Статус 2Captcha: {ok}, код: {why}")
                if not ok:
                    print("[LOGIN] 2Captcha не помогла при логине.")
        save_cookies()
        if is_logged():
            print("[LOGIN] Успешно залогинились.")
            return True
        else:
            print("[LOGIN] После попытки залогиниться — не найден профиль, возможна блокировка.")
            return False
    except Exception as e:
        print("[LOGIN] Ошибка во время логина:", e)
        return False

# ---------------------- BIDDING (основная логика) ----------------------
async def send_alert(msg: str):
    try:
        await alert_bot.send_message(chat_id=ALERT_CHAT_ID, text=msg)
        print("[ALERT -> TG]", msg)
    except Exception as e:
        print("[ALERT] Не удалось отправить Telegram-уведомление:", e)

async def make_bid(url: str):
    print(f"[JOB] Начинаю обработку: {url}")
    try:
        if not ensure_dns():
            await send_alert(f"⚠️ DNS ошибка, не могу открыть {url}")
            return
        # сначала убеждаемся, что залогинены (загружаем cookies и логинимся при необходимости)
        if not login_if_needed():
            await send_alert(f"❌ Не удалось пройти логин перед открытием проекта: {url}")
            return
        # теперь открываем сам проект
        print("[JOB] Открываю страницу проекта...")
        driver.get(url)
        wait_for_body()
        time.sleep(0.6)
        # если сайт редиректит не на проект — выходим
        cur = driver.current_url
        if "/project/" not in cur:
            print("[JOB] Предупреждение: URL после открытия отличается:", cur)
            # попытаемся ещё раз после краткой паузы
            time.sleep(1)
            driver.get(url); wait_for_body()
            if "/project/" not in driver.current_url:
                print("[JOB] После повторной загрузки URL всё ещё некорректен — прерываю задачу.")
                await send_alert(f"❌ Редирект при открытии проекта: {url}")
                return
        # проверяем капчу на странице проекта
        if page_has_captcha_text() or find_recaptcha_sitekey():
            print("[JOB] На странице проекта обнаружена капча.")
            sk = find_recaptcha_sitekey()
            if sk:
                ok, why = solve_recaptcha_and_inject(sk, driver.current_url)
                print(f"[JOB] Результат 2Captcha: {ok} ({why})")
                if not ok:
                    await send_alert(f"⚠️ 2Captcha не смогла решить капчу на {url} ({why})")
                    return
            else:
                await send_alert(f"⚠️ На странице {url} есть защита, требующая ручного решения.")
                return
        # КЛИК: "Сделать ставку" (id="add-bid")
        try:
            print("[JOB] Ищу кнопку 'Сделать ставку' (id=add-bid) и кликаю...")
            btn = WebDriverWait(driver, 10).until(EC.element_to_be_clickable((By.ID, "add-bid")))
            driver.execute_script("arguments[0].scrollIntoView({block:'center'});", btn)
            time.sleep(0.12)
            driver.execute_script("arguments[0].click();", btn)
            time.sleep(0.6)
        except Exception as e:
            print("[JOB] Не удалось найти/кликнуть 'Сделать ставку':", e)
            await send_alert(f"❌ Кнопка 'Сделать ставку' не найдена на {url}")
            return
        # СКРОЛЛ и ожидание формы
        human_scroll_and_move()
        time.sleep(0.4)
        # Если есть span с ценой — парсим цифры
        amount_value = "1111"
        try:
            # селектор, который ты дал: span.text-green.bold.pull-right.price (возможны вариации)
            print("[JOB] Проверяю наличие бюджетного спана (цены) на странице...")
            span = driver.find_element(By.CSS_SELECTOR, "span.text-green.bold.pull-right.price")
            raw = span.text.strip()
            print(f"[JOB] Найден span с ценой: '{raw}'")
            # извлекаем цифры и точки/запятые -> заменяем запятую на точку и убираем пробелы
            num = re.sub(r"[^\d,\.]", "", raw).replace(",", ".").strip()
            if num:
                # иногда значение "400 PLN" может быть с NBSP и пробелами; оставляем только цифры и точку
                # также, если есть тысячные пробелы — удаляем
                num = num.replace("\u202f", "").replace(" ", "")
                # если в num есть точка и дробная часть — оставляем, иначе целое
                amount_value = num
                print(f"[JOB] parsed amount: {amount_value}")
            else:
                print("[JOB] Не удалось распарсить сумму, использую дефолт:", amount_value)
        except NoSuchElementException:
            print("[JOB] Span с ценой не найден, использую дефолт:", amount_value)
        except Exception as e:
            print("[JOB] Ошибка при парсинге суммы:", e, " — берем дефолт", amount_value)
        # Заполняем поля формы: amount-0, days_to_deliver-0, comment-0
        try:
            print("[JOB] Жду поле 'amount-0' и заполняю сумму:", amount_value)
            el_amount = WebDriverWait(driver, 8).until(EC.presence_of_element_located((By.ID, "amount-0")))
            el_days = driver.find_element(By.ID, "days_to_deliver-0")
            el_comment = driver.find_element(By.ID, "comment-0")
            # очищаем и вводим
            try:
                el_amount.clear()
            except Exception: pass
            human_type(el_amount, str(amount_value))
            try:
                el_days.clear()
            except Exception: pass
            human_type(el_days, "3")
            human_type(el_comment, COMMENT_TEXT, delay=(0.02,0.06))
            time.sleep(0.3)
        except Exception as e:
            print("[JOB] Ошибка при поиске/заполнении полей формы:", e)
            await send_alert(f"❌ Поля формы не найдены/не заполнились на {url}")
            return
        # Финальный клик — строго кнопка с id btn-submit-0
        try:
            print("[JOB] Ищу кнопку 'Добавить' (id=btn-submit-0) и кликаю...")
            submit = WebDriverWait(driver, 8).until(EC.element_to_be_clickable((By.ID, "btn-submit-0")))
            driver.execute_script("arguments[0].scrollIntoView({block:'center'});", submit)
            time.sleep(0.12)
            driver.execute_script("arguments[0].click();", submit)
            print("[JOB] Нажал 'Добавить'. Жду подтверждения отправки...")
            time.sleep(1.2)
            # можно проверить, появилась ли нотификация об успехе, но сайт разный — отправим alert
            await send_alert(f"✅ Ставка отправлена: {url} (сумма: {amount_value})")
            save_cookies()
            print("[JOB] Готово: ставка отправлена.")
        except Exception as e:
            print("[JOB] Не удалось кликнуть кнопку 'Добавить':", e)
            await send_alert(f"❌ Не удалось нажать 'Добавить' на {url}")
            return
    except Exception as e:
        print("[ERROR] Внутренняя ошибка make_bid:", e)
        await send_alert(f"❌ Внутренняя ошибка при обработке {url}: {e}")

# ---------------------- TELEGRAM HANDLER ----------------------
def extract_links(text):
    return [ln for ln in re.findall(r"https?://[^\s]+", text) if "freelancehunt.com" in ln]

@tg_client.on(events.NewMessage)
async def on_msg(event):
    text = (event.message.text or "").lower()
    print("[TG] Получено сообщение:", text[:200])
    links = extract_links(text)
    if links and any(k in text for k in KEYWORDS):
        url = links[0]
        print("[TG] Триггер: ключевые слова найдены, запускаю задачу для:", url)
        asyncio.create_task(make_bid(url))
    else:
        print("[TG] Сообщение не содержит нужных ключевых слов или ссылок — пропускаю.")

# ---------------------- MAIN ----------------------
async def main():
    print("[STEP] Старт бота. Проверяю DNS...")
    ensure_dns()
    # preload cookies (если есть)
    if os.path.exists(COOKIES_FILE):
        try:
            print("[STEP] Предзагрузка cookies...")
            driver.get("https://freelancehunt.com/")
            wait_for_body()
            load_cookies()
            driver.refresh()
            time.sleep(0.6)
            print("[STEP] Cookies предзагружены.")
        except Exception as e:
            print("[STEP] Ошибка при предзагрузке cookies:", e)
    # старт Telethon
    try:
        await tg_client.start()
        print("[STEP] Telegram-клиент запущен. Жду сообщений...")
        await tg_client.run_until_disconnected()
    except Exception as e:
        print("[FATAL] Ошибка старта Telethon:", e)
        raise

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Выход по Ctrl-C")
    finally:
        try:
            driver.quit()
        except Exception:
            pass
