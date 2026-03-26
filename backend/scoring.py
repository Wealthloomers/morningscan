"""
Scoring engine — 4 independent ranked lists.
All filter thresholds read from the params dict passed by the scanner,
which in turn comes from the user's browser parameter settings.
Hardcoded defaults are used only as fallback when params is None.
Compatible with Python 3.9+.
"""

from dataclasses import dataclass, field
from typing import Optional, List, Dict


@dataclass
class StockData:
    ticker:                     str
    name:                       str
    price:                      float
    change_pct:                 float
    weekly_rsi:                 Optional[float]
    daily_rsi:                  Optional[float]
    trend:                      Dict
    support:                    Optional[Dict]
    resistance:                 Optional[Dict]
    wick_rejection_support:     bool = False
    wick_rejection_resistance:  bool = False
    iv_rank:                    Optional[float] = None
    iv_pct:                     Optional[float] = None
    spread_pct:                 Optional[float] = None
    quote_data_available:       bool = True
    put_call_ratio:             Optional[float] = None
    call_put_ratio:             Optional[float] = None
    atm_oi:                     int   = 0
    oi_data_available:          bool  = True
    daily_options_vol_usd:      float = 0.0
    unusual_activity:           bool  = False
    unusual_strikes:            List  = field(default_factory=list)
    call_oi_skewed_at_res:      bool  = False
    implied_move_pct:           Optional[float] = None
    days_to_earnings:           Optional[int]   = None


# ── Global gates (thresholds from params) ─────────────────────────────────────

def _passes_gates(d: StockData, p: Dict) -> bool:
    spread_max         = float(p.get("spread_max",          10.0))
    min_atm_oi         = int(p.get("min_atm_oi",            500))
    min_options_vol    = float(p.get("min_options_vol_usd",  500_000))

    if d.quote_data_available and (d.spread_pct is None or d.spread_pct >= spread_max):
        return False
    if d.oi_data_available and d.atm_oi < min_atm_oi:
        return False
    if d.daily_options_vol_usd < min_options_vol:
        return False
    return True


# ── List 1 — Long Calls ───────────────────────────────────────────────────────

def score_long_call(d: StockData, p: Dict) -> Optional[float]:
    if not _passes_gates(d, p):
        return None

    rsi_max          = float(p.get("lc_rsi_max",           35))
    ivr_max          = float(p.get("lc_ivr_max",           35))
    catalyst_min     = int(p.get("lc_catalyst_min_days",   5))
    catalyst_max     = int(p.get("lc_catalyst_max_days",   21))
    pc_ratio_min     = float(p.get("lc_pc_ratio_min",      1.2))

    if d.weekly_rsi is None or d.weekly_rsi >= rsi_max:
        return None
    if d.iv_rank is None or d.iv_rank >= ivr_max:
        return None
    if d.support is None:
        return None
    if d.trend.get("above_200ma") is False:
        return None

    score = 0.0

    # RSI — 20%
    score += ((rsi_max - d.weekly_rsi) / rsi_max * 100) * 0.20

    # IV — 20%
    score += ((ivr_max - d.iv_rank) / ivr_max * 100) * 0.20

    # S/R — 20%
    sr = (1 - d.support["distance_pct"] / 2.0) * 80
    sr += min(d.support["touches"] * 5, 15)
    if d.wick_rejection_support:
        sr += 5
    score += min(sr, 100) * 0.20

    # Spread — 15%
    spread_max = float(p.get("spread_max", 10.0))
    score += ((spread_max - d.spread_pct) / spread_max * 100) * 0.15

    # Catalyst — 15%
    cat = 0
    if d.days_to_earnings is not None:
        if catalyst_min <= d.days_to_earnings <= catalyst_max:
            cat = 100
        elif d.days_to_earnings <= catalyst_max + 9:
            cat = 40
    score += cat * 0.15

    # Flow — 10%
    flow = 0
    if d.unusual_activity:
        flow += 60
    if d.put_call_ratio is not None and d.put_call_ratio > pc_ratio_min:
        flow += 40
    score += min(flow, 100) * 0.10

    # Bonus points (not weighted)
    if d.trend.get("volume_tapering_on_down_days"):
        score += 3

    return round(score, 1)


