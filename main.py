import yfinance as yf
import pandas as pd
import numpy as np
import requests
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo
import os
import time as t_time
import sys
import json
import re
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# -----------------------------
# CONFIGURATION
# -----------------------------
FINNHUB_API_KEY = os.getenv("FINNHUB_API_KEY")
POLYGON_API_KEY = os.getenv("POLYGON_API_KEY")

USE_FINNHUB = True
USE_POLYGON = False  # keep false unless you want Polygon volume fallback

TICKERS = [
    'ONDS','UMAC', 'RCAT','DFTX','KTOS',
    'VST','RKLB', 'PLTR', 'CEG', 
    'ISRG',
    'WFRD',
    'SPY',
    'VXX',
    'IEF',
    'UUP'
]

INVERSE_MACRO = ['VXX', 'UUP']

REFRESH_RATE_SECONDS = 30
HISTORY_REFRESH_CYCLES = 10

session = requests.Session()
session.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
})

class MarketDataCache:
    def __init__(self):
        self.history = {}
        self.technicals = {}
        self.prices = {}
        self.gaps = {}
        self.vwaps = {}
        self.volumes = {}
        self.session = {}
        self.session_liquidity = {}
        self.pre_market_change = {}
        self.after_hours_change = {}
        self.overnight_return = {}
        self.pre_market_price = {}
        self.after_hours_price = {}
        self.cycles = 0
        self.vwap_pointer = 0

    def clear(self):
        self.__init__()

cache = MarketDataCache()
app = FastAPI()

# -----------------------------
# UTILS
# -----------------------------
def get_market_status():
    ny_now = datetime.now(ZoneInfo("America/New_York"))
    t = ny_now.time()
    if ny_now.weekday() >= 5:
        return "CLOSED"
    if time(4, 0) <= t < time(9, 30):
        return "PRE-MARKET"
    if time(9, 30) <= t < time(16, 0):
        return "OPEN"
    if time(16, 0) <= t < time(20, 0):
        return "AFTER-HOURS"
    return "CLOSED"

def to_float(val):
    try:
        if isinstance(val, (pd.Series, pd.DataFrame)):
            return float(val.iloc[-1])
        return float(val)
    except:
        return 0.0

# -----------------------------
# FETCHERS
# -----------------------------
def get_live_chart_data(symbol, status):
    try:
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?range=1d&interval=1m&includePrePost=true"
        r = session.get(url, timeout=2)
        data = r.json()
        result = data['chart']['result'][0]
        timestamps = result['timestamp']
        quote = result['indicators']['quote'][0]
        closes = quote.get('close', [])
        volumes = quote.get('volume', [])

        live_price = 0.0
        if closes:
            valid_closes = [c for c in closes if c is not None]
            if valid_closes:
                live_price = float(valid_closes[-1])

        total_vol = 0
        ny_tz = ZoneInfo("America/New_York")
        now = datetime.now(ny_tz)
        cutoff_ts = 0

        if status == "OPEN":
            cutoff_dt = now.replace(hour=9, minute=30, second=0, microsecond=0)
            cutoff_ts = cutoff_dt.timestamp()
        elif status == "AFTER-HOURS":
            cutoff_dt = now.replace(hour=16, minute=0, second=0, microsecond=0)
            cutoff_ts = cutoff_dt.timestamp()

        if volumes and timestamps:
            for ts, v in zip(timestamps, volumes):
                if v is None:
                    continue
                if ts >= cutoff_ts:
                    total_vol += v

        return live_price, total_vol
    except:
        return 0.0, 0

def get_true_intraday_vwap(symbol, status):
    try:
        ny_tz = ZoneInfo("America/New_York")
        now = datetime.now(ny_tz)

        if status == "PRE-MARKET":
            anchor_time = now.replace(hour=4, minute=0, second=0, microsecond=0)
            include_pre = "true"
        else:
            anchor_time = now.replace(hour=9, minute=30, second=0, microsecond=0)
            include_pre = "false"

        if now < anchor_time:
            return 0.0

        ts_open = int(anchor_time.timestamp())
        ts_now = int(now.timestamp())

        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?period1={ts_open}&period2={ts_now}&interval=1m&includePrePost={include_pre}"
        r = session.get(url, timeout=3)
        data = r.json()
        result = data['chart']['result'][0]
        indicators = result['indicators']['quote'][0]
        closes = indicators.get('close', [])
        volumes = indicators.get('volume', [])

        valid = [(c, v) for c, v in zip(closes, volumes) if c is not None and v is not None and v > 0]
        if not valid:
            return 0.0

        total_vp = sum(c * v for c, v in valid)
        total_v = sum(v for _, v in valid)
        if total_v > 0:
            return total_vp / total_v
        return 0.0
    except:
        return 0.0

