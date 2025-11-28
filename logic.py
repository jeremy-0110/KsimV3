# logic.py
# 核心業務邏輯：包含狀態管理、交易執行、資金計算與回測控制

import streamlit as st
import pandas as pd
import numpy as np
import uuid
from datetime import datetime
import config
from data_manager import (
    fetch_historical_data, 
    select_random_start_index, 
    get_price_info_by_index
)

# --- 輔助函式：核心損益計算 ---

def calculate_pnl_value(direction, qty, open_avg, current_price):
    """統一損益 (PnL) 計算邏輯"""
    price_diff = 0.0
    if direction == 'Long':
        price_diff = current_price - open_avg
    else: # Short
        price_diff = open_avg - current_price

    return price_diff * qty

# --- 資金計算函式 ---

def get_current_asset_value(core_data, current_idx):
    """計算當前總資產價值"""
    if st.session_state.core_data is None or st.session_state.core_data.empty:
         return st.session_state.balance
         
    if st.session_state.sim_active and current_idx < len(core_data):
        price = core_data['Open'].iloc[current_idx].item() if 'Open' in core_data.columns else 0.0
    else:
        return st.session_state.balance
    
    total_position_net_value = 0.0
    
    for pos in st.session_state.positions:
        qty = pos['qty']
        cost = pos['cost']
        leverage = pos.get('leverage', 1.0)
        pos_mode_key = pos['pos_mode_key']
        
        mode_info = config.TRADE_MODE_MAP.get(pos_mode_key, {})
        is_margin = mode_info.get('type') == 'Margin'
        direction = mode_info.get('direction', 'Long')
        
        if not is_margin: # Spot
             total_position_net_value += (qty * price)
        else: # Margin
             initial_margin = (cost * qty) / leverage
             unrealized_pnl = calculate_pnl_value(direction, qty, cost, price)
             total_position_net_value += (initial_margin + unrealized_pnl)
    
    total_locked_in_orders = sum(order.get('locked_funds', 0.0) for order in st.session_state.pending_orders)

    return st.session_state.balance + total_locked_in_orders + total_position_net_value

def get_total_unrealized_pnl(price):
    """計算投資組合的總未實現損益"""
    total_pnl = 0.0
    for pos in st.session_state.positions:
        qty = pos['qty']
        cost = pos['cost']
        pos_mode_key = pos['pos_mode_key']
        mode_info = config.TRADE_MODE_MAP.get(pos_mode_key, {})
        direction = mode_info.get('direction', 'Long')
        pnl = calculate_pnl_value(direction, qty, cost, price)
        total_pnl += pnl
    return total_pnl

def get_spot_summary(core_data, current_idx):
    """彙總現貨部位資訊"""
    if not st.session_state.sim_active or core_data is None or current_idx >= len(core_data):
        return {'qty': 0.0, 'avg_cost': 0.0, 'unrealized_pnl': 0.0}

    price = core_data['Open'].iloc[current_idx].item()
    spot_positions = []
    for pos in st.session_state.positions:
        mode_info = config.TRADE_MODE_MAP.get(pos['pos_mode_key'], {})
        if mode_info.get('type') == 'Spot':
            spot_positions.append(pos)
    
    if not spot_positions:
        return {'qty': 0.0, 'avg_cost': 0.0, 'unrealized_pnl': 0.0}

    total_qty = sum(pos['qty'] for pos in spot_positions)
    total_cost = sum(pos['qty'] * pos['cost'] for pos in spot_positions)
    avg_cost = total_cost / total_qty if total_qty > 0 else 0.0
    unrealized_pnl = sum((pos['qty'] * price) - (pos['qty'] * pos['cost']) for pos in spot_positions)
    
    return {'qty': total_qty, 'avg_cost': avg_cost, 'unrealized_pnl': unrealized_pnl}

