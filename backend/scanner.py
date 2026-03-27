"""
Main scanner orchestrator.
Fetches data for every ticker in the universe, scores them, returns 4 ranked lists.
User-configurable params are passed through to polygon_client and scoring functions.
"""

import asyncio
import inspect
import aiohttp
import logging
import os
from typing import Optional, List, Dict
from datetime import datetime

from polygon_client import (
    get_daily_bars, get_weekly_bars, get_options_chain,
    get_iv_rank, get_options_liquidity, get_ticker_name,
)
from technical import (
    calculate_rsi, get_trend,
    get_nearest_support, get_nearest_resistance,
    has_wick_rejection, detect_unusual_activity,
    call_oi_skewed_at_resistance,
)
from scoring import StockData, build_all_lists
from universe import get_universe

logger = logging.getLogger(__name__)

BATCH_SIZE = 8
BATCH_DELAY = 1.5

SCAN_DEFAULTS: Dict = {
    "dte_min": 30,
    "dte_max": 90,
    "min_atm_oi": 500,
    "sr_min_touches": 2,
    "sr_lookback_days": 30,
    "sr_proximity_pct": 2.0,
    "lc_rsi_max": 35,
    "lc_ivr_max": 35,
    "lc_pc_ratio_min": 1.2,
    "sc_rsi_min": 70,
    "sc_ivr_min": 70,
    "lp_rsi_min": 70,
    "lp_ivr_max": 35,
    "lp_cp_ratio_min": 1.5,
    "sp_rsi_max": 35,
    "sp_ivr_min": 70,
}


async def process_ticker(
    session: aiohttp.ClientSession,
    ticker: str,
    p: Dict,
) -> Optional[StockData]:
    """Fetch and process a single ticker using the provided params."""
    try:
        daily_bars, weekly_bars, name = await asyncio.gather(
            get_daily_bars(session, ticker, days=365),
            get_weekly_bars(session, ticker, weeks=52),
            get_ticker_name(session, ticker),
        )

        if not daily_bars or len(daily_bars) < 30:
            logger.debug(f"{ticker}: insufficient daily bars ({len(daily_bars) if daily_bars else 0})")
            return None

        current_price = daily_bars[-1]["c"]
        if not current_price or current_price <= 0:
            return None

        prev_close = daily_bars[-2]["c"] if len(daily_bars) >= 2 else current_price
        change_pct = round((current_price - prev_close) / prev_close * 100, 2)

        dte_min = int(p["dte_min"])
        dte_max = int(p["dte_max"])

        chain, ivr, liquidity = await asyncio.gather(
            get_options_chain(session, ticker, dte_min=dte_min, dte_max=dte_max),
            get_iv_rank(session, ticker, current_price, dte_min=dte_min, dte_max=dte_max),
            get_options_liquidity(session, ticker, current_price, dte_min=dte_min, dte_max=dte_max),
        )

        weekly_rsi = calculate_rsi(weekly_bars, 14)
        daily_rsi = calculate_rsi(daily_bars, 14)
        trend = get_trend(daily_bars)

        support = get_nearest_support(
            daily_bars,
            current_price,
            proximity_pct=float(p["sr_proximity_pct"]),
            min_touches=int(p["sr_min_touches"]),
            lookback_days=int(p["sr_lookback_days"]),
        )
        resistance = get_nearest_resistance(
            daily_bars,
            current_price,
            proximity_pct=float(p["sr_proximity_pct"]),
            min_touches=int(p["sr_min_touches"]),
            lookback_days=int(p["sr_lookback_days"]),
        )

        wick_sup = has_wick_rejection(daily_bars, support["price"]) if support else False
        wick_res = has_wick_rejection(daily_bars, resistance["price"]) if resistance else False

        unusual = detect_unusual_activity(chain)
        call_skewed = call_oi_skewed_at_resistance(chain, resistance["price"]) if resistance else False

        return StockData(
            ticker=ticker,
            name=name,
            price=current_price,
            change_pct=change_pct,
            weekly_rsi=weekly_rsi,
            daily_rsi=daily_rsi,
            trend=trend,
            support=support,
            resistance=resistance,
            wick_rejection_support=wick_sup,
            wick_rejection_resistance=wick_res,
            iv_rank=ivr,
            put_call_ratio=unusual.get("put_call_ratio"),
            call_put_ratio=unusual.get("call_put_ratio"),
            atm_oi=liquidity.get("atm_oi", 0),
            oi_data_available=liquidity.get("oi_data_available", False),
            unusual_activity=unusual.get("unusual", False),
            unusual_strikes=unusual.get("unusual_strikes", []),
            call_oi_skewed_at_res=call_skewed,
        )
    except Exception as e:
        logger.warning(f"Failed to process {ticker}: {e}")
        return None


