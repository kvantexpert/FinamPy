#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Мониторинг котировок
Уникальное имя: arb_monitor.py
"""

import logging
import threading
import time
from datetime import datetime
from typing import Dict, Callable, List

from FinamPy.grpc.marketdata.marketdata_service_pb2 import SubscribeQuoteResponse

from config.arb_config import ARB_CURRENCY_PAIRS, ArbColors
from core.arb_models import ArbTick

logger = logging.getLogger('ArbMonitor')


class ArbMonitor:
    """Монитор котировок"""
    
    def __init__(self, fp):
        self.fp = fp
        self.ticks: Dict[str, ArbTick] = {}
        self.callbacks: List[Callable] = []
        self.running = False
        self.updates = 0
        self.start_time = None
        
    def add_callback(self, callback: Callable):
        self.callbacks.append(callback)
    
    def _handler(self, quote: SubscribeQuoteResponse):
        for q in quote.quote:
            symbol = q.symbol
            tick = ArbTick(
                symbol=symbol,
                bid=float(q.bid.value) if q.bid and q.bid.value else 0,
                ask=float(q.ask.value) if q.ask and q.ask.value else 0,
                last=float(q.last.value) if q.last and q.last.value else 0,
                volume=int(float(q.volume.value)) if q.volume and q.volume.value else 0,
                timestamp=datetime.now()
            )
            self.ticks[symbol] = tick
            self.updates += 1
            
            for cb in self.callbacks:
                try:
                    cb(symbol, tick)
                except Exception as e:
                    logger.error(f"Callback error: {e}")
    
    def start(self):
        if self.running:
            return
        
        self.running = True
        self.start_time = datetime.now()
        
        symbols = list(ARB_CURRENCY_PAIRS.values())
        self.fp.on_quote.subscribe(self._handler)
        
        def thread_func():
            logger.info(f"{ArbColors.CYAN}📡 Мониторинг {len(symbols)} пар{ArbColors.END}")
            self.fp.subscribe_quote_thread(tuple(symbols))
        
        thread = threading.Thread(target=thread_func, daemon=True)
        thread.start()
        time.sleep(2)
    
    def stop(self):
        self.running = False
        logger.info("🛑 Мониторинг остановлен")
    
    def get_tick(self, currency: str) -> ArbTick:
        symbol = ARB_CURRENCY_PAIRS.get(currency)
        return self.ticks.get(symbol) if symbol else None
    
    def get_stats(self) -> Dict:
        uptime = datetime.now() - self.start_time if self.start_time else 0
        return {
            'uptime': str(uptime).split('.')[0],
            'updates': self.updates,
            'active': len(self.ticks)
        }