def check_and_end_simulation(asset_value):
    """風險控制：破產檢測"""
    if asset_value <= 0:
        if st.session_state.sim_active: 
            settle_portfolio(force_end=True) 
            msg = "🚨 風險控制警告！總資產歸零，模擬強制結束！"
            st.session_state.last_event_msg = {'text': msg, 'type': 'error', 'mode': 'toast'}
        return True
    return False

# --- 交易執行函式 ---

def close_position_lot(pos_id: str, settle_qty: float, settle_price: float, reason: str, mode: str = '自動'):
    """核心平倉邏輯"""
    pos_index = next((i for i, pos in enumerate(st.session_state.positions) if pos['id'] == pos_id), -1)
    
    if pos_index == -1: return False
    pos = st.session_state.positions[pos_index]
    
    if settle_qty <= 0 or settle_qty > pos['qty'] * 1.000001: return False
    if abs(settle_qty - pos['qty']) < 1e-9: settle_qty = pos['qty']

    current_datetime, _, _ = get_price_info_by_index(st.session_state.core_data, st.session_state.current_sim_index)
    pos_mode_key = pos['pos_mode_key']
    mode_info = config.TRADE_MODE_MAP.get(pos_mode_key, {})
    is_margin = mode_info.get('type') == 'Margin'
    direction = mode_info.get('direction', 'Long')
    asset_type = st.session_state.asset_type
    
    # 計算費用與資金
    fee_rate_used = config.LEVERAGE_FEE_RATE if is_margin else config.FEE_RATE
    close_amount = settle_qty * settle_price
    close_fee = close_amount * fee_rate_used
    
    st.session_state.balance -= close_fee
    
    is_fully_closed = (settle_qty == pos['qty'])
    leverage = pos.get('leverage', 1.0)
    margin_released = (pos['cost'] * settle_qty) / leverage
    realized_pnl = calculate_pnl_value(direction, settle_qty, pos['cost'], settle_price)

    st.session_state.balance += (margin_released + realized_pnl)
    
    # 紀錄
    prorated_open_fee = pos['total_open_fee'] * (settle_qty / pos['initial_qty'])
    total_fee = prorated_open_fee + close_fee
    display_name = pos['display_name']
    type_display = f"{display_name} ({leverage}x)" if is_margin else display_name
    if "強平" in reason: type_display += " [強平]"
    
    trade_record = {
        'ID': pos['id'], 'asset': asset_type, 'mode_name': display_name,
        'type_display': type_display, 'leverage': leverage, 'direction': direction,
        'open_date': pos['open_date'], 'close_date': current_datetime,
        'qty': settle_qty, 'open_price': pos['cost'], 'close_price': settle_price,
        'pnl': realized_pnl, 'fees': total_fee, 'net_pnl': realized_pnl - total_fee,
        'reason': reason
    }
    st.session_state.transactions.append(trade_record)
    
    # 訊息通知
    if mode == '自動':
        icon = "💰" if realized_pnl > 0 else "📉"
        msg_text = f"{icon} {reason}：{display_name} {settle_qty:.3f} 單位 @ ${settle_price:,.2f} (損益: ${realized_pnl:,.2f})"
        st.session_state.last_event_msg = {'text': msg_text, 'type': 'success' if realized_pnl > 0 else 'error', 'mode': 'toast'}
    
    if is_fully_closed:
        st.session_state.positions.pop(pos_index)
        if mode == '手動': 
            st.session_state.last_event_msg = {'text': f"✅ {display_name} 已完全平倉", 'type': 'success', 'mode': 'toast'}
    else: 
        pos['qty'] -= settle_qty
        pos['total_open_fee'] -= prorated_open_fee
        if mode == '手動': 
            st.session_state.last_event_msg = {'text': f"✅ {display_name} 已部分平倉", 'type': 'success', 'mode': 'toast'}

    total_asset_new = get_current_asset_value(st.session_state.core_data, st.session_state.current_sim_index)
    check_and_end_simulation(total_asset_new)
    return True

