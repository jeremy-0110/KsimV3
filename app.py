# app.py
# 應用程式入口：負責 UI 介面、事件處理與資料呈現

import streamlit as st
import pandas as pd
import numpy as np
import time 
import config
import logic
import charts

# --- 初始化 ---
st.set_page_config(layout="wide", page_title="Ksim V3")

# 確保 Session State 已初始化
if 'initialized' not in st.session_state:
    logic.reset_state()

if 'chart_reset_id' not in st.session_state:
    st.session_state.chart_reset_id = 0 

if 'pending_orders' not in st.session_state:
    st.session_state.pending_orders = []

if 'indicator_selector' not in st.session_state:
    st.session_state.indicator_selector = []

if 'auto_play' not in st.session_state:
    st.session_state.auto_play = False

# 簡化變數引用
state = st.session_state

# --- 回調函數 ---
def on_reset_click():
    logic.reset_state()
    st.session_state.indicator_selector = [] 
    st.session_state.auto_play = False

def toggle_autoplay():
    st.session_state.auto_play = not st.session_state.auto_play

# --- 側邊欄：初始設定 ---
if not state.initialized:
    with st.sidebar:
        st.header("Ksim V3")
        
        selected_asset_type = st.radio(
            "選擇回測資產類型 (定義交易規則)",
            ('Stock', 'Forex', 'Crypto'),
            format_func=lambda x: {'Stock': '📈 股票', 'Forex': '💱 匯率', 'Crypto': '₿ 加密貨幣'}[x]
        )
        
        state.ticker = st.text_input(
            "**請輸入代碼**  \n(請從yahoo finance搜尋代碼  \ne.g. TSLA, JPY=X, BTC-USD)",
            value=state.ticker 
        ).strip().upper() 
        
        if st.button("🚀點擊開始回測"):
            if state.ticker:
                valid_input = True
                error_msg = ""
                
                if selected_asset_type == 'Forex':
                    if not state.ticker.endswith('=X'):
                        valid_input = False
                        error_msg = f"錯誤：匯率代碼通常以 '=X' 結尾 (例如 JPY=X)。您輸入的是 {state.ticker}。"
                elif selected_asset_type == 'Crypto':
                    if not state.ticker.endswith('-USD'):
                        valid_input = False
                        error_msg = f"錯誤：加密貨幣代碼通常以 '-USD' 結尾 (例如 BTC-USD)。您輸入的是 {state.ticker}。"
                elif selected_asset_type == 'Stock':
                    if state.ticker.endswith('=X') or state.ticker.endswith('-USD'):
                        valid_input = False
                        error_msg = f"錯誤：您選擇了「股票」，但輸入的代碼看起來像匯率或加密貨幣。"

                if valid_input:
                    logic.reset_state()
                    state.chart_reset_id = 0
                    st.session_state.indicator_selector = []
                    logic.initialize_data_and_simulation(selected_asset_type) 
                    st.rerun()
                else:
                    st.error(error_msg)
            else:
                st.error("請輸入有效的代碼！")
    
    st.info(f"請在左側欄選擇資產類型，輸入代碼，並點擊 '🚀點擊開始回測'。目前預設: {state.ticker}")
    st.markdown(config.GUIDE_CONTENT)
    st.stop()

# --- 載入當前狀態參數 ---
asset_conf = config.ASSET_CONFIGS[state.asset_type]
unit_name = asset_conf['unit']
min_qty = asset_conf['min_qty']
default_qty = asset_conf['default_qty']

_, open_price, _ = logic.get_price_info_by_index(state.core_data, state.current_sim_index)
current_open_price = open_price if open_price > 0 else 0.0

