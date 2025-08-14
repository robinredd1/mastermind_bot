# ====== key_check.py ======
# Quick sanity check for your Alpaca PAPER keys and data access.
import httpx
from config import API_KEY, API_SECRET, BROKER_BASE_URL, DATA_BASE_URL

HEADERS = {
    "APCA-API-KEY-ID": API_KEY,
    "APCA-API-SECRET-KEY": API_SECRET,
}

with httpx.Client() as client:
    r = client.get(f"{BROKER_BASE_URL}/v2/account", headers=HEADERS, timeout=15.0)
    print("Account status:", r.status_code, r.text[:500])

    r2 = client.get(f"{DATA_BASE_URL}/v2/stocks/snapshots", params={"symbols": "AAPL,TSLA,NVDA"}, headers=HEADERS, timeout=15.0)
    print("Data status:", r2.status_code, r2.text[:200])
