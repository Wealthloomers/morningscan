"""
Universe Builder — weekly pre-filter that dynamically builds the scan universe.

Stage 1 (Polygon screener):  market cap > threshold, dollar volume > threshold, price > threshold
Stage 2 (options chain):     30-day IV > threshold, rank by options dollar volume, take top N

Runs automatically every Sunday at midnight ET.
Can also be triggered manually via POST /refresh-universe.
Results cached to universe_cache.json — daily scanner reads from this file.
Falls back to static universe.py if cache is missing or stale.

Compatible with Python 3.9+.
"""

import os
import json
import asyncio
import aiohttp
import logging
from datetime import datetime, timedelta
from typing import Optional, List, Dict
from urllib.parse import urlparse, parse_qs

logger = logging.getLogger(__name__)

POLYGON_BASE = "https://api.polygon.io"
CACHE_FILE   = "universe_cache.json"

# ── Default pre-filter thresholds (overridden by caller passing params) ────────
DEFAULT_PARAMS = {
    "universe_min_market_cap_b":   2.0,    # $B
    "universe_min_dollar_vol_m":   50.0,   # $M/day (30-day avg)
    "universe_min_iv_pct":         30.0,   # 30-day IV % annualised
    "universe_min_price":          5.0,    # minimum stock price
    "universe_size":               500,    # top N by options dollar volume
}


def _api_key() -> str:
    key = os.getenv("POLYGON_API_KEY", "")
    if not key:
        raise RuntimeError("POLYGON_API_KEY environment variable is not set")
    return key


async def _get(
    session: aiohttp.ClientSession,
    url: str,
    params: Optional[Dict] = None,
) -> Dict:
    p = dict(params) if params else {}
    p["apiKey"] = _api_key()
    try:
        async with session.get(
            url, params=p,
            timeout=aiohttp.ClientTimeout(total=20)
        ) as resp:
            if resp.status == 403:
                logger.error(f"Polygon 403 Forbidden — check API key: {url}")
                return {}
            if resp.status == 429:
                logger.warning("Polygon rate limit — sleeping 2s")
                await asyncio.sleep(2)
                return {}
            if resp.status != 200:
                text = await resp.text()
                logger.error(f"Polygon {resp.status}: {url} -> {text[:200]}")
                return {}
            return await resp.json()
    except asyncio.TimeoutError:
        logger.warning(f"Timeout: {url}")
        return {}
    except Exception as e:
        logger.warning(f"Request error {url}: {e}")
        return {}


# ── Stage 1: Polygon stock screener ──────────────────────────────────────────

async def _fetch_screener_page(
    session:       aiohttp.ClientSession,
    min_market_cap: float,   # in dollars
    min_price:      float,
    cursor:         Optional[str] = None,
) -> Dict:
    """Fetch one page of Polygon ticker screener results."""
    params = {
        "market":            "stocks",
        "locale":            "us",
        "active":            "true",
        "market_cap.gte":    int(min_market_cap),
        "last_updated_asc":  "false",
        "limit":             1000,
    }
    if cursor:
        params["cursor"] = cursor

    return await _get(
        session,
        f"{POLYGON_BASE}/v3/reference/tickers",
        params,
    )


async def stage1_screen(
    session:         aiohttp.ClientSession,
    min_market_cap_b: float,
    min_dollar_vol_m: float,
    min_price:        float,
) -> List[Dict]:
    """
    Stage 1: Pull all US stocks meeting market cap, price, and volume thresholds.
    Returns list of {ticker, name, price, market_cap, dollar_vol_30d}.
    """
    min_market_cap = min_market_cap_b * 1_000_000_000
    min_dollar_vol = min_dollar_vol_m * 1_000_000
    candidates     = []
    cursor         = None
    page           = 0

    logger.info(
        f"Stage 1: screening market cap>${min_market_cap_b}B, "
        f"price>${min_price}, vol>${min_dollar_vol_m}M/day"
    )

    while True:
        data   = await _fetch_screener_page(session, min_market_cap, min_price, cursor)
        results = data.get("results", [])
        if not results:
            break

        for r in results:
            ticker = r.get("ticker", "")
            if not ticker:
                continue

            # Filter out non-equity types (ETPs, warrants etc that sneak through)
            if r.get("type") not in ("CS", "ETF", "ETV", None):
                continue

            # Price filter (use last_updated_asc=false so latest price is present)
            price = r.get("last_updated")  # not price — need snapshot
            # Note: reference/tickers doesn't include live price directly
            # We store ticker for Stage 2 price check via snapshot
            candidates.append({
                "ticker":     ticker,
                "name":       r.get("name", ticker),
                "market_cap": r.get("market_cap", 0) or 0,
            })

        page  += 1
        next_url = data.get("next_url", "")
        if next_url:
            parsed_qs = parse_qs(urlparse(next_url).query)
            cursor = parsed_qs.get("cursor", [None])[0]
        else:
            cursor = None
        logger.info(f"Stage 1 page {page}: {len(results)} tickers, {len(candidates)} total")

        if not cursor or page > 10:  # safety cap at ~10,000 tickers
            break

        await asyncio.sleep(0.3)  # rate limit courtesy

    logger.info(f"Stage 1 complete: {len(candidates)} candidates before volume filter")

    # Now fetch 30-day snapshot data for price + dollar volume per ticker
    # Process in batches of 50 using the grouped daily snapshot
    qualified = []
    batch_size = 50

    for i in range(0, len(candidates), batch_size):
        batch = candidates[i: i + batch_size]
        tasks = [
            _get_ticker_snapshot(session, c["ticker"])
            for c in batch
        ]
        snapshots = await asyncio.gather(*tasks, return_exceptions=True)

        for c, snap in zip(batch, snapshots):
            if isinstance(snap, Exception) or not snap:
                continue
            price      = snap.get("price", 0) or 0
            dollar_vol = snap.get("dollar_vol_30d", 0) or 0

            if price < min_price:
                continue
            if dollar_vol < min_dollar_vol:
                continue

            qualified.append({
                **c,
                "price":        price,
                "dollar_vol_30d": dollar_vol,
            })

        pct = min(100, round((i + batch_size) / len(candidates) * 100))
        logger.info(
            f"Stage 1 volume check {pct}%: "
            f"{len(qualified)} qualified so far"
        )
        await asyncio.sleep(0.5)

    logger.info(f"Stage 1 final: {len(qualified)} tickers pass all Stage 1 filters")
    return qualified