# --- 側邊欄 ---
with st.sidebar:
    st.subheader(f"📈 {state.ticker} ({unit_name}回測)")
    
    days_passed = state.current_sim_index - config.INITIAL_OBSERVATION_DAYS + 1
    days_remain = state.max_sim_index - state.current_sim_index
    
    st.markdown(f"**進度:** {max(1, days_passed)} 天 / 剩餘 {max(0, days_remain)} 天")
    st.caption(f"(觀察期: {config.INITIAL_OBSERVATION_DAYS}天 / 顯示範圍: {config.VIEW_DAYS}天)")
    st.markdown("---")

    st.subheader("🔍 指標設定")
    selected_indicators = st.multiselect(
        "選擇要顯示的技術指標",
        options=['MA (移動平均線)', 'BBands (主圖)', 'MACD', 'RSI'],
        key='indicator_selector'
    )
    st.markdown("---")
    
    if state.sim_active:
        st.subheader("⏯️ 自動播放 (Auto-Play)")
        col_speed1, col_speed2 = st.columns(2)
        with col_speed1:
            refresh_rate = st.slider("刷新間隔 (秒)", 0.1, 2.0, 1.0, 0.1)
        with col_speed2:
            batch_size = st.slider("每次前進 (根)", 1, 10, 1, 1)
        
        btn_label = "⏸️ 暫停" if state.auto_play else "▶️ 開始播放"
        if st.button(btn_label, use_container_width=True, type="primary" if not state.auto_play else "secondary"):
            toggle_autoplay()
            st.rerun()
        st.markdown("---")

    if state.sim_active:
        disable_manual = state.auto_play
        col_t1, col_t2 = st.columns(2)
        with col_t1:
            if st.button("➡️ 下一天", use_container_width=True, disabled=disable_manual): 
                logic.next_day()
                st.rerun()
        with col_t2:
            if st.button("⏭️ 下十天", use_container_width=True, disabled=disable_manual): 
                logic.next_ten_days()
                st.rerun()
        if st.button("🛑 **提早結算**", use_container_width=True, help="結束模擬並平倉", disabled=disable_manual):
            logic.settle_portfolio(force_end=True)
            st.rerun()
    else:
        st.button("重新開始回測", use_container_width=True, on_click=on_reset_click)
    
    st.markdown("---")

    with st.expander("🛠️ 繪圖工具箱", expanded=True):
        st.caption("使用圖表右上角工具列進行手動繪圖。")
        if st.button("🗑️ 清除所有繪圖", use_container_width=True):
            state.chart_reset_id += 1 
            st.success("圖表已重置，繪圖已清除")
            st.rerun()

    st.markdown("---")
    
    st.subheader("🛒 開倉交易")
    
    if state.sim_active:
        if state.auto_play:
            st.warning("⚠️ 自動播放中，請暫停後再交易。")
        
        disable_trade = state.auto_play
        
        def get_mode_label(key):
            if key == 'Spot_Buy': return asset_conf['mode_spot']
            if key == 'Margin_Long': return asset_conf['mode_margin_long']
            if key == 'Margin_Short': return asset_conf['mode_margin_short']
            return key

        trade_mode_key = st.radio(
             "交易模式",
             ('Spot_Buy', 'Margin_Long', 'Margin_Short'), 
             format_func=get_mode_label,
             horizontal=True, key='trade_mode_select', disabled=disable_trade
        )

        mode_conf = config.TRADE_MODE_MAP[trade_mode_key]
        is_margin = mode_conf['type'] == 'Margin'
        leverage = 1.0
        
        if is_margin:
            leverage = st.slider("槓桿倍數", 1.0, 20.0, 2.0, 0.5, format='%.1fx', disabled=disable_trade)

        order_type = st.radio("訂單類型", ('Market', 'Limit', 'Stop'), 
                              format_func=lambda x: {'Market': '📌 市價單', 'Limit': '🏷️ 限價單', 'Stop': '🏷️ 止損單'}[x],
                              horizontal=True, disabled=disable_trade)

        order_price = current_open_price
        if order_type != 'Market':
            default_ratio = 1.05 if (order_type == 'Stop' and 'Long' in str(mode_conf)) or (order_type == 'Limit' and 'Short' in str(mode_conf)) else 0.95
            order_price = st.number_input(f"{order_type} 價格", 
                                          value=float(current_open_price) * default_ratio, 
                                          min_value=0.01, step=0.1, format="%.2f", disabled=disable_trade)
        
        qty_mode = st.radio("數量模式", ('Absolute', 'Percentage'), 
                            format_func=lambda x: unit_name if x == 'Absolute' else '百分比 (%)', 
                            horizontal=True, label_visibility="collapsed", disabled=disable_trade)
        
        final_qty = 0.0
        is_int_qty = (min_qty >= 1.0 and min_qty == int(min_qty))
        price_for_calc = order_price 
        
        if qty_mode == 'Absolute':
            if is_int_qty:
                qty_input = st.number_input(
                    f"數量 ({unit_name})", min_value=int(min_qty), value=int(default_qty), step=int(max(1, min_qty)), format='%i', disabled=disable_trade
                )
                final_qty = float(qty_input)
            else:
                qty_input = st.number_input(
                    f"數量 ({unit_name})", min_value=float(min_qty), value=float(default_qty), step=float(min_qty) if min_qty < 1 else 1.0, format='%.3f', disabled=disable_trade
                )
                final_qty = float(qty_input)
        else:
            pct = st.slider("開倉比例 (%)", 1.0, 100.0, 50.0, 1.0, disabled=disable_trade)
            asset_to_use = state.balance * (pct / 100.0)
            max_shares = (asset_to_use / price_for_calc * leverage) if price_for_calc > 0 else 0.0
            
            if is_int_qty:
                 final_qty = float(int(max_shares / min_qty) * min_qty)
            else:
                 precision = len(str(min_qty).split('.')[-1])
                 final_qty = round(max_shares / min_qty) * min_qty
                 final_qty = round(final_qty, precision)
            
            st.markdown(f"<p style='font-size: small;'>換算數量: {final_qty:,.3f} {unit_name}</p>", unsafe_allow_html=True)

        est_cost = final_qty * price_for_calc
        est_margin = est_cost / leverage
        fee_rate = config.LEVERAGE_FEE_RATE if is_margin else config.FEE_RATE
        est_fee = est_cost * fee_rate
        
        st.info(f"參考價: ${price_for_calc:,.2f} (市價: ${current_open_price:,.2f})")
        col_fee, col_cost = st.columns(2)
        with col_fee: st.markdown(f"<p style='font-size: small;'>預估費用: ${est_fee:,.2f}</p>", unsafe_allow_html=True)
        with col_cost: st.markdown(f"<p style='font-size: small;'>總值: ${est_cost:,.2f}</p>", unsafe_allow_html=True)
        
        if is_margin:
            liq_price = 0.0
            if mode_conf['direction'] == 'Long': liq_price = price_for_calc * (1.0 - (1.0 / leverage))
            else: liq_price = price_for_calc * (1.0 + (1.0 / leverage))
            st.markdown(f"**預估保證金:** ${est_margin:,.2f}")
            st.markdown(f"**預估強平價:** ${liq_price:,.2f}")

        btn_label = f"執行開倉" if order_type == 'Market' else f"確認 {order_type} 掛單 @ {order_price:,.2f}"
        
        if st.button(btn_label, use_container_width=True, disabled=disable_trade):
            if order_type == 'Market':
                if logic.execute_trade(trade_mode_key, final_qty, current_open_price, leverage):
                    st.rerun()
            else:
                if logic.place_limit_order(trade_mode_key, final_qty, order_price, leverage, order_type):
                    st.rerun()
    else:
        st.info("模擬已結束。")

