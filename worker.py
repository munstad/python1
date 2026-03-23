"""
TaskWorker — запускает мониторинг для одной задачи.
VFSMonitor — логинится через undetected-chromedriver, затем HTTP.
"""
import asyncio
import json
import logging
import os
import threading
import time
from datetime import datetime, date
from typing import Callable, Awaitable, Any

import requests
from selenium import webdriver
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
import structlog

log = structlog.get_logger()

MONITOR_INTERVAL = int(os.environ.get("MONITOR_INTERVAL_MS", "15000")) / 1000
VFS_API_BASE = "https://lift-api.vfsglobal.com"
VFS_LOGIN_PAGE = "https://visa.vfsglobal.com/rus/en/nld/login"


class VFSSession:
    """Хранит данные сессии после логина."""
    def __init__(self, access_token: str, cookies: dict, user_agent: str, email: str):
        self.access_token = access_token
        self.cookies = cookies
        self.user_agent = user_agent
        self.email = email

    def headers(self, content_type="application/json;charset=UTF-8") -> dict:
        return {
            "Content-Type": content_type,
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8",
            "Origin": "https://visa.vfsglobal.com",
            "Referer": "https://visa.vfsglobal.com/",
            "Route": "rus/en/nld",
            "Authorize": self.access_token,
            "User-Agent": self.user_agent,
        }


