#!/bin/bash

# Конфигурация
PROJECT_DIR="/home/keltjd/medical_monitor"
SCREEN_NAME="medical_monitor"
CONFIG_BACKUP="/home/keltjd/monitors_config.backup.json"
LOG_FILE="$PROJECT_DIR/logs/updater.log"

# Функция для логирования
log() {
    echo "$(date '+%Y-%m-%d %H:%M:%S'): $1" | tee -a "$LOG_FILE"
}

log "=== ЗАПУСК СКРИПТА ОБНОВЛЕНИЯ ==="

# Переходим в папку проекта
cd "$PROJECT_DIR" || { log "ОШИБКА: Не могу перейти в $PROJECT_DIR"; exit 1; }

# Сохраняем текущую версию
CURRENT_HASH=$(git rev-parse HEAD)
log "Текущая версия: $CURRENT_HASH"

# Скачиваем информацию об изменениях
git fetch origin

# Проверяем изменения в ветке main
if [ "$(git rev-parse HEAD)" != "$(git rev-parse origin/main)" ]; then
    log "🔍 Обнаружены изменения. Начинаю обновление..."

    # Останавливаем приложение (убиваем screen сессию)
    log "🛑 Останавливаю приложение..."
    screen -S "$SCREEN_NAME" -X quit 2>/dev/null || true
    sleep 2

    # Обновляем код
    log "📥 Обновляю код из GitHub..."
    git fetch --all
    git reset --hard origin/main

    # Восстанавливаем конфиг
    if [ -f "$CONFIG_BACKUP" ]; then
        cp "$CONFIG_BACKUP" "$PROJECT_DIR/config/monitors_config.json"
        log "✅ Конфиг восстановлен из бэкапа"
    else
        log "⚠️  ВНИМАНИЕ: Бэкап конфига не найден!"
    fi

    # Запускаем приложение заново
    log "🚀 Запускаю приложение..."
    cd "$PROJECT_DIR"
    screen -dmS "$SCREEN_NAME" bash -c "cd /home/keltjd/medical_monitor && source medical_env/bin/activate && ALL_PROXY=socks5://127.0.0.1:10808 python3 main.py"
    
    # Проверяем, что запустилось
    sleep 3
    if screen -list | grep -q "$SCREEN_NAME"; then
        log "✅ Приложение успешно запущено в screen сессии '$SCREEN_NAME'"
    else
        log "❌ ОШИБКА: Приложение не запустилось!"
    fi

    log "✅ Процесс обновления завершен."
else
    log "📌 Изменений нет."
fi

# Показываем финальный статус
log "📊 Текущий статус:"
screen -list | grep "$SCREEN_NAME" >> "$LOG_FILE" 2>&1
log "=== СКРИПТ ЗАВЕРШЕН ==="