def fallback_vwap(symbol):
    try:
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?range=1d&interval=1m"
        r = session.get(url, timeout=2)
        data = r.json()
        result = data['chart']['result'][0]
        q = result['indicators']['quote'][0]
        closes = q.get('close', [])
        volumes = q.get('volume', [])
        vp = 0.0
        tv = 0.0
        for c, v in zip(closes, volumes):
            if c is None or v is None or v <= 0:
                continue
            vp += c * v
            tv += v
        if tv > 0:
            return vp / tv
        return 0.0
    except:
        return 0.0

def get_finnhub_quote(symbol):
    if not USE_FINNHUB:
        return None, None
    try:
        url = f"https://finnhub.io/api/v1/quote?symbol={symbol}&token={FINNHUB_API_KEY}"
        r = session.get(url, timeout=2)
        if r.status_code != 200:
            return None, None
        data = r.json()
        c = float(data.get('c', 0))
        pc = float(data.get('pc', 0))
        if c > 0:
            return c, pc
    except:
        pass
    return None, None

def get_polygon_history_df(symbol):
    if not USE_POLYGON:
        return pd.DataFrame()
    end_dt = datetime.now().strftime('%Y-%m-%d')
    start_dt = (datetime.now() - timedelta(days=70)).strftime('%Y-%m-%d')
    url = f"https://api.polygon.io/v2/aggs/ticker/{symbol}/range/1/day/{start_dt}/{end_dt}?adjusted=true&sort=asc&apiKey={POLYGON_API_KEY}"
    try:
        t_time.sleep(15)
        r = session.get(url, timeout=5)
        if r.status_code == 200:
            data = r.json()
            if data.get('resultsCount', 0) > 0:
                results = data['results']
                df = pd.DataFrame(results)
                df['Date'] = pd.to_datetime(df['t'], unit='ms')
                df.set_index('Date', inplace=True)
                df.rename(columns={'c': 'Close', 'h': 'High', 'l': 'Low', 'o': 'Open', 'v': 'Volume'}, inplace=True)
                return df[['Open', 'High', 'Low', 'Close', 'Volume']]
    except:
        pass
    return pd.DataFrame()

def polygon_volume(symbol):
    if not USE_POLYGON:
        return None
    try:
        url = f"https://api.polygon.io/v2/aggs/ticker/{symbol}/prev?adjusted=true&apiKey={POLYGON_API_KEY}"
        r = session.get(url, timeout=2)
        if r.status_code == 200:
            data = r.json()
            if data.get('resultsCount', 0) > 0:
                return data['results'][0].get('v', None)
    except:
        pass
    return None

def get_previous_close(symbol):
    try:
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?range=5d&interval=1d"
        r = session.get(url, timeout=2)
        data = r.json()
        result = data['chart']['result'][0]
        q = result['indicators']['quote'][0]
        closes = q.get('close', [])
        valid = [c for c in closes if c is not None]
        if len(valid) >= 2:
            return float(valid[-2])
    except:
        pass
    return None

def get_batch_quotes(symbols):
    try:
        syms = ",".join(symbols)
        url = f"https://query1.finance.yahoo.com/v7/finance/quote?symbols={syms}"
        r = session.get(url, timeout=3)
        data = r.json()
        return {q['symbol']: q for q in data['quoteResponse']['result']}
    except:
        return {}

# -----------------------------
# LOGIC (UPDATED)
# -----------------------------