def execute_trade(trade_mode_key, quantity, price, leverage=1.0):
    """執行開倉交易"""
    if not st.session_state.sim_active: return False
    if quantity <= 0 or price <= 0: return False

    mode_conf = config.TRADE_MODE_MAP.get(trade_mode_key)
    if not mode_conf: return False
    
    is_margin = mode_conf['type'] == 'Margin'
    direction = mode_conf['direction']
    asset_type = st.session_state.asset_type
    asset_conf = config.ASSET_CONFIGS[asset_type]
    
    display_name = ""
    if trade_mode_key == 'Spot_Buy': display_name = asset_conf['mode_spot']
    elif trade_mode_key == 'Margin_Long': display_name = asset_conf['mode_margin_long']
    elif trade_mode_key == 'Margin_Short': display_name = asset_conf['mode_margin_short']

    # 倉位檢查
    if is_margin:
        for pos in st.session_state.positions:
            pos_mode_conf = config.TRADE_MODE_MAP.get(pos['pos_mode_key'])
            if pos_mode_conf and pos_mode_conf['type'] == 'Margin' and pos_mode_conf['direction'] == direction:
                 st.session_state.last_event_msg = {'text': f"🚫 限制：{display_name} 最多只能持有一個倉位！", 'type': 'error', 'mode': 'toast'}
                 return False

    transaction_amount = quantity * price
    fee_rate_used = config.LEVERAGE_FEE_RATE if is_margin else config.FEE_RATE
    open_fee = transaction_amount * fee_rate_used
    
    st.session_state.balance -= open_fee
    if check_and_end_simulation(get_current_asset_value(st.session_state.core_data, st.session_state.current_sim_index)):
        return False

    margin_required = transaction_amount / leverage if is_margin else transaction_amount
    liquidation_price = 0.0
    
    if is_margin:
        if direction == 'Long': liquidation_price = price * (1.0 - (1.0 / leverage))
        else: liquidation_price = price * (1.0 + (1.0 / leverage))
            
    if st.session_state.balance < margin_required:
            st.session_state.balance += open_fee 
            st.session_state.last_event_msg = {'text': f"💸 餘額不足！需保證金 ${margin_required:,.0f}", 'type': 'error', 'mode': 'toast'}
            return False
    
    st.session_state.balance -= margin_required
    current_datetime, _, _ = get_price_info_by_index(st.session_state.core_data, st.session_state.current_sim_index)
    
    new_position = {
        'id': str(uuid.uuid4())[:8], 'open_date': current_datetime, 
        'pos_mode_key': trade_mode_key, 'display_name': display_name,     
        'qty': quantity, 'initial_qty': quantity,          
        'cost': price, 'initial_cost': transaction_amount, 
        'leverage': leverage, 'liquidation_price': liquidation_price, 
        'sl': 0.0, 'tp': 0.0, 'total_open_fee': open_fee        
    }
    st.session_state.positions.append(new_position)
    st.session_state.last_event_msg = {'text': f"✅ {display_name} 成功！開倉 {quantity:,.3f} {asset_conf['unit']} @ ${price:,.2f}", 'type': 'success', 'mode': 'toast'}
    return True

# --- 掛單 (Limit/Stop Order) 相關函式 ---

