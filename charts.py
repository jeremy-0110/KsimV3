# charts.py
# 負責繪製 Plotly 圖表 (K線、MA、Volume、RSI)

import plotly.graph_objects as go
from plotly.subplots import make_subplots
import config
import numpy as np
import pandas as pd

def render_main_chart(ticker, core_data, current_idx, positions, end_sim_index_on_settle, saved_layout=None, pending_orders=None, selected_indicators=None, asset_type='Stock', transactions=None):
    """
    繪製主圖表，包括 K 線、成交量、技術指標等
    """
    if selected_indicators is None:
        selected_indicators = []
        
    # 判斷是否顯示成交量
    show_volume = (asset_type != 'Forex')
    
    # 決定子圖數量和高度
    num_subplots = 1 # 預設只有 K 線
    row_heights = [0.6 if show_volume else 0.8] # K 線高度
    subplot_titles = [f"{ticker} 日線 (Log)"]
    
    if show_volume:
        num_subplots += 1
        row_heights.append(0.2)
        subplot_titles.append("成交量")
    
    if 'MACD' in selected_indicators:
        num_subplots += 1
        row_heights.append(0.2)
        subplot_titles.append("MACD")
    
    if 'RSI' in selected_indicators:
        num_subplots += 1
        row_heights.append(0.2)
        subplot_titles.append("RSI(14)")
        
    # 定義各指標所在的 Row
    row_ptr = 1
    k_line_row = row_ptr
    row_ptr += 1
    
    volume_row = 0
    if show_volume:
        volume_row = row_ptr
        row_ptr += 1
        
    macd_row = 0
    if 'MACD' in selected_indicators:
        macd_row = row_ptr
        row_ptr += 1
        
    rsi_row = 0
    if 'RSI' in selected_indicators:
        rsi_row = row_ptr
        row_ptr += 1
        
    # --- 數據準備 ---
    display_start_idx = 0 
    display_end_idx = current_idx + 1
    
    data_to_display = core_data.iloc[display_start_idx : display_end_idx].copy()
    data_to_display['DateStr'] = data_to_display['Date'].dt.strftime('%Y-%m-%d')
    x_axis_data = data_to_display['DateStr']

    last_visible_date = x_axis_data.iloc[-1]

    # --- Y 軸動態範圍計算 ---
    view_window_data = data_to_display.iloc[-config.VIEW_DAYS:] if len(data_to_display) > config.VIEW_DAYS else data_to_display
    
    if not view_window_data.empty:
        cols_to_check = ['Low', 'High']
        if 'BBands (主圖)' in selected_indicators and 'BB_UPPER' in view_window_data.columns:
             cols_to_check.extend(['BB_UPPER', 'BB_LOWER'])

        price_min = view_window_data[cols_to_check].min().min()
        price_max = view_window_data[cols_to_check].max().max()
        
        padding = (price_max - price_min) * 0.1 
        y_range_min = max(0.0001, price_min - padding)
        y_range_max = price_max + padding
        if y_range_max <= y_range_min: y_range_max = y_range_min * 1.1
    else:
        y_range_min, y_range_max = 1, 100

    # 建立子圖
    fig = make_subplots(
        rows=num_subplots, cols=1, 
        row_heights=row_heights, 
        shared_xaxes=True, 
        vertical_spacing=0.03,
        subplot_titles=subplot_titles 
    )

    # 1. K線圖
    fig.add_trace(go.Candlestick(
        x=x_axis_data, 
        open=data_to_display['Open'], high=data_to_display['High'],
        low=data_to_display['Low'], close=data_to_display['Close'], 
        name='K-Line'
    ), row=k_line_row, col=1)

    # 2. MA 線
    if 'MA (移動平均線)' in selected_indicators:
        for p_ma in config.MA_PERIODS:
            if f'MA{p_ma}' in data_to_display.columns:
                fig.add_trace(go.Scatter(
                    x=x_axis_data, y=data_to_display[f'MA{p_ma}'], mode='lines', 
                    name=f'MA{p_ma}', line=dict(color=config.MA_COLORS.get(p_ma, 'gray'), width=1)
                ), row=k_line_row, col=1) 

    # 3. BBands
    if 'BBands (主圖)' in selected_indicators and 'BB_MA' in data_to_display.columns:
        fig.add_trace(go.Scatter(x=x_axis_data, y=data_to_display['BB_UPPER'], mode='lines', 
                                 name='BB Upper', line=dict(color='orange', width=1)), row=k_line_row, col=1)
        fig.add_trace(go.Scatter(x=x_axis_data, y=data_to_display['BB_MA'], mode='lines', 
                                 name='BB MA', line=dict(color='yellow', width=1)), row=k_line_row, col=1)
        fig.add_trace(go.Scatter(x=x_axis_data, y=data_to_display['BB_LOWER'], mode='lines', 
                                 name='BB Lower', line=dict(color='orange', width=1)), row=k_line_row, col=1)
        
    # --- 繪製輔助線與標籤 (持倉中) ---
    for pos in positions:
        is_spot = (pos['display_name'] == '現貨')
        if is_spot: continue 

        lines_to_plot = {'開倉': {'price': pos['cost'], 'color': 'yellow', 'dash': 'dot'}}
        
        is_long = pos['display_name'] in config.LONG_MODES
        dir_str = '多' if is_long else '空'
        
        if pos.get('liquidation_price', 0) > 0:
            lines_to_plot['強平'] = {'price': pos['liquidation_price'], 'color': 'red', 'dash': 'dash'}
        if pos['sl'] > 0:
            lines_to_plot['止損'] = {'price': pos['sl'], 'color': 'red', 'dash': 'dot'}
        if pos['tp'] > 0:
            lines_to_plot['止盈'] = {'price': pos['tp'], 'color': 'green', 'dash': 'dot'}

        for name, info in lines_to_plot.items():
            price = info['price']
            if price <= 0: continue
            
            fig.add_hline(y=price, line_width=1, line_dash=info['dash'], line_color=info['color'], row=k_line_row, col=1)
            
            label_text = f"  {dir_str}{name} {price:,.2f}"
            fig.add_trace(go.Scatter(
                x=[last_visible_date], y=[price], text=[label_text], mode="text",
                textposition="middle right", textfont=dict(color=info['color'], size=12, family="Roboto, Arial, sans-serif"),
                cliponaxis=False, showlegend=False, hoverinfo='skip'
            ), row=k_line_row, col=1)

    # --- 繪製掛單 (Pending Orders) ---
    if pending_orders:
        for order in pending_orders:
            price = order['price']
            is_long = 'Buy' in order.get('trade_mode_key', '') or 'Long' in order.get('trade_mode_key', '')
            color = 'cyan' if is_long else 'orange'
            label_prefix = f"掛{order.get('order_type', 'Limit')}-買" if is_long else f"掛{order.get('order_type', 'Limit')}-賣"
            
            fig.add_hline(y=price, line_width=1, line_dash="dashdot", line_color=color, row=k_line_row, col=1)
            
            label_text = f"  ⏳ {label_prefix} {price:,.2f}"
            fig.add_trace(go.Scatter(
                x=[last_visible_date], y=[price], text=[label_text], mode="text",
                textposition="middle right", textfont=dict(color=color, size=11, family="Roboto, Arial, sans-serif"),
                cliponaxis=False, showlegend=False, hoverinfo='skip'
            ), row=k_line_row, col=1)

    # --- 繪製歷史交易箭頭 (Buy/Sell Markers) ---
    if transactions:
        buy_x, buy_y, buy_text = [], [], []
        sell_x, sell_y, sell_text = [], [], []

        for tx in transactions:
            try:
                open_d = pd.to_datetime(tx['open_date']).strftime('%Y-%m-%d')
                close_d = pd.to_datetime(tx['close_date']).strftime('%Y-%m-%d')
                
                if tx['direction'] == 'Long': 
                    buy_x.append(open_d); buy_y.append(tx['open_price']); buy_text.append(f"開多 @ {tx['open_price']:.2f}")
                    sell_x.append(close_d); sell_y.append(tx['close_price']); sell_text.append(f"平多 ({tx['reason']})<br>損益: {tx['net_pnl']:.2f}")
                else: 
                    sell_x.append(open_d); sell_y.append(tx['open_price']); sell_text.append(f"開空 @ {tx['open_price']:.2f}")
                    buy_x.append(close_d); buy_y.append(tx['close_price']); buy_text.append(f"平空 ({tx['reason']})<br>損益: {tx['net_pnl']:.2f}")
            except:
                continue

        if buy_x:
            fig.add_trace(go.Scatter(
                x=buy_x, y=buy_y, mode='markers', name='Buy', text=buy_text, hoverinfo='text',
                marker=dict(symbol='triangle-up', size=12, color='#00CC96', line=dict(width=1, color='white'))
            ), row=k_line_row, col=1)
        if sell_x:
            fig.add_trace(go.Scatter(
                x=sell_x, y=sell_y, mode='markers', name='Sell', text=sell_text, hoverinfo='text',
                marker=dict(symbol='triangle-down', size=12, color='#EF553B', line=dict(width=1, color='white'))
            ), row=k_line_row, col=1)

    # 4. Volume
    if show_volume:
        fig.add_trace(go.Bar(x=x_axis_data, y=data_to_display['Volume'], marker_color='grey', name='Volume'), row=volume_row, col=1)

    # 5. MACD
    if macd_row > 0 and 'MACD_Line' in data_to_display.columns:
        colors = ['red' if val < 0 else 'green' for val in data_to_display['MACD_Hist']]
        fig.add_trace(go.Bar(x=x_axis_data, y=data_to_display['MACD_Hist'], marker_color=colors, name='MACD Hist'), row=macd_row, col=1)
        fig.add_trace(go.Scatter(x=x_axis_data, y=data_to_display['MACD_Line'], mode='lines', 
                                 name='MACD Line', line=dict(color='blue', width=1)), row=macd_row, col=1)
        fig.add_trace(go.Scatter(x=x_axis_data, y=data_to_display['MACD_Signal'], mode='lines', 
                                 name='MACD Signal', line=dict(color='orange', width=1)), row=macd_row, col=1)
        fig.add_hline(y=0, line_dash="dot", line_color="gray", row=macd_row, col=1)
    
    # 6. RSI
    if rsi_row > 0 and 'RSI' in data_to_display.columns:
        fig.add_trace(go.Scatter(x=x_axis_data, y=data_to_display['RSI'], line=dict(color='purple'), name='RSI'), row=rsi_row, col=1)
        fig.add_hline(y=70, line_dash="dash", line_color="red", row=rsi_row, col=1)
        fig.add_hline(y=30, line_dash="dash", line_color="green", row=rsi_row, col=1)
        fig.add_hline(y=50, line_dash="dot", line_color="gray", row=rsi_row, col=1)

    # 垂直線
    if end_sim_index_on_settle:
        try:
            start_abs_idx = config.INITIAL_OBSERVATION_DAYS
            end_abs_idx = end_sim_index_on_settle
            if start_abs_idx < len(x_axis_data):
                fig.add_vline(x=x_axis_data.iloc[start_abs_idx], line_dash="dot", line_color="green", row=k_line_row, col=1)
            if end_abs_idx < len(x_axis_data):
                fig.add_vline(x=x_axis_data.iloc[end_abs_idx], line_dash="dot", line_color="white", row=k_line_row, col=1)
        except:
            pass

    initial_range = None
    if end_sim_index_on_settle is not None:
        initial_range = None 
    else:
        total_len = len(x_axis_data)
        end_idx = total_len - 1
        start_idx = max(0, end_idx - config.VIEW_DAYS)
        initial_range = [start_idx - 0.5, end_idx + 0.5]

    common_font = "Roboto, Arial, sans-serif"
    invisible_text = '\u200b' 
    
    yaxis_dict = {
        k_line_row: dict(side='right', type='log', range=[np.log10(y_range_min), np.log10(y_range_max)], fixedrange=False),
    }
    if show_volume:
        yaxis_dict[volume_row] = dict(side='right')
        
    if macd_row > 0:
        yaxis_dict[macd_row] = dict(side='right')
    if rsi_row > 0:
        yaxis_dict[rsi_row] = dict(side='right', range=[0, 100])

    fig.update_xaxes(
        type='category', showticklabels=False, range=initial_range, rangeslider=dict(visible=False) 
    )
    
    total_height = 500 
    if show_volume: total_height += 100
    if macd_row > 0: total_height += 150
    if rsi_row > 0: total_height += 150
    
    layout_updates = {
        "template": "plotly_dark", 
        "height": total_height, 
        "showlegend": False, 
        "dragmode": 'pan', 
        "hovermode": 'x unified', 
        "font": dict(family=common_font),
        "margin": dict(t=30, b=30, l=50, r=120), 
        "xaxis": dict(unifiedhovertitle=dict(text=invisible_text)),
        "uirevision": "constant_value", # [保留] 鎖定圖表狀態，避免重置
        "newshape": dict(line=dict(color='#00BFFF', width=2)) # [保留] 設定畫筆顏色為淺藍色
    }
    
    if show_volume:
        layout_updates[f"xaxis{volume_row}"] = dict(unifiedhovertitle=dict(text=invisible_text))

    for row, yaxis_config in yaxis_dict.items():
        if row == 1:
            layout_updates['yaxis'] = yaxis_config
        else:
            layout_updates[f'yaxis{row}'] = yaxis_config
            
    fig.update_layout(**layout_updates)
    
    return fig

