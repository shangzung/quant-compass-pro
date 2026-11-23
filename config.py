"""
Quant Compass Pro v2.0 (Web Edition)
Configuration & Strategy Parameters
"""

STRATEGY_VERSION = "v2.0.0-web-rs-ranked"
TIMEZONE = "Asia/Taipei"

# Capital & Portfolio Constraints
INITIAL_CAPITAL = 1_000_000.0  # TWD
MAX_POSITIONS = 5
MAX_RISK_PER_TRADE_PCT = 0.01  # 1% of current equity
MAX_SINGLE_POSITION_PCT = 0.20  # 20% of total equity
MIN_CASH_RESERVE_PCT = 0.02     # 2% cash reserve

# Strategy Parameters (Phase 1 Core + RS Ranking)
MA_SHORT = 20
MA_LONG = 60
RSI_PERIOD = 14
RSI_MIN = 45.0
RSI_MAX = 72.0
ATR_PERIOD = 14
VOL_MA_PERIOD = 20
MIN_AVG_VOLUME_SHARES = 500_000  # >= 500 lots avg daily volume
MIN_PRICE = 15.0                 # Exclude low-priced penny stocks

# Risk / Reward & Execution Rules
STOP_LOSS_ATR_MULT = 2.0
TAKE_PROFIT_ATR_MULT = 3.0
MIN_RISK_REWARD_RATIO = 1.5
MAX_HOLDING_TRADING_DAYS = 20
MAX_OPEN_CHASE_PCT = 0.04
USE_MARKET_REGIME_FILTER = True  # Pause new BUYs if TAIEX Close < TAIEX MA20

# Taiwan Stock Transaction Cost Assumptions
BROKERAGE_FEE_RATE = 0.001425
BROKERAGE_DISCOUNT = 1.0         # 1.0 = standard rate (no discount)
MIN_BROKERAGE_FEE_LOT = 20.0
MIN_BROKERAGE_FEE_ODD = 1.0
SELL_TAX_RATE = 0.003
SLIPPAGE_RATE = 0.001

MIN_SAMPLE_SIZE_WARNING = 10
DB_PATH = "quant_compass_v2_ledger.db"

# Fallback / Core Liquid Taiwan Stock Universe (TWSE & TPEx)
DEFAULT_TW_UNIVERSE = [
    ("2330", "台積電", "TW"), ("2317", "鴻海", "TW"), ("2454", "聯發科", "TW"),
    ("2308", "台達電", "TW"), ("2303", "聯電", "TW"), ("2881", "富邦金", "TW"),
    ("2882", "國泰金", "TW"), ("2891", "中信金", "TW"), ("2603", "長榮", "TW"),
    ("2609", "陽明", "TW"), ("2615", "萬海", "TW"), ("3231", "緯創", "TW"),
    ("2382", "廣達", "TW"), ("2376", "技嘉", "TW"), ("2357", "華碩", "TW"),
    ("3008", "大立光", "TW"), ("3034", "聯詠", "TW"), ("2379", "瑞昱", "TW"),
    ("2327", "國巨", "TW"), ("2301", "光寶科", "TW"), ("2345", "智邦", "TW"),
    ("3017", "奇鋐", "TW"), ("2368", "金像電", "TW"), ("3711", "日月光投控", "TW"),
    ("2408", "南亞科", "TW"), ("3481", "群創", "TW"), ("2409", "友達", "TW"),
    ("2002", "中鋼", "TW"), ("1301", "台塑", "TW"), ("1303", "南亞", "TW"),
    ("1216", "統一", "TW"), ("2912", "統一超", "TW"), ("2618", "長榮航", "TW"),
    ("2610", "華航", "TW"), ("1513", "中興電", "TW"), ("1519", "華城", "TW"),
    ("2356", "英業達", "TW"), ("2324", "仁寶", "TW"), ("2353", "宏碁", "TW"),
    ("2344", "華邦電", "TW"), ("2337", "旺宏", "TW"), ("3037", "欣興", "TW"),
    ("3189", "景碩", "TW"), ("8046", "南電", "TW"), ("2313", "華通", "TW"),
    ("2383", "台光電", "TW"), ("6669", "緯穎", "TW"), ("3661", "世芯-KY", "TW"),
    ("3443", "創意", "TW"), ("2359", "所羅門", "TW"), ("2049", "上銀", "TW"),
    ("8069", "元太", "TWO"), ("6488", "環球晶", "TWO"), ("5347", "世界", "TWO"),
    ("3293", "鈊象", "TWO"), ("5274", "信驊", "TWO"), ("3529", "力旺", "TWO"),
    ("5351", "鈺創", "TWO"), ("1815", "富喬", "TWO"), ("3324", "雙鴻", "TWO"),
    ("8299", "群聯", "TWO"), ("6147", "頎邦", "TWO"), ("5483", "中美晶", "TWO"),
]
