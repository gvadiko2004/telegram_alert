#!/usr/bin/env python3
# coding: utf-8
"""
Telegram -> Selenium bot for Freelancehunt
Поведение:
- слушает Telegram (Telethon), при получении сообщения с ключевым словом
  извлекает ВСЕ ссылки (текст, entities, inline-кнопки),
  пробует открыть каждую ссылку в видимом Chrome и выполнить ставку.
- логирование на русском, тихая обработка отсутствующих элементов.
- решает reCAPTCHA через 2captcha (если ключ указан).
"""

import os, time, random, pickle, asyncio, socket, re
from pathlib import Path
from twocaptcha import TwoCaptcha
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from webdriver_manager.chrome import ChromeDriverManager
from telethon import TelegramClient, events
from telegram import Bot

# ---------------- CONFIG ----------------
API_ID, API_HASH = 21882740, "c80a68894509d01a93f5acfeabfdd922"
ALERT_BOT_TOKEN, ALERT_CHAT_ID = "6566504110:AAFK9hA4jxZ0eA7KZGhVvPe8mL2HZj2tQmE", 1168962519

# твой 2captcha API ключ
CAPTCHA_API_KEY = "898059857fb8c709ca5c9613d44ffae4"

# ВИДИМЫЙ БРАУЗЕР (чтобы ты видел действия через MobaXterm/X11)
HEADLESS = False

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

# ---------------- INIT ----------------
alert_bot = Bot(token=ALERT_BOT_TOKEN)
tg_client = TelegramClient("session", API_ID, API_HASH)
solver = None  # инициализируем ниже, если ключ есть

# ---------------- HELPERS / LOG ----------------
def log(msg: str):
    print(f"[ЛОГ] {msg}")

def ensure_dns(host="freelancehunt.com") -> bool:
    try:
        ip = socket.gethostbyname(host)
        log(f"DNS OK: {host} -> {ip}")
        return True
    except Exception:
        log(f"DNS НЕУДАЛОСЬ: {host}")
        return False

def make_tmp_profile() -> str:
    tmp = os.path.join("/tmp", f"chrome-temp-{int(time.time())}-{random.randint(0,9999)}")
    Path(tmp).mkdir(parents=True, exist_ok=True)
    return tmp

def create_driver() -> webdriver.Chrome:
    opts = Options()
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--window-size=1366,900")
    if HEADLESS:
        opts.add_argument("--headless=new")
    # уникальный профиль
    opts.add_argument(f"--user-data-dir={make_tmp_profile()}")
    opts.add_experimental_option("excludeSwitches", ["enable-automation"])
    opts.add_experimental_option("useAutomationExtension", False)
    svc = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=svc, options=opts)
    driver.set_page_load_timeout(60)
    log(f"Chrome готов, HEADLESS={HEADLESS}")
    return driver

driver = create_driver()

def wait_body(timeout=20):
    try:
        WebDriverWait(driver, timeout).until(EC.presence_of_element_located((By.TAG_NAME, "body")))
        time.sleep(0.3)
    except TimeoutException:
        log("Таймаут загрузки страницы (wait_body)")

def human_type(el, text, delay=(0.04,0.12)):
    try:
        for ch in text:
            el.send_keys(ch)
            time.sleep(random.uniform(*delay))
    except Exception:
        # тихо пропускаем ошибки ввода (элемент мог исчезнуть)
        pass

def human_scroll_and_move():
    try:
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight*0.3);")
        time.sleep(random.uniform(0.15, 0.4))
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight*0.6);")
        ActionChains(driver).move_by_offset(random.randint(1,50), random.randint(1,50)).perform()
    except Exception:
        pass

def save_cookies():
    try:
        with open(COOKIES_FILE, "wb") as f:
            pickle.dump(driver.get_cookies(), f)
        log("Куки сохранены")
    except Exception:
        pass

def load_cookies() -> bool:
    if not os.path.exists(COOKIES_FILE):
        return False
    try:
        with open(COOKIES_FILE, "rb") as f:
            for c in pickle.load(f):
                try:
                    driver.add_cookie(c)
                except Exception:
                    pass
        log("Куки загружены")
        return True
    except Exception:
        return False

