#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Диагностика арбитражной системы
Уникальное имя: arb_diagnostic.py
"""

import logging
import time
from datetime import datetime

from config.arb_config import ArbColors, ARB_CURRENCY_PAIRS, ARB_CURRENCY_NAMES, ARB_TRIANGLE_DESCRIPTIONS

logger = logging.getLogger('ArbDiagnostic')


class ArbDiagnostic:
    """Диагностика системы"""
    
    def __init__(self, connection):
        self.conn = connection
    
    def run_all(self):
        """Запуск диагностики"""
        print(f"\n{ArbColors.BOLD}{ArbColors.CYAN}{'=' * 60}")
        print("🔍 ДИАГНОСТИКА АРБИТРАЖНОЙ СИСТЕМЫ")
        print(f"{'=' * 60}{ArbColors.END}")
        
        # 1. Время
        print(f"\n{ArbColors.YELLOW}⏰ Время:{ArbColors.END}")
        server = self.conn.get_server_time()
        if server:
            local = datetime.now()
            print(f"   Сервер: {server.strftime('%H:%M:%S')}")
            print(f"   Локальное: {local.strftime('%H:%M:%S')}")
            print(f"   Разница: {abs((server-local).total_seconds()):.1f} сек")
        
        # 2. Баланс
        print(f"\n{ArbColors.YELLOW}💰 Баланс:{ArbColors.END}")
        bal = self.conn.get_balance()
        if bal:
            print(f"   {bal['amount']:.2f} {bal['currency']}")
        
        # 3. Валютные пары
        print(f"\n{ArbColors.YELLOW}💱 Валютные пары:{ArbColors.END}")
        available = 0
        for code, name in ARB_CURRENCY_NAMES.items():
            quote = self.conn.get_quote(code)
            if quote and quote.quote:
                available += 1
                print(f"   ✅ {name}")
            else:
                print(f"   ⚠️ {name}")
        print(f"\n   Доступно: {available}/{len(ARB_CURRENCY_PAIRS)}")
        
        # 4. Треугольники
        print(f"\n{ArbColors.YELLOW}🔺 Треугольники:{ArbColors.END}")
        for i, desc in enumerate(ARB_TRIANGLE_DESCRIPTIONS):
            print(f"   {i+1}. {desc}")
        
        print(f"\n{ArbColors.BOLD}{ArbColors.GREEN}✅ Диагностика завершена{ArbColors.END}")