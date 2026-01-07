#!/usr/bin/env python3
"""
Главный скрипт системы мониторинга медицинских книжек
"""

import logging
import sys
import os
import time  # Добавил этот импорт
from datetime import datetime

# Добавляем src в путь импорта
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

# Импорт из модулей в папке src
from config import ConfigManager
from google_sheets import GoogleSheetsClient
from telegram_bot import TelegramBot
from monitor import MedicalMonitor, StateManager
from scheduler import MonitorScheduler


def setup_logging(log_dir: str, log_level: str = "INFO"):
    """Настройка логирования"""
    os.makedirs(log_dir, exist_ok=True)

    # Формат для логов
    log_format = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    date_format = '%Y-%m-%d %H:%M:%S'

    # Уровень логирования
    numeric_level = getattr(logging, log_level.upper(), logging.INFO)

    # Настройка root логгера
    logging.basicConfig(
        level=numeric_level,
        format=log_format,
        datefmt=date_format,
        handlers=[
            logging.FileHandler(
                os.path.join(log_dir, f"medical_monitor_{datetime.now().strftime('%Y%m%d')}.log")
            ),
            logging.StreamHandler(sys.stdout)
        ]
    )


def create_monitors(config_manager, system_config):
    """Создание мониторов из конфигурации"""
    monitors = []

    # Инициализация клиента Google Sheets
    try:
        google_client = GoogleSheetsClient("credentials.json")
    except Exception as e:
        logging.error(f"Не удалось инициализировать Google Sheets клиент: {e}")
        return []

    for monitor_config in config_manager.monitors:
        try:
            # Инициализация Telegram бота
            telegram_bot = TelegramBot(
                monitor_config.telegram_bot_token,
                monitor_config.telegram_chat_ids
            )

            # Тестирование подключения к Telegram
            if not telegram_bot.test_connection():
                logging.error(f"Не удалось подключиться к Telegram для монитора {monitor_config.name}")
                continue

            # Инициализация менеджера состояния
            state_manager = StateManager(
                system_config.state_dir,
                monitor_config.name.replace(' ', '_')
            )
            state_manager.load()

            # Создание монитора
            monitor = MedicalMonitor(
                monitor_config,
                google_client,
                telegram_bot,
                state_manager
            )

            monitors.append(monitor)
            logging.info(f"✅ Монитор '{monitor_config.name}' успешно создан")

            # Отправка тестового сообщения
            telegram_bot.send_test_message()

        except Exception as e:
            logging.error(f"❌ Ошибка создания монитора {monitor_config.name}: {e}")
            continue

    return monitors


def main():
    """Основная функция"""
    print("\n" + "=" * 60)
    print("🚀 ЗАПУСК СИСТЕМЫ МОНИТОРИНГА МЕДИЦИНСКИХ КНИЖЕК")
    print("=" * 60 + "\n")

    # Загрузка конфигурации
    config_manager = ConfigManager("config/monitors_config.json")
    if not config_manager.load():
        print("❌ Ошибка загрузки конфигурации")
        sys.exit(1)

    # Настройка логирования
    setup_logging(config_manager.system_config.log_dir, "INFO")

    # Создание мониторов
    monitors = create_monitors(config_manager, config_manager.system_config)

    if not monitors:
        print("❌ Нет рабочих мониторов для запуска")
        sys.exit(1)

    print(f"\n✅ Создано {len(monitors)} мониторов")

    # Тестирование первоначальной проверки
    print("\n" + "=" * 60)
    print("🧪 ТЕСТИРОВАНИЕ ПЕРВОНАЧАЛЬНОЙ ПРОВЕРКИ")
    print("=" * 60)

    for i, monitor in enumerate(monitors, 1):
        print(f"\n{i}. Тест монитора: {monitor.config.name}")
        result = monitor.check_medical_records()

        if result.get('status') == 'success':
            print(f"   ✅ Проверка успешна: {result['total_employees']} сотрудников")
        else:
            print(f"   ❌ Ошибка проверки: {result.get('error', 'Unknown error')}")

    # Запуск планировщика
    print("\n" + "=" * 60)
    print("🔄 ЗАПУСК АВТОМАТИЧЕСКОГО МОНИТОРИНГА")
    print("=" * 60 + "\n")

    scheduler = MonitorScheduler(monitors)

    try:
        scheduler.start()

        # Основной цикл программы
        while True:
            try:
                time.sleep(1)
            except KeyboardInterrupt:
                print("\n\n⚠️ Получен сигнал прерывания")
                break
            except Exception as e:
                logging.error(f"Ошибка в основном цикле: {e}")

    except Exception as e:
        logging.error(f"Критическая ошибка: {e}")
    finally:
        print("\n🛑 Остановка системы...")
        scheduler.stop()
        print("✅ Система остановлена")


if __name__ == "__main__":
    main()