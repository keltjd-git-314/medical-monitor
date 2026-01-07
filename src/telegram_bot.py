import requests
from typing import List, Optional
import logging


class TelegramBot:
    """Класс для работы с Telegram Bot API"""

    def __init__(self, bot_token: str, chat_ids: List[str]):
        self.bot_token = bot_token
        self.chat_ids = chat_ids
        self.base_url = f"https://api.telegram.org/bot{bot_token}"

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

                response = requests.post(url, json=payload, timeout=10)

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
            response = requests.get(url, timeout=5)

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