def is_logged_in() -> bool:
    try:
        driver.find_element(By.CSS_SELECTOR, "a[href='/profile']")
        return True
    except Exception:
        return False

# ---------------- LOGIN (robust) ----------------
def login_if_needed() -> bool:
    try:
        driver.get(LOGIN_URL)
        wait_body()
        load_cookies()
        if is_logged_in():
            log("Уже авторизован")
            return True

        # пробуем несколько вариантов селекторов, чтобы не ловить no such element
        # 1) name=login и name=password
        try:
            login_field = WebDriverWait(driver, 6).until(EC.presence_of_element_located((By.NAME, "login")))
            passwd_field = driver.find_element(By.NAME, "password")
            submit = None
            # возможный submit
            try:
                submit = driver.find_element(By.CSS_SELECTOR, "button[type='submit']")
            except Exception:
                pass
            human_type(login_field, LOGIN_DATA["login"])
            human_type(passwd_field, LOGIN_DATA["password"])
            if submit:
                try:
                    submit.click()
                except Exception:
                    driver.execute_script("arguments[0].click();", submit)
            else:
                # если нет кнопки, отправим Enter в поле пароля
                passwd_field.send_keys("\n")
            time.sleep(2)
            wait_body()
            if is_logged_in():
                save_cookies()
                log("Авторизация успешна")
                return True
            else:
                log("Авторизация неуспешна — проверяй селекторы / страницу")
                return False
        except Exception:
            # второй вариант: id=login-0 / id=password-0
            try:
                lf = driver.find_element(By.ID, "login-0")
                pf = driver.find_element(By.ID, "password-0")
                btn = driver.find_element(By.ID, "save-0")
                human_type(lf, LOGIN_DATA["login"])
                human_type(pf, LOGIN_DATA["password"])
                try:
                    btn.click()
                except Exception:
                    driver.execute_script("arguments[0].click();", btn)
                time.sleep(2)
                wait_body()
                if is_logged_in():
                    save_cookies()
                    log("Авторизация успешна (второй вариант селекторов)")
                    return True
            except Exception:
                log("Авторизация: не удалось найти поля (страница могла измениться)")
                return False
    except Exception as e:
        log(f"Авторизация: неожиданная ошибка: {e}")
        return False

# ---------------- CAPTCHA (2captcha) ----------------
def init_captcha():
    global solver
    if CAPTCHA_API_KEY:
        try:
            solver = TwoCaptcha(CAPTCHA_API_KEY)
            log("Анти-капча инициализирована и готова к работе")
        except Exception as e:
            solver = None
            log(f"Анти-капча: ошибка инициализации: {e}")
    else:
        solver = None
        log("Анти-капча: ключ не задан — капча отключена")

def try_solve_recaptcha():
    """Если на странице есть iframe recaptcha — попытаемся решить и инжектить токен."""
    if solver is None:
        return False
    try:
        iframes = driver.find_elements(By.TAG_NAME, "iframe")
        for f in iframes:
            src = f.get_attribute("src") or ""
            if "recaptcha" in src or "google.com/recaptcha" in src:
                log("Обнаружен iframe reCAPTCHA на странице")
                m = re.search(r"sitekey=([A-Za-z0-9_-]+)", src)
                if not m:
                    # иногда ключ спрятан в data-sitekey элемента
                    try:
                        el = driver.find_element(By.CSS_SELECTOR, "[data-sitekey]")
                        sitekey = el.get_attribute("data-sitekey")
                    except Exception:
                        sitekey = None
                else:
                    sitekey = m.group(1)
                if not sitekey:
                    log("Не удалось извлечь sitekey reCAPTCHA")
                    return False
                log(f"Отправляю задачу на 2captcha, sitekey={sitekey}")
                try:
                    res = solver.recaptcha(sitekey=sitekey, url=driver.current_url)
                    token = None
                    if isinstance(res, dict):
                        token = res.get("code") or res.get("request")
                    elif isinstance(res, str):
                        token = res
                    if not token:
                        log("2captcha вернул пустой токен")
                        return False
                    # инжектим токен в g-recaptcha-response
                    driver.execute_script("""
                    (function(token){
                        var el = document.getElementById('g-recaptcha-response');
                        if(!el){
                            el = document.createElement('textarea');
                            el.id = 'g-recaptcha-response';
                            el.name = 'g-recaptcha-response';
                            el.style.display = 'none';
                            document.body.appendChild(el);
                        }
                        el.innerHTML = token;
                    })(arguments[0]);
                    """, token)
                    time.sleep(1)
                    # Попробуем сабмитнуть ближайшую форму
                    try:
                        btn = driver.find_element(By.CSS_SELECTOR, "form button[type='submit'], form input[type='submit']")
                        driver.execute_script("arguments[0].click();", btn)
                    except Exception:
                        try:
                            driver.execute_script("document.querySelectorAll('form').forEach(f=>f.submit());")
                        except Exception:
                            pass
                    log("Капча решена (токен инжектирован)")
                    return True
                except Exception as e:
                    log(f"2captcha ошибка: {e}")
                    return False
        # если iframe не найден
        return False
    except Exception as e:
        log(f"try_solve_recaptcha: ошибка: {e}")
        return False

