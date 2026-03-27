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


def _count_true(stocks: List[StockData], predicate) -> int:
    return sum(1 for s in stocks if predicate(s))


def build_rsi_diagnostics(stocks: List[StockData]) -> Dict:
    weekly = [(s.ticker, s.weekly_rsi) for s in stocks if s.weekly_rsi is not None]
    daily = [(s.ticker, s.daily_rsi) for s in stocks if s.daily_rsi is not None]

    weekly_values = sorted(val for _, val in weekly)
    daily_values = sorted(val for _, val in daily)

    def _median(values: List[float]) -> Optional[float]:
        if not values:
            return None
        mid = len(values) // 2
        if len(values) % 2:
            return round(values[mid], 1)
        return round((values[mid - 1] + values[mid]) / 2, 1)

    def _examples(pairs: List, reverse: bool = False) -> List[Dict]:
        ordered = sorted(pairs, key=lambda x: x[1], reverse=reverse)[:5]
        return [{"ticker": ticker, "rsi": round(value, 1)} for ticker, value in ordered]

    return {
        "weekly_rsi_available": len(weekly),
        "weekly_rsi_min": round(weekly_values[0], 1) if weekly_values else None,
        "weekly_rsi_median": _median(weekly_values),
        "weekly_rsi_max": round(weekly_values[-1], 1) if weekly_values else None,
        "weekly_rsi_low_examples": _examples(weekly, reverse=False),
        "weekly_rsi_high_examples": _examples(weekly, reverse=True),
        "daily_rsi_available": len(daily),
        "daily_rsi_min": round(daily_values[0], 1) if daily_values else None,
        "daily_rsi_median": _median(daily_values),
        "daily_rsi_max": round(daily_values[-1], 1) if daily_values else None,
    }


def build_strategy_diagnostics(
    stocks: List[StockData],
    params: Optional[Dict] = None,
) -> Dict:
    p = params or {}

    lc_rsi_max = float(p.get("lc_rsi_max", 35))
    lc_ivr_max = float(p.get("lc_ivr_max", 35))

    sc_rsi_min = float(p.get("sc_rsi_min", 70))
    sc_ivr_min = float(p.get("sc_ivr_min", 70))

    lp_rsi_min = float(p.get("lp_rsi_min", 70))
    lp_ivr_max = float(p.get("lp_ivr_max", 35))

    sp_rsi_max = float(p.get("sp_rsi_max", 35))
    sp_ivr_min = float(p.get("sp_ivr_min", 70))

    return {
        "long_calls": {
            "global_gate_pass": _count_true(stocks, lambda s: _passes_gates(s, p)),
            "rsi_pass": _count_true(stocks, lambda s: s.weekly_rsi is not None and s.weekly_rsi < lc_rsi_max),
            "ivr_pass": _count_true(stocks, lambda s: s.iv_rank is not None and s.iv_rank < lc_ivr_max),
            "support_pass": _count_true(stocks, lambda s: s.support is not None),
            "trend_pass": _count_true(stocks, lambda s: s.trend.get("above_200ma") is not False),
            "final_pass": _count_true(stocks, lambda s: score_long_call(s, p) is not None),
        },
        "short_calls": {
            "global_gate_pass": _count_true(stocks, lambda s: _passes_gates(s, p)),
            "rsi_pass": _count_true(stocks, lambda s: s.weekly_rsi is not None and s.weekly_rsi > sc_rsi_min),
            "ivr_pass": _count_true(stocks, lambda s: s.iv_rank is not None and s.iv_rank > sc_ivr_min),
            "resistance_pass": _count_true(stocks, lambda s: s.resistance is not None),
            "final_pass": _count_true(stocks, lambda s: score_short_call(s, p) is not None),
        },
        "long_puts": {
            "global_gate_pass": _count_true(stocks, lambda s: _passes_gates(s, p)),
            "rsi_pass": _count_true(stocks, lambda s: s.weekly_rsi is not None and s.weekly_rsi > lp_rsi_min),
            "ivr_pass": _count_true(stocks, lambda s: s.iv_rank is not None and s.iv_rank < lp_ivr_max),
            "resistance_pass": _count_true(stocks, lambda s: s.resistance is not None),
            "trend_pass": _count_true(stocks, lambda s: s.trend.get("above_50ma") is not True),
            "final_pass": _count_true(stocks, lambda s: score_long_put(s, p) is not None),
        },
        "short_puts": {
            "global_gate_pass": _count_true(stocks, lambda s: _passes_gates(s, p)),
            "rsi_pass": _count_true(stocks, lambda s: s.weekly_rsi is not None and s.weekly_rsi < sp_rsi_max),
            "ivr_pass": _count_true(stocks, lambda s: s.iv_rank is not None and s.iv_rank > sp_ivr_min),
            "support_pass": _count_true(stocks, lambda s: s.support is not None),
            "trend_pass": _count_true(stocks, lambda s: s.trend.get("above_200ma") is not False),
            "final_pass": _count_true(stocks, lambda s: score_short_put(s, p) is not None),
        },
    }


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
        "strategy_diagnostics": build_strategy_diagnostics(stocks, p),
        "rsi_diagnostics": build_rsi_diagnostics(stocks),
        "scanned": len(stocks),
    }
