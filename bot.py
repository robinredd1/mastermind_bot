# ====== bot.py ======
import time, math, os, sys, json, itertools
from datetime import datetime, timezone
import httpx
from tenacity import retry, wait_exponential, stop_after_attempt
from typing import List, Dict, Any, Tuple

from config import (
    API_KEY, API_SECRET, SCAN_INTERVAL_SECONDS, SCAN_BATCH_SIZE, UNIVERSE_FILE,
    MIN_PCT_UP_FROM_PREV_CLOSE, MIN_MINUTE_VOLUME, MIN_PRICE, MAX_PRICE,
    DOLLARS_PER_TRADE, MAX_OPEN_POSITIONS, USE_EXTENDED_HOURS, LIMIT_SLIPPAGE_BPS,
    TRAIL_PERCENT, BROKER_BASE_URL, DATA_BASE_URL
)

HEADERS = {
    "APCA-API-KEY-ID": API_KEY,
    "APCA-API-SECRET-KEY": API_SECRET,
}

def load_universe(path: str) -> List[str]:
    if not os.path.exists(path):
        print(f"[WARN] Universe file {path} not found. Create symbols_150.txt with tickers (one per line).")
        return []
    with open(path, "r") as f:
        syms = [ln.strip().upper() for ln in f if ln.strip() and not ln.startswith("#")]
    return syms

def chunked(iterable, n):
    it = iter(iterable)
    while True:
        chunk = tuple(itertools.islice(it, n))
        if not chunk:
            return
        yield chunk

@retry(wait=wait_exponential(multiplier=0.5, min=0.5, max=8), stop=stop_after_attempt(5))
def get_snapshots(client: httpx.Client, symbols: List[str]) -> Dict[str, Any]:
    # Multi-symbol snapshots to avoid rate limits
    # API: GET /v2/stocks/snapshots?symbols=AAPL,TSLA,...
    url = f"{DATA_BASE_URL}/v2/stocks/snapshots"
    params = {"symbols": ",".join(symbols)}
    r = client.get(url, params=params, headers=HEADERS, timeout=20.0)
    if r.status_code == 429:
        raise httpx.HTTPStatusError("Rate limited", request=r.request, response=r)
    r.raise_for_status()
    data = r.json()
    # data: {"snapshots": {"AAPL": {...}, "TSLA": {...}}}
    return data.get("snapshots", {})

def get_account(client: httpx.Client) -> Dict[str, Any]:
    r = client.get(f"{BROKER_BASE_URL}/v2/account", headers=HEADERS, timeout=15.0)
    r.raise_for_status()
    return r.json()

def get_positions(client: httpx.Client) -> List[Dict[str, Any]]:
    r = client.get(f"{BROKER_BASE_URL}/v2/positions", headers=HEADERS, timeout=20.0)
    if r.status_code == 404:
        return []
    r.raise_for_status()
    return r.json()

def get_open_orders(client: httpx.Client) -> List[Dict[str, Any]]:
    r = client.get(f"{BROKER_BASE_URL}/v2/orders", headers=HEADERS, timeout=20.0, params={"status": "open"})
    r.raise_for_status()
    return r.json()

def submit_order(client: httpx.Client, symbol: str, qty: str, limit_price: float) -> Dict[str, Any]:
    payload = {
        "symbol": symbol,
        "qty": qty,
        "side": "buy",
        "type": "limit",
        "time_in_force": "day",
        "limit_price": round(limit_price, 4),
        "extended_hours": bool(USE_EXTENDED_HOURS),
    }
    r = client.post(f"{BROKER_BASE_URL}/v2/orders", headers=HEADERS, json=payload, timeout=20.0)
    if r.status_code == 422:
        print(f"[WARN] Order rejected for {symbol}: {r.text}")
    r.raise_for_status()
    return r.json()

def submit_trailing_stop(client: httpx.Client, symbol: str, qty: str, trail_percent: float) -> Dict[str, Any]:
    payload = {
        "symbol": symbol,
        "qty": qty,
        "side": "sell",
        "type": "trailing_stop",
        "time_in_force": "day",
        "trail_percent": round(float(trail_percent), 4),
        "extended_hours": bool(USE_EXTENDED_HOURS),
    }
    r = client.post(f"{BROKER_BASE_URL}/v2/orders", headers=HEADERS, json=payload, timeout=20.0)
    if r.status_code == 422:
        print(f"[WARN] Trailing stop rejected for {symbol}: {r.text}")
    r.raise_for_status()
    return r.json()

def dollars_to_qty(price: float, dollars: float) -> str:
    if price <= 0:
        return "0"
    # fractional shares supported on Alpaca
    qty = max(dollars / price, 0)
    return f"{qty:.4f}"