# ---------------- EXTRACT LINKS (text + entities + buttons) ----------------
url_regex = re.compile(r"https?://[^\s\)\]\}]+", re.IGNORECASE)

def extract_urls_from_message_object(message) -> list:
    """
    Собирает все URL'ы из:
    - текстовой части сообщения (регексп)
    - inline-кнопок (btn.url)
    - текста кнопки (если в тексте кнопки есть URL)
    Возвращает уникальный list.
    """
    found = []

    # 1) текст сообщения (включая случаи "Текст (https://...)" )
    text = ""
    try:
        # telethon Message может иметь .message, .text, .raw_text
        text = message.text or ""
    except Exception:
        try:
            text = message.message or ""
        except Exception:
            text = ""

    if text:
        for m in url_regex.findall(text):
            found.append(m)

    # 2) entities: иногда ссылка хранится как entity (MessageEntityUrl/TextUrl) - прочитаем raw text уже покрывает большинство,
    #    но оставим на будущее (если нужно - можно дополнить).
    #    (Мы не используем низкоуровневые entities чтобы не падать при отсутствии типов)

    # 3) inline-кнопки (ищем .buttons у message)
    try:
        buttons = getattr(message, "buttons", None)
        if buttons:
            for row in buttons:
                # row — список кнопок
                for btn in row:
                    # Telethon InlineButton может иметь url или text
                    url = getattr(btn, "url", None)
                    if url and "freelancehunt.com" in url:
                        found.append(url)
                    else:
                        # возможно в тексте кнопки есть ссылка в формате "Текст (https://...)" — возьмём regex
                        btn_text = getattr(btn, "text", "") or ""
                        if btn_text:
                            for m in url_regex.findall(btn_text):
                                found.append(m)
    except Exception:
        pass

    # 4) убрать дубли и вернуть
    uniq = []
    for u in found:
        if u not in uniq:
            uniq.append(u)
    return uniq

# ---------------- BIDDING FLOW ----------------
async def send_alert(msg: str):
    try:
        await alert_bot.send_message(chat_id=ALERT_CHAT_ID, text=msg)
        log(f"TG ALERT: {msg}")
    except Exception:
        # тихо: если Telegram алерт не ушёл — просто лог
        log(f"TG ALERT: не отправлено: {msg}")

def page_has_already_bid() -> (bool, str):
    """Проверка блока 'Вы уже сделали ставку' — если найдено, вернуть (True, текст)."""
    try:
        el = driver.find_element(By.CSS_SELECTOR, "div.alert.alert-info")
        txt = el.text.strip()
        if txt:
            return True, txt
    except Exception:
        pass
    return False, ""

