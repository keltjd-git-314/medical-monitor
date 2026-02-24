import pickle
import os
from datetime import datetime, date
from typing import List, Dict, Any, Set, Tuple
import logging
from dataclasses import dataclass, asdict
import json


@dataclass
class EmployeeState:
    """Состояние сотрудника для отслеживания изменений"""
    name: str
    position: str
    days_left: int
    has_medical_book: bool
    last_seen: datetime
    first_seen: datetime
    key: str  # Уникальный ключ для сравнения

    @classmethod
    def from_employee_data(cls, employee_data: Dict[str, Any]) -> 'EmployeeState':
        """Создание состояния из данных сотрудника"""
        name = employee_data['name']
        days_left = employee_data['days_left']
        has_medical_book = employee_data['has_medical_book']

        # Создаем уникальный ключ
        key = f"{name}_{days_left}_{has_medical_book}"

        now = datetime.now()
        return cls(
            name=name,
            position=employee_data.get('position', ''),
            days_left=days_left,
            has_medical_book=has_medical_book,
            last_seen=now,
            first_seen=now,
            key=key
        )


class StateManager:
    """Менеджер состояния монитора"""

    def __init__(self, state_dir: str, monitor_name: str):
        self.state_dir = state_dir
        self.monitor_name = monitor_name
        self.state_file = os.path.join(state_dir, f"{monitor_name}.json")
        self.employees: Dict[str, EmployeeState] = {}

    def load(self) -> bool:
        """Загрузка состояния из файла"""
        try:
            if os.path.exists(self.state_file):
                with open(self.state_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)

                # Восстанавливаем состояния сотрудников
                self.employees = {}
                for key, emp_data in data.get('employees', {}).items():
                    # Конвертируем строки дат обратно в datetime
                    emp_data['last_seen'] = datetime.fromisoformat(emp_data['last_seen'])
                    emp_data['first_seen'] = datetime.fromisoformat(emp_data['first_seen'])
                    self.employees[key] = EmployeeState(**emp_data)

                logging.info(f"Загружено состояние {len(self.employees)} сотрудников")
                return True

        except Exception as e:
            logging.error(f"Ошибка загрузки состояния: {e}")

        return False

    def save(self) -> bool:
        """Сохранение состояния в файл"""
        try:
            # Конвертируем состояния в словарь
            employees_data = {}
            for key, employee in self.employees.items():
                emp_dict = asdict(employee)
                # Конвертируем datetime в строки для JSON
                emp_dict['last_seen'] = employee.last_seen.isoformat()
                emp_dict['first_seen'] = employee.first_seen.isoformat()
                employees_data[key] = emp_dict

            state_data = {
                'monitor_name': self.monitor_name,
                'last_update': datetime.now().isoformat(),
                'employees': employees_data
            }

            with open(self.state_file, 'w', encoding='utf-8') as f:
                json.dump(state_data, f, ensure_ascii=False, indent=2)

            logging.debug(f"Состояние сохранено: {len(self.employees)} сотрудников")
            return True

        except Exception as e:
            logging.error(f"Ошибка сохранения состояния: {e}")
            return False

    def update_employees(self, current_employees: List[Dict[str, Any]]) -> Tuple[
        List[EmployeeState], List[EmployeeState]]:
        """
        Обновление состояния сотрудников

        Returns:
            Tuple[List[EmployeeState], List[EmployeeState]]:
                (новые сотрудники, удаленные сотрудники)
        """
        current_keys = set()
        new_employees = []

        # Обновляем существующих и находим новых
        for emp_data in current_employees:
            employee_state = EmployeeState.from_employee_data(emp_data)
            key = employee_state.key
            current_keys.add(key)

            if key in self.employees:
                # Обновляем существующего сотрудника
                existing = self.employees[key]
                existing.last_seen = employee_state.last_seen
                # Можно обновить другие поля если нужно
                if not existing.position and employee_state.position:
                    existing.position = employee_state.position
            else:
                # Новый сотрудник
                self.employees[key] = employee_state
                new_employees.append(employee_state)

        # Находим удаленных сотрудников
        removed_keys = set(self.employees.keys()) - current_keys
        removed_employees = [self.employees[key] for key in removed_keys]

        # Удаляем отсутствующих сотрудников
        for key in removed_keys:
            del self.employees[key]

        return new_employees, removed_employees

    def get_employee_count(self) -> int:
        """Получить количество отслеживаемых сотрудников"""
        return len(self.employees)


