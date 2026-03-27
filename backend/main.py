"""
FastAPI backend for MorningScan.

Endpoints:
  GET  /                   health check
  GET  /status             scan + universe status
  GET  /results            latest scan results
  POST /scan               trigger manual scan       (requires X-Api-Key)
  POST /cancel-scan        cancel active scan        (requires X-Api-Key)
  POST /refresh-universe   trigger universe rebuild  (requires X-Api-Key)

Scheduled jobs:
  08:30 ET daily    — morning scan
  00:00 ET Sunday   — universe refresh
"""

import asyncio
import logging
import os
from datetime import datetime, timezone
from contextlib import asynccontextmanager

from typing import Optional
from fastapi import FastAPI, HTTPException, Header, Body
from fastapi.middleware.cors import CORSMiddleware
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from env_config import ensure_env_loaded
from scanner import run_scan
from universe import get_universe
from universe_builder import build_universe, get_cache_metadata

ensure_env_loaded()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

# ── Config ────────────────────────────────────────────────────────────────────
SCAN_API_KEY    = os.getenv("SCAN_API_KEY", "")
ALLOWED_ORIGINS = os.getenv("ALLOWED_ORIGINS", "*").split(",")

if not SCAN_API_KEY:
    logger.warning("SCAN_API_KEY not set — /scan, /cancel-scan, and /refresh-universe are unprotected!")

# ── In-memory state ───────────────────────────────────────────────────────────
state = {
    "last_result":        None,
    "last_scan_time":     None,
    "is_scanning":        False,
    "last_scan_error":    None,
    "scan_task":          None,
    "is_refreshing":      False,
    "last_refresh_time":  None,
    "last_refresh_error": None,
}

# ── Scheduler ─────────────────────────────────────────────────────────────────
scheduler = AsyncIOScheduler(timezone="America/New_York")


async def _run_scan_task(params: dict = None) -> None:
    if state["is_scanning"]:
        logger.info("Scan already in progress — skipping")
        return
    state["is_scanning"]     = True
    state["last_scan_error"] = None
    try:
        universe = get_universe()
        result   = await run_scan(tickers=universe, params=params)
        state["last_result"]    = result
        state["last_scan_time"] = datetime.now(timezone.utc).isoformat()
        logger.info(f"Scan complete — {result.get('scanned', 0)} tickers processed")
    except asyncio.CancelledError:
        state["last_scan_error"] = "Scan cancelled by user"
        logger.info("Scan cancelled by user")
        raise
    except Exception as e:
        state["last_scan_error"] = str(e)
        logger.error(f"Scan failed: {e}")
    finally:
        state["is_scanning"] = False
        state["scan_task"] = None


async def _run_universe_refresh(params: dict = None) -> None:
    if state["is_refreshing"]:
        logger.info("Universe refresh already in progress — skipping")
        return
    state["is_refreshing"]      = True
    state["last_refresh_error"] = None
    try:
        logger.info("Starting weekly universe refresh...")
        result = await build_universe(params)
        state["last_refresh_time"] = datetime.now(timezone.utc).isoformat()
        logger.info(
            f"Universe refresh complete — "
            f"{result.get('count', 0)} tickers, "
            f"{result.get('elapsed_seconds', 0)}s"
        )
    except Exception as e:
        state["last_refresh_error"] = str(e)
        logger.error(f"Universe refresh failed: {e}")
    finally:
        state["is_refreshing"] = False


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Daily morning scan — 8:30 am ET
    scheduler.add_job(
        _run_scan_task,
        CronTrigger(hour=8, minute=30, timezone="America/New_York"),
        id="morning_scan",
        replace_existing=True,
    )
    # Weekly universe refresh — Sunday midnight ET
    scheduler.add_job(
        _run_universe_refresh,
        CronTrigger(day_of_week="sun", hour=0, minute=0, timezone="America/New_York"),
        id="universe_refresh",
        replace_existing=True,
    )
    scheduler.start()
    logger.info("Scheduler started — scan 8:30am ET daily, universe refresh Sunday midnight ET")
    yield
    scheduler.shutdown()