async def attempt_bid_on_url(url: str):
    """Один полный проход по ссылке: открыть, залогиниться, решить капчу, нажать 'Сделать ставку', заполнить и нажать 'Добавить'."""
    try:
        log(f"Открываю ссылку: {url}")
        driver.get(url)
        wait_body()
        load_cookies()

        # если не залогинен — залогиниться
        if not is_logged_in():
            ok = login_if_needed()
            if not ok:
                await send_alert(f"❌ Не удалось авторизоваться перед попыткой ставки: {url}")
                return False
            # после логина снова откроем страницу проекта
            driver.get(url)
            wait_body()

        # попробовать решить капчу, если есть
        try_solve_recaptcha()

        # проверить, не сделана ли уже ставка
        already, text = page_has_already_bid()
        if already:
            log(f"Ставка уже сделана/закрыта на странице: {text}")
            await send_alert(f"⚠️ Ставка уже сделана или закрыта: {url}\n{text}")
            return False

        # найти кнопку "Сделать ставку" и нажать
        clicked = False
        selectors = ["#add-bid", "a.with-tooltip.btn.btn-primary", "a.btn-primary:contains('Сделать ставку')"]
        # пробуем универсально: ищем элемент с id add-bid или кнопку по тексту
        try:
            btn = WebDriverWait(driver, 6).until(EC.element_to_be_clickable((By.ID, "add-bid")))
            try:
                btn.click()
            except Exception:
                driver.execute_script("arguments[0].click();", btn)
            clicked = True
            log("Нажата кнопка 'Сделать ставку' (id=add-bid)")
        except Exception:
            # пробуем найти по классу/тексту — универсальная попытка
            try:
                # стараемся найти любую кнопку с иконкой молотка и текстом
                candidates = driver.find_elements(By.CSS_SELECTOR, "a.btn, button.btn")
                for c in candidates:
                    txt = (c.text or "").lower()
                    if "ставк" in txt or "сделать" in txt:
                        try:
                            driver.execute_script("arguments[0].scrollIntoView({block:'center'})", c)
                            time.sleep(0.2)
                            c.click()
                            clicked = True
                            log("Нажата кнопка 'Сделать ставку' (fallback по тексту)")
                            break
                        except Exception:
                            try:
                                driver.execute_script("arguments[0].click();", c)
                                clicked = True
                                break
                            except Exception:
                                continue
            except Exception:
                pass

        if not clicked:
            log("Кнопка 'Сделать ставку' не найдена — пропускаю эту ссылку")
            return False

        time.sleep(0.8)
        human_scroll_and_move()

        # найти сумму: span.text-green.bold.pull-right.price
        amount = None
        try:
            span = driver.find_element(By.CSS_SELECTOR, "span.text-green.bold.pull-right.price")
            amount = re.sub(r"[^\d\.,]", "", span.text).replace(",", ".")
            # взять только числа и точку
            amount = re.sub(r"[^0-9\.]", "", amount)
            log(f"Определена сумма из страницы: {amount}")
        except Exception:
            amount = "1111"
            log("Не удалось определить сумму — используем стандартную: 1111")

        # заполняем форму (игнорируем отсутствие полей)
        try:
            amt_el = driver.find_element(By.ID, "amount-0")
            try:
                amt_el.clear()
            except Exception:
                pass
            human_type(amt_el, amount)
        except Exception:
            pass

        try:
            days_el = driver.find_element(By.ID, "days_to_deliver-0")
            try:
                days_el.clear()
            except Exception:
                pass
            human_type(days_el, "3")
        except Exception:
            pass

        try:
            comment_el = driver.find_element(By.ID, "comment-0")
            human_type(comment_el, COMMENT_TEXT, delay=(0.02, 0.07))
        except Exception:
            pass

        time.sleep(0.4)

        # финальный клик "Добавить" — ищем кнопку по id btn-submit-0 или общий селектор
        submitted = False
        try:
            submit_btn = driver.find_element(By.ID, "btn-submit-0")
            try:
                submit_btn.click()
            except Exception:
                driver.execute_script("arguments[0].click();", submit_btn)
            submitted = True
            log("Нажата кнопка 'Добавить' (id=btn-submit-0)")
        except Exception:
            # fallback: найти кнопку с классом btn-primary и текстом 'Добавить' / 'Добавити'
            try:
                candidates = driver.find_elements(By.CSS_SELECTOR, "button.btn.btn-primary, button.btn-primary, .btn-primary")
                for c in candidates:
                    txt = (c.text or "").lower()
                    if "добав" in txt or "додати" in txt:
                        try:
                            c.click()
                        except Exception:
                            try:
                                driver.execute_script("arguments[0].click();", c)
                            except Exception:
                                continue
                        submitted = True
                        log("Нажата кнопка 'Добавить' (fallback)")
                        break
            except Exception:
                pass

        if submitted:
            await send_alert(f"✅ Ставка отправлена: {url}")
            save_cookies()
            return True
        else:
            log("Не удалось найти/нажать кнопку 'Добавить'")
            return False

    except Exception as e:
        log(f"Ошибка в attempt_bid_on_url: {e}")
        await send_alert(f"❌ Ошибка при попытке ставки: {e}\n{url}")
        return False