def update_history_and_technicals(symbol, t_obj):
    try:
        hist = t_obj.history(period="3mo", interval="1d")
        if hist.empty:
            hist = t_obj.history(period="1mo", interval="1d")
        if hist.empty:
            hist = t_obj.history(period="5d", interval="1d")
        if hist.empty:
            raise ValueError("Empty YF")
    except:
        hist = get_polygon_history_df(symbol)

    cache.history[symbol] = hist

    if not hist.empty:
        try:
            close = hist['Close']

            # --- SAFER SMA CHECKS ---
            sma_20 = to_float(close.rolling(20).mean().iloc[-1]) if len(close) >= 20 else None
            sma_50 = to_float(close.rolling(50).mean().iloc[-1]) if len(close) >= 50 else None
            sma_200 = to_float(close.rolling(200).mean().iloc[-1]) if len(close) >= 200 else None

            # --- RSI (Wilder) ---
            delta = close.diff()
            gain = (delta.where(delta > 0, 0)).ewm(com=13, adjust=False).mean()
            loss = (-delta.where(delta < 0, 0)).ewm(com=13, adjust=False).mean()
            rs = gain / (loss + 1e-9)
            rsi_val = (100 - (100 / (1 + rs))).iloc[-1]

            # --- ATR (Wilder) ---
            tr = pd.concat([
                hist['High'] - hist['Low'],
                (hist['High'] - close.shift(1)).abs(),
                (hist['Low'] - close.shift(1)).abs()
            ], axis=1).max(axis=1)

            atr = tr.ewm(alpha=1/14, adjust=False).mean().iloc[-1]
            atr_pct = (atr / close.iloc[-1]) * 100

            # --- Previous Regular Close ---
            last_reg_close = 0.0
            if hasattr(t_obj, 'fast_info'):
                try:
                    last_reg_close = float(t_obj.fast_info.previous_close)
                except:
                    pass

            if last_reg_close == 0.0 and len(close) >= 2:
                last_reg_close = to_float(close.iloc[-2])

            if last_reg_close == 0.0:
                alt_pc = get_previous_close(symbol)
                if alt_pc:
                    last_reg_close = alt_pc

            # --- Trend Score (Improved) ---
            trend_score = 0
            if sma_20 is not None and sma_50 is not None:
                trend_score += 1 if sma_20 > sma_50 else -1
            if sma_50 is not None and sma_200 is not None:
                trend_score += 1 if sma_50 > sma_200 else -1
            if sma_20 is not None:
                trend_score += 1 if close.iloc[-1] > sma_20 else -1

            cache.technicals[symbol] = {
                "SMA_20": sma_20,
                "SMA_50": sma_50,
                "SMA_200": sma_200,
                "RSI": to_float(rsi_val),
                "ATR_Pct": to_float(atr_pct),
                "ATR": to_float(atr),
                "Trend_Score": int(trend_score),
                "Last_Reg_Close": last_reg_close
            }

        except Exception as e:
            # This should be logged properly in a real app
            print("Tech error:", e)
            pass


def update_price_tick(symbol, t_obj, status, quote_data=None):
    price = 0.0
    vol = 0
    used_batch = False

    # --- SESSION TAG ---
    cache.session[symbol] = status

    # --- SESSION LIQUIDITY ---
    cache.session_liquidity[symbol] = (
        "LOW" if status in ("AFTER-HOURS", "PRE-MARKET") else "HIGH"
    )

    # --- Extract session prices ---
    pre_price = None
    post_price = None
    reg_price = None

    if quote_data:
        try:
            pre_price = quote_data.get('preMarketPrice')
            post_price = quote_data.get('postMarketPrice')
            reg_price = quote_data.get('regularMarketPrice')
            vol = int(quote_data.get('regularMarketVolume', 0) or 0)
            used_batch = True
        except:
            pass

    # --- Session-aware price selection ---
    if status == "PRE-MARKET" and pre_price:
        price = float(pre_price)
    elif status == "AFTER-HOURS" and post_price:
        price = float(post_price)
    elif reg_price:
        price = float(reg_price)

    # --- Fallbacks ---
    if price == 0:
        api_price, api_vol = get_live_chart_data(symbol, status)
        if api_price > 0:
            price = api_price
        if api_vol > 0:
            vol = api_vol

    if price == 0 and USE_FINNHUB:
        fh_c, fh_pc = get_finnhub_quote(symbol)
        if fh_c:
            price = fh_c

    # --- Final fallback to fast_info ---
    try:
        fi = t_obj.fast_info
        if vol == 0:
            vol = fi.last_volume or fi.three_month_average_volume
        if price == 0:
            if status == "PRE-MARKET" and getattr(fi, 'pre_market_price', None):
                price = float(fi.pre_market_price)
            elif status == "AFTER-HOURS" and getattr(fi, 'post_market_price', None):
                price = float(fi.post_market_price)
            elif getattr(fi, 'last_price', None):
                price = float(fi.last_price)
    except:
        pass

    # --- Volume fallback ---
    if vol == 0:
        alt_vol = polygon_volume(symbol)
        if alt_vol:
            vol = alt_vol

    # --- Cache updates ---
    if vol > 0:
        cache.volumes[symbol] = vol

    if price > 0:
        cache.prices[symbol] = price

        if status == "PRE-MARKET" and (pre_price is None or pre_price == 0):
            pre_price = price
        elif status == "AFTER-HOURS" and (post_price is None or post_price == 0):
            post_price = price

        techs = cache.technicals.get(symbol, {})
        reg_close = techs.get("Last_Reg_Close", 0.0)

        # --- Session-aware returns ---
        if reg_close > 0:
            cache.gaps[symbol] = ((price - reg_close) / reg_close) * 100

        if pre_price is not None:
            cache.pre_market_price[symbol] = pre_price
            if reg_close > 0:
                cache.pre_market_change[symbol] = ((pre_price - reg_close) / reg_close) * 100

        if post_price is not None:
            cache.after_hours_price[symbol] = post_price
            if reg_close > 0:
                cache.after_hours_change[symbol] = ((post_price - reg_close) / reg_close) * 100

        # --- Overnight return (non-compounded) ---
        if pre_price is not None and post_price is not None and post_price > 0:
            cache.overnight_return[symbol] = ((pre_price - post_price) / post_price) * 100


