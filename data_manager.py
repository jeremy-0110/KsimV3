# data_manager.py
# 負責獲取 Yahoo Finance 數據與計算技術指標

import yfinance as yf
import pandas as pd
import streamlit as st
from datetime import datetime
import random
import config

# --- 技術指標計算 ---

def calculate_rsi(data: pd.DataFrame, window: int = 14) -> pd.Series:
    """計算 RSI (Wilder's Smoothing)"""
    delta = data['Close'].diff()
    gain = (delta.where(delta > 0, 0))
    loss = (-delta.where(delta < 0, 0))
    
    avg_gain = gain.ewm(com=window - 1, min_periods=window).mean()
    avg_loss = loss.ewm(com=window - 1, min_periods=window).mean()
    
    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    return rsi

def calculate_bollinger_bands(data: pd.DataFrame, window: int = 20, num_std: float = 2.0) -> pd.DataFrame:
    """計算布林通道"""
    ma = data['Close'].rolling(window=window).mean()
    std = data['Close'].rolling(window=window).std()
    upper = ma + (std * num_std)
    lower = ma - (std * num_std)
    
    return pd.DataFrame({
        'BB_MA': ma,
        'BB_UPPER': upper,
        'BB_LOWER': lower
    })

def calculate_macd(data: pd.DataFrame, fast_period: int = 12, slow_period: int = 26, signal_period: int = 9) -> pd.DataFrame:
    """計算 MACD"""
    ema_fast = data['Close'].ewm(span=fast_period, adjust=False).mean()
    ema_slow = data['Close'].ewm(span=slow_period, adjust=False).mean()
    
    macd_line = ema_fast - ema_slow
    macd_signal = macd_line.ewm(span=signal_period, adjust=False).mean()
    macd_hist = macd_line - macd_signal
    
    return pd.DataFrame({
        'MACD_Line': macd_line,
        'MACD_Signal': macd_signal,
        'MACD_Hist': macd_hist
    })

# --- 資料獲取與處理 (ETL) ---

@st.cache_data(ttl=3600, show_spinner="📈 正在載入並計算指標 (MA, RSI, MACD, BBands)...")
def fetch_historical_data(ticker: str = "TSLA") -> pd.DataFrame | None:
    """從 Yahoo Finance 下載歷史數據並進行預處理"""
    period = 'max'

    try:
        data = yf.download(ticker.upper(), period=period, interval='1d', progress=False)
        
        if data.empty:
            return None
        
        if isinstance(data.columns, pd.MultiIndex):
            data.columns = data.columns.droplevel(1)

        required_cols = ['Open', 'High', 'Low', 'Close', 'Volume']
        if not all(col in data.columns for col in required_cols):
            st.error(f"數據格式錯誤：缺少必要欄位。可用欄位: {data.columns.tolist()}")
            return None

        data = data[required_cols].reset_index()
        data.columns = ['Date', 'Open', 'High', 'Low', 'Close', 'Volume']
        data['Date'] = pd.to_datetime(data['Date'])
        
        # 1. MA
        for p in config.MA_PERIODS:
            data[f'MA{p}'] = data['Close'].rolling(window=p).mean()
            
        # 2. RSI
        data['RSI'] = calculate_rsi(data, window=14)
        
        # 3. Bollinger Bands
        bb_data = calculate_bollinger_bands(data, window=20, num_std=2.0)
        data = pd.concat([data, bb_data], axis=1)
        
        # 4. MACD
        macd_data = calculate_macd(data)
        data = pd.concat([data, macd_data], axis=1)
        
        data.dropna(inplace=True) 
        data = data.reset_index(drop=True)
        return data

    except Exception as e:
        st.error(f"數據載入錯誤: {e}")
        return None
    
# --- 模擬輔助函式 ---

def select_random_start_index(data: pd.DataFrame) -> tuple[int, int] | None:
    """隨機挑選一段歷史區間"""
    total_days = len(data)
    required_days = config.INITIAL_OBSERVATION_DAYS + config.MIN_SIMULATION_DAYS
    
    if total_days < config.INITIAL_OBSERVATION_DAYS:
         return None
         
    if total_days < required_days:
        max_start_index = total_days - config.INITIAL_OBSERVATION_DAYS
        start_view_index = 0
        sim_start_index = start_view_index + config.INITIAL_OBSERVATION_DAYS
        return start_view_index, sim_start_index
    
    max_start_index = total_days - required_days
    start_view_index = random.randint(0, max_start_index)
    sim_start_index = start_view_index + config.INITIAL_OBSERVATION_DAYS
    
    return start_view_index, sim_start_index

def get_price_info_by_index(data: pd.DataFrame, index: int) -> tuple[datetime, float, float]:
    """根據索引取得某一天的價格資訊"""
    if data is not None and index < len(data):
        current_row = data.iloc[index]
        
        date_timestamp = current_row['Date']
        if isinstance(date_timestamp, pd.Series):
             date_timestamp = date_timestamp.iloc[0]
        
        date = pd.to_datetime(date_timestamp).to_pydatetime()
        
        # 強制轉換為 float
        open_price = float(current_row['Open'].item() if hasattr(current_row['Open'], 'item') else current_row['Open'])
        close_price = float(current_row['Close'].item() if hasattr(current_row['Close'], 'item') else current_row['Close'])
        
        return date, open_price, close_price
    return datetime.now(), 0.0, 0.0