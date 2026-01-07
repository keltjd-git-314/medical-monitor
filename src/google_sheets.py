import gspread
from google.oauth2.service_account import Credentials
from typing import List, Dict, Any
import logging


class GoogleSheetsClient:
    """Клиент для работы с Google Sheets"""

    SCOPES = [
        'https://www.googleapis.com/auth/spreadsheets',
        'https://www.googleapis.com/auth/drive'
    ]

    def __init__(self, credentials_file: str = "credentials.json"):
        self.credentials_file = credentials_file
        self.client = None
        self._authenticate()

    def _authenticate(self):
        """Аутентификация в Google Sheets"""
        try:
            creds = Credentials.from_service_account_file(
                self.credentials_file,
                scopes=self.SCOPES
            )
            self.client = gspread.authorize(creds)
            logging.info("✅ Успешная аутентификация в Google Sheets")
        except Exception as e:
            logging.error(f"❌ Ошибка аутентификации: {e}")
            raise

    def get_worksheet_data(self, spreadsheet_id: str, worksheet_name: str = "Лист1") -> List[Dict[str, Any]]:
        """Получение данных из указанного листа"""
        try:
            # Открываем таблицу
            spreadsheet = self.client.open_by_key(spreadsheet_id)

            # Получаем список всех листов для информации
            worksheets = spreadsheet.worksheets()
            logging.debug(f"Найдено листов: {[ws.title for ws in worksheets]}")

            # Получаем указанный лист
            try:
                worksheet = spreadsheet.worksheet(worksheet_name)
            except gspread.exceptions.WorksheetNotFound:
                logging.warning(f"Лист '{worksheet_name}' не найден, используем первый лист")
                worksheet = worksheets[0]
                worksheet_name = worksheet.title

            # Получаем все данные
            all_values = worksheet.get_all_values()

            if len(all_values) < 2:
                logging.warning("Таблица содержит меньше 2 строк")
                return []

            # Парсим заголовки и данные
            headers = [h.strip() if h.strip() else f"Column_{i + 1}"
                       for i, h in enumerate(all_values[0])]

            data = []
            for row_idx, row in enumerate(all_values[1:], start=2):
                # Пропускаем полностью пустые строки
                if not any(cell.strip() for cell in row):
                    continue

                record = {}
                for col_idx, (header, value) in enumerate(zip(headers, row)):
                    if col_idx < len(row):
                        record[header] = value.strip() if value else ""

                # Добавляем метаданные
                record['_row'] = row_idx
                record['_sheet'] = worksheet_name

                data.append(record)

            logging.info(f"Получено {len(data)} записей из листа '{worksheet_name}'")
            return data

        except Exception as e:
            logging.error(f"Ошибка получения данных из Google Sheets: {e}")
            return []

    def normalize_employee_data(self, raw_data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Нормализация данных о сотрудниках"""
        normalized = []

        for record in raw_data:
            try:
                # Поиск ФИО в различных полях
                name = self._extract_name(record)

                # Поиск дней до истечения срока
                days_info = self._extract_days_info(record)

                # Поиск должности
                position = self._extract_position(record)

                employee = {
                    'name': name,
                    'position': position,
                    'days_left': days_info['days_left'],
                    'has_medical_book': days_info['has_medical_book'],
                    'raw_days_value': days_info['raw_value'],
                    'original_data': record
                }

                normalized.append(employee)

            except Exception as e:
                logging.warning(f"Ошибка нормализации записи {record.get('ФИО', 'Unknown')}: {e}")
                continue

        return normalized

    def _extract_name(self, record: Dict[str, Any]) -> str:
        """Извлечение имени сотрудника"""
        name_fields = ['ФИО', 'Имя', 'Сотрудник', 'Name', 'медкнижка']

        for field in name_fields:
            if field in record and record[field]:
                value = record[field].strip()
                if value and not self._looks_like_date(value) and not value.replace('.', '').isdigit():
                    return value

        # Если не нашли в стандартных полях, ищем первое непустое поле
        for key, value in record.items():
            if (value and key not in ['Срок', 'Days', 'Дней', 'Осталось'] and
                    not self._looks_like_date(value) and
                    not value.replace('.', '').isdigit() and
                    len(value) > 3 and len(value) < 50):
                return value

        return "Неизвестный сотрудник"

    def _extract_days_info(self, record: Dict[str, Any]) -> Dict[str, Any]:
        """Извлечение информации о днях"""
        days_fields = ['Срок', 'срок', 'Days', 'days', 'Дней', 'Осталось']

        raw_value = ""
        has_medical_book = True
        days_left = 0

        # Поиск в стандартных полях
        for field in days_fields:
            if field in record and record[field]:
                raw_value = str(record[field]).strip()
                break

        # Если не нашли, ищем числовое значение в любом поле
        if not raw_value:
            for key, value in record.items():
                if value and str(value).strip().lstrip('-').replace('.', '', 1).isdigit():
                    raw_value = str(value).strip()
                    break

        # Обработка значения
        if not raw_value or raw_value.lower() in ['нет', 'н', 'no', 'none', '']:
            has_medical_book = False
            days_left = -999  # Специальное значение для отсутствия медкнижки
        elif raw_value.replace('-', '', 1).isdigit():
            days_left = int(raw_value)
        elif self._looks_like_date(raw_value):
            # Если это дата, вычисляем разницу в днях
            days_left = self._calculate_days_from_date(raw_value)
        else:
            # Неизвестный формат
            has_medical_book = False
            days_left = -999

        return {
            'raw_value': raw_value,
            'days_left': days_left,
            'has_medical_book': has_medical_book
        }

    def _extract_position(self, record: Dict[str, Any]) -> str:
        """Извлечение должности"""
        position_fields = ['Должность', 'Position', 'Role', 'Должн']

        for field in position_fields:
            if field in record and record[field]:
                value = record[field].strip()
                if value and len(value) < 50:
                    return value

        return ""

    def _looks_like_date(self, value: str) -> bool:
        """Проверка, похоже ли значение на дату"""
        date_separators = ['.', '/', '-']
        for sep in date_separators:
            if sep in value and len(value.split(sep)) == 3:
                parts = value.split(sep)
                if len(parts[0]) in [1, 2] and len(parts[1]) in [1, 2] and len(parts[2]) in [2, 4]:
                    return True
        return False

    def _calculate_days_from_date(self, date_str: str) -> int:
        """Вычисление дней от текущей даты"""
        try:
            from datetime import datetime
            date_formats = ['%d.%m.%Y', '%d/%m/%Y', '%d-%m-%Y']

            for fmt in date_formats:
                try:
                    target_date = datetime.strptime(date_str, fmt)
                    current_date = datetime.now()
                    days_left = (target_date - current_date).days
                    return days_left
                except ValueError:
                    continue

            return 0
        except:
            return 0