# --- 主畫面區 ---

if 'last_event_msg' in state and state.last_event_msg:
    msg = state.last_event_msg
    msg_text = msg['text']
    msg_type = msg.get('type', 'info')
    msg_mode = msg.get('mode', 'alert')
    if msg_mode == 'toast':
        if msg_type == 'error': st.toast(msg_text, icon="❌")
        elif msg_type == 'success': st.toast(msg_text, icon="✅")
        else: st.toast(msg_text, icon="ℹ️")
    else:
        if msg_type == 'error': st.error(f"### {msg_text}")
        elif msg_type == 'success': st.success(f"### {msg_text}")
        else: st.info(f"### {msg_text}")
    del state.last_event_msg

if not state.sim_active and state.get('settlement_stats'):
    stats = state.settlement_stats
    with st.container():
        st.success(f"🏁 回測模擬結束！")
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("最終資產", f"${stats['final_asset']:,.2f}")
        pnl = stats['total_pnl']
        color = "normal" 
        c2.metric("總損益", f"${pnl:,.2f}", delta_color=color)
        c3.metric("投資報酬率 (ROI)", f"{stats['roi']:+.2f}%", delta_color=color)
        with c4:
            s_str = stats['start_date'].strftime('%Y/%m/%d')
            e_str = stats['end_date'].strftime('%Y/%m/%d')
            st.metric("回測期間", f"{s_str} ~ {e_str}")
        st.markdown("---")

