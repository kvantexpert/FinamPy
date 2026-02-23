#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Мониторинг валютных котировок в реальном времени
"""

import logging
import time
import threading
from datetime import datetime
from typing import Dict, List, Optional, Callable
from collections import deque
import json
from pathlib import Path

from colorama import init, Fore, Back, Style
from tabulate import tabulate

from config.settings import CURRENCY_PAIRS, CURRENCY_NAMES, DATA_DIR

# Инициализация colorama для Windows/Linux
init(autoreset=True)

logger = logging.getLogger('CurrencyMonitor')

class CurrencyData:
    """Данные по одной валюте"""
    
    def __init__(self, code: str, name: str, symbol: str):
        self.code = code
        self.name = name
        self.symbol = symbol
        self.bid = 0.0
        self.ask = 0.0
        self.last = 0.0
        self.change = 0.0
        self.change_percent = 0.0
        self.volume = 0
        self.timestamp = None
        self.history = deque(maxlen=100)  # храним последние 100 значений
        
    def update(self, bid: float, ask: float, last: float, volume: int, timestamp: datetime):
        """Обновление данных"""
        old_last = self.last
        self.bid = bid
        self.ask = ask
        self.last = last
        self.volume = volume
        self.timestamp = timestamp
        
        if old_last > 0:
            self.change = last - old_last
            self.change_percent = (self.change / old_last) * 100
        
        self.history.append({
            'timestamp': timestamp,
            'last': last,
            'bid': bid,
            'ask': ask
        })
    
    @property
    def spread(self) -> float:
        """Текущий спред в пунктах"""
        if self.ask > 0 and self.bid > 0:
            return (self.ask - self.bid) / 0.0001
        return 0
    
    @property
    def color(self) -> str:
        """Цвет для отображения изменения"""
        if self.change > 0:
            return Fore.GREEN
        elif self.change < 0:
            return Fore.RED
        return Fore.WHITE


class CurrencyMonitor:
    """Мониторинг всех валютных пар в реальном времени"""
    
    def __init__(self, fp_connection):
        """
        Инициализация монитора
        
        Args:
            fp_connection: Объект подключения FinamConnection
        """
        self.fp = fp_connection.fp
        self.connected = fp_connection.connected
        self.running = False
        self.currencies: Dict[str, CurrencyData] = {}
        self.callbacks: List[Callable] = []
        self.update_count = 0
        self.start_time = None
        
        # Инициализация валют
        for code, symbol in CURRENCY_PAIRS.items():
            self.currencies[code] = CurrencyData(
                code=code,
                name=CURRENCY_NAMES.get(code, code),
                symbol=symbol
            )
        
        logger.info(f"💱 Монитор инициализирован: {len(self.currencies)} валют")
    
    def on_quote_update(self, callback: Callable):
        """Подписка на обновления котировок"""
        self.callbacks.append(callback)
    
    def _quote_handler(self, quote):
        """Обработчик входящих котировок"""
        try:
            for q in quote.quote:
                symbol = q.symbol
                
                # Находим валюту по символу
                for code, currency in self.currencies.items():
                    if currency.symbol == symbol:
                        bid = float(q.bid.value) if q.bid and q.bid.value else 0
                        ask = float(q.ask.value) if q.ask and q.ask.value else 0
                        last = float(q.last.value) if q.last and q.last.value else 0
                        volume = int(float(q.volume.value)) if q.volume and q.volume.value else 0
                        
                        currency.update(
                            bid=bid,
                            ask=ask,
                            last=last,
                            volume=volume,
                            timestamp=datetime.now()
                        )
                        
                        self.update_count += 1
                        
                        # Вызываем колбэки
                        for callback in self.callbacks:
                            try:
                                callback(code, currency)
                            except:
                                pass
                        break
        except Exception as e:
            logger.error(f"Ошибка обработки котировки: {e}")
    
    def start(self):
        """Запуск мониторинга"""
        if not self.connected:
            logger.error("Нет подключения к Finam API")
            return False
        
        logger.info("🚀 Запуск мониторинга валют...")
        self.running = True
        self.start_time = datetime.now()
        
        # Подписываемся на котировки
        symbols = list(CURRENCY_PAIRS.values())
        self.fp.on_quote.subscribe(self._quote_handler)
        
        # Запускаем поток подписки
        def quote_thread():
            self.fp.subscribe_quote_thread(tuple(symbols))
        
        thread = threading.Thread(target=quote_thread, daemon=True)
        thread.start()
        
        logger.info(f"✅ Мониторинг запущен для {len(symbols)} валютных пар")
        return True
    
    def stop(self):
        """Остановка мониторинга"""
        self.running = False
        logger.info("🛑 Мониторинг остановлен")
    
    def get_all_rates(self) -> Dict:
        """Получение всех текущих курсов"""
        return {
            code: {
                'bid': curr.bid,
                'ask': curr.ask,
                'last': curr.last,
                'change': curr.change,
                'change_percent': curr.change_percent,
                'spread': curr.spread,
                'volume': curr.volume
            }
            for code, curr in self.currencies.items()
            if curr.last > 0
        }
    
    def get_top_changes(self, n: int = 5) -> List:
        """Получение топ-N по изменению"""
        active = [c for c in self.currencies.values() if c.last > 0]
        sorted_by_change = sorted(active, key=lambda x: abs(x.change_percent), reverse=True)
        return sorted_by_change[:n]
    
    def save_snapshot(self, filename: str = None):
        """Сохранение снимка данных"""
        if not filename:
            filename = DATA_DIR / f'snapshot_{datetime.now().strftime("%Y%m%d_%H%M%S")}.json'
        
        data = {
            'timestamp': datetime.now().isoformat(),
            'update_count': self.update_count,
            'currencies': {}
        }
        
        for code, curr in self.currencies.items():
            if curr.last > 0:
                data['currencies'][code] = {
                    'last': curr.last,
                    'bid': curr.bid,
                    'ask': curr.ask,
                    'change': curr.change,
                    'change_percent': curr.change_percent,
                    'spread': curr.spread,
                    'volume': curr.volume,
                    'timestamp': curr.timestamp.isoformat() if curr.timestamp else None
                }
        
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        
        logger.info(f"💾 Снимок сохранен: {filename}")
    
    def print_table(self):
        """Вывод таблицы курсов"""
        if not self.start_time:
            return
        
        active = [c for c in self.currencies.values() if c.last > 0]
        
        if not active:
            print(Fore.YELLOW + "⏳ Ожидание данных..." + Style.RESET_ALL)
            return
        
        # Сортируем по коду валюты
        active.sort(key=lambda x: x.code)
        
        # Подготавливаем данные для таблицы
        table_data = []
        for curr in active:
            color = curr.color
            table_data.append([
                f"{curr.code}",
                curr.name,
                f"{color}{curr.last:.4f}{Style.RESET_ALL}",
                f"{curr.bid:.4f}" if curr.bid > 0 else "-",
                f"{curr.ask:.4f}" if curr.ask > 0 else "-",
                f"{color}{curr.change:+.4f}{Style.RESET_ALL}" if curr.change != 0 else "-",
                f"{color}{curr.change_percent:+.2f}%{Style.RESET_ALL}" if curr.change_percent != 0 else "-",
                f"{curr.spread:.1f}" if curr.spread > 0 else "-",
                f"{curr.volume:,}" if curr.volume > 0 else "-"
            ])
        
        # Заголовки
        headers = [
            "Код", "Валюта", "Курс", "Bid", "Ask", 
            "Изменение", "%", "Спред", "Объем"
        ]
        
        # Очищаем экран (для Linux и Windows)
        print("\033[2J\033[H", end='')
        
        # Заголовок
        uptime = datetime.now() - self.start_time
        print(Fore.CYAN + "=" * 120 + Style.RESET_ALL)
        print(Fore.CYAN + f"💱 ВАЛЮТНЫЙ МОНИТОР В РЕАЛЬНОМ ВРЕМЕНИ".center(120) + Style.RESET_ALL)
        print(Fore.CYAN + f"Обновлений: {self.update_count} | Время работы: {str(uptime).split('.')[0]}".center(120) + Style.RESET_ALL)
        print(Fore.CYAN + "=" * 120 + Style.RESET_ALL)
        
        # Таблица
        print(tabulate(table_data, headers=headers, tablefmt="grid", stralign="left"))
        
        # Топ изменения
        top = self.get_top_changes(3)
        if top:
            print(Fore.YELLOW + "\n📊 ТОП ИЗМЕНЕНИЙ:" + Style.RESET_ALL)
            for curr in top:
                color = Fore.GREEN if curr.change > 0 else Fore.RED
                print(f"  {curr.code}: {color}{curr.change_percent:+.2f}%{Style.RESET_ALL}")


class AlertSystem:
    """Система оповещений об изменениях курсов"""
    
    def __init__(self, threshold_percent: float = 0.5):
        self.threshold = threshold_percent
        self.last_alert = {}
        self.alert_cooldown = 60  # секунд между оповещениями
        
    def check_alerts(self, code: str, currency: CurrencyData):
        """Проверка условий для оповещения"""
        if abs(currency.change_percent) >= self.threshold:
            last = self.last_alert.get(code, datetime(2000, 1, 1))
            if (datetime.now() - last).total_seconds() > self.alert_cooldown:
                self._send_alert(code, currency)
                self.last_alert[code] = datetime.now()
    
    def _send_alert(self, code: str, currency: CurrencyData):
        """Отправка оповещения"""
        direction = "📈" if currency.change > 0 else "📉"
        print(Fore.MAGENTA + f"\n⚠️ АЛЕРТ {direction} {code}: {currency.change_percent:+.2f}% "
              f"({currency.last:.4f})" + Style.RESET_ALL)
        
        # Здесь можно добавить отправку в Telegram, email и т.д.