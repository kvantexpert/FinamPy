#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Универсальный скрипт для поиска треугольного арбитража на Finam API
Автоматически находит все возможные валютные треугольники и ищет арбитраж
"""

import logging
import time
import threading
from datetime import datetime
from typing import Dict, List, Tuple, Optional, Set
from dataclasses import dataclass
from itertools import combinations
import math

from FinamPy import FinamPy
from FinamPy.grpc.orders.orders_service_pb2 import Order, OrderType
from FinamPy.grpc.marketdata.marketdata_service_pb2 import QuoteRequest, SubscribeQuoteResponse
from FinamPy.grpc.assets.assets_service_pb2 import AssetsRequest
import FinamPy.grpc.side_pb2 as side_pb
from google.type.decimal_pb2 import Decimal


# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%H:%M:%S',
    handlers=[
        logging.FileHandler('arbitrage_finder.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger('ArbitrageFinder')


@dataclass
class CurrencyPair:
    """Валютная пара"""
    base_currency: str      # Базовая валюта (например, USD)
    quote_currency: str     # Котируемая валюта (например, RUB)
    symbol: str             # Символ в Finam (USD000000TOD@CETS)
    bid: float = 0.0        # Текущая цена покупки
    ask: float = 0.0        # Текущая цена продажи
    last: float = 0.0       # Последняя сделка
    
    @property
    def name(self) -> str:
        return f"{self.base_currency}/{self.quote_currency}"


@dataclass
class Triangle:
    """Арбитражный треугольник"""
    pairs: List[CurrencyPair]           # 3 валютные пары
    operations: List[str]                # Операции: BUY или SELL для каждой пары
    formula_type: str                    # "MUL" или "DIV"
    synthetic_rate: float = 0.0          # Синтетический курс
    market_rate: float = 0.0              # Рыночный курс
    deviation: float = 0.0                # Отклонение в процентах
    deviation_points: float = 0.0         # Отклонение в пунктах
    
    @property
    def description(self) -> str:
        """Описание треугольника"""
        desc = ""
        for i, pair in enumerate(self.pairs):
            desc += f"{pair.base_currency}{pair.quote_currency} "
            desc += f"({self.operations[i]}) "
        desc += f"-> {self.pairs[2].base_currency}{self.pairs[2].quote_currency}"
        return desc


class ArbitrageFinder:
    """
    Поиск и исполнение треугольного арбитража на Finam
    """
    
    def __init__(self, 
                 min_deviation_points: float = 2.0,
                 min_profit_percent: float = 0.1,
                 max_spread_points: float = 3.0,
                 lot_size: float = 0.1,
                 max_concurrent_triangles: int = 3):
        """
        Инициализация поисковика арбитража
        
        Параметры:
            min_deviation_points: Минимальное отклонение в пунктах для входа
            min_profit_percent: Минимальная прибыль в процентах
            max_spread_points: Максимальный спред в пунктах
            lot_size: Базовый размер лота
            max_concurrent_triangles: Максимум одновременных треугольников
        """
        
        self.min_deviation_points = min_deviation_points
        self.min_profit_percent = min_profit_percent
        self.max_spread_points = max_spread_points
        self.lot_size = lot_size
        self.max_concurrent_triangles = max_concurrent_triangles
        
        # Подключение к Finam
        logger.info("Подключение к Finam API...")
        self.fp = FinamPy()
        self.account_id = self.fp.account_ids[0] if self.fp.account_ids else None
        
        if not self.account_id:
            raise Exception("Нет доступных счетов")
        
        logger.info(f"Подключено к счету: {self.account_id}")
        
        # Данные о валютах и парах
        self.currency_pairs: Dict[str, CurrencyPair] = {}  # symbol -> pair
        self.currencies: Set[str] = set()                   # Все найденные валюты
        self.triangles: List[Triangle] = []                  # Все возможные треугольники
        
        # Текущие котировки
        self.last_quotes: Dict[str, Dict] = {}
        
        # Активные треугольники
        self.active_triangles: List[Dict] = []
        
        # Флаги
        self.running = True
        
        # Загружаем все валютные пары
        self.load_currency_pairs()
        
        # Строим все возможные треугольники
        self.build_all_triangles()
        
        # Запускаем мониторинг котировок
        self.start_quotes_monitor()
        
        logger.info(f"Найдено валютных пар: {len(self.currency_pairs)}")
        logger.info(f"Найдено валют: {len(self.currencies)}")
        logger.info(f"Построено треугольников: {len(self.triangles)}")
    
    def load_currency_pairs(self):
        """Загрузка всех валютных пар с Финам"""
        logger.info("Загрузка валютных пар...")
        
        try:
            # Получаем все инструменты
            assets = self.fp.call_function(
                self.fp.assets_stub.Assets,
                AssetsRequest()
            )
            
            if not assets:
                logger.error("Не удалось загрузить инструменты")
                return
            
            # Фильтруем валютные пары (CETS)
            for asset in assets.assets:
                if asset.symbol.endswith('@CETS') and 'TOD' in asset.symbol:
                    # Парсим валютную пару
                    symbol = asset.symbol
                    
                    # Определяем валюты из символа
                    # Формат: USD000000TOD@CETS -> USD/RUB
                    if symbol.startswith('USD'):
                        base, quote = 'USD', 'RUB'
                    elif symbol.startswith('EUR'):
                        if 'RUB' in symbol:
                            base, quote = 'EUR', 'RUB'
                        else:
                            continue
                    elif symbol.startswith('CNY'):
                        base, quote = 'CNY', 'RUB'
                    elif symbol.startswith('GBP'):
                        base, quote = 'GBP', 'RUB'
                    elif symbol.startswith('CHF'):
                        base, quote = 'CHF', 'RUB'
                    elif symbol.startswith('JPY'):
                        base, quote = 'JPY', 'RUB'
                    elif symbol.startswith('HKD'):
                        base, quote = 'HKD', 'RUB'
                    elif symbol.startswith('BYN'):
                        base, quote = 'BYN', 'RUB'
                    elif symbol.startswith('KZT'):
                        base, quote = 'KZT', 'RUB'
                    elif symbol.startswith('TRY'):
                        base, quote = 'TRY', 'RUB'
                    elif symbol.startswith('AUD'):
                        base, quote = 'AUD', 'RUB'
                    elif symbol.startswith('CAD'):
                        base, quote = 'CAD', 'RUB'
                    else:
                        continue
                    
                    pair = CurrencyPair(
                        base_currency=base,
                        quote_currency=quote,
                        symbol=symbol
                    )
                    
                    self.currency_pairs[symbol] = pair
                    self.currencies.add(base)
                    self.currencies.add(quote)
            
            # Добавляем также пары RUB/USD (инвертированные)
            # Для полного покрытия треугольников
            
        except Exception as e:
            logger.error(f"Ошибка загрузки валютных пар: {e}")
    
    def build_all_triangles(self):
        """Построение всех возможных арбитражных треугольников"""
        logger.info("Построение всех возможных треугольников...")
        
        currencies_list = list(self.currencies)
        
        # Перебираем все тройки валют
        for c1, c2, c3 in combinations(currencies_list, 3):
            # Пробуем построить треугольники для этой тройки
            
            # Треугольник типа A/B * B/C = A/C
            pair1 = self.find_pair(c1, c2)
            pair2 = self.find_pair(c2, c3)
            pair3 = self.find_pair(c1, c3)
            
            if pair1 and pair2 and pair3:
                # Умножение: (c1/c2) * (c2/c3) = c1/c3
                triangle = Triangle(
                    pairs=[pair1, pair2, pair3],
                    operations=['BUY', 'BUY', 'SELL'],  # Направление для арбитража
                    formula_type="MUL"
                )
                self.triangles.append(triangle)
                
                # Обратное направление
                triangle_rev = Triangle(
                    pairs=[pair1, pair2, pair3],
                    operations=['SELL', 'SELL', 'BUY'],
                    formula_type="MUL"
                )
                self.triangles.append(triangle_rev)
            
            # Треугольник типа (c1/c2) / (c1/c3) = c3/c2
            pair1 = self.find_pair(c1, c2)
            pair2 = self.find_pair(c1, c3)
            pair3 = self.find_pair(c3, c2)
            
            if pair1 and pair2 and pair3:
                # Деление
                triangle = Triangle(
                    pairs=[pair1, pair2, pair3],
                    operations=['BUY', 'SELL', 'SELL'],  # Специфично для деления
                    formula_type="DIV"
                )
                self.triangles.append(triangle)
                
                # Обратное направление
                triangle_rev = Triangle(
                    pairs=[pair1, pair2, pair3],
                    operations=['SELL', 'BUY', 'BUY'],
                    formula_type="DIV"
                )
                self.triangles.append(triangle_rev)
    
    def find_pair(self, base: str, quote: str) -> Optional[CurrencyPair]:
        """Поиск валютной пары по базовой и котируемой валютам"""
        for pair in self.currency_pairs.values():
            if pair.base_currency == base and pair.quote_currency == quote:
                return pair
        return None
    
    def start_quotes_monitor(self):
        """Запуск мониторинга котировок"""
        
        def on_quote(quote: SubscribeQuoteResponse):
            """Обработчик новых котировок"""
            for q in quote.quote:
                symbol = q.symbol
                if symbol in self.currency_pairs:
                    pair = self.currency_pairs[symbol]
                    pair.bid = float(q.bid.value) if q.bid and q.bid.value else 0
                    pair.ask = float(q.ask.value) if q.ask and q.ask.value else 0
                    pair.last = float(q.last.value) if q.last and q.last.value else 0
                    
                    self.last_quotes[symbol] = {
                        'bid': pair.bid,
                        'ask': pair.ask,
                        'last': pair.last,
                        'timestamp': datetime.now()
                    }
        
        # Подписываемся на все валютные пары
        symbols = list(self.currency_pairs.keys())
        
        self.fp.on_quote.subscribe(on_quote)
        
        def quote_thread_func():
            logger.info(f"Запуск мониторинга {len(symbols)} валютных пар")
            self.fp.subscribe_quote_thread(tuple(symbols))
        
        thread = threading.Thread(target=quote_thread_func, daemon=True)
        thread.start()
        
        # Ждем первые котировки
        time.sleep(3)
    
    def check_spread(self, pair: CurrencyPair) -> bool:
        """Проверка спреда пары"""
        if pair.ask <= 0 or pair.bid <= 0:
            return False
        
        spread = (pair.ask - pair.bid) / 0.0001  # в пунктах
        return spread <= self.max_spread_points
    
    def calculate_triangle_rate(self, triangle: Triangle) -> Tuple[float, float, float]:
        """
        Расчет синтетического и рыночного курсов для треугольника
        
        Returns:
            (synthetic_rate, market_rate, deviation_points)
        """
        p1, p2, p3 = triangle.pairs
        
        if triangle.formula_type == "MUL":
            # Для умножения: p1 * p2 = p3
            
            if triangle.operations[0] == 'BUY' and triangle.operations[1] == 'BUY':
                # Покупаем p1 и p2 по ask, продаем p3 по bid
                synthetic = p1.ask * p2.ask
                market = p3.bid
            else:
                # Продаем p1 и p2 по bid, покупаем p3 по ask
                synthetic = p1.bid * p2.bid
                market = p3.ask
            
        else:  # DIV
            # Для деления: p1 / p2 = p3
            
            if triangle.operations[0] == 'BUY' and triangle.operations[1] == 'SELL':
                # Покупаем p1 по ask, продаем p2 по bid
                if p2.bid > 0:
                    synthetic = p1.ask / p2.bid
                else:
                    synthetic = 0
                market = p3.bid
            else:
                # Продаем p1 по bid, покупаем p2 по ask
                if p2.ask > 0:
                    synthetic = p1.bid / p2.ask
                else:
                    synthetic = 0
                market = p3.ask
        
        if market > 0 and synthetic > 0:
            deviation_percent = ((market - synthetic) / synthetic) * 100
            deviation_points = (market - synthetic) / 0.0001
        else:
            deviation_percent = 0
            deviation_points = 0
        
        return synthetic, market, deviation_points
    
    def find_arbitrage_opportunities(self) -> List[Triangle]:
        """Поиск арбитражных возможностей среди всех треугольников"""
        opportunities = []
        
        for triangle in self.triangles:
            # Проверяем наличие котировок
            if not all(p.bid > 0 and p.ask > 0 for p in triangle.pairs):
                continue
            
            # Проверяем спреды
            if not all(self.check_spread(p) for p in triangle.pairs):
                continue
            
            # Рассчитываем отклонение
            synthetic, market, deviation = self.calculate_triangle_rate(triangle)
            
            if abs(deviation) >= self.min_deviation_points:
                triangle.synthetic_rate = synthetic
                triangle.market_rate = market
                triangle.deviation = deviation
                opportunities.append(triangle)
        
        # Сортируем по величине отклонения
        opportunities.sort(key=lambda t: abs(t.deviation), reverse=True)
        
        return opportunities
    
    def execute_arbitrage(self, triangle: Triangle) -> bool:
        """
        Исполнение арбитражной сделки
        """
        logger.info(f"🎯 Исполнение арбитража: {triangle.description}")
        logger.info(f"    Отклонение: {triangle.deviation:.2f} pts")
        
        tickets = []
        
        try:
            for i, pair in enumerate(triangle.pairs):
                operation = triangle.operations[i]
                
                # Определяем сторону сделки
                side = side_pb.SIDE_BUY if operation == 'BUY' else side_pb.SIDE_SELL
                
                # Рассчитываем лот (базовый с корректировкой)
                lot = self.lot_size
                if i == 1:
                    lot *= 1.05  # Немного корректируем для второй пары
                elif i == 2:
                    lot *= 0.98  # Корректируем для третьей пары
                
                lot = round(lot, 2)
                
                # Создаем заявку
                order = Order(
                    account_id=self.account_id,
                    symbol=pair.symbol,
                    quantity=Decimal(value=str(lot)),
                    side=side,
                    type=OrderType.ORDER_TYPE_MARKET,
                    client_order_id=f"arb_{int(time.time())}_{i}",
                    comment=f"ARB_{triangle.formula_type}_{i}"
                )
                
                logger.info(f"  Открытие {pair.name} {operation} лот {lot}")
                
                # Отправляем заявку
                order_state = self.fp.call_function(self.fp.orders_stub.PlaceOrder, order)
                
                if order_state and order_state.order_id:
                    tickets.append(order_state.order_id)
                    logger.info(f"    ✓ Исполнено, тикет {order_state.order_id}")
                    time.sleep(0.5)
                else:
                    logger.error(f"    ✗ Ошибка открытия {pair.name}")
                    # Откатываем уже открытые
                    for ticket in tickets:
                        self.close_position(ticket)
                    return False
            
            # Сохраняем в активные
            self.active_triangles.append({
                'triangle': triangle,
                'tickets': tickets,
                'open_time': datetime.now(),
                'expected_profit': triangle.deviation * self.lot_size * 10
            })
            
            logger.info(f"✅ Арбитраж успешно открыт!")
            return True
            
        except Exception as e:
            logger.error(f"Ошибка исполнения арбитража: {e}")
            for ticket in tickets:
                self.close_position(ticket)
            return False
    
    def close_position(self, ticket: str) -> bool:
        """Закрытие позиции по тикету"""
        try:
            from FinamPy.grpc.orders.orders_service_pb2 import CancelOrderRequest
            
            result = self.fp.call_function(
                self.fp.orders_stub.CancelOrder,
                CancelOrderRequest(account_id=self.account_id, order_id=ticket)
            )
            
            if result:
                logger.info(f"Позиция {ticket} закрыта")
                return True
            return False
            
        except Exception as e:
            logger.error(f"Ошибка закрытия {ticket}: {e}")
            return False
    
    def monitor_active_positions(self):
        """Мониторинг открытых позиций"""
        to_remove = []
        
        for active in self.active_triangles:
            # Здесь можно добавить логику закрытия по тейк-профиту или стоп-лоссу
            # Пока просто проверяем время
            
            if (datetime.now() - active['open_time']).seconds > 3600:  # 1 час
                logger.info(f"Закрытие треугольника по времени")
                for ticket in active['tickets']:
                    self.close_position(ticket)
                to_remove.append(active)
        
        for item in to_remove:
            self.active_triangles.remove(item)
    
    def print_opportunities(self, opportunities: List[Triangle]):
        """Вывод найденных возможностей"""
        if not opportunities:
            print("\n❌ Арбитражные возможности не найдены")
            return
        
        print("\n" + "=" * 90)
        print(f"🔥 НАЙДЕНЫ АРБИТРАЖНЫЕ ВОЗМОЖНОСТИ ({len(opportunities)})")
        print("=" * 90)
        
        for i, t in enumerate(opportunities[:10]):  # Топ-10
            direction = "📈" if t.deviation > 0 else "📉"
            print(f"\n{i+1}. {direction} {t.description}")
            print(f"   Операции: {t.operations}")
            print(f"   Отклонение: {t.deviation:+.2f} pts ({t.deviation/0.0001:.4f}%)")
            print(f"   Синтетический: {t.synthetic_rate:.6f}")
            print(f"   Рыночный: {t.market_rate:.6f}")
            
            # Показываем текущие цены
            for j, p in enumerate(t.pairs):
                print(f"      {p.name}: Bid={p.bid:.6f} Ask={p.ask:.6f}")
    
    def print_all_triangles(self):
        """Вывод всех возможных треугольников"""
        print("\n" + "=" * 90)
        print(f"📊 ВСЕ ВОЗМОЖНЫЕ ТРЕУГОЛЬНИКИ ({len(self.triangles)})")
        print("=" * 90)
        
        by_type = {"MUL": [], "DIV": []}
        for t in self.triangles:
            by_type[t.formula_type].append(t)
        
        print(f"\n📌 Треугольники умножения (MUL): {len(by_type['MUL'])}")
        for i, t in enumerate(by_type['MUL'][:10]):
            print(f"  {i+1}. {t.description}")
        
        print(f"\n📌 Треугольники деления (DIV): {len(by_type['DIV'])}")
        for i, t in enumerate(by_type['DIV'][:10]):
            print(f"  {i+1}. {t.description}")
    
    def print_currency_pairs(self):
        """Вывод всех валютных пар"""
        print("\n" + "=" * 90)
        print("💱 ДОСТУПНЫЕ ВАЛЮТНЫЕ ПАРЫ")
        print("=" * 90)
        
        rub_pairs = []
        cross_pairs = []
        
        for pair in self.currency_pairs.values():
            if pair.quote_currency == 'RUB':
                rub_pairs.append(pair)
            else:
                cross_pairs.append(pair)
        
        print(f"\n📌 Пары к рублю ({len(rub_pairs)}):")
        for pair in sorted(rub_pairs, key=lambda p: p.base_currency):
            print(f"  {pair.base_currency}/{pair.quote_currency}: {pair.symbol}")
        
        if cross_pairs:
            print(f"\n📌 Кросс-пары ({len(cross_pairs)}):")
            for pair in sorted(cross_pairs, key=lambda p: p.base_currency):
                print(f"  {pair.base_currency}/{pair.quote_currency}: {pair.symbol}")
    
    def run(self):
        """Основной цикл поиска арбитража"""
        logger.info("=" * 90)
        logger.info("🚀 ЗАПУСК ПОИСКА АРБИТРАЖА")
        logger.info("=" * 90)
        
        self.print_currency_pairs()
        self.print_all_triangles()
        
        last_scan_time = datetime.now()
        
        try:
            while self.running:
                current_time = datetime.now()
                
                # Сканируем каждые 5 секунд
                if (current_time - last_scan_time).seconds >= 5:
                    opportunities = self.find_arbitrage_opportunities()
                    
                    if opportunities:
                        self.print_opportunities(opportunities)
                        
                        # Если есть сильные возможности, исполняем
                        best = opportunities[0]
                        if abs(best.deviation) >= self.min_deviation_points * 2:
                            if len(self.active_triangles) < self.max_concurrent_triangles:
                                self.execute_arbitrage(best)
                    
                    last_scan_time = current_time
                
                # Мониторим активные позиции
                self.monitor_active_positions()
                
                time.sleep(1)
                
        except KeyboardInterrupt:
            logger.info("Остановка по запросу пользователя")
        finally:
            self.cleanup()
    
    def cleanup(self):
        """Очистка при завершении"""
        logger.info("Завершение работы...")
        self.running = False
        
        # Закрываем все позиции
        for active in self.active_triangles:
            for ticket in active['tickets']:
                self.close_position(ticket)
        
        if self.fp:
            self.fp.close_channel()
        
        logger.info("Бот остановлен")


def main():
    """Главная функция"""
    
    print("\n" + "=" * 90)
    print("🔍 ПОИСК ТРЕУГОЛЬНОГО АРБИТРАЖА НА FINAM")
    print("=" * 90)
    
    # Создаем бота с параметрами
    bot = ArbitrageFinder(
        min_deviation_points=2.0,      # Минимальное отклонение 2 пункта
        min_profit_percent=0.1,        # Минимальная прибыль 0.1%
        max_spread_points=3.0,         # Максимальный спред 3 пункта
        lot_size=0.1,                   # Размер лота
        max_concurrent_triangles=2      # Максимум 2 одновременных треугольника
    )
    
    # Запускаем
    bot.run()


if __name__ == "__main__":
    main()