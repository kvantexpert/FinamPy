#!/usr/bin/env python3
from FinamPy import FinamPy
import sys

print(f"Python version: {sys.version}")
print("-" * 50)

try:
    # Создаем объект (если токен уже сохраняли)
    fp = FinamPy()
    print("✓ Объект FinamPy создан")
    
    # Получаем все методы и атрибуты (исключая служебные)
    methods = [m for m in dir(fp) if not m.startswith('_')]
    print(f"\n📋 Доступные методы ({len(methods)}):")
    for method in sorted(methods):
        print(f"  - {method}")
    
    # Проверяем конкретные методы для времени сервера
    time_methods = ['get_server_time', 'get_time', 'get_clock', 'get_server_clock', 'get_current_time']
    print(f"\n⏰ Проверка методов времени:")
    for method in time_methods:
        if hasattr(fp, method):
            print(f"  ✓ {method}() доступен")
        else:
            print(f"  ✗ {method}() НЕ доступен")
    
    # Пробуем найти любой метод, возвращающий время
    print(f"\n🔍 Поиск методов, связанных со временем:")
    for method in methods:
        if 'time' in method.lower() or 'clock' in method.lower() or 'date' in method.lower():
            print(f"  - {method}")
    
    # Закрываем соединение
    fp.close_channel()
    
except Exception as e:
    print(f"✗ Ошибка: {e}")
