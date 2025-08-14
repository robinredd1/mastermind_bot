# ====== config.py ======
# Alpaca PAPER trading credentials (provided by user)
API_KEY = "PKXB8N50RX1YLX2N39AE"
API_SECRET = "3IGZrOtdWnuOCNGOVAYfGTCaccZh7h0tPDmNvFHq"

# Trade + scan settings
SCAN_INTERVAL_SECONDS = 5            # how often to scan
SCAN_BATCH_SIZE = 150                # how many tickers per API call (snapshots supports batches)
UNIVERSE_FILE = "symbols_150.txt"    # list of symbols to rotate through

# Signal thresholds (made less strict so it actually trades)
MIN_PCT_UP_FROM_PREV_CLOSE = 0.8     # % up vs previous close to consider momentum
MIN_MINUTE_VOLUME = 2000             # recent minute volume threshold
MIN_PRICE = 1.0                      # min price
MAX_PRICE = 2000.0                   # max price

# Risk / position sizing
DOLLARS_PER_TRADE = 75               # fixed dollars per entry
MAX_OPEN_POSITIONS = 5               # allow multiple positions

# Order params
USE_EXTENDED_HOURS = True            # allow pre/after market for limit orders
LIMIT_SLIPPAGE_BPS = 15              # limit buy at last trade * (1 + 0.0015) for momentum entries

# Exit: trailing stop once filled
TRAIL_PERCENT = 3.0                  # trailing stop %
BROKER_BASE_URL = "https://paper-api.alpaca.markets"
DATA_BASE_URL = "https://data.alpaca.markets"
