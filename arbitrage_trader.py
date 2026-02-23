#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Скрипт для треугольного арбитража на Finam API
Использует валютные пары из currency_rates.py
Автор: Ваше имя
Дата: 22.02.2026
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
from FinamPy.grpc.orders.orders_service_pb2 import Order, OrderType, CancelOrderRequest
from FinamPy.grpc.marketdata.marketdata_service_pb2 import QuoteRequest, SubscribeQuoteResponse
from FinamPy.grpc.accounts.accounts_service_pb2 import GetAccountRequest
import FinamPy.grpc.side_pb2 as side_pb
from google.type.decimal_pb2 import Decimal


# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%H:%M:%S',
    handlers=[
        logging.FileHandler('arbitrage_trader.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger('ArbitrageTrader')


@dataclass
class CurrencyPair:
    """Валютная пара"""
    base_currency: str      # Базовая валюта (например, USD)
    quote_currency: str     # Котируемая валюта (например, RUB)
    symbol: str             # Символ в Finam (USD000000TOD@CETS)
    name: str = ""          # Название пары
    bid: float = 0.0        # Текущая цена покупки
    ask: float = 0.0        # Текущая цена продажи
    last: float = 0.0       # Последняя сделка
    
    @property
    def display_name(self) -> str:
        return f"{self.base_currency}/{self.quote_currency}"


@dataclass
class Triangle:
    """Арбитражный треугольник"""
    pairs: List[CurrencyPair]           # 3 валютные пары
    operations: List[str]                # Операции: BUY или SELL для каждой пары
    formula_type: str                    # "MUL" или "DIV"
    synthetic_rate: float = 0.0          # Синтетический курс
    market_rate: float = 0.0              # Рыночный курс
    deviation_points: float = 0.0         # Отклонение в пунктах
    deviation_percent: float = 0.0        # Отклонение в процентах
    
    @property
    def description(self) -> str:
        """Описание треугольника"""
        ops_str = []
        for i, p in enumerate(self.pairs):
            ops_str.append(f"{p.base_currency}/{p.quote_currency}({self.operations[i]})")
        return " × ".join(ops_str) if self.formula_type == "MUL" else " / ".join(ops_str)


@dataclass
class ActiveTriangle:
    """Активный открытый треугольник"""
    triangle: Triangle
    tickets: List[str]          # Тикеты позиций
    entry_prices: List[float]   # Цены входа
    lots: List[float]           # Лоты
    open_time: datetime         # Время открытия
    expected_profit: float      # Ожидаемая прибыль


class ArbitrageTrader:
    """
    Торговый бот для треугольного арбитража на Finam
    """
    
    def __init__(self, 
                 min_deviation_points: float = 2.0,      # Минимальное отклонение в пунктах
                 max_spread_points: float = 3.0,         # Максимальный спред в пунктах
                 lot_size: float = 0.1,                  # Размер лота
                 max_concurrent_triangles: int = 2,      # Максимум одновременных треугольников
                 take_profit_points: float = 5.0,        # Тейк-профит в пунктах
                 stop_loss_points: float = 3.0):         # Стоп-лосс в пунктах
        """
        Инициализация торгового бота
        """
        
        self.min_deviation_points = min_deviation_points
        self.max_spread_points = max_spread_points
        self.lot_size = lot_size
        self.max_concurrent_triangles = max_concurrent_triangles
        self.take_profit_points = take_profit_points
        self.stop_loss_points = stop_loss_points
        
        # Подключение к Finam
        logger.info("Подключение к Finam API...")
        self.fp = FinamPy()
        self.account_id = self.fp.account_ids[0] if self.fp.account_ids else None
        
        if not self.account_id:
            raise Exception("Нет доступных счетов")
        
        logger.info(f"Подключено к счету: {self.account_id}")
        
        # Проверяем баланс
        self.check_balance()
        
        # Словарь валютных пар (как в currency_rates.py)
        self.currency_pairs: Dict[str, CurrencyPair] = {}
        self.init_currency_pairs()
        
        # Все возможные треугольники
        self.triangles: List[Triangle] = []
        self.build_all_triangles()
        
        # Текущие котировки
        self.last_quotes: Dict[str, Dict] = {}
        
        # Активные треугольники
        self.active_triangles: List[ActiveTriangle] = []
        
        # Флаги
        self.running = True
        
        # Запускаем мониторинг котировок
        self.start_quotes_monitor()
        
        logger.info(f"Загружено валютных пар: {len(self.currency_pairs)}")
        logger.info(f"Построено треугольников: {len(self.triangles)}")
        logger.info("=" * 80)
        logger.info("🚀 БОТ ТРЕУГОЛЬНОГО АРБИТРАЖА ЗАПУЩЕН")
        logger.info("=" * 80)
    
    def init_currency_pairs(self):
        """Инициализация валютных пар (как в currency_rates.py)"""
        
        # Словарь валют: код валюты -> тикер на бирже
        currency_symbols = {
            'USD': 'USD000000TOD@CETS',    # Доллар США
            'EUR': 'EUR_RUB__TOD@CETS',    # Евро
            'CNY': 'CNY000000TOD@CETS',    # Китайский юань
            'GBP': 'GBP000000TOD@CETS',    # Британский фунт
            'CHF': 'CHF000000TOD@CETS',    # Швейцарский франк
            'JPY': 'JPY000000TOD@CETS',    # Японская иена (в сотнях)
            'HKD': 'HKD000000TOD@CETS',    # Гонконгский доллар
            'BYN': 'BYN000000TOD@CETS',    # Белорусский рубль
            'KZT': 'KZT000000TOD@CETS',    # Казахстанский тенге (в сотнях)
            'TRY': 'TRY000000TOD@CETS',    # Турецкая лира
            'AUD': 'AUD000000TOD@CETS',    # Австралийский доллар
            'CAD': 'CAD000000TOD@CETS',    # Канадский доллар
            'NOK': 'NOK000000TOD@CETS',    # Норвежская крона
            'SEK': 'SEK000000TOD@CETS',    # Шведская крона
            'DKK': 'DKK000000TOD@CETS',    # Датская крона
            'CZK': 'CZK000000TOD@CETS',    # Чешская крона
            'PLN': 'PLN000000TOD@CETS',    # Польский злотый
            'INR': 'INR000000TOD@CETS',    # Индийская рупия
            'BRL': 'BRL000000TOD@CETS',    # Бразильский реал
            'ZAR': 'ZAR000000TOD@CETS',    # Южноафриканский рэнд
        }
        
        # Названия валют на русском
        currency_names = {
            'USD': 'Доллар США',
            'EUR': 'Евро',
            'CNY': 'Китайский юань',
            'GBP': 'Фунт стерлингов',
            'CHF': 'Швейцарский франк',
            'JPY': 'Японская иена (100)',
            'HKD': 'Гонконгский доллар',
            'BYN': 'Белорусский рубль',
            'KZT': 'Казахстанский тенге (100)',
            'TRY': 'Турецкая лира',
            'AUD': 'Австралийский доллар',
            'CAD': 'Канадский доллар',
            'NOK': 'Норвежская крона',
            'SEK': 'Шведская крона',
            'DKK': 'Датская крона',
            'CZK': 'Чешская крона',
            'PLN': 'Польский злотый',
            'INR': 'Индийская рупия',
            'BRL': 'Бразильский реал',
            'ZAR': 'Южноафриканский рэнд',
        }
        
        # Создаем объекты валютных пар
        for code, symbol in currency_symbols.items():
            pair = CurrencyPair(
                base_currency=code,
                quote_currency='RUB',
                symbol=symbol,
                name=currency_names.get(code, code)
            )
            self.currency_pairs[symbol] = pair
    
    def check_balance(self):
        """Проверка баланса счета"""
        try:
            account = self.fp.call_function(
                self.fp.accounts_stub.GetAccount,
                GetAccountRequest(account_id=self.account_id)
            )
            if account and account.cash:
                for cash in account.cash:
                    amount = cash.units + cash.nanos / 1e9
                    logger.info(f"💰 Баланс счета: {amount:.2f} {cash.currency_code}")
        except Exception as e:
            logger.error(f"Ошибка проверки баланса: {e}")
    
    def build_all_triangles(self):
        """Построение всех возможных арбитражных треугольников"""
        
        # Получаем список всех валют (базовые валюты)
        currencies = list(set(p.base_currency for p in self.currency_pairs.values()))
        currencies.append('RUB')  # Добавляем рубль
        
        logger.info(f"Доступные валюты: {currencies}")
        
        # Перебираем все тройки валют
        for c1, c2, c3 in combinations(currencies, 3):
            # Треугольник типа A/B * B/C = A/C
            self._build_multiplication_triangle(c1, c2, c3)
            
            # Треугольник типа (A/C) / (A/B) = B/C
            self._build_division_triangle(c1, c2, c3)
    
    def _build_multiplication_triangle(self, c1: str, c2: str, c3: str):
        """Построение треугольника умножения: A/B * B/C = A/C"""
        
        # Ищем пары
        pair_ab = self._find_pair(c1, c2)
        pair_bc = self._find_pair(c2, c3)
        pair_ac = self._find_pair(c1, c3)
        
        if pair_ab and pair_bc and pair_ac:
            # Прямое направление: BUY A/B, BUY B/C, SELL A/C
            triangle1 = Triangle(
                pairs=[pair_ab, pair_bc, pair_ac],
                operations=['BUY', 'BUY', 'SELL'],
                formula_type="MUL"
            )
            self.triangles.append(triangle1)
            
            # Обратное направление: SELL A/B, SELL B/C, BUY A/C
            triangle2 = Triangle(
                pairs=[pair_ab, pair_bc, pair_ac],
                operations=['SELL', 'SELL', 'BUY'],
                formula_type="MUL"
            )
            self.triangles.append(triangle2)
    
    def _build_division_triangle(self, c1: str, c2: str, c3: str):
        """Построение треугольника деления: (A/C) / (A/B) = B/C"""
        
        pair_ac = self._find_pair(c1, c3)
        pair_ab = self._find_pair(c1, c2)
        pair_bc = self._find_pair(c2, c3)
        
        if pair_ac and pair_ab and pair_bc:
            # Прямое направление: BUY A/C, SELL A/B, SELL B/C
            triangle1 = Triangle(
                pairs=[pair_ac, pair_ab, pair_bc],
                operations=['BUY', 'SELL', 'SELL'],
                formula_type="DIV"
            )
            self.triangles.append(triangle1)
            
            # Обратное направление: SELL A/C, BUY A/B, BUY B/C
            triangle2 = Triangle(
                pairs=[pair_ac, pair_ab, pair_bc],
                operations=['SELL', 'BUY', 'BUY'],
                formula_type="DIV"
            )
            self.triangles.append(triangle2)
    
    def _find_pair(self, base: str, quote: str) -> Optional[CurrencyPair]:
        """Поиск валютной пары"""
        if quote == 'RUB':
            # Ищем пару base/RUB
            for pair in self.currency_pairs.values():
                if pair.base_currency == base and pair.quote_currency == 'RUB':
                    return pair
        elif base == 'RUB':
            # Для пар RUB/quote создаем виртуальную пару (через обратный курс)
            # Находим пару quote/RUB и будем использовать обратный курс
            for pair in self.currency_pairs.values():
                if pair.base_currency == quote and pair.quote_currency == 'RUB':
                    # Создаем виртуальную пару RUB/quote
                    virtual_pair = CurrencyPair(
                        base_currency='RUB',
                        quote_currency=quote,
                        symbol=f"VIRTUAL_RUB{quote}",
                        name=f"Виртуальная RUB/{quote}"
                    )
                    return virtual_pair
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
        
        logger.info(f"Подписка на {len(symbols)} валютных пар")
        self.fp.on_quote.subscribe(on_quote)
        
        def quote_thread_func():
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
    
    def get_effective_rate(self, pair: CurrencyPair, operation: str) -> float:
        """Получение эффективного курса для операции"""
        if pair.symbol.startswith('VIRTUAL'):
            # Для виртуальных пар (RUB/XXX) используем обратный курс
            real_pair = None
            for p in self.currency_pairs.values():
                if p.base_currency == pair.quote_currency and p.quote_currency == 'RUB':
                    real_pair = p
                    break
            
            if real_pair:
                if operation == 'BUY':
                    # Покупка RUB/XXX = продажа XXX/RUB
                    return 1 / real_pair.ask if real_pair.ask > 0 else 0
                else:
                    # Продажа RUB/XXX = покупка XXX/RUB
                    return 1 / real_pair.bid if real_pair.bid > 0 else 0
            return 0
        else:
            # Обычная пара
            return pair.ask if operation == 'BUY' else pair.bid
    
    def calculate_triangle(self, triangle: Triangle) -> Tuple[float, float, float, float]:
        """
        Расчет синтетического и рыночного курсов для треугольника
        Возвращает: (synthetic_rate, market_rate, deviation_points, deviation_percent)
        """
        p1, p2, p3 = triangle.pairs
        
        # Получаем эффективные курсы для каждой операции
        rate1 = self.get_effective_rate(p1, triangle.operations[0])
        rate2 = self.get_effective_rate(p2, triangle.operations[1])
        rate3 = self.get_effective_rate(p3, triangle.operations[2])
        
        if rate1 <= 0 or rate2 <= 0 or rate3 <= 0:
            return 0, 0, 0, 0
        
        if triangle.formula_type == "MUL":
            synthetic = rate1 * rate2
            market = rate3
        else:  # DIV
            if rate2 > 0:
                synthetic = rate1 / rate2
            else:
                synthetic = 0
            market = rate3
        
        if market > 0 and synthetic > 0:
            deviation_points = (market - synthetic) / 0.0001
            deviation_percent = ((market - synthetic) / synthetic) * 100
        else:
            deviation_points = 0
            deviation_percent = 0
        
        return synthetic, market, deviation_points, deviation_percent
    
    def find_opportunities(self) -> List[Triangle]:
        """Поиск арбитражных возможностей"""
        opportunities = []
        
        for triangle in self.triangles:
            # Проверяем наличие котировок
            all_have_quotes = True
            for p in triangle.pairs:
                if p.symbol.startswith('VIRTUAL'):
                    # Для виртуальных пар проверяем реальные
                    real_pair = None
                    for rp in self.currency_pairs.values():
                        if rp.base_currency == p.quote_currency and rp.quote_currency == 'RUB':
                            real_pair = rp
                            break
                    if not real_pair or real_pair.bid <= 0 or real_pair.ask <= 0:
                        all_have_quotes = False
                        break
                elif p.bid <= 0 or p.ask <= 0:
                    all_have_quotes = False
                    break
            
            if not all_have_quotes:
                continue
            
            # Проверяем спреды для реальных пар
            spread_ok = True
            for p in triangle.pairs:
                if not p.symbol.startswith('VIRTUAL'):
                    if not self.check_spread(p):
                        spread_ok = False
                        break
            
            if not spread_ok:
                continue
            
            # Рассчитываем отклонение
            synthetic, market, dev_points, dev_percent = self.calculate_triangle(triangle)
            
            if abs(dev_points) >= self.min_deviation_points:
                triangle.synthetic_rate = synthetic
                triangle.market_rate = market
                triangle.deviation_points = dev_points
                triangle.deviation_percent = dev_percent
                opportunities.append(triangle)
        
        # Сортируем по абсолютному отклонению
        opportunities.sort(key=lambda t: abs(t.deviation_points), reverse=True)
        
        return opportunities
    
    def calculate_lots(self, triangle: Triangle) -> List[float]:
        """Расчет лотов для треугольника"""
        lots = [self.lot_size, self.lot_size, self.lot_size]
        
        # Корректировка лотов для балансировки
        p1, p2, p3 = triangle.pairs
        
        # Базовая корректировка в зависимости от типа треугольника
        if triangle.formula_type == "MUL":
            lots[2] = self.lot_size * 0.98  # Немного уменьшаем лот третьей пары
        else:
            lots[2] = self.lot_size * 1.02  # Немного увеличиваем лот третьей пары
        
        # Округляем до 2 знаков
        lots = [round(lot, 2) for lot in lots]
        
        return lots
    
    def execute_triangle(self, triangle: Triangle) -> bool:
        """
        Исполнение арбитражной сделки
        """
        if len(self.active_triangles) >= self.max_concurrent_triangles:
            logger.warning("Достигнут лимит одновременных треугольников")
            return False
        
        logger.info("=" * 80)
        logger.info(f"🎯 НАЙДЕНА АРБИТРАЖНАЯ ВОЗМОЖНОСТЬ")
        logger.info(f"Треугольник: {triangle.description}")
        logger.info(f"Тип: {triangle.formula_type}")
        logger.info(f"Отклонение: {triangle.deviation_points:+.2f} pts ({triangle.deviation_percent:+.4f}%)")
        logger.info(f"Синтетический курс: {triangle.synthetic_rate:.6f}")
        logger.info(f"Рыночный курс: {triangle.market_rate:.6f}")
        logger.info("-" * 80)
        
        tickets = []
        entry_prices = []
        lots = self.calculate_lots(triangle)
        
        try:
            for i, pair in enumerate(triangle.pairs):
                operation = triangle.operations[i]
                
                # Определяем сторону сделки
                side = side_pb.SIDE_BUY if operation == 'BUY' else side_pb.SIDE_SELL
                
                # Получаем цену для исполнения
                if pair.symbol.startswith('VIRTUAL'):
                    # Для виртуальных пар используем реальную цену через обратную пару
                    real_pair = None
                    for rp in self.currency_pairs.values():
                        if rp.base_currency == pair.quote_currency and rp.quote_currency == 'RUB':
                            real_pair = rp
                            break
                    
                    if real_pair:
                        price = real_pair.ask if side == side_pb.SIDE_SELL else real_pair.bid
                        price = 1 / price if price > 0 else 0
                        symbol = real_pair.symbol
                    else:
                        logger.error(f"Не найдена реальная пара для {pair.display_name}")
                        return False
                else:
                    price = pair.ask if side == side_pb.SIDE_BUY else pair.bid
                    symbol = pair.symbol
                
                logger.info(f"  {i+1}. {pair.display_name} {operation} лот {lots[i]} по цене {price:.6f}")
                
                # Создаем заявку
                order = Order(
                    account_id=self.account_id,
                    symbol=symbol,
                    quantity=Decimal(value=str(lots[i])),
                    side=side,
                    type=OrderType.ORDER_TYPE_MARKET,
                    client_order_id=f"arb_{int(time.time())}_{i}",
                    comment=f"ARB_{triangle.formula_type}_{i}"
                )
                
                # Отправляем заявку
                order_state = self.fp.call_function(self.fp.orders_stub.PlaceOrder, order)
                
                if order_state and order_state.order_id:
                    tickets.append(order_state.order_id)
                    entry_prices.append(price)
                    logger.info(f"    ✓ Исполнено, тикет {order_state.order_id}")
                    time.sleep(0.5)  # Пауза между заявками
                else:
                    logger.error(f"    ✗ Ошибка открытия {pair.display_name}")
                    # Откатываем уже открытые
                    for ticket in tickets:
                        self.close_position(ticket)
                    return False
            
            # Сохраняем активный треугольник
            active = ActiveTriangle(
                triangle=triangle,
                tickets=tickets,
                entry_prices=entry_prices,
                lots=lots,
                open_time=datetime.now(),
                expected_profit=triangle.deviation_points * self.lot_size * 1000
            )
            self.active_triangles.append(active)
            
            logger.info(f"✅ ТРЕУГОЛЬНИК УСПЕШНО ОТКРЫТ!")
            logger.info(f"   Ожидаемая прибыль: {active.expected_profit:.2f} ₽")
            logger.info("=" * 80)
            
            return True
            
        except Exception as e:
            logger.error(f"Ошибка исполнения арбитража: {e}")
            for ticket in tickets:
                self.close_position(ticket)
            return False
    
    def close_position(self, ticket: str) -> bool:
        """Закрытие позиции по тикету"""
        try:
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
    
    def monitor_active_triangles(self):
        """Мониторинг открытых треугольников"""
        to_remove = []
        
        for active in self.active_triangles:
            # Получаем текущие цены и рассчитываем прибыль
            current_profit = 0
            all_closed = True
            
            for i, ticket in enumerate(active.tickets):
                try:
                    from FinamPy.grpc.orders.orders_service_pb2 import GetOrderRequest
                    
                    order_state = self.fp.call_function(
                        self.fp.orders_stub.GetOrder,
                        GetOrderRequest(account_id=self.account_id, order_id=ticket)
                    )
                    
                    if order_state:
                        all_closed = False
                        
                        # Получаем текущую цену
                        pair = active.triangle.pairs[i]
                        if pair.symbol.startswith('VIRTUAL'):
                            # Для виртуальных пар
                            for rp in self.currency_pairs.values():
                                if rp.base_currency == pair.quote_currency and rp.quote_currency == 'RUB':
                                    current_price = rp.last
                                    if current_price > 0:
                                        current_price = 1 / current_price
                                    break
                            else:
                                current_price = 0
                        else:
                            current_price = pair.last
                        
                        if current_price > 0 and active.entry_prices[i] > 0:
                            if order_state.order.side == side_pb.SIDE_BUY:
                                profit = (current_price - active.entry_prices[i]) * active.lots[i] * 100000
                            else:
                                profit = (active.entry_prices[i] - current_price) * active.lots[i] * 100000
                            current_profit += profit
                except:
                    pass
            
            if all_closed:
                to_remove.append(active)
                continue
            
            # Проверка условий закрытия
            if current_profit >= self.take_profit_points * self.lot_size * 1000:
                logger.info(f"🎯 Тейк-профит достигнут: +{current_profit:.2f} ₽")
                for ticket in active.tickets:
                    self.close_position(ticket)
                to_remove.append(active)
            
            elif current_profit <= -self.stop_loss_points * self.lot_size * 1000:
                logger.info(f"🛑 Стоп-лосс сработал: {current_profit:.2f} ₽")
                for ticket in active.tickets:
                    self.close_position(ticket)
                to_remove.append(active)
        
        # Удаляем закрытые треугольники
        for active in to_remove:
            self.active_triangles.remove(active)
    
    def print_status(self):
        """Вывод статуса бота"""
        print("\n" + "=" * 80)
        print(f"📊 СТАТУС БОТА - {datetime.now().strftime('%H:%M:%S')}")
        print("=" * 80)
        print(f"Активных треугольников: {len(self.active_triangles)}/{self.max_concurrent_triangles}")
        
        if self.active_triangles:
            print("-" * 80)
            for i, active in enumerate(self.active_triangles):
                print(f"\nТреугольник #{i+1}:")
                print(f"  {active.triangle.description}")
                print(f"  Открыт: {active.open_time.strftime('%H:%M:%S')}")
                print(f"  Ожидаемая прибыль: {active.expected_profit:.2f} ₽")
    
    def run(self):
        """Основной цикл работы бота"""
        last_scan_time = datetime.now()
        last_status_time = datetime.now()
        
        try:
            while self.running:
                current_time = datetime.now()
                
                # Сканируем возможности каждые 3 секунды
                if (current_time - last_scan_time).seconds >= 3:
                    opportunities = self.find_opportunities()
                    
                    if opportunities:
                        # Берём лучшую возможность
                        best = opportunities[0]
                        if abs(best.deviation_points) >= self.min_deviation_points:
                            self.execute_triangle(best)
                    
                    last_scan_time = current_time
                
                # Мониторим активные треугольники
                self.monitor_active_triangles()
                
                # Выводим статус каждые 10 секунд
                if (current_time - last_status_time).seconds >= 10:
                    self.print_status()
                    last_status_time = current_time
                
                time.sleep(1)
                
        except KeyboardInterrupt:
            logger.info("Остановка по запросу пользователя")
        finally:
            self.cleanup()
    
    def cleanup(self):
        """Очистка при завершении"""
        logger.info("Завершение работы...")
        self.running = False
        
        # Закрываем все активные треугольники
        for active in self.active_triangles:
            for ticket in active.tickets:
                self.close_position(ticket)
        
        if self.fp:
            self.fp.close_channel()
        
        logger.info("Бот остановлен")


def main():
    """Главная функция"""
    
    print("\n" + "=" * 80)
    print("🔄 ТРЕУГОЛЬНЫЙ АРБИТРАЖ НА FINAM API")
    print("=" * 80)
    print("\nНастройки по умолчанию:")
    print("  • Минимальное отклонение: 2.0 пункта")
    print("  • Максимальный спред: 3.0 пункта")
    print("  • Размер лота: 0.1")
    print("  • Максимум треугольников: 2")
    print("  • Тейк-профит: 5.0 пунктов")
    print("  • Стоп-лосс: 3.0 пункта")
    print("=" * 80)
    
    # Создаем бота
    bot = ArbitrageTrader(
        min_deviation_points=2.0,
        max_spread_points=3.0,
        lot_size=0.1,
        max_concurrent_triangles=2,
        take_profit_points=5.0,
        stop_loss_points=3.0
    )
    
    # Запускаем
    bot.run()


if __name__ == "__main__":
    main()