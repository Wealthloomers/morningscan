"""
Technical analysis calculations from OHLCV bar data.
Pure functions — no API calls, just math on lists of bar dicts.
Each bar dict uses Polygon format: {o, h, l, c, v, t}
Compatible with Python 3.9+.
"""

from typing import Optional, List, Dict


# ── RSI ───────────────────────────────────────────────────────────────────────

def calculate_rsi(bars: List[Dict], period: int = 14) -> Optional[float]:
    if len(bars) < period + 1:
        return None
    closes = [b["c"] for b in bars]
    gains, losses = [], []
    for i in range(1, len(closes)):
        delta = closes[i] - closes[i - 1]
        gains.append(max(delta, 0.0))
        losses.append(max(-delta, 0.0))

    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period

    for i in range(period, len(gains)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period

    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return round(100 - (100 / (1 + rs)), 2)


# ── Moving averages ───────────────────────────────────────────────────────────

def sma(bars: List[Dict], period: int) -> Optional[float]:
    if len(bars) < period:
        return None
    return round(sum(b["c"] for b in bars[-period:]) / period, 4)


def ema(bars: List[Dict], period: int) -> Optional[float]:
    if len(bars) < period:
        return None
    closes = [b["c"] for b in bars]
    k = 2 / (period + 1)
    val = sum(closes[:period]) / period
    for price in closes[period:]:
        val = price * k + val * (1 - k)
    return round(val, 4)


# ── Support / Resistance ──────────────────────────────────────────────────────

def find_pivot_highs(bars: List[Dict], window: int = 5) -> List[Dict]:
    pivots = []
    for i in range(window, len(bars) - window):
        high = bars[i]["h"]
        if high > max(bars[j]["h"] for j in range(i - window, i)) \
           and high > max(bars[j]["h"] for j in range(i + 1, i + window + 1)):
            pivots.append({"price": high, "index": i, "t": bars[i]["t"]})
    return pivots


def find_pivot_lows(bars: List[Dict], window: int = 5) -> List[Dict]:
    pivots = []
    for i in range(window, len(bars) - window):
        low = bars[i]["l"]
        if low < min(bars[j]["l"] for j in range(i - window, i)) \
           and low < min(bars[j]["l"] for j in range(i + 1, i + window + 1)):
            pivots.append({"price": low, "index": i, "t": bars[i]["t"]})
    return pivots


def cluster_levels(pivots: List[Dict], tolerance_pct: float = 0.5) -> List[Dict]:
    """Group nearby pivot points into S/R levels."""
    if not pivots:
        return []
    sorted_pivots = sorted(pivots, key=lambda x: x["price"])
    clusters = [[sorted_pivots[0]]]

    for pivot in sorted_pivots[1:]:
        ref = clusters[-1][0]["price"]
        if abs(pivot["price"] - ref) / ref * 100 <= tolerance_pct:
            clusters[-1].append(pivot)
        else:
            clusters.append([pivot])

    result = []
    for cluster in clusters:
        prices = [p["price"] for p in cluster]
        timestamps = [p["t"] for p in cluster]
        result.append({
            "price": round(sum(prices) / len(prices), 4),
            "touches": len(cluster),
            "last_touch_t": max(timestamps),
        })
    return result


def get_nearest_support(
    bars: List[Dict],
    current_price: float,
    proximity_pct: float = 2.0,
    min_touches: int = 2,
    lookback_days: int = 30,
) -> Optional[Dict]:
    if not bars:
        return None
    pivots = find_pivot_lows(bars)
    levels = cluster_levels(pivots)
    now_ms = bars[-1]["t"]
    cutoff_ms = now_ms - lookback_days * 24 * 3600 * 1000

    candidates = []
    for lvl in levels:
        if lvl["price"] >= current_price:
            continue
        dist_pct = (current_price - lvl["price"]) / current_price * 100
        if dist_pct > proximity_pct:
            continue
        if lvl["touches"] < min_touches:
            continue
        if lvl["last_touch_t"] < cutoff_ms:
            continue
        candidates.append({**lvl, "distance_pct": round(dist_pct, 2)})

    return min(candidates, key=lambda x: x["distance_pct"]) if candidates else None


def get_nearest_resistance(
    bars: List[Dict],
    current_price: float,
    proximity_pct: float = 2.0,
    min_touches: int = 2,
    lookback_days: int = 30,
) -> Optional[Dict]:
    if not bars:
        return None
    pivots = find_pivot_highs(bars)
    levels = cluster_levels(pivots)
    now_ms = bars[-1]["t"]
    cutoff_ms = now_ms - lookback_days * 24 * 3600 * 1000

    candidates = []
    for lvl in levels:
        if lvl["price"] <= current_price:
            continue
        dist_pct = (lvl["price"] - current_price) / current_price * 100
        if dist_pct > proximity_pct:
            continue
        if lvl["touches"] < min_touches:
            continue
        if lvl["last_touch_t"] < cutoff_ms:
            continue
        candidates.append({**lvl, "distance_pct": round(dist_pct, 2)})

    return min(candidates, key=lambda x: x["distance_pct"]) if candidates else None


def has_wick_rejection(
    bars: List[Dict],
    level_price: float,
    tolerance_pct: float = 0.5,
    lookback: int = 10,
) -> bool:
    """True if a candle touched the level with a wick but closed away from it."""
    for bar in bars[-lookback:]:
        near = (
            abs(bar["h"] - level_price) / level_price * 100 < tolerance_pct
            or abs(bar["l"] - level_price) / level_price * 100 < tolerance_pct
        )
        if near:
            body_away = abs(bar["c"] - level_price) / level_price * 100 > tolerance_pct
            if body_away:
                return True
    return False


# ── Trend ─────────────────────────────────────────────────────────────────────

def get_trend(bars: List[Dict]) -> Dict:
    ma200 = sma(bars, 200)
    ma50  = sma(bars, 50)
    ma20  = sma(bars, 20)
    current = bars[-1]["c"] if bars else 0

    recent = bars[-10:] if len(bars) >= 10 else bars
    down_vols = [b["v"] for b in recent if b["c"] < b["o"]]
    up_vols   = [b["v"] for b in recent if b["c"] > b["o"]]
    vol_avg_20 = sum(b["v"] for b in bars[-20:]) / 20 if len(bars) >= 20 else 1

    avg_down = sum(down_vols) / len(down_vols) if down_vols else 0
    avg_up   = sum(up_vols)   / len(up_vols)   if up_vols   else 0

    recently_crossed_below = False
    if ma20 and len(bars) >= 4:
        recently_crossed_below = bars[-4]["c"] > ma20 and bars[-1]["c"] < ma20

    return {
        "above_200ma":                  (current > ma200) if ma200 else None,
        "above_50ma":                   (current > ma50)  if ma50  else None,
        "above_20ma":                   (current > ma20)  if ma20  else None,
        "recently_crossed_below_20ma":  recently_crossed_below,
        "volume_tapering_on_down_days": avg_down < vol_avg_20 * 0.8 if avg_down > 0 else False,
        "volume_declining_on_up_days":  avg_up   < vol_avg_20 * 0.8 if avg_up   > 0 else False,
        "ma200": ma200,
        "ma50":  ma50,
        "ma20":  ma20,
    }


# ── Unusual options activity ──────────────────────────────────────────────────

def detect_unusual_activity(chain: List[Dict]) -> Dict:
    """Volume/OI > 3 on any strike = unusual."""
    unusual_strikes = []
    call_vol = put_vol = 0

    for opt in chain:
        details  = opt.get("details") or {}
        day      = opt.get("day")     or {}
        vol      = day.get("volume", 0) or 0
        oi       = opt.get("open_interest", 0) or 0
        ctype    = details.get("contract_type")
        strike   = details.get("strike_price")

        if ctype == "call":
            call_vol += vol
        elif ctype == "put":
            put_vol += vol

        if oi > 100 and vol > 0 and vol / oi > 3:
            unusual_strikes.append({
                "strike": strike,
                "type":   ctype,
                "vol":    vol,
                "oi":     oi,
                "ratio":  round(vol / oi, 1),
            })

    pc_ratio = round(put_vol / call_vol, 2) if call_vol > 0 else None
    cp_ratio = round(call_vol / put_vol, 2) if put_vol  > 0 else None

    return {
        "unusual":         len(unusual_strikes) > 0,
        "unusual_strikes": unusual_strikes[:5],
        "put_call_ratio":  pc_ratio,
        "call_put_ratio":  cp_ratio,
        "call_vol":        call_vol,
        "put_vol":         put_vol,
    }


def call_oi_skewed_at_resistance(
    chain: List[Dict],
    resistance_price: float,
    tolerance_pct: float = 2.0,
) -> bool:
    call_oi = put_oi = 0
    for opt in chain:
        details = opt.get("details") or {}
        strike  = details.get("strike_price", 0)
        if not strike or not resistance_price:
            continue
        if abs(strike - resistance_price) / resistance_price * 100 > tolerance_pct:
            continue
        oi = opt.get("open_interest", 0) or 0
        if details.get("contract_type") == "call":
            call_oi += oi
        elif details.get("contract_type") == "put":
            put_oi += oi

    if put_oi == 0:
        return call_oi > 0
    return call_oi / put_oi > 1.5