async def run_scan(
    tickers: Optional[List[str]] = None,
    params: Optional[Dict] = None,
    progress_cb=None,
) -> Dict:
    """Run the full scan using the provided params."""
    if tickers is None:
        tickers = get_universe()

    if not os.getenv("POLYGON_API_KEY"):
        raise RuntimeError(
            "POLYGON_API_KEY is not set. Create backend/.env from .env.example "
            "or set the environment variable before running scans."
        )

    p = {**SCAN_DEFAULTS, **(params or {})}

    async def emit_progress(payload: Dict) -> None:
        if progress_cb is None:
            return
        result = progress_cb(payload)
        if inspect.isawaitable(result):
            await result

    logger.info(
        f"Scan started - {len(tickers)} tickers, "
        f"DTE {p['dte_min']}-{p['dte_max']}, "
        f"SR proximity {p['sr_proximity_pct']}%"
    )
    await emit_progress({
        "phase": "scan",
        "percent": 0,
        "processed": 0,
        "total": len(tickers),
        "valid": 0,
        "message": f"Starting scan on {len(tickers)} tickers",
    })

    results: List[StockData] = []

    async with aiohttp.ClientSession() as session:
        for i in range(0, len(tickers), BATCH_SIZE):
            batch = tickers[i:i + BATCH_SIZE]
            batch_results = await asyncio.gather(
                *[process_ticker(session, t, p) for t in batch],
                return_exceptions=True,
            )
            for r in batch_results:
                if isinstance(r, StockData):
                    results.append(r)
                elif isinstance(r, Exception):
                    logger.warning(f"Batch exception: {r}")

            pct = min(100, round((i + BATCH_SIZE) / len(tickers) * 100))
            logger.info(f"Progress {pct}% - {len(results)} valid so far")
            await emit_progress({
                "phase": "scan",
                "percent": pct,
                "processed": min(i + BATCH_SIZE, len(tickers)),
                "total": len(tickers),
                "valid": len(results),
                "message": f"Progress {pct}% - {len(results)} valid so far",
            })

            if i + BATCH_SIZE < len(tickers):
                await asyncio.sleep(BATCH_DELAY)

    logger.info(f"Scan complete - {len(results)} tickers processed")
    await emit_progress({
        "phase": "scan",
        "percent": 100,
        "processed": len(tickers),
        "total": len(tickers),
        "valid": len(results),
        "message": f"Scan complete - {len(results)} valid stocks",
    })

    output = build_all_lists(results, params=p)
    output["diagnostics"] = {
        "processed_stocks": len(results),
        "support_found": sum(1 for s in results if s.support is not None),
        "resistance_found": sum(1 for s in results if s.resistance is not None),
        "iv_rank_available": sum(1 for s in results if s.iv_rank is not None),
        "oi_data_available": sum(1 for s in results if s.oi_data_available),
        "unusual_activity_found": sum(1 for s in results if s.unusual_activity),
    }
    output["scan_time"] = datetime.utcnow().isoformat() + "Z"
    output["universe_size"] = len(tickers)
    output["params_used"] = {k: p[k] for k in SCAN_DEFAULTS}
    return output


if __name__ == "__main__":
    import json

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    result = asyncio.run(run_scan())
    print(json.dumps(result, indent=2, default=str))
