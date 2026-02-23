#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Исполнение арбитражных сделок
Уникальное имя: arb_executor.py
"""

import logging
import time
from datetime import datetime
from typing import List, Optional

from FinamPy.grpc.orders.orders_service_pb2 import Order, OrderType, CancelOrderRequest
from google.type.decimal_pb2 import Decimal
import FinamPy.grpc.side_pb2 as side_pb

from config.arb_config import ArbColors, ARB_CURRENCY_PAIRS
from core.arb_models import ArbOpportunity, ArbTriangle
from core.arb_calculator import calc_lots

logger = logging.getLogger('ArbExecutor')


class ArbExecutor:
    """Исполнитель сделок"""
    
    def __init__(self, fp_connection, account_id: str, config):
        self.fp = fp_connection.fp
        self.account_id = account_id
        self.config = config
        self.triangles: List[ArbTriangle] = [ArbTriangle() for _ in range(50)]
        
    def open_triangle(self, opp: ArbOpportunity, comp: bool = False, parent: int = -1) -> Optional[int]:
        """Открытие треугольника"""
        
        # Поиск свободного слота
        slot = next((i for i, t in enumerate(self.triangles) if not t.active), None)
        if slot is None:
            logger.warning("Нет свободных слотов")
            return None
        
        # Расчет лотов
        base_lot = self.config.LotSize
        if comp:
            base_lot *= self.config.CompensationLotMultiplier
        
        lots = calc_lots(opp.triangle_type, opp.direction, base_lot)
        
        # Подготовка ордеров
        symbols = [ARB_CURRENCY_PAIRS[code] for code in 
                  [opp.ticks[0].symbol.split('@')[0],
                   opp.ticks[1].symbol.split('@')[0],
                   opp.ticks[2].symbol.split('@')[0]]]
        
        if opp.signal_type == "MUL":
            if opp.direction == 1:
                sides = [side_pb.SIDE_BUY, side_pb.SIDE_BUY, side_pb.SIDE_SELL]
                prices = [opp.ticks[0].ask, opp.ticks[1].ask, opp.ticks[2].bid]
            else:
                sides = [side_pb.SIDE_SELL, side_pb.SIDE_SELL, side_pb.SIDE_BUY]
                prices = [opp.ticks[0].bid, opp.ticks[1].bid, opp.ticks[2].ask]
        else:
            if opp.direction == 1:
                sides = [side_pb.SIDE_BUY, side_pb.SIDE_SELL, side_pb.SIDE_SELL]
                prices = [opp.ticks[0].ask, opp.ticks[1].bid, opp.ticks[2].bid]
            else:
                sides = [side_pb.SIDE_SELL, side_pb.SIDE_BUY, side_pb.SIDE_BUY]
                prices = [opp.ticks[0].bid, opp.ticks[1].ask, opp.ticks[2].ask]
        
        logger.info(f"{ArbColors.CYAN}📈 Открытие #{slot}{ArbColors.END}")
        logger.info(f"   {opp.description} | {opp.deviation:.2f} pts")
        
        tickets = []
        
        # Исполнение ордеров
        for i in range(3):
            if self.config.PaperTrading:
                logger.info(f"   [БУМАГА] {symbols[i]} лот {lots[i]}")
                tickets.append(f"PAPER_{slot}_{i}_{int(time.time())}")
            else:
                comment = "COMP_" if comp else "ARB_"
                comment += f"T{opp.triangle_type}_D{opp.direction}_{i}"
                
                order = Order(
                    account_id=self.account_id,
                    symbol=symbols[i],
                    quantity=Decimal(value=str(lots[i])),
                    side=sides[i],
                    type=OrderType.ORDER_TYPE_MARKET,
                    client_order_id=f"{int(time.time())}_{slot}_{i}",
                    comment=comment
                )
                
                try:
                    state = self.fp.call_function(self.fp.orders_stub.PlaceOrder, order)
                    if state and state.order_id:
                        tickets.append(state.order_id)
                        logger.info(f"   ✅ {symbols[i]} тикет {state.order_id}")
                        time.sleep(0.5)
                    else:
                        logger.error(f"   ❌ Ошибка {symbols[i]}")
                        self._rollback(tickets)
                        return None
                except Exception as e:
                    logger.error(f"   ❌ {e}")
                    self._rollback(tickets)
                    return None
        
        # Сохранение треугольника
        self.triangles[slot] = ArbTriangle(
            triangle_type=opp.triangle_type,
            direction=opp.direction,
            tickets=tickets,
            entry_prices=prices,
            lots=lots,
            deviation=opp.deviation,
            open_time=datetime.now(),
            active=True,
            compensation=comp,
            parent_index=parent,
            symbols=symbols
        )
        
        logger.info(f"{ArbColors.GREEN}✅ Треугольник #{slot} открыт{ArbColors.END}")
        return slot
    
    def _rollback(self, tickets: List[str]):
        """Откат при ошибке"""
        for ticket in tickets:
            self.close_position(ticket)
    
    def close_position(self, ticket: str) -> bool:
        """Закрытие позиции"""
        if ticket.startswith('PAPER_'):
            logger.info(f"   [БУМАГА] Закрыто {ticket}")
            return True
        
        try:
            result = self.fp.call_function(
                self.fp.orders_stub.CancelOrder,
                CancelOrderRequest(account_id=self.account_id, order_id=ticket)
            )
            if result:
                logger.info(f"   Закрыто {ticket}")
                return True
        except Exception as e:
            logger.error(f"Ошибка закрытия {ticket}: {e}")
        return False
    
    def close_triangle(self, index: int):
        """Закрытие треугольника"""
        if index >= len(self.triangles) or not self.triangles[index].active:
            return
        
        tri = self.triangles[index]
        logger.info(f"Закрытие треугольника #{index}")
        
        for ticket in tri.tickets:
            if ticket:
                self.close_position(ticket)
                time.sleep(0.3)
        
        tri.active = False
        tri.compensation = False