total_asset = logic.get_current_asset_value(state.core_data, state.current_sim_index)
unrealized_pnl = logic.get_total_unrealized_pnl(current_open_price)
spot_info = logic.get_spot_summary(state.core_data, state.current_sim_index)

m1, m2, m3, m4 = st.columns(4)
m1.metric("總資產 (含未實現)", f"${total_asset:,.2f}")
m2.metric("現金餘額", f"${state.balance:,.2f}")
m3.metric("未實現損益", f"${unrealized_pnl:,.2f}")
m4.metric(f"現貨持倉 ({unit_name})", f"{spot_info['qty']:,.3f}")

# =========================================================
dynamic_key = f"main_chart_{state.chart_reset_id}"

fig = charts.render_main_chart(
    state.ticker, state.core_data, state.current_sim_index, 
    state.positions, state.end_sim_index_on_settle, state.plot_layout,
    pending_orders=state.pending_orders,
    selected_indicators=state.indicator_selector, 
    asset_type=state.asset_type,
    transactions=state.transactions
)

drawing_config = {
    'scrollZoom': True,
    'displayModeBar': True,
    'modeBarButtonsToAdd': [
        'drawline', 'drawopenpath', 'drawcircle', 'drawrect', 'eraseshape'
    ]
}

chart_event = st.plotly_chart(
    fig, 
    use_container_width=True, 
    key=dynamic_key,
    config=drawing_config
)

if dynamic_key in state and state[dynamic_key]:
    layout = state[dynamic_key].get('layout', {})
    if layout:
        saved = {}
        for i in [None, 2, 3]:
            k = f'xaxis{i}' if i else 'xaxis'
            if k in layout and 'range' in layout[k]:
                 saved[f'{k}.range'] = layout[k]['range']
        if saved: state.plot_layout = saved

st.markdown("---")
st.header("📋 掛單管理 (Pending Orders)")

if state.pending_orders:
    pending_data = []
    for order in state.pending_orders:
        pending_data.append({
            'ID': order['id'],
            '類型': order['display_name'],
            '訂單類型': order['order_type'],
            '掛單價格': order['price'],
            '數量': order['qty'],
            '槓桿': f"{order['leverage']}x",
        })
    df_pending = pd.DataFrame(pending_data)
    col_p_table, col_p_action = st.columns([3, 1])
    with col_p_table:
        st.dataframe(
            df_pending, 
            column_config={
                "掛單價格": st.column_config.NumberColumn(format="$%.2f"),
                "數量": st.column_config.NumberColumn(format="%.3f"),
            },
            hide_index=True,
            use_container_width=True
        )
    with col_p_action:
        st.caption("取消操作")
        order_to_cancel = st.selectbox("選擇掛單取消", options=[o['id'] for o in state.pending_orders], format_func=lambda x: f"ID: {x} (點擊取消)")
        if st.button("🚫 取消選定掛單", disabled=state.auto_play):
            logic.cancel_order(order_to_cancel)
            st.rerun()
else:
    st.info("目前沒有待成交的掛單。")

st.markdown("---")
st.header("🎯 交易倉位 (Open Positions)")