class VFSMonitor:
    """
    Логинится через undetected-chromedriver (обходит Cloudflare),
    перехватывает accessToken из ответа /user/login,
    затем проверяет слоты через HTTP API.
    """
    def _take_screenshot(self, driver, name):
        """Сохраняет скриншот для отладки."""
        os.makedirs("debug_screens", exist_ok=True)
        path = f"debug_screens/{name}_{int(time.time())}.png"
        driver.save_screenshot(path)
        log.info("debug.screenshot_saved", path=path)

    def __init__(self, task: dict):
        self.task = task
        self.email = task["vfs_email"]
        self.password = task["vfs_password"]
        self.visa_type = task.get("visa_type", "tourist")
        self.category = task.get("category", "standard")
        self.date_from = self._parse_date(task["date_from"])
        self.date_to = self._parse_date(task["date_to"])
        self.applicant_count = task.get("applicant_count", 1)
        self.proxy = os.environ.get("SITE_PROXY", "")

    @staticmethod
    def _parse_date(value) -> date:
        if isinstance(value, (int, float)):
            return date.fromtimestamp(value)
        for fmt in ("%d.%m.%Y", "%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%d/%m/%Y"):
            try:
                return datetime.strptime(value, fmt).date()
            except ValueError:
                continue
        return datetime.fromisoformat(value).date()

    def _visa_category_code(self) -> str:
        if self.visa_type in ("tourist", "business", "guest", "other"):
            return "SEA"
        if self.visa_type in ("student", "work"):
            return "LSV"
        return "SEA"

    def login(self) -> VFSSession:
        """
        Логин через Nstbrowser ConnectOnceBrowser — реальный Chrome обходит Cloudflare.
        API: https://apidocs.nstbrowser.io
        """
        import json as _json, urllib.request
        log.info("vfs.login.start", vfs_email=self.email)

        nst_api_key = os.environ.get("NSTBROWSER_API_KEY", "")
        nst_host = os.environ.get("NSTBROWSER_HOST", "http://nstbrowser:8848")
        if not nst_api_key:
            raise RuntimeError("NSTBROWSER_API_KEY не задан в .env")

        import urllib.parse
        from selenium import webdriver as _wd
        from selenium.webdriver.chrome.options import Options as _Options
        from selenium.webdriver.chrome.service import Service as _Service
        import shutil

        # ConnectOnceBrowser — запускаем one-shot браузер
        config = {
            "once": True,
            "headless": False,
            "autoClose": True,
            "platform": "Windows",
            "kernelMilestone": "122",
        }
        connect_url = (
            f"{nst_host}/api/v2/connect/once?"
            f"apikey={nst_api_key}&"
            f"config={urllib.parse.quote(_json.dumps(config))}"
        )
        log.info("vfs.nstbrowser.connecting", url=connect_url[:80])
        req = urllib.request.Request(connect_url, method="GET")
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                resp_data = _json.loads(resp.read())
        except Exception as e:
            raise RuntimeError(f"Nstbrowser connect failed: {e}")

        ws_url = resp_data.get("webSocketDebuggerUrl", "")
        if not ws_url:
            raise RuntimeError(f"No webSocketDebuggerUrl in response: {resp_data}")

        log.info("vfs.nstbrowser.connected", ws=ws_url[:60])

        # Подключаемся selenium к CDP endpoint браузера Nstbrowser
        # ws://host:port/devtools/browser/ID -> debuggerAddress = host:port
        debugger_addr = ws_url.replace("wss://", "").replace("ws://", "").split("/devtools/")[0]
        chrome_opts = _Options()
        chrome_opts.add_experimental_option("debuggerAddress", debugger_addr)

        chromedriver = shutil.which("chromedriver") or "/usr/bin/chromedriver"
        driver = _wd.Chrome(service=_Service(chromedriver), options=chrome_opts)

        try:
            driver.get("https://visa.vfsglobal.com/rus/en/nld/login")
            log.info("vfs.login.page_opened", url=driver.current_url)
            time.sleep(8)

            # Скриншот
            try:
                with open("/tmp/vfs_page.png", "wb") as f:
                    f.write(driver.get_screenshot_as_png())
                log.info("vfs.screenshot_saved", title=driver.title, url=driver.current_url)
            except Exception:
                pass

            wait = WebDriverWait(driver, 60)
            email_input = wait.until(EC.presence_of_element_located((
                By.CSS_SELECTOR, 'input[formcontrolname="username"], input[type="email"]'
            )))
            email_input.send_keys(self.email)
            driver.find_element(By.CSS_SELECTOR, 'input[formcontrolname="password"]').send_keys(self.password)
            time.sleep(2)
            driver.find_element(By.CSS_SELECTOR, 'button[type="submit"]').click()

            access_token = None
            for _ in range(20):
                access_token = driver.execute_script("return localStorage.getItem('accessToken')")
                if access_token:
                    break
                time.sleep(2)

            if not access_token:
                raise RuntimeError("accessToken не найден после входа")

            user_agent = driver.execute_script("return navigator.userAgent")
            cookies = {c["name"]: c["value"] for c in driver.get_cookies()}
            log.info("vfs.login.success", cookies_count=len(cookies))
            return VFSSession(access_token, cookies, user_agent, self.email)

        finally:
            try:
                driver.quit()
            except Exception:
                pass


    def check_slots(self, session: VFSSession) -> list[dict]:
        """Проверяет наличие слотов через HTTP API."""
        payload = {
            "countryCode": "rus",
            "missionCode": "nld",
            "loginUser": self.email,
            "vacCode": "NVAC",
            "visaCategoryCode": self._visa_category_code(),
            "payCode": "",
            "roleName": "Individual",
        }
        resp = requests.post(
            f"{VFS_API_BASE}/appointment/CheckIsSlotAvailable",
            json=payload,
            headers=session.headers(),
            cookies=session.cookies,
            timeout=30,
        )
        log.info("vfs.check_slots.response", status=resp.status_code)
        if resp.status_code >= 400:
            raise RuntimeError(f"check_slots HTTP {resp.status_code}: {resp.text[:300]}")

        data = resp.json()
        error = data.get("error")
        if error and error.get("code") == 1035:
            log.info("vfs.check_slots.no_slots")
            return []

        slots = []
        for s in data.get("earliestSlotLists", []):
            try:
                slot_date = datetime.strptime(s["appointmentDate"][:10], "%Y-%m-%d").date()
            except Exception:
                continue
            if self.date_from <= slot_date <= self.date_to:
                slots.append(s)
        return slots

    def book_slot(self, session: VFSSession, slot: dict) -> str:
        """Бронирует слот."""
        full_name = self.task.get("full_name", "")
        parts = full_name.split(" ", 1)
        first_name = parts[0] if parts else ""
        last_name = parts[1] if len(parts) > 1 else ""

        payload = {
            "countryCode": "rus",
            "missionCode": "nld",
            "loginUser": self.email,
            "vacCode": slot.get("vacCode", "NVAC"),
            "visaCategoryCode": slot.get("visaCategoryCode", self._visa_category_code()),
            "appointmentDate": slot["appointmentDate"],
            "appointmentTime": slot.get("appointmentTime", ""),
            "numberOfApplicants": self.applicant_count,
            "applicants": [{
                "firstName": first_name,
                "lastName": last_name,
                "dateOfBirth": self.task.get("birth_date", ""),
                "passportNumber": self.task.get("passport_no", ""),
                "passportExpiry": self.task.get("passport_exp", ""),
                "countryOfBirth": self.task.get("passport_country", ""),
                "contactNumber": self.task.get("phone", ""),
                "emailAddress": self.task.get("email", ""),
            }],
        }
        resp = requests.post(
            f"{VFS_API_BASE}/appointment/book",
            json=payload,
            headers=session.headers(),
            cookies=session.cookies,
            timeout=30,
        )
        if resp.status_code >= 400:
            raise RuntimeError(f"book HTTP {resp.status_code}: {resp.text[:300]}")

        data = resp.json()
        if data.get("error") and data["error"].get("code"):
            raise RuntimeError(f"book error: {data['error'].get('description')}")

        ref = data.get("confirmationNumber") or f"VFS-{slot['appointmentDate']}"
        log.info("vfs.book.success", ref=ref)
        return ref


