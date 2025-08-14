# Mastermind Bot — Batch 150 Momentum Scalper (Alpaca PAPER)

**What changed vs. your strict bot:**
- Scans **150 tickers at once** using Alpaca's multi-symbol **snapshots** endpoint (1 request per batch).
- **Looser signals** so it actually finds trades (momentum up from previous close + green last minute + minimal volume floor).
- Uses **limit buys** (extended hours enabled) and auto-attaches **trailing stops** after fills.
- Rotates through your 150-symbol universe every 5 seconds by default.

## Files
- `bot.py` — main loop, scanning & trading logic
- `config.py` — keys and settings (edit thresholds here)
- `.replit` — runs `python bot.py` by default
- `requirements.txt` — Python deps (no heavy SDKs, uses raw HTTP)
- `key_check.py` — quick credentials & data endpoint test
- `symbols_150.txt` — 150 common liquid tickers (edit as you like)

## Quick Start (Replit)
1. Create a new Repl (Python).
2. Upload this ZIP and extract; or just upload the files directly.
3. Open **Shell** and run:
   ```bash
   pip install -r requirements.txt
   python key_check.py
   python bot.py
   ```
   (In Replit, the **Run** button will run `python bot.py` automatically.)

## Tuning
All in `config.py`:
- `SCAN_BATCH_SIZE = 150` — keep at 150 to avoid rate-limit spam while scaling up scans.
- `SCAN_INTERVAL_SECONDS = 5` — faster scans = more CPU; keep ≥ 3–5s.
- `MIN_PCT_UP_FROM_PREV_CLOSE` — lower this if it's still too picky.
- `MIN_MINUTE_VOLUME` — lower for low-float runners; raise to avoid illiquid.
- `DOLLARS_PER_TRADE` — position size per entry (fractional shares).
- `MAX_OPEN_POSITIONS` — how many symbols to hold at once.
- `TRAIL_PERCENT` — trailing stop; e.g., 3.0 means give it 3% room.
- `USE_EXTENDED_HOURS = True` — trades in pre/after hours with limit orders.

## Notes
- This bot polls REST endpoints; it avoids streaming/websockets to stay simple and stable on Replit.
- **Rate limits**: using the batch snapshots endpoint drastically cuts requests. If you still see 429s, increase `SCAN_INTERVAL_SECONDS` a bit.
- **Live trading**: This is PAPER-only by default. Switching to live is your responsibility.
- **You are responsible for all risk.** Test, tweak thresholds, and monitor behavior.