# ── List 2 — Short Calls ──────────────────────────────────────────────────────

def score_short_call(d: StockData, p: Dict) -> Optional[float]:
    if not _passes_gates(d, p):
        return None

    rsi_min      = float(p.get("sc_rsi_min",            70))
    ivr_min      = float(p.get("sc_ivr_min",            70))
    blackout     = int(p.get("earnings_blackout_days",   21))

    if d.weekly_rsi is None or d.weekly_rsi <= rsi_min:
        return None
    if d.iv_rank is None or d.iv_rank <= ivr_min:
        return None
    if d.resistance is None:
        return None
    if d.days_to_earnings is not None and d.days_to_earnings <= blackout:
        return None

    score = 0.0

    # RSI — 20%
    rsi_range = max(100 - rsi_min, 1)
    score += ((d.weekly_rsi - rsi_min) / rsi_range * 100) * 0.20

    # IV — 20%
    ivr_range = max(100 - ivr_min, 1)
    score += ((d.iv_rank - ivr_min) / ivr_range * 100) * 0.20

    # S/R — 20%
    sr = (1 - d.resistance["distance_pct"] / 2.0) * 60
    sr += min(d.resistance["touches"] * 5, 20)
    if d.wick_rejection_resistance:
        sr += 10
    if d.call_oi_skewed_at_res:
        sr += 10
    score += min(sr, 100) * 0.20

    # Spread — 15%
    spread_max = float(p.get("spread_max", 10.0))
    score += ((spread_max - d.spread_pct) / spread_max * 100) * 0.15

    # Caution (earnings proximity) — 10%
    caution = 100
    if d.days_to_earnings is not None and d.days_to_earnings <= blackout + 14:
        caution = 30
    score += caution * 0.10

    # Flow — 15%
    flow = 0
    if d.unusual_activity:
        flow += 50
    if d.call_put_ratio is not None and d.call_put_ratio > 1.5:
        flow += 50
    score += min(flow, 100) * 0.15

    # Bonus points (not weighted)
    if not d.trend.get("above_20ma", True):
        score += 3
    if d.trend.get("recently_crossed_below_20ma"):
        score += 3
    if d.trend.get("volume_declining_on_up_days"):
        score += 2

    return round(score, 1)


# ── List 3 — Long Puts ────────────────────────────────────────────────────────

def score_long_put(d: StockData, p: Dict) -> Optional[float]:
    if not _passes_gates(d, p):
        return None

    rsi_min          = float(p.get("lp_rsi_min",           70))
    ivr_max          = float(p.get("lp_ivr_max",           35))
    cp_ratio_min     = float(p.get("lp_cp_ratio_min",      1.5))
    catalyst_min     = int(p.get("lp_catalyst_min_days",   5))
    catalyst_max     = int(p.get("lp_catalyst_max_days",   21))

    if d.weekly_rsi is None or d.weekly_rsi <= rsi_min:
        return None
    if d.iv_rank is None or d.iv_rank >= ivr_max:
        return None
    if d.resistance is None:
        return None
    if d.trend.get("above_50ma") is True:
        return None

    score = 0.0

    # RSI — 20%
    rsi_range = max(100 - rsi_min, 1)
    score += ((d.weekly_rsi - rsi_min) / rsi_range * 100) * 0.20

    # IV — 20%
    score += ((ivr_max - d.iv_rank) / ivr_max * 100) * 0.20

    # S/R — 20%
    sr = (1 - d.resistance["distance_pct"] / 2.0) * 80
    sr += min(d.resistance["touches"] * 5, 15)
    if d.wick_rejection_resistance:
        sr += 5
    score += min(sr, 100) * 0.20

    # Spread — 15%
    spread_max = float(p.get("spread_max", 10.0))
    score += ((spread_max - d.spread_pct) / spread_max * 100) * 0.15

    # Catalyst — 15%
    cat = 0
    if d.days_to_earnings is not None:
        if catalyst_min <= d.days_to_earnings <= catalyst_max:
            cat = 100
        elif d.days_to_earnings <= catalyst_max + 9:
            cat = 40
    score += cat * 0.15

    # Flow — 10%
    flow = 0
    if d.unusual_activity:
        flow += 50
    if d.call_put_ratio is not None and d.call_put_ratio > cp_ratio_min:
        flow += 50
    score += min(flow, 100) * 0.10

    return round(score, 1)