def signal_from_snapshot(snp: Dict[str, Any]) -> Tuple[bool, str, float]:
    # Returns (should_buy, reason, recommended_limit_price)
    if not snp:
        return (False, "no snapshot", 0.0)

    latest = snp.get("latestTrade") or {}
    last_price = latest.get("p")
    if not last_price:
        return (False, "no last trade", 0.0)

    prev = snp.get("prevDailyBar") or {}
    prev_close = prev.get("c")
    if not prev_close or prev_close <= 0:
        return (False, "no prev close", 0.0)

    minute = snp.get("minuteBar") or {}
    minute_o = minute.get("o")
    minute_c = minute.get("c")
    minute_v = minute.get("v", 0)

    if last_price < MIN_PRICE or last_price > MAX_PRICE:
        return (False, "price filter", 0.0)

    # Easier momentum gates
    pct_up = (last_price - prev_close) / prev_close * 100.0
    if pct_up < MIN_PCT_UP_FROM_PREV_CLOSE:
        return (False, f"pct_up {pct_up:.2f}% < {MIN_PCT_UP_FROM_PREV_CLOSE}%", 0.0)

    if minute and (minute_c is not None and minute_o is not None) and minute_c < minute_o:
        return (False, "red last minute", 0.0)

    if minute_v is not None and minute_v < MIN_MINUTE_VOLUME:
        return (False, f"minute vol {minute_v} < {MIN_MINUTE_VOLUME}", 0.0)

    # Buy at slight premium to chase momentum but cap with limit
    limit_price = last_price * (1.0 + LIMIT_SLIPPAGE_BPS / 10000.0)
    return (True, f"pct_up={pct_up:.2f}% vol={minute_v}", limit_price)

def ensure_trailing_stops(client: httpx.Client, trail_percent: float):
    # Ensure each open position has an associated trailing stop (simple check)
    open_orders = get_open_orders(client)
    has_sell = {o.get("symbol"): True for o in open_orders if o.get("side") == "sell"}
    positions = get_positions(client)
    for pos in positions:
        sym = pos.get("symbol")
        qty = pos.get("qty")
        # If there's no open sell order for this symbol, place a trailing stop
        if not has_sell.get(sym):
            try:
                submit_trailing_stop(client, sym, qty, trail_percent)
                print(f"[EXIT] Trailing stop submitted for {sym} at trail {trail_percent}% on qty {qty}")
            except Exception as e:
                print(f"[ERR] trailing stop submit {sym}: {e}")

def main():
    print("=== Momentum scalper (batch 150, less strict) ===")
    universe = load_universe(UNIVERSE_FILE)
    if not universe:
        print("[FATAL] No universe loaded. Create symbols_150.txt.")
        sys.exit(1)

    with httpx.Client() as client:
        acct = get_account(client)
        print(f"[ACCOUNT] {acct.get('account_number')} | Buying power: {acct.get('buying_power')} | Cash: {acct.get('cash')}")

        symbol_cycle = itertools.cycle(universe)
        while True:
            # limit number of concurrent positions
            try:
                open_positions = get_positions(client)
            except Exception as e:
                print(f"[WARN] get_positions failed: {e}")
                open_positions = []

            if len(open_positions) >= MAX_OPEN_POSITIONS:
                print(f"[INFO] Max positions {len(open_positions)}/{MAX_OPEN_POSITIONS}. Managing exits...")
                ensure_trailing_stops(client, TRAIL_PERCENT)
                time.sleep(SCAN_INTERVAL_SECONDS)
                continue

            # pull next SCAN_BATCH_SIZE symbols
            batch = list(itertools.islice(symbol_cycle, SCAN_BATCH_SIZE))
            try:
                snapshots = get_snapshots(client, batch)
            except Exception as e:
                print(f"[WARN] snapshot batch failed ({len(batch)} syms): {e}")
                time.sleep(1.0)
                continue

            # evaluate signals
            candidates = []
            for sym in batch:
                snp = snapshots.get(sym)
                ok, reason, limit_price = signal_from_snapshot(snp)
                if ok:
                    candidates.append((sym, reason, limit_price, snp))

            # prefer strongest % up move this minute (if present)
            def minute_gain(snp):
                m = snp.get("minuteBar") or {}
                o = m.get("o") or 0
                c = m.get("c") or 0
                return (c - o) / o * 100.0 if o else 0.0

            candidates.sort(key=lambda x: minute_gain(x[3]), reverse=True)

            # place up to available slots
            slots = max(MAX_OPEN_POSITIONS - len(open_positions), 0)
            for sym, reason, limit_price, snp in candidates[:slots]:
                latest = snp.get("latestTrade") or {}
                price = latest.get("p")
                if not price:
                    continue
                qty = dollars_to_qty(price, DOLLARS_PER_TRADE)
                try:
                    order = submit_order(client, sym, qty, limit_price)
                    oid = order.get("id")
                    print(f"[ENTRY] {sym} @ ~{limit_price:.4f} qty={qty} | {reason} | order_id={oid}")
                except Exception as e:
                    print(f"[ERR] submit_order {sym}: {e}")

            # manage exits (place trailing stops for any fills lacking one)
            try:
                ensure_trailing_stops(client, TRAIL_PERCENT)
            except Exception as e:
                print(f"[WARN] ensure_trailing_stops failed: {e}")

            time.sleep(SCAN_INTERVAL_SECONDS)

if __name__ == "__main__":
    main()