# ── App ───────────────────────────────────────────────────────────────────────
app = FastAPI(
    title="MorningScan API",
    version="1.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)


# ── Auth helper ───────────────────────────────────────────────────────────────

def _check_key(x_api_key: str) -> None:
    if SCAN_API_KEY and x_api_key != SCAN_API_KEY:
        raise HTTPException(status_code=401, detail="Invalid or missing X-Api-Key header")


# ── Routes ────────────────────────────────────────────────────────────────────

@app.get("/")
def health():
    return {"status": "ok", "service": "MorningScan API", "version": "1.1.0"}


@app.get("/status")
def status():
    universe     = get_universe()
    cache_meta   = get_cache_metadata()
    return {
        "is_scanning":          state["is_scanning"],
        "last_scan_time":       state["last_scan_time"],
        "last_scan_error":      state["last_scan_error"],
        "has_data":             state["last_result"] is not None,
        "is_refreshing":        state["is_refreshing"],
        "last_refresh_time":    state["last_refresh_time"],
        "last_refresh_error":   state["last_refresh_error"],
        "universe_size":        len(universe),
        "universe_cache":       cache_meta,
    }


@app.get("/results")
def results():
    if state["last_result"] is None:
        return {
            "status":         "no_data",
            "message":        "No scan has run yet. Click RUN SCAN or wait for 8:30 am ET.",
            "last_scan_time": None,
            "is_scanning":    state["is_scanning"],
        }
    return {
        "status":         "ok",
        "last_scan_time": state["last_scan_time"],
        "is_scanning":    state["is_scanning"],
        **state["last_result"],
    }


@app.get("/universe")
def universe_list():
    """Return the current scan universe — full ticker list, count, and source."""
    tickers      = get_universe()
    cache_meta   = get_cache_metadata()
    is_from_cache = cache_meta.get("built_at") is not None and cache_meta.get("count", 0) > 0
    return {
        "tickers":    sorted(tickers),
        "count":      len(tickers),
        "source":     "dynamic_cache" if is_from_cache else "static_fallback",
        "cache_meta": cache_meta,
    }


@app.post("/scan")
async def trigger_scan(
    x_api_key: str = Header(default=""),
    params:    Optional[dict] = Body(default=None),
):
    """Manually trigger a morning scan. Protected by X-Api-Key header."""
    _check_key(x_api_key)
    if state["is_scanning"]:
        return {"status": "already_running", "message": "A scan is already in progress"}
    state["scan_task"] = asyncio.create_task(_run_scan_task(params=params))
    return {"status": "started", "message": "Scan started. Poll /results every few seconds."}


@app.post("/cancel-scan")
async def cancel_scan(
    x_api_key: str = Header(default=""),
):
    """Cancel an in-progress scan. Protected by X-Api-Key header."""
    _check_key(x_api_key)
    task = state.get("scan_task")
    if not state["is_scanning"] or task is None or task.done():
        return {"status": "idle", "message": "No scan is currently running."}
    task.cancel()
    return {"status": "cancelling", "message": "Scan cancellation requested. Poll /status or /results to confirm."}


@app.post("/refresh-universe")
async def refresh_universe(
    x_api_key: str = Header(default=""),
    params:    Optional[dict] = Body(default=None),
):
    """
    Trigger a universe rebuild.
    Analyzes ~5,000+ assets across two stages (~15 minutes).
    Protected by X-Api-Key header.
    """
    _check_key(x_api_key)
    if state["is_refreshing"]:
        return {
            "status":  "already_running",
            "message": "Universe refresh already in progress (~15 minutes)"
        }
    asyncio.create_task(_run_universe_refresh(params=params))
    return {
        "status":  "started",
        "message": (
            "Universe refresh started. This analyzes 5,000+ assets across two stages "
            "and takes ~15 minutes. Poll /status to check progress."
        ),
    }