# ── List 4 — Short Puts ───────────────────────────────────────────────────────

def score_short_put(d: StockData, p: Dict) -> Optional[float]:
    if not _passes_gates(d, p):
        return None

    rsi_max      = float(p.get("sp_rsi_max",            35))
    ivr_min      = float(p.get("sp_ivr_min",            70))
    blackout     = int(p.get("earnings_blackout_days",   21))

    if d.weekly_rsi is None or d.weekly_rsi >= rsi_max:
        return None
    if d.iv_rank is None or d.iv_rank <= ivr_min:
        return None
    if d.support is None:
        return None
    if d.trend.get("above_200ma") is False:
        return None
    if d.days_to_earnings is not None and d.days_to_earnings <= blackout:
        return None
    if (d.implied_move_pct is not None
            and d.implied_move_pct > d.support["distance_pct"]):
        return None

    score = 0.0

    # RSI — 20%
    score += ((rsi_max - d.weekly_rsi) / rsi_max * 100) * 0.20

    # IV — 20%
    ivr_range = max(100 - ivr_min, 1)
    score += ((d.iv_rank - ivr_min) / ivr_range * 100) * 0.20

    # S/R — 20%
    sr = (1 - d.support["distance_pct"] / 2.0) * 50
    sr += min(d.support["touches"] * 8, 30)
    if d.wick_rejection_support:
        sr += 10
    if d.implied_move_pct is not None:
        buf = d.support["distance_pct"] - d.implied_move_pct
        if buf > 0:
            sr += min(buf * 5, 10)
    score += min(sr, 100) * 0.20

    # Spread — 15%
    spread_max = float(p.get("spread_max", 10.0))
    score += ((spread_max - d.spread_pct) / spread_max * 100) * 0.15

    # Caution (earnings proximity) — 5%
    caution = 100
    if d.days_to_earnings is not None and d.days_to_earnings <= blackout + 14:
        caution = 20
    score += caution * 0.05

    # Flow — 20%
    flow = 0
    if d.unusual_activity:
        flow += 60
    if d.put_call_ratio is not None and d.put_call_ratio > 1.5:
        flow += 40
    score += min(flow, 100) * 0.20

    return round(score, 1)


# ── Rank and build output ─────────────────────────────────────────────────────

def _rank(
    stocks:   List[StockData],
    score_fn,
    p:        Dict,
    top_n:    int = 10,
) -> List[Dict]:
    scored = [(score_fn(s, p), s) for s in stocks]
    scored = [(sc, s) for sc, s in scored if sc is not None]
    scored.sort(key=lambda x: x[0], reverse=True)
    out = []
    for rank, (sc, s) in enumerate(scored[:top_n], start=1):
        out.append({
            "rank":             rank,
            "ticker":           s.ticker,
            "name":             s.name,
            "price":            s.price,
            "change_pct":       s.change_pct,
            "score":            sc,
            "weekly_rsi":       s.weekly_rsi,
            "iv_rank":          s.iv_rank,
            "spread_pct":       s.spread_pct,
            "support":          s.support,
            "resistance":       s.resistance,
            "days_to_earnings": s.days_to_earnings,
            "unusual_activity": s.unusual_activity,
            "unusual_strikes":  s.unusual_strikes,
            "put_call_ratio":   s.put_call_ratio,
            "call_put_ratio":   s.call_put_ratio,
            "implied_move_pct": s.implied_move_pct,
            "above_200ma":      s.trend.get("above_200ma"),
            "above_50ma":       s.trend.get("above_50ma"),
            "above_20ma":       s.trend.get("above_20ma"),
            "wick_rejection":   s.wick_rejection_support or s.wick_rejection_resistance,
        })
    return out


def build_all_lists(
    stocks: List[StockData],
    params: Optional[Dict] = None,
) -> Dict:
    p = params or {}
    return {
        "long_calls":  _rank(stocks, score_long_call,  p),
        "short_calls": _rank(stocks, score_short_call, p),
        "long_puts":   _rank(stocks, score_long_put,   p),
        "short_puts":  _rank(stocks, score_short_put,  p),
        "scanned":     len(stocks),
    }