# ---------------- TELEGRAM HANDLER ----------------
def gather_all_links_from_event(event) -> list:
    """
    Собирает ссылки из:
    - текста сообщения (включая ссылки в скобках)
    - inline-кнопок (btn.url и URL внутри текста кнопки)
    Возвращает список уникальных ссылок.
    """
    msg = event.message
    found = []

    # 1) текст сообщения (raw text)
    try:
        txt = ""
        # telethon может предоставлять .text или .message
        if getattr(msg, "text", None):
            txt = msg.text
        elif getattr(msg, "message", None):
            txt = msg.message
        else:
            txt = str(msg)
        for m in url_regex.findall(txt):
            found.append(m)
    except Exception:
        pass

    # 2) entities in message (если есть) — регексп обычно покрывает
    # 3) inline buttons
    try:
        buttons = getattr(msg, "buttons", None)
        if buttons:
            for row in buttons:
                for btn in row:
                    # btn may have .url or .data or .text
                    url = getattr(btn, "url", None)
                    if url and "freelancehunt.com" in url:
                        found.append(url)
                    else:
                        # попытка вытащить ссылку из текста кнопки
                        btn_text = getattr(btn, "text", "") or ""
                        for m in url_regex.findall(btn_text):
                            found.append(m)
    except Exception:
        pass

    # 4) убираем дубли
    uniq = []
    for u in found:
        if u not in uniq:
            uniq.append(u)
    return uniq

@tg_client.on(events.NewMessage)
async def handler_newmsg(event):
    try:
        raw_text = (event.message.text or "").lower() if getattr(event, "message", None) else ""
        # проверка ключевых слов в тексте (если нужно учитывать заголовок кнопки - отдельно)
        if any(k in raw_text for k in KEYWORDS):
            log("Ключевое слово найдено в сообщении — собираем ссылки")
            links = gather_all_links_from_event(event)
            if not links:
                log("Не найдено ссылок в тексте/кнопках — пробуем поиск ссылок в полной структуре сообщения")
                # дополнительный шаг: ищем ссылку через regex всего raw message (включая кнопки)
                try:
                    s = str(event.message)
                    for m in url_regex.findall(s):
                        if m not in links:
                            links.append(m)
                except Exception:
                    pass

            if not links:
                log("Ссылок не найдено — пропускаю сообщение")
                await send_alert("⚠️ Ключевое слово найдено, но ссылки не обнаружены в сообщении.")
                return

            log(f"Найдено ссылок: {len(links)}")
            # пробуем открыть/обработать каждую ссылку пока не получится отправить ставку
            for u in links:
                try:
                    ok = await attempt_bid_on_url(u)
                    if ok:
                        # если удалось успешно поставить — можно остановиться (или не останавливаемся, по желанию)
                        log(f"Успешно обработана ссылка: {u}")
                        break
                    else:
                        log(f"Не удалось поставить по ссылке: {u} — пробуем следующую")
                except Exception as e:
                    log(f"Ошибка при обработке ссылки {u}: {e}")
            return
        else:
            # если ключевое слово отсутствует — игнорируем
            return
    except Exception as e:
        log(f"handler_newmsg: unexpected error: {e}")

# ---------------- MAIN ----------------
async def main():
    ensure_dns()
    init_captcha()
    # preload cookies
    if os.path.exists(COOKIES_FILE):
        try:
            driver.get("https://freelancehunt.com")
            wait_body()
            load_cookies()
            driver.refresh()
            wait_body()
            log("Куки предварительно загружены")
        except Exception:
            pass
    await tg_client.start()
    log("Telegram клиент запущен, ожидаю сообщений...")
    await tg_client.run_until_disconnected()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        log("Завершение работы")
        try:
            driver.quit()
        except Exception:
            pass
