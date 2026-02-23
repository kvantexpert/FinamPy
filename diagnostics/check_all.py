#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Расширенная диагностика всех компонентов системы
"""

import logging
import sys
import time
from pathlib import Path

# Добавляем родительскую папку в путь для импортов
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.connection import FinamConnection
from core.currency_monitor import CurrencyMonitor
from config.settings import LOG_DIR

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOG_DIR / 'diagnostics.log'),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger('Diagnostics')

def check_system():
    """Полная проверка системы"""
    
    print("\n" + "=" * 70)
    print("🔬 ПОЛНАЯ ДИАГНОСТИКА СИСТЕМЫ")
    print("=" * 70)
    
    # 1. Проверка Python
    print(f"\n🐍 Python: {sys.version}")
    
    # 2. Проверка импортов
    print("\n📦 Проверка импортов:")
    modules = ['FinamPy', 'colorama', 'tabulate']
    for module in modules:
        try:
            __import__(module)
            print(f"   ✅ {module}")
        except ImportError as e:
            print(f"   ❌ {module}: {e}")
    
    # 3. Проверка папок
    print("\n📁 Проверка структуры папок:")
    paths = [
        Path(__file__).parent.parent,
        LOG_DIR,
    ]
    for path in paths:
        if path.exists():
            print(f"   ✅ {path}")
        else:
            print(f"   ❌ {path} (не найдено)")
    
    # 4. Проверка подключения
    print("\n🔌 Проверка подключения к Finam...")
    conn = FinamConnection()
    
    if conn.connect():
        # Запускаем диагностику
        results = conn.run_diagnostics()
        conn.print_diagnostic_summary()
        
        # 5. Быстрый тест мониторинга
        print("\n📡 Тест мониторинга (5 секунд)...")
        monitor = CurrencyMonitor(conn)
        monitor.start()
        
        # Ждем немного для сбора данных
        for i in range(5):
            time.sleep(1)
            print(f"   {i+1}... получено обновлений: {monitor.update_count}")
        
        monitor.stop()
        
        # Показываем собранные данные
        if monitor.update_count > 0:
            monitor.print_table()
        
        conn.disconnect()
    else:
        print("❌ Не удалось подключиться к Finam")
    
    print("\n" + "=" * 70)
    print("✅ ДИАГНОСТИКА ЗАВЕРШЕНА")
    print("=" * 70)

if __name__ == "__main__":
    check_system()