def calculate_rvol(symbol):
    hist = cache.history.get(symbol)
    if hist is None or hist.empty or 'Volume' not in hist.columns:
        return 1.0

    avg_vol = hist['Volume'].tail(20).mean()
    cur_vol = cache.volumes.get(symbol, 0)

    if avg_vol == 0:
        return 1.0

    return cur_vol / avg_vol


def distance_from_vwap(symbol):
    p = cache.prices.get(symbol, 0)
    v = cache.vwaps.get(symbol, 0)

    if p == 0 or v == 0:
        return 0.0

    return ((p - v) / v) * 100.0


def classify_signal(symbol):
    t = cache.technicals.get(symbol, {})
    rsi = t.get("RSI", 50)
    atr = t.get("ATR_Pct", 0)
    rvol = calculate_rvol(symbol)
    dist_vwap = distance_from_vwap(symbol)

    if rvol > 2 and dist_vwap > atr:
        return "BREAKOUT"
    if rvol > 2 and dist_vwap < -atr:
        return "BREAKDOWN"
    if rsi < 30:
        return "OVERSOLD"
    if rsi > 70:
        return "OVERBOUGHT"
    if abs(dist_vwap) < 0.2:
        return "VWAP PIN"
    return "NEUTRAL"


def calculate_score(symbol):
    t = cache.technicals.get(symbol, {})
    p = cache.prices.get(symbol, 0)
    v = cache.vwaps.get(symbol, 0)

    if p == 0 or not t:
        return 0, ""

    score = 0
    note = ""

    # -----------------------------
    # 1. TREND SCORE (single use)
    # -----------------------------
    trend_component = t.get("Trend_Score", 0)
    score += trend_component

    # -----------------------------
    # 2. RSI COMPONENT
    # -----------------------------
    rsi = t.get("RSI", 50)
    if rsi > 60:
        score += 1
    elif rsi < 40:
        score -= 1

    # -----------------------------
    # 3. VWAP COMPONENT (fixed)
    # -----------------------------
    if v > 0:
        dist = distance_from_vwap(symbol)      # % distance
        atr = t.get("ATR_Pct", 0)              # ATR%

        if dist > 0:
            score += 1
        else:
            # Always penalize price < VWAP
            score -= 1

            # HV BREAK: stronger penalty
            if abs(dist) > atr * 0.25:
                score -= 1
                note = "(HV BREAK)"

    # -----------------------------
    # 4. RVOL COMPONENT
    # -----------------------------
    rvol = calculate_rvol(symbol)
    if rvol > 2:
        score += 1
    elif rvol < 0.5:
        score -= 1

    # -----------------------------
    # 5. INVERSE MACRO (apply last)
    # -----------------------------
    return score, note