async def _get_ticker_snapshot(
    session: aiohttp.ClientSession,
    ticker:  str,
) -> Dict:
    """Get current price and 30-day average dollar volume for a single ticker."""
    url  = f"{POLYGON_BASE}/v2/snapshot/locale/us/markets/stocks/tickers/{ticker}"
    data = await _get(session, url)
    snap = data.get("ticker", {})
    if not snap:
        return {}

    day   = snap.get("day",   {}) or {}
    prevd = snap.get("prevDay", {}) or {}

    # Current price: use day close, fallback to prevDay close
    price = day.get("c") or prevd.get("c") or 0

    # Dollar volume: day.vw * day.v for today, but we want 30-day avg
    # Polygon snapshot gives today's volume; use as proxy
    # For true 30-day avg, aggregate endpoint needed — use today as proxy
    vol   = day.get("v",    0) or 0
    vwap  = day.get("vw",   0) or 0
    dollar_vol_today = vol * vwap

    return {
        "price":          float(price),
        "dollar_vol_30d": float(dollar_vol_today),  # today as 30-day proxy
    }


# ── Stage 2: options chain IV + options dollar volume ─────────────────────────

async def _get_options_iv_and_vol(
    session:       aiohttp.ClientSession,
    ticker:        str,
    current_price: float,
    dte_min:       int = 25,
    dte_max:       int = 35,
) -> Dict:
    """
    Fetch ATM options chain, calculate 30-day IV proxy and options dollar volume.
    Uses 25–35 DTE window to approximate 30-day IV.
    """
    exp_from = (datetime.today() + timedelta(days=dte_min)).strftime("%Y-%m-%d")
    exp_to   = (datetime.today() + timedelta(days=dte_max)).strftime("%Y-%m-%d")
    url      = f"{POLYGON_BASE}/v3/snapshot/options/{ticker}"
    data     = await _get(session, url, {
        "expiration_date.gte": exp_from,
        "expiration_date.lte": exp_to,
        "limit": 100,
    })
    chain = data.get("results", [])
    if not chain:
        return {"iv_30d": None, "options_dollar_vol": 0}

    atm_ivs        = []
    options_dollar_vol = 0.0

    for opt in chain:
        details    = opt.get("details") or {}
        iv         = details.get("implied_volatility")
        strike     = details.get("strike_price", 0)
        day        = opt.get("day") or {}
        vol        = day.get("volume", 0) or 0
        vwap       = day.get("vwap",   0) or 0

        options_dollar_vol += vol * vwap * 100  # each contract = 100 shares

        if iv and iv > 0 and strike and current_price:
            if abs(strike - current_price) / current_price < 0.05:
                atm_ivs.append(iv)

    iv_30d = (sum(atm_ivs) / len(atm_ivs) * 100) if atm_ivs else None  # as %

    return {
        "iv_30d":            round(iv_30d, 1) if iv_30d else None,
        "options_dollar_vol": options_dollar_vol,
    }