def place_limit_order(trade_mode_key, quantity, limit_price, leverage=1.0, order_type='Limit'):
    """新增掛單"""
    if quantity <= 0 or limit_price <= 0: return False
    
    mode_conf = config.TRADE_MODE_MAP.get(trade_mode_key)
    if not mode_conf: return False

    is_margin = mode_conf['type'] == 'Margin'
    direction = mode_conf['direction']
    asset_type = st.session_state.asset_type
    asset_conf = config.ASSET_CONFIGS[asset_type]
    
    display_name = ""
    if trade_mode_key == 'Spot_Buy': display_name = asset_conf['mode_spot']
    elif trade_mode_key == 'Margin_Long': display_name = asset_conf['mode_margin_long']
    elif trade_mode_key == 'Margin_Short': display_name = asset_conf['mode_margin_short']

    # 取得當前市價
    current_open_price = st.session_state.core_data['Open'].iloc[st.session_state.current_sim_index].item()

    # --- 1. 訂單價格檢查 ---
    if order_type == 'Limit':
        if direction == 'Long' and limit_price >= current_open_price:
            st.session_state.last_event_msg = {'text': f"🚫 Limit Buy 錯誤：限價單 ({limit_price:,.2f}) 必須低於市價 ({current_open_price:,.2f})。", 'type': 'error', 'mode': 'toast'}
            return False
        elif direction == 'Short' and limit_price <= current_open_price:
            st.session_state.last_event_msg = {'text': f"🚫 Limit Sell 錯誤：限價單 ({limit_price:,.2f}) 必須高於市價 ({current_open_price:,.2f})。", 'type': 'error', 'mode': 'toast'}
            return False
    elif order_type == 'Stop':
        if direction == 'Long' and limit_price <= current_open_price:
            st.session_state.last_event_msg = {'text': f"🚫 Stop Buy 錯誤：止損單 ({limit_price:,.2f}) 必須高於市價 ({current_open_price:,.2f})。", 'type': 'error', 'mode': 'toast'}
            return False
        elif direction == 'Short' and limit_price >= current_open_price:
            st.session_state.last_event_msg = {'text': f"🚫 Stop Sell 錯誤：止損單 ({limit_price:,.2f}) 必須低於市價 ({current_open_price:,.2f})。", 'type': 'error', 'mode': 'toast'}
            return False

    # --- 2. 倉位互斥檢查 ---
    if is_margin:
        for pos in st.session_state.positions:
            pos_mode_conf = config.TRADE_MODE_MAP.get(pos['pos_mode_key'])
            if pos_mode_conf and pos_mode_conf['type'] == 'Margin' and pos_mode_conf['direction'] == direction:
                 st.session_state.last_event_msg = {'text': f"🚫 禁止：已有 {display_name} 持倉，無法新增掛單。", 'type': 'error', 'mode': 'toast'}
                 return False
        
        for order in st.session_state.pending_orders:
            order_mode_conf = config.TRADE_MODE_MAP.get(order['trade_mode_key'])
            if order_mode_conf and order_mode_conf['type'] == 'Margin' and order_mode_conf['direction'] == direction:
                 st.session_state.last_event_msg = {'text': f"🚫 禁止：已有 {display_name} 掛單，請先刪除舊單。", 'type': 'error', 'mode': 'toast'}
                 return False

    # --- 3. 資金預扣 ---
    transaction_amount = quantity * limit_price
    fee_rate_used = config.LEVERAGE_FEE_RATE if is_margin else config.FEE_RATE
    estimated_fee = transaction_amount * fee_rate_used
    margin_required = transaction_amount / leverage if is_margin else transaction_amount
    
    total_locked = margin_required + estimated_fee
    
    if st.session_state.balance < total_locked:
        st.session_state.last_event_msg = {'text': f"💸 掛單失敗：餘額不足！(需 ${total_locked:,.0f})", 'type': 'error', 'mode': 'toast'}
        return False

    st.session_state.balance -= total_locked

    new_order = {
        'id': str(uuid.uuid4())[:8],
        'trade_mode_key': trade_mode_key,
        'display_name': display_name,
        'order_type': order_type, 
        'qty': quantity,
        'price': limit_price,
        'leverage': leverage,
        'created_at': st.session_state.current_sim_index,
        'locked_funds': total_locked 
    }
    
    st.session_state.pending_orders.append(new_order)
    st.session_state.last_event_msg = {'text': f"📌 {order_type} 掛單成功：{display_name} @ {limit_price} (圈存 ${total_locked:,.0f})", 'type': 'success', 'mode': 'toast'}
    return True