def render_equity_curve(equity_history):
    """繪製總資產變動曲線"""
    if not equity_history:
        return None
        
    df = pd.DataFrame(equity_history)
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=df['date'], y=df['equity'], mode='lines', name='總資產',
        line=dict(color='#00CC96', width=2), fill='tozeroy', fillcolor='rgba(0, 204, 150, 0.1)'
    ))
    initial_cap = config.INITIAL_CAPITAL
    fig.add_hline(y=initial_cap, line_dash="dash", line_color="gray", annotation_text="初始本金")
    
    if len(df) > 1:
        max_idx = df['equity'].idxmax()
        min_idx = df['equity'].idxmin()
        max_equity = df['equity'].max()
        min_equity = df['equity'].min()
        fig.add_annotation(x=df.iloc[max_idx]['date'], y=max_equity, text=f"Max: ${max_equity:,.0f}", showarrow=True, arrowhead=1, yshift=10)
        if min_equity < initial_cap:
            fig.add_annotation(x=df.iloc[min_idx]['date'], y=min_equity, text=f"Min: ${min_equity:,.0f}", showarrow=True, arrowhead=1, yshift=-10, ay=30)

    fig.update_layout(
        title=" ",
        margin=dict(t=50, b=30, l=50, r=30), 
        xaxis_title=" ", 
        yaxis_title="資產總值", 
        hovermode="x unified",
        xaxis=dict(showticklabels=False)
    )
    return fig