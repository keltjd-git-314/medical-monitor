import os
import time
import requests
from typing import List, Optional, Dict, Any
import logging


class TelegramBot:
    """Класс для работы с Telegram Bot API"""

    def __init__(self, bot_token: str, chat_ids: List[str]):
        self.bot_token = bot_token
        self.chat_ids = chat_ids
        self.base_url = f"https://api.telegram.org/bot{bot_token}"
        self.session = requests.Session()
        # Явно подхватываем прокси. Ожидается, что у вас заданы HTTP(S)_PROXY
        # (например http://127.0.0.1:8080) или TELEGRAM_PROXY.
        self.proxies = self._load_proxies()

    def _load_proxies(self) -> Optional[Dict[str, str]]:
        telegram_proxy = os.getenv("TELEGRAM_PROXY")
        if telegram_proxy:
            return {"http": telegram_proxy, "https": telegram_proxy}

        http_proxy = os.getenv("HTTP_PROXY") or os.getenv("http_proxy")
        https_proxy = os.getenv("HTTPS_PROXY") or os.getenv("https_proxy")

        proxies: Dict[str, str] = {}
        if http_proxy:
            proxies["http"] = http_proxy
        if https_proxy:
            proxies["https"] = https_proxy

        return proxies or None

    def _request_with_retries(
        self,
        method: str,
        url: str,
        *,
        timeout: int = 10,
        max_attempts: int = 3,
        backoff_seconds: float = 1.0,
        **kwargs: Any,
    ):
        last_exc: Optional[Exception] = None
        for attempt in range(1, max_attempts + 1):
            try:
                return self.session.request(
                    method=method,
                    url=url,
                    timeout=timeout,
                    proxies=self.proxies,
                    **kwargs,
                )
            except Exception as e:
                last_exc = e
                sleep_s = backoff_seconds * (2 ** (attempt - 1))
                logging.warning(
                    f"Telegram request failed (attempt {attempt}/{max_attempts}): "
                    f"{type(e).__name__}: {e}. Sleep {sleep_s:.1f}s"
                )
                time.sleep(sleep_s)

        assert last_exc is not None
        raise last_exc

    def send_message(self, text: str, parse_mode: str = "HTML",
                     disable_web_page_preview: bool = True) -> bool:
        """
        Отправка сообщения во все чаты

        Args:
            text: Текст сообщения
            parse_mode: Режим парсинга (HTML/Markdown)
            disable_web_page_preview: Отключить превью ссылок

        Returns:
            bool: Успешность отправки
        """
        if not self.chat_ids:
            logging.warning("Нет chat_id для отправки сообщений")
            return False

        success_count = 0

        for chat_id in self.chat_ids:
            try:
                url = f"{self.base_url}/sendMessage"
                payload = {
                    'chat_id': chat_id,
                    'text': text,
                    'parse_mode': parse_mode,
                    'disable_web_page_preview': disable_web_page_preview
                }

                response = self._request_with_retries(
                    "POST",
                    url,
                    json=payload,
                    timeout=10,
                    max_attempts=3,
                    backoff_seconds=1.0,
                )

                if response.status_code == 200:
                    success_count += 1
                    logging.debug(f"Сообщение отправлено в чат {chat_id}")
                else:
                    logging.error(f"Ошибка отправки в чат {chat_id}: {response.status_code}")

            except Exception as e:
                logging.error(f"Ошибка при отправке в чат {chat_id}: {e}")

        return success_count > 0

    def test_connection(self) -> bool:
        """Тестирование подключения к боту"""
        try:
            url = f"{self.base_url}/getMe"
            response = self._request_with_retries(
                "GET",
                url,
                timeout=5,
                max_attempts=3,
                backoff_seconds=0.5,
            )

            if response.status_code == 200:
                bot_info = response.json()
                logging.info(f"✅ Telegram бот подключен: @{bot_info['result']['username']}")
                return True
            else:
                logging.error(f"❌ Ошибка Telegram: {response.status_code}")
                return False

        except Exception as e:
            logging.error(f"❌ Ошибка подключения к Telegram: {e}")
            return False

    def send_test_message(self) -> bool:
        """Отправка тестового сообщения"""
        test_text = "✅ <b>Тестовое сообщение</b>\nСистема мониторинга медицинских книжек работает!"
        return self.send_message(test_text)