def cancel_order(order_id):
    """取消掛單並退還資金"""
    order_to_cancel = next((o for o in st.session_state.pending_orders if o['id'] == order_id), None)
    
    if order_to_cancel:
        locked = order_to_cancel.get('locked_funds', 0.0)
        st.session_state.balance += locked
        
        st.session_state.pending_orders = [o for o in st.session_state.pending_orders if o['id'] != order_id]
        st.session_state.last_event_msg = {'text': f"🗑️ 掛單已取消 (退還 ${locked:,.0f})", 'type': 'info', 'mode': 'toast'}

def check_pending_orders(core_data, current_idx):
    """
    檢查掛單是否觸發。
    """
    if not st.session_state.pending_orders: return False 
    
    current_open = core_data['Open'].iloc[current_idx].item()
    current_high = core_data['High'].iloc[current_idx].item()
    current_low = core_data['Low'].iloc[current_idx].item()
    
    triggered_orders = []
    
    for order in st.session_state.pending_orders:
        mode_key = order['trade_mode_key']
        mode_conf = config.TRADE_MODE_MAP.get(mode_key)
        direction = mode_conf['direction']
        limit_price = float(order['price'])
        order_type = order.get('order_type', 'Limit')
        
        fill_price = 0.0
        is_triggered = False
        
        # --- 觸發檢查 ---
        if order_type == 'Limit':
            if direction == 'Long':
                if current_low <= limit_price: is_triggered = True
            elif direction == 'Short':
                if current_high >= limit_price: is_triggered = True
            
            if is_triggered:
                if direction == 'Long':
                    fill_price = min(current_open, limit_price)
                else: 
                    fill_price = max(current_open, limit_price)

        elif order_type == 'Stop':
            if direction == 'Long':
                if current_high >= limit_price: is_triggered = True
                if is_triggered:
                    if current_open >= limit_price: fill_price = current_open
                    else: fill_price = limit_price
            elif direction == 'Short':
                if current_low <= limit_price: is_triggered = True
                if is_triggered:
                    if current_open <= limit_price: fill_price = current_open
                    else: fill_price = limit_price
        
        # --- 執行成交 ---
        if fill_price > 0 and is_triggered:
            locked = order.get('locked_funds', 0.0)
            st.session_state.balance += locked
            
            if execute_trade(mode_key, order['qty'], fill_price, order['leverage']):
                triggered_orders.append(order['id'])
                msg_text = f"成交：{order_type} 單 @ ${fill_price:,.2f} ({order['display_name']})"
                st.session_state.last_event_msg = {'text': msg_text, 'type': 'success', 'mode': 'toast'}
            else:
                triggered_orders.append(order['id'])
                st.session_state.last_event_msg = {'text': f"⚠️ 掛單 {order['display_name']} 觸發但餘額不足以成交 (已撤單)", 'type': 'error', 'mode': 'toast'}
    
    if triggered_orders:
        st.session_state.pending_orders = [o for o in st.session_state.pending_orders if o['id'] not in triggered_orders]
        return True 
    
    return False

def settle_portfolio(force_end=False):
    """結算功能 (包含掛單退款)"""
    if not st.session_state.sim_active and not force_end: return

    current_idx = st.session_state.current_sim_index
    core_data = st.session_state.core_data
    if core_data is None or core_data.empty: return

    settle_price = core_data['Close'].iloc[-1].item() if current_idx >= len(core_data) else \
                   (core_data['Close'].iloc[current_idx].item() if force_end else core_data['Open'].iloc[current_idx].item())

    positions_to_close = list(st.session_state.positions) 
    if positions_to_close:
        msg = "強制結算" if force_end else "手動全平"
        for pos in positions_to_close:
            close_position_lot(pos['id'], pos['qty'], settle_price, reason=msg, mode='自動結算')

    if force_end:
        for order in st.session_state.pending_orders:
            st.session_state.balance += order.get('locked_funds', 0.0)
        st.session_state.pending_orders = []

        st.session_state.sim_active = False
        st.session_state.end_sim_index_on_settle = current_idx
        
        final_asset = get_current_asset_value(core_data, current_idx)
        initial_cap = config.INITIAL_CAPITAL
        total_pnl = final_asset - initial_cap
        roi = (total_pnl / initial_cap) * 100
        
        start_date = st.session_state.start_date
        end_date, _, _ = get_price_info_by_index(core_data, current_idx)
        
        st.session_state.settlement_stats = {
            'final_asset': final_asset, 'total_pnl': total_pnl, 'roi': roi,
            'start_date': start_date, 'end_date': end_date
        }

