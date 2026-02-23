#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Главный скрипт для запуска треугольного арбитража
Уникальное имя: run_arbitrage.py
"""

import logging
import time
import argparse
import sys
from pathlib import Path

# Добавляем путь для импортов
sys.path.insert(0, str(Path(__file__).parent))

from config.arb_config import ArbConfig, ArbColors, LOG_DIR
from core.arb_connection import ArbConnection
from core.arb_monitor import ArbMonitor
from core.arb_executor import ArbExecutor
from core.arb_calculator import find_opportunities
from diagnostics.arb_diagnostic import ArbDiagnostic

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOG_DIR / 'arbitrage.log'),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger('Arbitrage')


class ArbitrageApp:
    """Главное приложение"""
    
    def __init__(self, token=None, paper=False):
        self.config = ArbConfig()
        if paper:
            self.config.PaperTrading = True
        
        self.connection = ArbConnection(token)
        self.monitor = None
        self.executor = None
        self.diagnostic = None
        self.running = False
        
    def initialize(self) -> bool:
        """Инициализация"""
        print(f"\n{ArbColors.BOLD}{ArbColors.CYAN}{'=' * 60}")
        print("🚀 ЗАПУСК АРБИТРАЖНОГО БОТА")
        print(f"{'=' * 60}{ArbColors.END}")
        
        # Подключение
        if not self.connection.connect():
            return False
        
        # Монитор
        self.monitor = ArbMonitor(self.connection.fp)
        self.monitor.start()
        
        # Исполнитель
        self.executor = ArbExecutor(
            self.connection,
            self.connection.account_id,
            self.config
        )
        
        # Диагностика
        self.diagnostic = ArbDiagnostic(self.connection)
        
        return True
    
    def get_ticks_for_triangle(self, tri_type: int):
        """Получение тиков для треугольника"""
        from config.arb_config import ARB_TRIANGLE_PAIRS
        
        ticks = []
        for currency in ARB_TRIANGLE_PAIRS[tri_type]:
            tick = self.monitor.get_tick(currency)
            if not tick or not tick.is_valid:
                return None
            ticks.append(tick)
        return ticks
    
    def run(self):
        """Запуск"""
        if not self.initialize():
            return
        
        self.running = True
        last_scan = time.time()
        last_status = time.time()
        
        print(f"\n{ArbColors.GREEN}✅ Бот запущен{ArbColors.END}")
        print(f"{ArbColors.CYAN}📊 Режим: {'БУМАЖНЫЙ' if self.config.PaperTrading else 'РЕАЛЬНЫЙ'}{ArbColors.END}")
        print(f"{ArbColors.YELLOW}⚡ Сканирование каждые {self.config.ScanInterval} сек{ArbColors.END}\n")
        
        try:
            while self.running:
                now = time.time()
                
                # Поиск возможностей
                if now - last_scan >= self.config.ScanInterval:
                    opportunities = find_opportunities(
                        self.executor.triangles,
                        self.get_ticks_for_triangle,
                        self.config
                    )
                    
                    if opportunities:
                        best = opportunities[0]
                        if abs(best.deviation) >= self.config.MinDeviation:
                            self.executor.open_triangle(best)
                    
                    last_scan = now
                
                # Статус каждые 10 сек
                if now - last_status >= 10:
                    stats = self.monitor.get_stats()
                    print(f"\n{ArbColors.CYAN}📊 Статус:{ArbColors.END}")
                    print(f"   Обновлений: {stats['updates']}")
                    print(f"   В работе: {stats['uptime']}")
                    last_status = now
                
                time.sleep(1)
                
        except KeyboardInterrupt:
            logger.info("Остановка по запросу")
        finally:
            self.stop()
    
    def stop(self):
        """Остановка"""
        self.running = False
        if self.monitor:
            self.monitor.stop()
        if self.connection:
            self.connection.disconnect()
        logger.info("Бот остановлен")


def main():
    """Точка входа"""
    parser = argparse.ArgumentParser(description='Треугольный арбитраж на Finam')
    parser.add_argument('--token', help='Токен для первого запуска')
    parser.add_argument('--paper', action='store_true', help='Бумажная торговля')
    parser.add_argument('--diagnostic', action='store_true', help='Запустить диагностику')
    
    args = parser.parse_args()
    
    app = ArbitrageApp(token=args.token, paper=args.paper)
    
    if args.diagnostic:
        if app.connection.connect():
            app.diagnostic.run_all()
            app.connection.disconnect()
        return
    
    app.run()


if __name__ == "__main__":
    main()