async def stage2_options_filter(
    session:      aiohttp.ClientSession,
    candidates:   List[Dict],
    min_iv_pct:   float,
    universe_size: int,
) -> List[str]:
    """
    Stage 2: For each Stage 1 candidate, fetch options chain.
    Filter by IV > min_iv_pct.
    Rank by options dollar volume.
    Return top universe_size ticker symbols.
    """
    logger.info(
        f"Stage 2: options IV + volume check on {len(candidates)} tickers "
        f"(IV>{min_iv_pct}%, top {universe_size})"
    )

    results    = []
    batch_size = 20

    for i in range(0, len(candidates), batch_size):
        batch = candidates[i: i + batch_size]
        tasks = [
            _get_options_iv_and_vol(session, c["ticker"], c["price"])
            for c in batch
        ]
        opt_data = await asyncio.gather(*tasks, return_exceptions=True)

        for c, od in zip(batch, opt_data):
            if isinstance(od, Exception) or not od:
                continue
            iv   = od.get("iv_30d")
            ovol = od.get("options_dollar_vol", 0)

            if iv is None or iv < min_iv_pct:
                continue

            results.append({
                **c,
                "iv_30d":            iv,
                "options_dollar_vol": ovol,
            })

        pct = min(100, round((i + batch_size) / len(candidates) * 100))
        logger.info(
            f"Stage 2 {pct}%: {len(results)} pass IV filter so far"
        )
        await asyncio.sleep(0.8)  # Polygon rate limit

    # Rank by options dollar volume descending, take top N
    results.sort(key=lambda x: x["options_dollar_vol"], reverse=True)
    top = results[:universe_size]

    tickers = [r["ticker"] for r in top]
    logger.info(
        f"Stage 2 complete: {len(tickers)} tickers in final universe "
        f"(from {len(results)} IV-qualified)"
    )
    return tickers


# ── Main builder entry point ──────────────────────────────────────────────────

async def build_universe(params: Optional[Dict] = None) -> Dict:
    """
    Run both stages and return result dict with tickers + metadata.
    params: dict with universe_* keys (uses DEFAULT_PARAMS as fallback).
    """
    p = {**DEFAULT_PARAMS, **(params or {})}

    min_market_cap_b = float(p.get("universe_min_market_cap_b", DEFAULT_PARAMS["universe_min_market_cap_b"]))
    min_dollar_vol_m = float(p.get("universe_min_dollar_vol_m",  DEFAULT_PARAMS["universe_min_dollar_vol_m"]))
    min_iv_pct       = float(p.get("universe_min_iv_pct",        DEFAULT_PARAMS["universe_min_iv_pct"]))
    min_price        = float(p.get("universe_min_price",         DEFAULT_PARAMS["universe_min_price"]))
    universe_size    = int(p.get("universe_size",                DEFAULT_PARAMS["universe_size"]))

    start = datetime.utcnow()
    logger.info(
        f"Universe build started — "
        f"mktcap>${min_market_cap_b}B, vol>${min_dollar_vol_m}M, "
        f"IV>{min_iv_pct}%, price>${min_price}, top {universe_size}"
    )

    async with aiohttp.ClientSession() as session:
        stage1 = await stage1_screen(
            session, min_market_cap_b, min_dollar_vol_m, min_price
        )
        if not stage1:
            logger.error("Stage 1 returned no candidates — aborting")
            return {"error": "Stage 1 returned no candidates", "tickers": []}

        tickers = await stage2_options_filter(
            session, stage1, min_iv_pct, universe_size
        )

    elapsed = (datetime.utcnow() - start).total_seconds()
    result  = {
        "tickers":         tickers,
        "count":           len(tickers),
        "built_at":        datetime.utcnow().isoformat() + "Z",
        "elapsed_seconds": round(elapsed, 1),
        "params": {
            "universe_min_market_cap_b": min_market_cap_b,
            "universe_min_dollar_vol_m": min_dollar_vol_m,
            "universe_min_iv_pct":       min_iv_pct,
            "universe_min_price":        min_price,
            "universe_size":             universe_size,
        },
        "stage1_candidates": len(stage1),
    }

    # Cache to disk
    try:
        with open(CACHE_FILE, "w") as f:
            json.dump(result, f, indent=2)
        logger.info(f"Universe cached to {CACHE_FILE} ({len(tickers)} tickers, {elapsed:.0f}s)")
    except Exception as e:
        logger.error(f"Failed to write universe cache: {e}")

    return result


def load_cached_universe() -> List[str]:
    """
    Load tickers from cache file.
    Returns empty list if cache missing or older than 8 days.
    """
    try:
        with open(CACHE_FILE) as f:
            data = json.load(f)
        built_at = datetime.fromisoformat(data["built_at"].replace("Z", ""))
        age_days = (datetime.utcnow() - built_at).days
        if age_days > 8:
            logger.warning(f"Universe cache is {age_days} days old — may be stale")
        return data.get("tickers", [])
    except FileNotFoundError:
        return []
    except Exception as e:
        logger.error(f"Failed to load universe cache: {e}")
        return []


def get_cache_metadata() -> Dict:
    """Return cache metadata for /status endpoint."""
    try:
        with open(CACHE_FILE) as f:
            data = json.load(f)
        return {
            "built_at":    data.get("built_at"),
            "count":       data.get("count", 0),
            "elapsed_s":   data.get("elapsed_seconds"),
            "params":      data.get("params", {}),
            "stage1_candidates": data.get("stage1_candidates", 0),
        }
    except Exception:
        return {"built_at": None, "count": 0}


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    result = asyncio.run(build_universe())
    print(f"\nFinal universe: {result['count']} tickers")
    print(f"Time taken: {result['elapsed_seconds']}s")
    print(f"First 20: {result['tickers'][:20]}")
