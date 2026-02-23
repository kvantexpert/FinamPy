#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Модели данных для арбитража
Уникальное имя: arb_models.py
"""

from dataclasses import dataclass, field
from typing import List, Optional
from datetime import datetime


@dataclass
class ArbTick:
    """Данные тика"""
    symbol: str
    bid: float = 0.0
    ask: float = 0.0
    last: float = 0.0
    volume: int = 0
    timestamp: datetime = None
    
    @property
    def spread_points(self) -> float:
        if self.ask > 0 and self.bid > 0:
            return (self.ask - self.bid) / 0.0001
        return 0
    
    @property
    def is_valid(self) -> bool:
        return self.bid > 0 and self.ask > 0 and self.last > 0


@dataclass
class ArbTriangle:
    """Информация о треугольнике"""
    
    triangle_type: int = -1
    direction: int = 0
    tickets: List[str] = field(default_factory=lambda: ["", "", ""])
    entry_prices: List[float] = field(default_factory=lambda: [0.0, 0.0, 0.0])
    lots: List[float] = field(default_factory=lambda: [0.0, 0.0, 0.0])
    deviation: float = 0.0
    current_profit: float = 0.0
    open_time: datetime = None
    active: bool = False
    compensation: bool = False
    parent_index: int = -1
    total_volume: float = 0.0
    symbols: List[str] = field(default_factory=list)
    
    def get_side(self, index: int) -> str:
        if self.direction == 1:
            return "BUY" if index < 2 else "SELL"
        return "SELL" if index < 2 else "BUY"


@dataclass
class ArbOpportunity:
    """Арбитражная возможность"""
    triangle_type: int
    direction: int
    deviation: float
    ticks: List[ArbTick]
    signal_type: str
    description: str
    
    @property
    def is_profitable(self) -> bool:
        return abs(self.deviation) > 0