if state.positions:
    pos_data = []
    for pos in state.positions:
        qty = pos['qty']
        cost = pos['cost']
        leverage = pos.get('leverage', 1.0)
        mode_info = config.TRADE_MODE_MAP.get(pos['pos_mode_key'], {})
        direction = mode_info.get('direction', 'Long')
        pnl = logic.calculate_pnl_value(direction, qty, cost, current_open_price)
        sl_val = pos['sl']
        tp_val = pos['tp']
        sl_pnl_str = ""
        tp_pnl_str = ""
        if sl_val > 0:
            est_sl_pnl = logic.calculate_pnl_value(direction, qty, cost, sl_val)
            sign = "+" if est_sl_pnl > 0 else "-"
            sl_pnl_str = f"預估 {sign}${abs(est_sl_pnl):,.0f}"
        if tp_val > 0:
            est_tp_pnl = logic.calculate_pnl_value(direction, qty, cost, tp_val)
            sign = "+" if est_tp_pnl > 0 else "-"
            tp_pnl_str = f"預估 {sign}${abs(est_tp_pnl):,.0f}"
        pos_data.append({
            'ID': pos['id'], '類型': pos['display_name'], '槓桿': f"{leverage:.1f}x",
            '數量': qty, '開倉價': cost, '未實現損益': pnl,
            'SL': sl_val, 'SL 預估損益': sl_pnl_str,
            'TP': tp_val, 'TP 預估損益': tp_pnl_str
        })
    
    df_pos = pd.DataFrame(pos_data)
    
    disabled_pos_edit = state.auto_play
    
    edited_df = st.data_editor(
        df_pos.set_index('ID'),
        column_config={
            "類型": st.column_config.TextColumn(disabled=True),
            "槓桿": st.column_config.TextColumn(disabled=True),
            "數量": st.column_config.NumberColumn(format="%.3f", disabled=True),
            "開倉價": st.column_config.NumberColumn(format="$%.2f", disabled=True),
            "未實現損益": st.column_config.NumberColumn(format="$%.2f", disabled=True),
            "SL": st.column_config.NumberColumn("止損價格 (SL)", format="$%.2f", step=0.1),
            "SL 預估損益": st.column_config.TextColumn("SL 損益", disabled=True),
            "TP": st.column_config.NumberColumn("止盈價格 (TP)", format="$%.2f", step=0.1),
            "TP 預估損益": st.column_config.TextColumn("TP 損益", disabled=True),
        },
        use_container_width=True, key='pos_editor', disabled=disabled_pos_edit
    )
    if st.button("💾 儲存 SL/TP 設定", use_container_width=True, disabled=disabled_pos_edit):
        updates = edited_df.to_dict('index')
        changed = False
        validation_error = False
        for pos in state.positions:
            pid = pos['id']
            if pid in updates:
                new_sl = updates[pid]['SL']
                new_tp = updates[pid]['TP']
                if pos['sl'] == new_sl and pos['tp'] == new_tp: continue
                liq_price = pos.get('liquidation_price', 0.0)
                cost_price = pos.get('cost', 0.0)
                mode_info = config.TRADE_MODE_MAP.get(pos['pos_mode_key'], {})
                direction = mode_info.get('direction', 'Long')
                if liq_price > 0:
                    if direction == 'Long' and new_sl > 0 and new_sl <= liq_price:
                        st.error(f"🚫 ID {pid[-4:]} 錯誤：多頭止損 ({new_sl}) 不能低於強制平倉價 ({liq_price:.2f})！"); validation_error = True; continue
                    elif direction == 'Short' and new_sl > 0 and new_sl >= liq_price:
                        st.error(f"🚫 ID {pid[-4:]} 錯誤：空頭止損 ({new_sl}) 不能高於強制平倉價 ({liq_price:.2f})！"); validation_error = True; continue
                if new_tp > 0:
                    if direction == 'Long' and new_tp <= cost_price:
                        st.error(f"🚫 ID {pid[-4:]} 錯誤：多頭止盈 ({new_tp}) 必須高於開倉價 ({cost_price:.2f})！"); validation_error = True; continue
                    elif direction == 'Short' and new_tp >= cost_price:
                        st.error(f"🚫 ID {pid[-4:]} 錯誤：空頭止盈 ({new_tp}) 必須低於開倉價 ({cost_price:.2f})！"); validation_error = True; continue
                pos['sl'] = new_sl
                pos['tp'] = new_tp
                changed = True
        if not validation_error:
            if changed: st.success("設定已更新！"); st.rerun() 
            else: st.info("無變更。")

    st.markdown("---")
    col_header, col_close_all = st.columns([4, 1])
    with col_header: st.subheader("手動平倉操作")
    if state.sim_active:
        pos_opts = {p['id']: f"{p['display_name']} {p['qty']:.3f} ({p['id'][-4:]})" for p in state.positions}
        with col_close_all:
             st.write("") 
             if st.button("🔴 平倉所有部位", use_container_width=True, key='close_all_btn', disabled=disabled_pos_edit):
                logic.settle_portfolio(); st.rerun()
        col_select, col_mode_radio = st.columns([3, 2])
        with col_select:
            st.caption("選擇部位")
            sel_pid = st.selectbox("選擇部位", options=list(pos_opts.keys()), format_func=lambda x: pos_opts[x], label_visibility='collapsed', key='manual_close_select', disabled=disabled_pos_edit)
        target_pos = next((p for p in state.positions if p['id'] == sel_pid), None)
        if target_pos:
            max_q = target_pos['qty']
            close_q = max_q
            with col_mode_radio:
                st.caption("平倉模式")
                close_mode = st.radio("平倉模式", ('全部', '指定數量', '指定比例'), horizontal=True, label_visibility='collapsed', key='manual_close_mode_radio', disabled=disabled_pos_edit)
            st.markdown("##### ") 
            col_input_value, col_execute = st.columns([4, 1])
            with col_input_value:
                if close_mode == '指定數量':
                    close_q = st.number_input(f"平倉數量 ({unit_name})", min_value=0.0, max_value=float(max_q), value=float(max_q), step=min_qty if min_qty < 1 else 1.0, key='manual_close_qty_input', disabled=disabled_pos_edit)
                elif close_mode == '指定比例':
                    pct_close = st.slider("比例 (%)", 1.0, 100.0, 50.0, key='manual_close_pct_slider', disabled=disabled_pos_edit)
                    close_q = max_q * (pct_close / 100.0)
                    st.caption(f"換算數量: **{close_q:,.3f} {unit_name}**")
                else: 
                    close_q = max_q
                    st.info(f"將平倉部位全部數量: **{max_q:,.3f} {unit_name}**")
            with col_execute:
                if close_mode == '指定數量': st.markdown("<br>", unsafe_allow_html=True) 
                else: st.markdown("##### ") 
                if st.button(f"執行平倉", use_container_width=True, key='execute_close_btn', disabled=disabled_pos_edit):
                    if logic.close_position_lot(sel_pid, close_q, current_open_price, reason='手動平倉', mode='手動'): st.rerun()