# -----------------------------
# API Endpoints
# -----------------------------

@app.get("/data")
def get_data():
    ny_now = datetime.now(ZoneInfo("America/New_York"))
    status = get_market_status()
    
    tickers_obj = {sym: yf.Ticker(sym) for sym in TICKERS}

    for sym, obj in tickers_obj.items():
        update_history_and_technicals(sym, obj)

    batch_quotes = get_batch_quotes(TICKERS)
    
    for sym in TICKERS:
        v_true = get_true_intraday_vwap(sym, status)
        if v_true == 0.0:
            v_true = fallback_vwap(sym)
        if v_true > 0:
            cache.vwaps[sym] = v_true
            
    for sym, obj in tickers_obj.items():
        update_price_tick(sym, obj, status, batch_quotes.get(sym))

    data = []
    for sym in TICKERS:
        p = cache.prices.get(sym, 0)
        gap = cache.gaps.get(sym, 0)
        vol = cache.volumes.get(sym, 0)
        vwap = cache.vwaps.get(sym, 0)
        techs = cache.technicals.get(sym, {})
        score, note = calculate_score(sym)
        ts = techs.get("Trend_Score", 0)

        data.append({
            "ticker": sym,
            "session": cache.session.get(sym),
            "session_liquidity": cache.session_liquidity.get(sym),
            "price": float(p),
            "regular_close": float(techs.get("Last_Reg_Close", 0.0)),
            "pre_market_price": float(cache.pre_market_price.get(sym, 0)),
            "after_hours_price": float(cache.after_hours_price.get(sym, 0)),
            "gap_percent": float(gap),
            "pre_market_change_percent": float(cache.pre_market_change.get(sym, 0)),
            "after_hours_change_percent": float(cache.after_hours_change.get(sym, 0)),
            "overnight_return_percent": float(cache.overnight_return.get(sym, 0)),
            "volume": int(vol),
            "rvol": float(calculate_rvol(sym)),
            "atr_percent": float(techs.get("ATR_Pct", 0)),
            "atr": float(techs.get("ATR", 0)),
            "rsi": float(techs.get("RSI", 0)),
            "vwap": float(vwap),
            "distance_from_vwap": float(distance_from_vwap(sym)),
            "trend_score": int(ts),
            "score": int(score),
            "signal": classify_signal(sym),
            "trend": "UP" if ts >= 2 else "DOWN" if ts <= -2 else "FLAT",
            "note": note.strip()
        })

    # Create summary
    summary_data = {}
    for item in data:
        if item['ticker'] == 'IEF': # Bond Yields
            summary_data['bond_yields'] = {
                "status": "FALLING" if item['gap_percent'] < 0 else "RISING",
                "tag": "YIELDS FALLING" if item['gap_percent'] < 0 else "YIELDS RISING",
                "value": f"IEF: {item['price']:.2f} ({item['gap_percent']:+.2f}%)"
            }
        elif item['ticker'] == 'UUP': # US Dollar
            summary_data['us_dollar'] = {
                "value": f"{item['price']:.2f}",
                "tag": "DOLLAR STRONG" if item['gap_percent'] > 0 else "DOLLAR WEAK"
            }
        elif item['ticker'] == 'VXX': # Market Fear
            summary_data['market_fear'] = {
                "status": "RISK ON" if item['gap_percent'] < 0 else "RISK OFF",
                "tag": "FEAR RISING" if item['gap_percent'] > 0 else "FEAR FALLING",
                "value": f"VXX: {item['price']:.2f} ({item['gap_percent']:+.2f}%)"
            }

    final_output = {
        "timestamp": datetime.now(ZoneInfo("America/New_York")).strftime('%Y-%m-%d %H:%M:%S'),
        "status": status,
        "tickers": data,
        "summary": summary_data
    }
    return final_output

@app.post("/symbols")
def update_symbols(new_tickers: list[str]):
    global TICKERS
    TICKERS = new_tickers
    cache.clear()
    return {"message": "Symbols updated successfully. Cache cleared."}

@app.post("/cache/reset")
def reset_cache():
    cache.clear()
    return {"message": "Cache cleared successfully."}

app.mount("/", StaticFiles(directory="public", html=True), name="static")

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
