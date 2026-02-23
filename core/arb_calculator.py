#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Расчеты для арбитража
Уникальное имя: arb_calculator.py
"""

import logging
from typing import List, Tuple, Optional

from config.arb_config import ARB_TRIANGLE_PAIRS, ARB_TRIANGLE_FORMULAS, ARB_TRIANGLE_DESCRIPTIONS
from core.arb_models import ArbTick, ArbOpportunity

logger = logging.getLogger('ArbCalculator')

POINT = 0.0001


def calc_deviations(tri_type: int, ticks: List[ArbTick]) -> Tuple[float, float, str]:
    """Расчет отклонений"""
    if len(ticks) != 3:
        return 0, 0, "ERROR"
    
    if ARB_TRIANGLE_FORMULAS[tri_type] == 0:  # Умножение
        dev_buy = (ticks[2].bid - (ticks[0].ask * ticks[1].ask)) / POINT
        dev_sell = ((ticks[0].bid * ticks[1].bid) - ticks[2].ask) / POINT
        sig_type = "MUL"
    else:  # Деление
        dev_buy = ((ticks[2].bid / ticks[0].ask) - ticks[1].ask) / POINT if ticks[0].ask > 0 else 0
        dev_sell = (ticks[1].bid - (ticks[2].ask / ticks[0].bid)) / POINT if ticks[0].bid > 0 else 0
        sig_type = "DIV"
    
    return dev_buy, dev_sell, sig_type


def check_spreads(ticks: List[ArbTick], max_spread: float) -> bool:
    """Проверка спредов"""
    return all(t.spread_points <= max_spread for t in ticks)


def calc_lots(tri_type: int, direction: int, base_lot: float) -> List[float]:
    """Расчет лотов"""
    lots = [base_lot, base_lot, base_lot]
    
    if tri_type == 0:
        lots[1] = base_lot * 0.95
        lots[2] = base_lot * 1.02
    elif tri_type == 1:
        lots[1] = base_lot * 1.05
        lots[2] = base_lot * 0.98
    elif tri_type == 2:
        lots[2] = base_lot * 0.9
    elif tri_type >= 3:
        lots[2] = base_lot * 1.03
    
    return [round(lot, 2) for lot in lots]


def find_opportunities(triangles_state: List, get_ticks_func, config) -> List[ArbOpportunity]:
    """Поиск возможностей"""
    opportunities = []
    
    active_count = sum(1 for t in triangles_state if t.active)
    if active_count >= config.MaxTriangles:
        return opportunities
    
    for tri in range(len(ARB_TRIANGLE_PAIRS)):
        if any(t.active and t.triangle_type == tri for t in triangles_state):
            continue
        
        ticks = get_ticks_func(tri)
        if not ticks or not all(t.is_valid for t in ticks):
            continue
        
        if not check_spreads(ticks, config.MaxSpread):
            continue
        
        dev_buy, dev_sell, sig_type = calc_deviations(tri, ticks)
        
        if dev_buy > config.MinDeviation:
            opportunities.append(ArbOpportunity(
                triangle_type=tri, direction=1, deviation=dev_buy,
                ticks=ticks, signal_type=sig_type,
                description=f"{ARB_TRIANGLE_DESCRIPTIONS[tri]} BUY"
            ))
        elif dev_sell > config.MinDeviation:
            opportunities.append(ArbOpportunity(
                triangle_type=tri, direction=-1, deviation=dev_sell,
                ticks=ticks, signal_type=sig_type,
                description=f"{ARB_TRIANGLE_DESCRIPTIONS[tri]} SELL"
            ))
    
    opportunities.sort(key=lambda x: abs(x.deviation), reverse=True)
    return opportunities