def check_sl_tp_trigger(core_data, current_idx):
    """
    檢查 SL/TP 與強平
    """
    if not st.session_state.sim_active: return False
    if current_idx >= len(core_data): return False

    high = core_data['High'].iloc[current_idx].item()
    low = core_data['Low'].iloc[current_idx].item()
    positions_to_close_info = [] 
    
    for pos in st.session_state.positions:
        sl = pos['sl']
        tp = pos['tp']
        triggered = False
        settle_price = 0.0
        reason = ''
        
        liq_price = pos.get('liquidation_price', 0.0)
        mode_info = config.TRADE_MODE_MAP.get(pos['pos_mode_key'], {})
        is_margin = mode_info.get('type') == 'Margin'
        direction = mode_info.get('direction', 'Long')

        # 強平檢查
        if is_margin and liq_price > 0:
            if direction == 'Long' and low <= liq_price:
                settle_price = liq_price; triggered = True; reason = '⚡ 強制平倉(多)'
            elif direction == 'Short' and high >= liq_price:
                settle_price = liq_price; triggered = True; reason = '⚡ 強制平倉(空)'
        
        # SL/TP 檢查
        if not triggered:
            if direction == 'Long' and pos['qty'] > 0:
                if sl > 0 and low <= sl: settle_price = sl; triggered = True; reason = '🛑 止損賣出'
                elif tp > 0 and high >= tp: settle_price = tp; triggered = True; reason = '🎯 止盈賣出'
            elif direction == 'Short' and pos['qty'] > 0:
                if sl > 0 and high >= sl: settle_price = sl; triggered = True; reason = '🛑 止損買回'
                elif tp > 0 and low <= tp: settle_price = tp; triggered = True; reason = '🎯 止盈買回'
        
        if triggered and settle_price > 0:
            positions_to_close_info.append({'id': pos['id'], 'qty': pos['qty'], 'price': settle_price, 'reason': reason})

    trigger_happened = False
    for info in positions_to_close_info:
        if close_position_lot(info['id'], info['qty'], info['price'], info['reason'], mode='自動'):
            trigger_happened = True
            
    return trigger_happened

def _advance_one_day():
    """推進一天 (記錄資產變化)"""
    if not st.session_state.sim_active: return False, False

    event_triggered = False

    if st.session_state.current_sim_index < st.session_state.max_sim_index:
        st.session_state.current_sim_index += 1
        
        if check_pending_orders(st.session_state.core_data, st.session_state.current_sim_index):
            event_triggered = True
            
        if check_sl_tp_trigger(st.session_state.core_data, st.session_state.current_sim_index):
            event_triggered = True
        
        total_asset_new = get_current_asset_value(st.session_state.core_data, st.session_state.current_sim_index)
        
        current_date, _, _ = get_price_info_by_index(st.session_state.core_data, st.session_state.current_sim_index)
        st.session_state.equity_history.append({'date': current_date, 'equity': total_asset_new})
        
        is_bankrupt = check_and_end_simulation(total_asset_new)
        
        if is_bankrupt:
            return False, True 
            
        return True, event_triggered
    else:
        settle_portfolio(force_end=True)
        return False, True 

