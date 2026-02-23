#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Подключение к Finam API
Уникальное имя: arb_connection.py
"""

import logging
from datetime import datetime
from typing import Optional, Dict

from FinamPy import FinamPy
from FinamPy.grpc.assets.assets_service_pb2 import ClockRequest
from FinamPy.grpc.accounts.accounts_service_pb2 import GetAccountRequest
from FinamPy.grpc.marketdata.marketdata_service_pb2 import QuoteRequest

from config.arb_config import ArbColors, ARB_CURRENCY_PAIRS

logger = logging.getLogger('ArbConnection')


class ArbConnection:
    """Подключение к Finam API"""
    
    def __init__(self, token: Optional[str] = None):
        self.fp = None
        self.token = token
        self.connected = False
        self.account_id = None
        self.connection_time = None
        
    def connect(self) -> bool:
        try:
            logger.info(f"{ArbColors.BOLD}{ArbColors.CYAN}🔌 Подключение...{ArbColors.END}")
            
            if self.token:
                self.fp = FinamPy(self.token)
            else:
                self.fp = FinamPy()
            
            self.connection_time = datetime.now()
            
            if self.fp.account_ids:
                self.account_id = self.fp.account_ids[0]
                logger.info(f"{ArbColors.GREEN}✅ Счет: {self.account_id}{ArbColors.END}")
                self.connected = True
                return True
            
            logger.error(f"{ArbColors.RED}❌ Нет счетов{ArbColors.END}")
            return False
            
        except Exception as e:
            logger.error(f"{ArbColors.RED}❌ Ошибка: {e}{ArbColors.END}")
            return False
    
    def get_server_time(self) -> Optional[datetime]:
        try:
            clock = self.fp.call_function(self.fp.assets_stub.Clock, ClockRequest())
            if clock:
                return datetime.fromtimestamp(clock.timestamp.seconds)
        except Exception as e:
            logger.error(f"Ошибка времени: {e}")
        return None
    
    def get_balance(self) -> Optional[Dict]:
        try:
            if self.account_id:
                account = self.fp.call_function(
                    self.fp.accounts_stub.GetAccount,
                    GetAccountRequest(account_id=self.account_id)
                )
                if account and account.cash:
                    for cash in account.cash:
                        return {
                            'amount': cash.units + cash.nanos / 1e9,
                            'currency': cash.currency_code
                        }
        except Exception as e:
            logger.error(f"Ошибка баланса: {e}")
        return None
    
    def get_quote(self, currency_code: str):
        if currency_code not in ARB_CURRENCY_PAIRS:
            return None
        symbol = ARB_CURRENCY_PAIRS[currency_code]
        try:
            return self.fp.call_function(
                self.fp.marketdata_stub.LastQuote,
                QuoteRequest(symbol=symbol)
            )
        except:
            return None
    
    def disconnect(self):
        if self.fp:
            self.fp.close_channel()
            self.connected = False
            logger.info("🔌 Соединение закрыто")