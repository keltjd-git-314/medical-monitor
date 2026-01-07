import schedule
import time  # Этот импорт уже был, убедитесь, что он есть
import threading
from datetime import datetime
import logging
from typing import List


class MonitorScheduler:
    """Планировщик задач для мониторов"""

    def __init__(self, monitors: List):
        self.monitors = monitors
        self.running = False
        self.schedule_thread = None

    def start(self):
        """Запуск планировщика"""
        if self.running:
            logging.warning("Планировщик уже запущен")
            return

        self.running = True

        # Настройка расписания для каждого монитора
        for monitor in self.monitors:
            # Ежедневный отчет в указанное время
            report_time = monitor.config.daily_report_time
            schedule.every().day.at(report_time).do(
                self._run_monitor_check, monitor
            ).tag('daily_report', monitor.config.name)

            # Регулярные проверки по интервалу
            schedule.every(monitor.config.check_interval).minutes.do(
                self._run_monitor_check, monitor
            ).tag('regular_check', monitor.config.name)

            logging.info(f"Настроен монитор '{monitor.config.name}': "
                         f"отчет в {report_time}, проверка каждые {monitor.config.check_interval} мин")

        # Запуск планировщика в отдельном потоке
        self.schedule_thread = threading.Thread(target=self._run_scheduler, daemon=True)
        self.schedule_thread.start()

        logging.info("Планировщик запущен")

    def stop(self):
        """Остановка планировщика"""
        self.running = False
        schedule.clear()

        if self.schedule_thread and self.schedule_thread.is_alive():
            self.schedule_thread.join(timeout=5)

        logging.info("Планировщик остановлен")

    def _run_scheduler(self):
        """Основной цикл планировщика"""
        while self.running:
            schedule.run_pending()
            time.sleep(60)  # Проверяем каждую минуту

    def _run_monitor_check(self, monitor):
        """Запуск проверки для монитора"""
        try:
            logging.debug(f"Запуск плановой проверки для монитора: {monitor.config.name}")
            result = monitor.check_medical_records()

            if result.get('status') == 'error':
                logging.error(f"Ошибка при проверке {monitor.config.name}: {result.get('error')}")

        except Exception as e:
            logging.error(f"Необработанная ошибка в проверке {monitor.config.name}: {e}")

    def run_immediate_check(self, monitor_index: int = 0):
        """Немедленная проверка для указанного монитора"""
        if 0 <= monitor_index < len(self.monitors):
            monitor = self.monitors[monitor_index]
            logging.info(f"Запуск немедленной проверки для {monitor.config.name}")
            return monitor.check_medical_records()
        return None

    def get_scheduled_jobs(self):
        """Получение списка запланированных задач"""
        jobs = []
        for job in schedule.get_jobs():
            jobs.append({
                'next_run': job.next_run,
                'job': str(job)
            })
        return jobs