def advance_multiple_days(days_to_advance):
    """一次推進多天"""
    if not st.session_state.sim_active: return False, False
    
    event_occurred = False
    can_continue = True
    
    for _ in range(days_to_advance):
        if st.session_state.current_sim_index >= st.session_state.max_sim_index:
            settle_portfolio(force_end=True)
            can_continue = False
            event_occurred = True 
            break
            
        st.session_state.current_sim_index += 1
        
        order_triggered = check_pending_orders(st.session_state.core_data, st.session_state.current_sim_index)
        sltp_triggered = check_sl_tp_trigger(st.session_state.core_data, st.session_state.current_sim_index)
        
        total_asset_new = get_current_asset_value(st.session_state.core_data, st.session_state.current_sim_index)
        
        current_date, _, _ = get_price_info_by_index(st.session_state.core_data, st.session_state.current_sim_index)
        st.session_state.equity_history.append({'date': current_date, 'equity': total_asset_new})
        
        is_bankrupt = check_and_end_simulation(total_asset_new)
        
        if order_triggered or sltp_triggered or is_bankrupt:
            event_occurred = True
            break
            
    return can_continue, event_occurred

def next_day():
    if not st.session_state.sim_active: return
    _advance_one_day()

def next_ten_days():
    if not st.session_state.sim_active: return
    days_to_advance = min(10, st.session_state.max_sim_index - st.session_state.current_sim_index)
    if days_to_advance <= 0: settle_portfolio(force_end=True); return
    advance_multiple_days(days_to_advance) 
    if st.session_state.sim_active and st.session_state.current_sim_index >= st.session_state.max_sim_index:
        settle_portfolio(force_end=True)
        st.session_state.last_event_msg = {'text': "回測結束。", 'type': 'info', 'mode': 'toast'}

def reset_state():
    """重置 Session State"""
    st.session_state.setdefault('ticker', config.DEFAULT_TICKER)
    st.session_state.setdefault('asset_type', 'Stock') 
    st.session_state.initialized = False
    st.session_state.core_data = None
    st.session_state.start_view_index = 0
    st.session_state.current_sim_index = 0
    st.session_state.max_sim_index = 0
    st.session_state.sim_active = True
    st.session_state.balance = config.INITIAL_CAPITAL
    st.session_state.transactions = [] 
    st.session_state.start_date = None
    st.session_state.end_sim_index_on_settle = None 
    st.session_state.positions = []
    st.session_state.pending_orders = [] 
    st.session_state.plot_layout = None 
    st.session_state.settlement_stats = None 
    st.session_state.last_event_msg = None
    st.session_state.auto_play = False 
    st.session_state.equity_history = [] 

def initialize_data_and_simulation(asset_type):
    """初始化資料與模擬環境"""
    ticker = st.session_state.ticker.upper()
    data = fetch_historical_data(ticker) 

    if data is None: 
        st.error(f"無法載入 {ticker} 的數據。")
        return
        
    st.session_state.core_data = data
    total_days = len(data)
    
    required_days = config.INITIAL_OBSERVATION_DAYS + config.MIN_SIMULATION_DAYS
    
    if total_days < required_days:
        st.warning(f"注意：{ticker} 數據不足。")
            
    start_indices = select_random_start_index(st.session_state.core_data)
    if start_indices is not None:
        start_view_idx, _ = start_indices
        data_end_idx = start_view_idx + required_days
        truncated_data = st.session_state.core_data.iloc[start_view_idx:data_end_idx].reset_index(drop=True)

        st.session_state.core_data = truncated_data
        st.session_state.start_view_index = 0
        
        st.session_state.current_sim_index = config.INITIAL_OBSERVATION_DAYS
        
        st.session_state.max_sim_index = len(truncated_data) - 1
        st.session_state.initialized = True
        st.session_state.sim_active = True
        st.session_state.asset_type = asset_type
        
        date_ts = st.session_state.core_data['Date'].iloc[st.session_state.current_sim_index]
        st.session_state.start_date = date_ts.to_pydatetime()
        st.session_state.settlement_stats = None
        st.session_state.last_event_msg = None
        
        st.session_state.equity_history = [{'date': st.session_state.start_date, 'equity': st.session_state.balance}]