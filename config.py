"""
Quant Compass AI Ultimate V2.0 — Core Configuration
Strictly separates Frozen Baseline (QC-PT-1.0-FROZEN) and AI Ultimate Strategy (QC-AI-2.0).
"""
import os

APP_NAME = "Quant Compass AI Ultimate V2.0"
TIMEZONE = "Asia/Taipei"

# Strategy Version Constants (DO NOT MODIFY FROZEN BASELINE)
STRATEGY_FROZEN = "QC-PT-1.0-FROZEN"
STRATEGY_AI_V2 = "QC-AI-2.0"

# Portfolio & Risk Constraints (Shared Baseline Rules)
INITIAL_CAPITAL = 1_000_000.0  # NT$1,000,000
MAX_POSITIONS = 5
MAX_RISK_PER_TRADE_PCT = 0.01  # 1% max risk per trade
MAX_SINGLE_POSITION_PCT = 0.20  # 20% max allocation per stock
MAX_SECTOR_EXPOSURE_PCT = 0.40  # 40% max exposure in same sector
MIN_CASH_RESERVE_PCT = 0.02     # 2% cash reserve for fees/slippage

# Technical & Liquidity Parameters
MA_SHORT = 20
MA_LONG = 60
RSI_PERIOD = 14
RSI_MIN_FROZEN = 45.0
RSI_MAX_FROZEN = 70.0
RSI_MIN_AI = 45.0
RSI_MAX_AI = 72.0
ATR_PERIOD = 14
VOL_MA_PERIOD = 20
MIN_AVG_VOLUME_SHARES = 500_000  # >= 500 lots avg daily volume
MIN_PRICE = 15.0

# Execution & Exit Parameters
STOP_LOSS_ATR_MULT = 2.0
TAKE_PROFIT_ATR_MULT = 3.0
TP2_ATR_MULT = 4.5
MIN_RISK_REWARD_RATIO = 1.5
MAX_HOLDING_TRADING_DAYS = 20
MAX_OPEN_CHASE_PCT = 0.04  # Cancel next-day open buy if gaps > 4%
AI_MIN_QUALITY_SCORE = 65.0
AI_MIN_DATA_CONFIDENCE = 50.0  # Below 50% -> Grey Light (Insufficient Data)
AI_MIN_MARKET_TEMP = 40.0      # Below 40 -> Pause new AI-2.0 BUYs

# 6-Factor AI Stock Scoring Weights (Sum = 1.0)
SCORE_WEIGHTS = {
    "health": 0.20,      # 健康度
    "growth": 0.20,      # 成長性
    "safety": 0.20,      # 安全性
    "popularity": 0.10,  # 人氣度
    "smart_money": 0.10, # 主力資金
    "trend": 0.20,       # 技術趨勢
}

# Taiwan Stock Transaction Cost Assumptions (Conservative Standard)
BROKERAGE_FEE_RATE = 0.001425
BROKERAGE_DISCOUNT = 1.0        # 1.0 = No discount (explicit assumption)
MIN_BROKERAGE_FEE_LOT = 20.0
MIN_BROKERAGE_FEE_ODD = 1.0
SELL_TAX_RATE = 0.003           # 0.3% Securities Transaction Tax
SLIPPAGE_RATE = 0.001           # 0.1% per side

MIN_SAMPLE_SIZE_WARNING = 10

# Relative Storage Paths (No private developer paths)
DB_PATH = "quant_compass_v2_ledger.db"
JSON_LEDGER_DIR = "QuantCompass"
JSON_LEDGER_PATH = os.path.join(JSON_LEDGER_DIR, "quant_compass_paper_ledger.json")

# Representative Liquid Taiwan Stock Universe (with Sector tags for concentration risk check)
# Tuple: (symbol, name, market, sector)
DEFAULT_TW_UNIVERSE = [
    ("2330", "台積電", "TW", "半導體"), ("2454", "聯發科", "TW", "半導體"),
    ("2303", "聯電", "TW", "半導體"), ("3711", "日月光投控", "TW", "半導體"),
    ("3034", "聯詠", "TW", "半導體"), ("2379", "瑞昱", "TW", "半導體"),
    ("2408", "南亞科", "TW", "半導體"), ("2344", "華邦電", "TW", "半導體"),
    ("2317", "鴻海", "TW", "電子代工"), ("2382", "廣達", "TW", "電子代工"),
    ("3231", "緯創", "TW", "電子代工"), ("2356", "英業達", "TW", "電子代工"),
    ("2324", "仁寶", "TW", "電子代工"), ("6669", "緯穎", "TW", "AI伺服器"),
    ("2376", "技嘉", "TW", "電腦週邊"), ("2357", "華碩", "TW", "電腦週邊"),
    ("2308", "台達電", "TW", "電子零組件"), ("2301", "光寶科", "TW", "電子零組件"),
    ("2327", "國巨", "TW", "電子零組件"), ("3017", "奇鋐", "TW", "散熱"),
    ("3324", "雙鴻", "TWO", "散熱"), ("2368", "金像電", "TW", "PCB"),
    ("2383", "台光電", "TW", "PCB"), ("3037", "欣興", "TW", "PCB"),
    ("2345", "智邦", "TW", "網通"), ("3008", "大立光", "TW", "光電"),
    ("3481", "群創", "TW", "光電"), ("2409", "友達", "TW", "光電"),
    ("2881", "富邦金", "TW", "金融"), ("2882", "國泰金", "TW", "金融"),
    ("2891", "中信金", "TW", "金融"), ("2603", "長榮", "TW", "航運"),
    ("2609", "陽明", "TW", "航運"), ("2615", "萬海", "TW", "航運"),
    ("2618", "長榮航", "TW", "航運"), ("2610", "華航", "TW", "航運"),
    ("1513", "中興電", "TW", "重電"), ("1519", "華城", "TW", "重電"),
    ("2002", "中鋼", "TW", "鋼鐵"), ("1301", "台塑", "TW", "塑化"),
    ("1216", "統一", "TW", "食品"), ("2912", "統一超", "TW", "貿易百貨"),
    ("8069", "元太", "TWO", "光電"), ("6488", "環球晶", "TWO", "半導體"),
    ("5347", "世界", "TWO", "半導體"), ("3293", "鈊象", "TWO", "文創遊戲"),
    ("5274", "信驊", "TWO", "半導體"), ("3529", "力旺", "TWO", "半導體"),
    ("5351", "鈺創", "TWO", "半導體"), ("1815", "富喬", "TWO", "PCB"),
    ("8299", "群聯", "TWO", "半導體"), ("5483", "中美晶", "TWO", "半導體"),
]