class MedicalMonitor:
    """Основной класс мониторинга медицинских книжек"""

    def __init__(self, config, google_client, telegram_bot, state_manager):
        self.config = config
        self.google_client = google_client
        self.telegram_bot = telegram_bot
        self.state_manager = state_manager

        # Время последнего ежедневного отчета
        self.last_daily_report = None

        logging.info(f"Инициализирован монитор: {config.name}")

    def check_medical_records(self, force_daily_report: bool = None) -> Dict[str, Any]:
        """
        Проверка медицинских записей.

        Args:
            force_daily_report: True — отправить ежедневный отчёт (вызов в назначенное время);
                False — не отправлять (периодическая проверка); None — решать по времени.

        Returns:
            Dict с результатами проверки
        """
        logging.info(f"Запуск проверки для монитора: {self.config.name}")

        try:
            now = datetime.now()
            # 1. Получение данных из Google Sheets
            raw_data = self.google_client.get_worksheet_data(
                self.config.spreadsheet_id,
                self.config.worksheet_name
            )

            if not raw_data:
                return {'error': 'Нет данных из таблицы'}

            # 2. Нормализация данных
            employees = self.google_client.normalize_employee_data(raw_data)

            if not employees:
                return {'error': 'Нет данных о сотрудниках'}

            # 3. Классификация сотрудников по срокам
            expired, critical, no_medical = self._classify_employees(employees)

            # 4. Обновление состояния и поиск новых сотрудников
            new_employees, removed_employees = self.state_manager.update_employees(employees)

            # 5. Проверка необходимости отправки уведомлений
            result = {
                'total_employees': len(employees),
                'expired': expired,
                'critical': critical,
                'no_medical': no_medical,
                'new_employees': new_employees,
                'removed_employees': removed_employees,
                'status': 'success'
            }

            # 6. Отправка уведомлений о новых сотрудниках
            # В полночь (час == 0) не шлём длинный список — только общее сообщение об обновлении данных
            if self.config.send_new_employee_notifications and new_employees:
                if now.hour == 0:
                    logging.info(
                        f\"Обнаружены новые сотрудники в полночь для монитора {self.config.name}, "
                        \"подробное уведомление пропущено (ночное обновление)\"
                    )
                else:
                    self._send_new_employee_notification(new_employees)

            # 7. Отправка ежедневного отчёта только раз в день в указанное время
            if force_daily_report is True or (force_daily_report is None and self._should_send_daily_report()):
                # В полночь не присылаем большой отчёт со списками — только короткое сообщение об обновлении
                if now.hour == 0:
                    self.send_data_updated_message()
                else:
                    self._send_daily_report(expired, critical, no_medical)
                self.last_daily_report = now.date()

            # 8. Сохранение состояния
            self.state_manager.save()

            logging.info(f"Проверка завершена: {len(employees)} сотрудников, "
                         f"{len(expired)} просрочено, {len(critical)} критических, "
                         f"{len(no_medical)} без медкнижки")

            return result

        except Exception as e:
            logging.error(f"Ошибка при проверке: {e}")
            return {'error': str(e), 'status': 'error'}

    def _classify_employees(self, employees: List[Dict[str, Any]]) -> Tuple[List, List, List]:
        """Классификация сотрудников по срокам"""
        expired = []
        critical = []
        no_medical = []

        for emp in employees:
            if not emp['has_medical_book']:
                no_medical.append(emp)
            elif emp['days_left'] < 0:
                expired.append(emp)
            elif emp['days_left'] <= 30:
                critical.append(emp)

        return expired, critical, no_medical

    def _should_send_daily_report(self) -> bool:
        """Проверка, нужно ли отправлять ежедневный отчет"""
        current_time = datetime.now().time()
        current_date = datetime.now().date()

        # Если отчет уже отправлен сегодня - пропускаем
        if self.last_daily_report == current_date:
            return False

        # Проверяем, наступило ли время отчета
        if (current_time.hour == self.config.report_time_obj.hour and
                current_time.minute == self.config.report_time_obj.minute):
            return True

        return False

    def _send_new_employee_notification(self, new_employees: List[EmployeeState]):
        """Отправка уведомления о новых сотрудниках"""
        if not new_employees:
            return

        message = f"🆕 <b>НОВЫЙ СОТРУДНИК ВНЕСЕН В ТАБЛИЦУ</b>\n\n"
        message += f"<b>Монитор:</b> {self.config.name}\n\n"

        for i, employee in enumerate(new_employees[:10], 1):  # Ограничим 10 сотрудниками
            status_emoji = "❌" if not employee.has_medical_book else "⚠️"
            status_text = "Нет медкнижки" if not employee.has_medical_book else f"Осталось дней: {employee.days_left}"

            message += f"{i}. {status_emoji} <b>{employee.name}</b>\n"
            if employee.position:
                message += f"   💼 {employee.position}\n"
            message += f"   📅 {status_text}\n\n"

        if len(new_employees) > 10:
            message += f"<i>...и еще {len(new_employees) - 10} сотрудников</i>\n\n"

        message += f"⏰ Время добавления: {datetime.now().strftime('%d.%m.%Y %H:%M')}"

        self.telegram_bot.send_message(message)
        logging.info(f"Отправлено уведомление о {len(new_employees)} новых сотрудниках")

    def _send_daily_report(self, expired: List, critical: List, no_medical: List):
        """Отправка ежедневного отчета"""
        message = f"📊 <b>ЕЖЕДНЕВНЫЙ ОТЧЕТ ПО МЕДИЦИНСКИМ КНИЖКАМ</b>\n\n"
        message += f"<b>Дата:</b> {datetime.now().strftime('%d.%m.%Y')}\n"
        message += f"<b>Монитор:</b> {self.config.name}\n"
        message += f"<b>Время отчета:</b> {self.config.daily_report_time}\n\n"

        # Статистика
        total_problematic = len(expired) + len(critical) + len(no_medical)

        if total_problematic == 0:
            message += "✅ <b>Все медицинские книжки в порядке!</b>\n"
            message += "Нет сотрудников с проблемными сроками или без медкнижек.\n"
        else:
            message += f"⚠️ <b>Требуют внимания:</b> {total_problematic} сотрудников\n\n"

            if no_medical:
                message += "🔴 <b>БЕЗ МЕДИЦИНСКОЙ КНИЖКИ:</b>\n"
                for i, emp in enumerate(no_medical[:5], 1):
                    message += f"{i}. ❌ {emp['name']}\n"
                    if emp.get('position'):
                        message += f"   💼 {emp['position']}\n"
                if len(no_medical) > 5:
                    message += f"   ...и еще {len(no_medical) - 5}\n"
                message += "\n"

            if expired:
                message += "🔴 <b>ПРОСРОЧЕНО:</b>\n"
                for i, emp in enumerate(expired[:5], 1):
                    message += f"{i}. ❌ {emp['name']}\n"
                    message += f"   📅 Просрочено: {abs(emp['days_left'])} дней\n"
                    if emp.get('position'):
                        message += f"   💼 {emp['position']}\n"
                if len(expired) > 5:
                    message += f"   ...и еще {len(expired) - 5}\n"
                message += "\n"

            if critical:
                message += "🟠 <b>КРИТИЧЕСКИЕ СРОКИ (≤30 дней):</b>\n"
                for i, emp in enumerate(critical[:5], 1):
                    days = emp['days_left']
                    emoji = "🔴" if days <= 7 else "🟠"
                    message += f"{i}. {emoji} {emp['name']}\n"
                    message += f"   📅 Осталось: {days} дней\n"
                    if emp.get('position'):
                        message += f"   💼 {emp['position']}\n"
                if len(critical) > 5:
                    message += f"   ...и еще {len(critical) - 5}\n"
                message += "\n"

        message += f"\n📈 <b>Всего сотрудников в системе:</b> {self.state_manager.get_employee_count()}"
        message += f"\n\n⏰ <i>Следующий отчет: завтра в {self.config.daily_report_time}</i>"

        self.telegram_bot.send_message(message)
        logging.info(f"Отправлен ежедневный отчет: {total_problematic} проблемных сотрудников")

    def send_data_updated_message(self):
        """Отправка короткого сообщения об обновлении данных (без отчёта со списком сотрудников)."""
        message = (
            f"🔄 <b>Обновление данных</b>\n\n"
            f"<b>Монитор:</b> {self.config.name}\n"
            f"⏰ {datetime.now().strftime('%d.%m.%Y %H:%M')}\n\n"
            f"Данные из таблицы успешно обновлены."
        )
        self.telegram_bot.send_message(message)
        logging.info(f"Отправлено сообщение об обновлении данных для монитора: {self.config.name}")

    def send_immediate_alert(self, employee: Dict[str, Any], alert_type: str):
        """
        Отправка немедленного уведомления

        Args:
            employee: Данные сотрудника
            alert_type: Тип алерта ('expired', 'critical', 'no_medical')
        """
        alert_titles = {
            'expired': '🚨 СОТРУДНИК С ПРОСРОЧЕННОЙ МЕДКНИЖКОЙ',
            'critical': '⚠️ СОТРУДНИК С КРИТИЧЕСКИМ СРОКОМ',
            'no_medical': '❌ СОТРУДНИК БЕЗ МЕДИЦИНСКОЙ КНИЖКИ'
        }

        emojis = {
            'expired': '🔴',
            'critical': '🟠',
            'no_medical': '❌'
        }

        title = alert_titles.get(alert_type, 'УВЕДОМЛЕНИЕ')
        emoji = emojis.get(alert_type, '⚠️')

        message = f"{emoji} <b>{title}</b>\n\n"
        message += f"<b>Монитор:</b> {self.config.name}\n\n"
        message += f"<b>Сотрудник:</b> {employee['name']}\n"

        if employee.get('position'):
            message += f"<b>Должность:</b> {employee['position']}\n"

        if alert_type == 'expired':
            message += f"<b>Статус:</b> Просрочено на {abs(employee['days_left'])} дней\n"
        elif alert_type == 'critical':
            message += f"<b>Статус:</b> Осталось {employee['days_left']} дней\n"
        elif alert_type == 'no_medical':
            message += f"<b>Статус:</b> Отсутствует медицинская книжка\n"

        message += f"\n⏰ Обнаружено: {datetime.now().strftime('%d.%m.%Y %H:%M')}"

        self.telegram_bot.send_message(message)
        logging.info(f"Отправлен немедленный алерт: {employee['name']} - {alert_type}")