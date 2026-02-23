#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Настройки для треугольного арбитража
Уникальное имя: arb_config.py
"""

from dataclasses import dataclass
from pathlib import Path

# Пути
BASE_DIR = Path(__file__).parent.parent.absolute()
LOG_DIR = BASE_DIR / 'logs'
DATA_DIR = BASE_DIR / 'data'

LOG_DIR.mkdir(exist_ok=True)
DATA_DIR.mkdir(exist_ok=True)


@dataclass
class ArbConfig:
    """Конфигурация арбитражного бота"""
    
    LotSize: float = 0.1
    MaxSpread: float = 2.0
    MinDeviation: float = 2.0
    LossCompensationThreshold: float = 5.0
    TargetProfit: float = 10.0
    MaxLoss: float = -20.0
    MaxTriangles: int = 3
    EnableCompensation: bool = True
    CompensationLotMultiplier: float = 0.6
    CloseAllOnTargetProfit: bool = True
    TimeCloseHours: float = 4.0
    PaperTrading: bool = False
    ScanInterval: float = 3.0


class ArbColors:
    """Цвета для терминала"""
    HEADER = '\033[95m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    END = '\033[0m'
    BOLD = '\033[1m'


# Валютные пары
ARB_CURRENCY_PAIRS = {
    'USD': 'USD000000TOD@CETS',
    'EUR': 'EUR_RUB__TOD@CETS',
    'CNY': 'CNY000000TOD@CETS',
    'GBP': 'GBP000000TOD@CETS',
    'CHF': 'CHF000000TOD@CETS',
    'JPY': 'JPY000000TOD@CETS',
    'HKD': 'HKD000000TOD@CETS',
    'BYN': 'BYN000000TOD@CETS',
    'KZT': 'KZT000000TOD@CETS',
    'TRY': 'TRY000000TOD@CETS',
    'AUD': 'AUD000000TOD@CETS',
    'CAD': 'CAD000000TOD@CETS',
}

ARB_CURRENCY_NAMES = {
    'USD': '🇺🇸 Доллар США',
    'EUR': '🇪🇺 Евро',
    'CNY': '🇨🇳 Китайский юань',
    'GBP': '🇬🇧 Фунт стерлингов',
    'CHF': '🇨🇭 Швейцарский франк',
    'JPY': '🇯🇵 Японская иена',
    'HKD': '🇭🇰 Гонконгский доллар',
    'BYN': '🇧🇾 Белорусский рубль',
    'KZT': '🇰🇿 Казахстанский тенге',
    'TRY': '🇹🇷 Турецкая лира',
    'AUD': '🇦🇺 Австралийский доллар',
    'CAD': '🇨🇦 Канадский доллар',
}

# Треугольники
ARB_TRIANGLE_PAIRS = [
    ["USD", "EUR", "EUR"],
    ["USD", "JPY", "JPY"],
    ["USD", "JPY", "JPY"],
    ["EUR", "USD", "EUR"],
    ["GBP", "USD", "GBP"],
    ["CNY", "USD", "CNY"],
]

ARB_TRIANGLE_FORMULAS = [0, 0, 0, 1, 1, 1]  # 0=умножение, 1=деление

ARB_TRIANGLE_DESCRIPTIONS = [
    "USD×EUR = EUR",
    "USD×JPY = JPY",
    "CHF×JPY = JPY",
    "EUR/USD = EUR",
    "GBP/USD = GBP",
    "CNY/USD = CNY",
]