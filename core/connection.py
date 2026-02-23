#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Модуль подключения и диагностики Finam API
"""

import logging
import sys
from datetime import datetime
from typing import Optional, List, Dict
import time

from FinamPy import FinamPy
from FinamPy.grpc.assets.assets_service_pb2 import ClockRequest
from FinamPy.grpc.accounts.accounts_service_pb2 import GetAccountRequest

logger = logging.getLogger('FinamConnection')

class FinamConnection:
    """Класс для управления подключением к Finam API"""
    
    def __init__(self, token: Optional[str] = None):
        """
        Инициализация подключения
        
        Args:
            token: Торговый токен (опционально, если уже сохранен)
        """
        self.fp = None
        self.token = token
        self.connected = False
        self.account_id = None
        self.connection_time = None
        self.diagnostic_results = {}
        
    def connect(self) -> bool:
        """Установка соединения с Finam API"""
        try:
            logger.info("🔄 Подключение к Finam API...")
            
            if self.token:
                self.fp = FinamPy(self.token)
            else:
                self.fp = FinamPy()
            
            self.connection_time = datetime.now()
            self.connected = True
            
            # Получаем информацию о счетах
            if self.fp.account_ids:
                self.account_id = self.fp.account_ids[0]
                logger.info(f"✅ Подключено к счету: {self.account_id}")
            else:
                logger.warning("⚠️ Нет доступных счетов")
            
            return True
            
        except Exception as e:
            logger.error(f"❌ Ошибка подключения: {e}")
            self.connected = False
            return False
    
    def run_diagnostics(self) -> Dict:
        """Запуск полной диагностики подключения"""
        logger.info("=" * 60)
        logger.info("🔍 ЗАПУСК ДИАГНОСТИКИ FINAM API")
        logger.info("=" * 60)
        
        results = {}
        
        # 1. Проверка подключения
        logger.info("\n📡 1. Проверка подключения...")
        if not self.connected and not self.connect():
            results['connection'] = {'status': 'ERROR', 'message': 'Не удалось подключиться'}
            return results
        
        results['connection'] = {'status': 'OK', 'time': self.connection_time}
        logger.info("   ✅ Подключение активно")
        
        # 2. Проверка времени на сервере
        logger.info("\n⏰ 2. Проверка времени на сервере...")
        try:
            clock = self.fp.call_function(self.fp.assets_stub.Clock, ClockRequest())
            if clock:
                server_time = datetime.fromtimestamp(clock.timestamp.seconds)
                local_time = datetime.now()
                diff = abs((server_time - local_time).total_seconds())
                
                results['server_time'] = {
                    'server': server_time,
                    'local': local_time,
                    'diff': diff
                }
                
                if diff < 5:
                    logger.info(f"   ✅ Время синхронизировано (разница {diff:.1f} сек)")
                else:
                    logger.warning(f"   ⚠️ Большая разница во времени: {diff:.1f} сек")
        except Exception as e:
            logger.error(f"   ❌ Ошибка получения времени: {e}")
        
        # 3. Проверка счетов
        logger.info("\n💰 3. Проверка счетов...")
        try:
            accounts = self.fp.account_ids
            results['accounts'] = {
                'count': len(accounts),
                'ids': accounts
            }
            logger.info(f"   ✅ Найдено счетов: {len(accounts)}")
            for acc in accounts:
                logger.info(f"      - {acc}")
        except Exception as e:
            logger.error(f"   ❌ Ошибка получения счетов: {e}")
        
        # 4. Проверка доступа к валютной секции
        logger.info("\n💱 4. Проверка валютной секции...")
        try:
            from config.settings import CURRENCY_PAIRS, CURRENCY_NAMES
            
            available = []
            for code, symbol in CURRENCY_PAIRS.items():
                try:
                    quote = self.fp.call_function(
                        self.fp.marketdata_stub.LastQuote,
                        self.fp.marketdata_stub.QuoteRequest(symbol=symbol)
                    )
                    if quote and quote.quote:
                        available.append(code)
                        logger.info(f"   ✅ {CURRENCY_NAMES[code]}: доступна")
                except:
                    logger.info(f"   ⚠️ {CURRENCY_NAMES[code]}: недоступна")
            
            results['currencies'] = {
                'total': len(CURRENCY_PAIRS),
                'available': available
            }
        except Exception as e:
            logger.error(f"   ❌ Ошибка проверки валют: {e}")
        
        # 5. Проверка баланса
        logger.info("\n📊 5. Проверка баланса...")
        try:
            if self.account_id:
                account = self.fp.call_function(
                    self.fp.accounts_stub.GetAccount,
                    GetAccountRequest(account_id=self.account_id)
                )
                if account and account.cash:
                    for cash in account.cash:
                        amount = cash.units + cash.nanos / 1e9
                        logger.info(f"   ✅ Баланс: {amount:.2f} {cash.currency_code}")
                        results['balance'] = {
                            'amount': amount,
                            'currency': cash.currency_code
                        }
        except Exception as e:
            logger.error(f"   ❌ Ошибка получения баланса: {e}")
        
        # 6. Проверка скорости ответа
        logger.info("\n⚡ 6. Проверка скорости ответа...")
        try:
            start = time.time()
            self.fp.call_function(self.fp.assets_stub.Clock, ClockRequest())
            response_time = (time.time() - start) * 1000
            
            results['response_time'] = response_time
            logger.info(f"   ✅ Время ответа: {response_time:.1f} мс")
        except Exception as e:
            logger.error(f"   ❌ Ошибка проверки скорости: {e}")
        
        logger.info("\n" + "=" * 60)
        logger.info("✅ ДИАГНОСТИКА ЗАВЕРШЕНА")
        logger.info("=" * 60)
        
        self.diagnostic_results = results
        return results
    
    def print_diagnostic_summary(self):
        """Вывод краткой сводки диагностики"""
        if not self.diagnostic_results:
            logger.warning("Диагностика не выполнялась")
            return
        
        print("\n" + "=" * 70)
        print("📊 СВОДКА ДИАГНОСТИКИ")
        print("=" * 70)
        
        if 'connection' in self.diagnostic_results:
            print(f"🔌 Подключение: ✅ Активно")
        
        if 'accounts' in self.diagnostic_results:
            print(f"💰 Счета: {self.diagnostic_results['accounts']['count']}")
        
        if 'currencies' in self.diagnostic_results:
            avail = len(self.diagnostic_results['currencies']['available'])
            total = self.diagnostic_results['currencies']['total']
            print(f"💱 Валютные пары: {avail}/{total} доступно")
        
        if 'balance' in self.diagnostic_results:
            bal = self.diagnostic_results['balance']
            print(f"💵 Баланс: {bal['amount']:.2f} {bal['currency']}")
        
        if 'response_time' in self.diagnostic_results:
            print(f"⚡ Скорость: {self.diagnostic_results['response_time']:.1f} мс")
        
        print("=" * 70)
    
    def disconnect(self):
        """Закрытие соединения"""
        if self.fp:
            self.fp.close_channel()
            self.connected = False
            logger.info("🔌 Соединение закрыто")