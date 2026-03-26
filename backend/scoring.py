"""
Scoring engine - 4 independent ranked lists.
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
    put_call_ratio:             Optional[float] = None
    call_put_ratio:             Optional[float] = None
    atm_oi:                     int = 0
    oi_data_available:          bool = True
    unusual_activity:           bool = False
    unusual_strikes:            List = field(default_factory=list)
    call_oi_skewed_at_res:      bool = False


def _passes_gates(d: StockData, p: Dict) -> bool:
    min_atm_oi = int(p.get("min_atm_oi", 500))
    if d.oi_data_available and d.atm_oi < min_atm_oi:
        return False
    return True


def score_long_call(d: StockData, p: Dict) -> Optional[float]:
    if not _passes_gates(d, p):
        return None

    rsi_max = float(p.get("lc_rsi_max", 35))
    ivr_max = float(p.get("lc_ivr_max", 35))
    pc_ratio_min = float(p.get("lc_pc_ratio_min", 1.2))

    if d.weekly_rsi is None or d.weekly_rsi >= rsi_max:
        return None
    if d.iv_rank is None or d.iv_rank >= ivr_max:
        return None
    if d.support is None:
        return None
    if d.trend.get("above_200ma") is False:
        return None

    score = 0.0
    score += ((rsi_max - d.weekly_rsi) / rsi_max * 100) * 0.20
    score += ((ivr_max - d.iv_rank) / ivr_max * 100) * 0.20

    sr = (1 - d.support["distance_pct"] / 2.0) * 80
    sr += min(d.support["touches"] * 5, 15)
    if d.wick_rejection_support:
        sr += 5
    score += min(sr, 100) * 0.20

    flow = 0
    if d.unusual_activity:
        flow += 60
    if d.put_call_ratio is not None and d.put_call_ratio > pc_ratio_min:
        flow += 40
    score += min(flow, 100) * 0.40

    if d.trend.get("volume_tapering_on_down_days"):
        score += 3

    return round(score, 1)


def score_short_call(d: StockData, p: Dict) -> Optional[float]:
    if not _passes_gates(d, p):
        return None

    rsi_min = float(p.get("sc_rsi_min", 70))
    ivr_min = float(p.get("sc_ivr_min", 70))

    if d.weekly_rsi is None or d.weekly_rsi <= rsi_min:
        return None
    if d.iv_rank is None or d.iv_rank <= ivr_min:
        return None
    if d.resistance is None:
        return None

    score = 0.0
    rsi_range = max(100 - rsi_min, 1)
    score += ((d.weekly_rsi - rsi_min) / rsi_range * 100) * 0.20

    ivr_range = max(100 - ivr_min, 1)
    score += ((d.iv_rank - ivr_min) / ivr_range * 100) * 0.20

    sr = (1 - d.resistance["distance_pct"] / 2.0) * 60
    sr += min(d.resistance["touches"] * 5, 20)
    if d.wick_rejection_resistance:
        sr += 10
    if d.call_oi_skewed_at_res:
        sr += 10
    score += min(sr, 100) * 0.20

    flow = 0
    if d.unusual_activity:
        flow += 50
    if d.call_put_ratio is not None and d.call_put_ratio > 1.5:
        flow += 50
    score += min(flow, 100) * 0.40

    if not d.trend.get("above_20ma", True):
        score += 3
    if d.trend.get("recently_crossed_below_20ma"):
        score += 3
    if d.trend.get("volume_declining_on_up_days"):
        score += 2

    return round(score, 1)


def score_long_put(d: StockData, p: Dict) -> Optional[float]:
    if not _passes_gates(d, p):
        return None

    rsi_min = float(p.get("lp_rsi_min", 70))
    ivr_max = float(p.get("lp_ivr_max", 35))
    cp_ratio_min = float(p.get("lp_cp_ratio_min", 1.5))

    if d.weekly_rsi is None or d.weekly_rsi <= rsi_min:
        return None
    if d.iv_rank is None or d.iv_rank >= ivr_max:
        return None
    if d.resistance is None:
        return None
    if d.trend.get("above_50ma") is True:
        return None

    score = 0.0
    rsi_range = max(100 - rsi_min, 1)
    score += ((d.weekly_rsi - rsi_min) / rsi_range * 100) * 0.20
    score += ((ivr_max - d.iv_rank) / ivr_max * 100) * 0.20

    sr = (1 - d.resistance["distance_pct"] / 2.0) * 80
    sr += min(d.resistance["touches"] * 5, 15)
    if d.wick_rejection_resistance:
        sr += 5
    score += min(sr, 100) * 0.20

    flow = 0
    if d.unusual_activity:
        flow += 50
    if d.call_put_ratio is not None and d.call_put_ratio > cp_ratio_min:
        flow += 50
    score += min(flow, 100) * 0.40

    return round(score, 1)


def score_short_put(d: StockData, p: Dict) -> Optional[float]:
    if not _passes_gates(d, p):
        return None

    rsi_max = float(p.get("sp_rsi_max", 35))
    ivr_min = float(p.get("sp_ivr_min", 70))

    if d.weekly_rsi is None or d.weekly_rsi >= rsi_max:
        return None
    if d.iv_rank is None or d.iv_rank <= ivr_min:
        return None
    if d.support is None:
        return None
    if d.trend.get("above_200ma") is False:
        return None

    score = 0.0
    score += ((rsi_max - d.weekly_rsi) / rsi_max * 100) * 0.20

    ivr_range = max(100 - ivr_min, 1)
    score += ((d.iv_rank - ivr_min) / ivr_range * 100) * 0.20

    sr = (1 - d.support["distance_pct"] / 2.0) * 50
    sr += min(d.support["touches"] * 8, 30)
    if d.wick_rejection_support:
        sr += 10
    score += min(sr, 100) * 0.20

    flow = 0
    if d.unusual_activity:
        flow += 60
    if d.put_call_ratio is not None and d.put_call_ratio > 1.5:
        flow += 40
    score += min(flow, 100) * 0.40

    return round(score, 1)


def _rank(
    stocks: List[StockData],
    score_fn,
    p: Dict,
    top_n: int = 10,
) -> List[Dict]:
    scored = [(score_fn(s, p), s) for s in stocks]
    scored = [(sc, s) for sc, s in scored if sc is not None]
    scored.sort(key=lambda x: x[0], reverse=True)
    out = []
    for rank, (sc, s) in enumerate(scored[:top_n], start=1):
        out.append({
            "rank": rank,
            "ticker": s.ticker,
            "name": s.name,
            "price": s.price,
            "change_pct": s.change_pct,
            "score": sc,
            "weekly_rsi": s.weekly_rsi,
            "iv_rank": s.iv_rank,
            "support": s.support,
            "resistance": s.resistance,
            "unusual_activity": s.unusual_activity,
            "unusual_strikes": s.unusual_strikes,
            "put_call_ratio": s.put_call_ratio,
            "call_put_ratio": s.call_put_ratio,
            "above_200ma": s.trend.get("above_200ma"),
            "above_50ma": s.trend.get("above_50ma"),
            "above_20ma": s.trend.get("above_20ma"),
            "wick_rejection": s.wick_rejection_support or s.wick_rejection_resistance,
        })
    return out


def build_all_lists(
    stocks: List[StockData],
    params: Optional[Dict] = None,
) -> Dict:
    p = params or {}
    return {
        "long_calls": _rank(stocks, score_long_call, p),
        "short_calls": _rank(stocks, score_short_call, p),
        "long_puts": _rank(stocks, score_long_put, p),
        "short_puts": _rank(stocks, score_short_put, p),
        "scanned": len(stocks),
    }