class TaskWorker:
    """Управляет жизненным циклом одной задачи мониторинга."""

    def __init__(self, task: dict, notify: Callable[[dict], Awaitable[None]]):
        self.task = task
        self.task_id = task["task_id"]
        self.user_id = task.get("user_id")
        self.notify = notify
        self._stop_event = threading.Event()
        self.monitor = VFSMonitor(task)

    def stop(self):
        self._stop_event.set()

    async def run(self):
        log.info("task.run.start", task_id=self.task_id)
        await self.notify({
            "event": "monitoring.started",
            "task_id": self.task_id,
            "user_id": self.user_id,
            "message": "Мониторинг запущен",
        })

        consecutive_errors = 0

        while not self._stop_event.is_set():
            try:
                # Логин через браузер
                log.info("task.login", task_id=self.task_id)
                session = await asyncio.get_event_loop().run_in_executor(
                    None, self.monitor.login
                )

                # Проверяем слоты
                log.info("task.check_slots", task_id=self.task_id)
                slots = await asyncio.get_event_loop().run_in_executor(
                    None, self.monitor.check_slots, session
                )
                consecutive_errors = 0

                if slots:
                    slot = slots[0]
                    log.info("task.slot_found", task_id=self.task_id, slot=slot)
                    await self.notify({
                        "event": "slot_found",
                        "task_id": self.task_id,
                        "user_id": self.user_id,
                        "message": f"Найден слот: {slot.get('appointmentDate')} {slot.get('appointmentTime', '')}",
                    })

                    # Бронируем
                    try:
                        ref = await asyncio.get_event_loop().run_in_executor(
                            None, self.monitor.book_slot, session, slot
                        )
                        await self.notify({
                            "event": "booked",
                            "task_id": self.task_id,
                            "user_id": self.user_id,
                            "message": f"Забронировано! Номер подтверждения: {ref}",
                            "booking_ref": ref,
                        })
                        break  # Задача выполнена
                    except Exception as e:
                        log.error("task.book_error", task_id=self.task_id, error=str(e))
                        await self.notify({
                            "event": "book_error",
                            "task_id": self.task_id,
                            "user_id": self.user_id,
                            "message": f"Слот найден но не забронирован: {e}",
                        })
                else:
                    log.info("task.no_slots", task_id=self.task_id)

            except Exception as e:
                consecutive_errors += 1
                log.error("task.error", task_id=self.task_id,
                          error=str(e), consecutive=consecutive_errors)
                # Экспоненциальный backoff: 60s, 120s, 240s, 480s, 960s
                backoff = min(60 * (2 ** (consecutive_errors - 1)), 960)
                await self.notify({
                    "event": "check_error",
                    "task_id": self.task_id,
                    "user_id": self.user_id,
                    "message": f"Ошибка #{consecutive_errors}: {e} Следующая попытка через {backoff} сек.",
                })
                if consecutive_errors >= 10:
                    await self.notify({
                        "event": "monitoring.stopped",
                        "task_id": self.task_id,
                        "user_id": self.user_id,
                        "message": "Мониторинг остановлен: слишком много ошибок подряд",
                    })
                    break
                # Ждём backoff перед следующей попыткой
                for _ in range(backoff):
                    if self._stop_event.is_set():
                        break
                    await asyncio.sleep(1)
                continue  # не ждём дополнительный MONITOR_INTERVAL

            # Ждём до следующей проверки (только при успехе)
            for _ in range(int(MONITOR_INTERVAL)):
                if self._stop_event.is_set():
                    break
                await asyncio.sleep(1)

        await self.notify({
            "event": "monitoring.stopped",
            "task_id": self.task_id,
            "user_id": self.user_id,
            "message": "Мониторинг завершён",
        })
        log.info("task.run.done", task_id=self.task_id)
