import json
import os
from dataclasses import dataclass, field
from typing import List, Dict, Any
from datetime import time
import logging


@dataclass
class MonitorConfig:
    """Конфигурация отдельного монитора"""
    name: str
    spreadsheet_id: str
    telegram_bot_token: str
    telegram_chat_ids: List[str]
    worksheet_name: str = "Лист1"
    check_interval: int = 10
    daily_report_time: str = "09:00"
    send_new_employee_notifications: bool = True
    log_level: str = "INFO"

    def __post_init__(self):
        # Преобразуем время из строки в объект time
        try:
            self.report_time_obj = time.fromisoformat(self.daily_report_time)
        except ValueError:
            # Если формат не ISO, парсим как HH:MM
            from datetime import datetime
            dt = datetime.strptime(self.daily_report_time, "%H:%M")
            self.report_time_obj = dt.time()

        # Убедимся, что telegram_chat_ids - это список строк
        if isinstance(self.telegram_chat_ids, str):
            self.telegram_chat_ids = [self.telegram_chat_ids]


@dataclass
class SystemConfig:
    """Системная конфигурация"""
    state_dir: str = "data/state"
    log_dir: str = "data/logs"
    max_log_files: int = 7
    retry_attempts: int = 3
    retry_delay: int = 5


class ConfigManager:
    """Менеджер конфигурации"""

    def __init__(self, config_path: str = "config/monitors_config.json"):
        self.config_path = config_path
        self.monitors: List[MonitorConfig] = []
        self.system_config = SystemConfig()

    def load(self):
        """Загрузка конфигурации из файла"""
        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                config_data = json.load(f)

            # Загружаем конфигурацию мониторов
            for monitor_data in config_data.get("monitors", []):
                monitor = MonitorConfig(**monitor_data)
                self.monitors.append(monitor)

            # Загружаем системную конфигурацию
            system_data = config_data.get("system", {})
            self.system_config = SystemConfig(**system_data)

            # Создаем необходимые директории
            os.makedirs(self.system_config.state_dir, exist_ok=True)
            os.makedirs(self.system_config.log_dir, exist_ok=True)

            logging.info(f"Загружено {len(self.monitors)} мониторов")
            return True

        except Exception as e:
            logging.error(f"Ошибка загрузки конфигурации: {e}")
            return False