# config.py
# 用於存放全域常數、交易規則與設定

# --- 回測參數 (Backtest Parameters) ---
VIEW_DAYS = 100                # 圖表可視範圍 (天)
INITIAL_OBSERVATION_DAYS = 250 # 初始觀察期 (天)

MIN_SIMULATION_DAYS = 720      # 最少需要多少天數據才能跑模擬
MA_PERIODS = [5, 10, 20, 60, 120]  # 移動平均線週期

# --- 預設值 (Defaults) ---
DEFAULT_TICKER = "TSLA"      # 預設載入的股票代號
INITIAL_CAPITAL = 100000.0   # 初始本金

# --- 圖表顏色配置 (Moving Average Colors) ---
MA_COLORS = {
    5: 'lightgray', 
    10: 'gray', 
    20: 'red',      
    60: 'blue',     
    120: 'white'    
}

# --- 交易費率設定 (Transaction Fees) ---
FEE_RATE = 0.005           # 現貨手續費 (0.5%)
LEVERAGE_FEE_RATE = 0.01   # 槓桿手續費 (1%)
MIN_MARGIN_RATE = 0.05     # 最小保證金比例 (5%)

# --- 資產類型配置 (Asset Configurations) ---
ASSET_CONFIGS = {
    'Stock': {
        'unit': '股', 
        'mode_spot': '現貨',          
        'mode_margin_long': '融資',   
        'mode_margin_short': '融券',  
        'default_qty': 1000.0, 
        'min_qty': 1.0
    }, 
    'Forex': {
        'unit': '點', 
        'mode_spot': '現貨',          
        'mode_margin_long': '做多',   
        'mode_margin_short': '做空',  
        'default_qty': 100.0, 
        'min_qty': 100.0
    }, 
    'Crypto': {
        'unit': '顆', 
        'mode_spot': '現貨',          
        'mode_margin_long': '合約做多', 
        'mode_margin_short': '合約做空', 
        'default_qty': 1.0, 
        'min_qty': 0.001
    }
}

# --- 輔助集合：用於邏輯判斷 ---
LONG_MODES = {'現貨', '融資', '做多', '合約做多'}
SHORT_MODES = {'融券', '做空', '合約做空'}
LEVERAGE_MODES = {'融資', '融券', '做多', '做空', '合約做多', '合約做空'}

# --- 交易模式映射表 ---
TRADE_MODE_MAP = {
    'Spot_Buy': {
        'type': 'Spot', 
        'direction': 'Long'
    },
    'Margin_Long': {
        'type': 'Margin', 
        'direction': 'Long'
    },
    'Margin_Short': {
        'type': 'Margin', 
        'direction': 'Short'
    },
}

GUIDE_CONTENT = """
# 🚀 Ksim V3 (K-line Simulation) 操作教學指南

歡迎使用 **Ksim V3**！這是一個專為交易者設計的歷史回測模擬器，讓您在無風險的環境下，使用真實的歷史數據練習交易策略。

## 1. 快速開始 (Quick Start)

1. **選擇資產類型**：
   * 在左側欄選擇 `Stock` (股票)、`Forex` (匯率) 或 `Crypto` (加密貨幣)。

2. **輸入代碼**：
   * 請輸入 Yahoo Finance 對應的代碼，例如 `TSLA`, `BTC-USD`。

3. **開始回測**：
   * 點擊 **`🚀 點擊開始回測`** 按鈕。
   * 系統會隨機抽取一段歷史數據，並給予 **$100,000** 初始資金。

## 2. 介面介紹 (Interface)

### **📊 主圖表區 (Main Chart)**
* **K 線圖**：顯示價格走勢 (Log Scale)。
* **技術指標**：包含 MA, BBands, MACD, RSI。
* **交易標記**：
  * `🟢 Buy`：買入點 (綠色向上箭頭)
  * `🔴 Sell`：賣出點 (紅色向下箭頭)

### **🛠️ 左側控制欄 (Sidebar)**
* **指標設定**：勾選要顯示的指標 (MA, BBands, MACD, RSI)。
* **自動播放**：控制回測速度與暫停。
* **下單面板**：執行買賣操作。

### **📋 下方資訊區**
* **資金看板**：即時顯示總資產、現金餘額、未實現損益。
* **掛單管理**：查看與取消未成交的限價/止損單。
* **交易倉位**：管理目前持有的部位 (設定 SL/TP)。

## 3. 下單操作 (Order Types)

在左側「**🛒 開倉交易**」面板選擇訂單類型：

### **A. ⚡ 市價單 (Market)**
* **定義**：立即以當前價格成交。
* **適用時機**：想要馬上進場或出場時。

### **B. 📉 限價單 (Limit) - "逢低買進 / 逢高賣出"**
* **做多 (Long)**：設定價格 **< (低於)** 市價。
  * *例子：現在 $100，我想等跌到 $95 再買。*
* **做空 (Short)**：設定價格 **> (高於)** 市價。
  * *例子：現在 $100，我想等漲到 $105 再空。*
* **注意**：若價格設定優於市價 (例如 $100 時掛買 $105)，會立即以市價成交。

### **C. 📈 止損單 (Stop) - "追價 / 突破策略"**
* **做多 (Long)**：設定價格 **> (高於)** 市價。
  * *例子：現在 $100，我想等突破 $105 確認趨勢後再追買。*
* **做空 (Short)**：設定價格 **< (低於)** 市價。
  * *例子：現在 $100，我想等跌破 $95 確認崩盤後再追空。*

## 4. 自動播放 (Auto-Play)

* **功能**：自動推進時間，無需手動點擊「下一天」。
* **設定**：
  * **刷新間隔**：控制每一幀的時間 (秒)。
  * **每次前進**：控制每次刷新跳幾根 K 棒 (設大一點可減少畫面閃爍)。
* **自動暫停機制**：
  * 當發生 **交易成交**、**止損/止盈觸發**、**強制平倉** 時，系統會自動暫停，方便您檢視狀況。

## 5. 風險管理 (Risk Management)

1. 在下方的「**🎯 交易倉位**」表格中。
2. 直接在欄位輸入價格：
   * **SL (Stop Loss)**：止損價格。
   * **TP (Take Profit)**：止盈價格。
3. 點擊 **`💾 儲存 SL/TP 設定`** 按鈕生效。
4. 系統會在每日開盤與盤中高低點自動檢查是否觸發。

## 6. 結算與分析

* 當回測天數結束，或手動點擊 **`🛑 提早結算`** 後，系統會顯示最終績效。
* 請參考下方的 **「💰 總資產成長曲線」** 檢視策略表現。
"""