else:
    st.info("目前無持倉。")

st.markdown("---")
st.header("📝 交易紀錄 (Transaction History)")
if state.transactions:
    df_tx = pd.DataFrame(state.transactions)
    df_display = df_tx[['type_display', 'qty', 'open_price', 'close_price', 'fees', 'net_pnl', 'reason']].copy()
    df_display.columns = ['類型', '數量', '開倉價', '平倉價', '總手續費', '淨損益', '備註']
    def color_pnl(val): return f'color: {"green" if val > 0 else "red" if val < 0 else ""}'
    st.dataframe(df_display.style.map(color_pnl, subset=['淨損益']).format({'數量': '{:,.3f}', '開倉價': '${:,.2f}', '平倉價': '${:,.2f}', '總手續費': '${:,.2f}', '淨損益': '${:,.2f}'}), use_container_width=True, hide_index=True)
else:
    st.info("尚無已平倉的交易紀錄。")

st.markdown("---")
if state.equity_history and len(state.equity_history) > 1:
    st.subheader("💰 總資產成長曲線")
    equity_fig = charts.render_equity_curve(state.equity_history)
    if equity_fig: st.plotly_chart(equity_fig, use_container_width=True, config={'displayModeBar': False})
else:
    st.caption("資產曲線將在回測開始後顯示...")

if state.auto_play and state.sim_active:
    time.sleep(refresh_rate) 
    can_continue, event_triggered = logic.advance_multiple_days(batch_size)
    if not can_continue:
        state.auto_play = False
        st.rerun()
    elif event_triggered:
        state.auto_play = False
        st.toast("⚠️ 交易觸發，自動暫停播放", icon="⏸️")
        st.rerun()
    else:

        st.rerun()
