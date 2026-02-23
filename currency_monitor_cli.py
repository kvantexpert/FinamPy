#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Главный скрипт для мониторинга валют в реальном времени
Объединяет все модули и запускает полноценный мониторинг
"""

import logging
import sys
import time
import argparse
from pathlib import Path
from datetime import datetime
import threading

# Добавляем текущую папку в путь для импортов
sys.path.insert(0, str(Path(__file__).parent))

from core.connection import FinamConnection
from core.currency_monitor import CurrencyMonitor, AlertSystem
from diagnostics.check_all import check_system
from config.settings import LOG_DIR, UPDATE_INTERVAL, DISPLAY_REFRESH

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOG_DIR / 'currency_monitor.log'),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger('Main')


class CurrencyMonitorApp:
    """Основное приложение для мониторинга валют"""
    
    def __init__(self):
        self.connection = None
        self.monitor = None
        self.alert_system = AlertSystem()
        self.running = False
        
    def initialize(self, token: str = None):
        """Инициализация всех компонентов"""
        
        print("\n" + "=" * 80)
        print("🚀 ЗАПУСК ВАЛЮТНОГО МОНИТОРА FINAM")
        print("=" * 80)
        
        # 1. Подключение
        logger.info("Инициализация подключения...")
        self.connection = FinamConnection(token)
        
        if not self.connection.connect():
            logger.error("Не удалось подключиться к Finam API")
            return False
        
        # 2. Создание монитора
        logger.info("Создание монитора валют...")
        self.monitor = CurrencyMonitor(self.connection)
        
        # 3. Подключение системы оповещений
        self.monitor.on_quote_update(self.alert_system.check_alerts)
        
        return True
    
    def run(self):
        """Запуск мониторинга"""
        if not self.monitor:
            logger.error("Монитор не инициализирован")
            return
        
        # Запускаем монитор
        if not self.monitor.start():
            return
        
        self.running = True
        
        # Функция для фонового сохранения данных
        def save_background():
            while self.running:
                time.sleep(300)  # каждые 5 минут
                if self.monitor:
                    self.monitor.save_snapshot()
        
        save_thread = threading.Thread(target=save_background, daemon=True)
        save_thread.start()
        
        try:
            # Основной цикл отображения
            last_display = time.time()
            
            while self.running:
                current_time = time.time()
                
                # Обновляем экран с заданной периодичностью
                if current_time - last_display >= DISPLAY_REFRESH:
                    self.monitor.print_table()
                    last_display = current_time
                
                # Небольшая пауза
                time.sleep(UPDATE_INTERVAL)
                
        except KeyboardInterrupt:
            logger.info("Получен сигнал остановки")
        finally:
            self.stop()
    
    def stop(self):
        """Остановка мониторинга"""
        self.running = False
        
        if self.monitor:
            self.monitor.stop()
            
            # Сохраняем финальный снимок
            self.monitor.save_snapshot(f"final_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")
        
        if self.connection:
            self.connection.disconnect()
        
        logger.info("Мониторинг остановлен")
    
    def run_diagnostics(self):
        """Запуск диагностики"""
        if self.connection:
            results = self.connection.run_diagnostics()
            self.connection.print_diagnostic_summary()
            return results
        return None


def main():
    """Главная функция"""
    
    parser = argparse.ArgumentParser(description='Валютный монитор Finam')
    parser.add_argument('--token', help='Торговый токен (если первый запуск)')
    parser.add_argument('--diagnostics', action='store_true', help='Запустить диагностику')
    parser.add_argument('--check', action='store_true', help='Полная проверка системы')
    
    args = parser.parse_args()
    
    if args.check:
        check_system()
        return
    
    # Создаем приложение
    app = CurrencyMonitorApp()
    
    if args.diagnostics:
        if app.initialize(args.token):
            app.run_diagnostics()
            app.stop()
        return
    
    # Запускаем мониторинг
    if app.initialize(args.token):
        try:
            app.run()
        except Exception as e:
            logger.error(f"Критическая ошибка: {e}")
        finally:
            app.stop()


if __name__ == "__main__":
    main()