"""
Universe loader.
Priority order:
  1. universe_cache.json  — built by universe_builder.py weekly
  2. STATIC_UNIVERSE      — curated fallback (~476 tickers) used on first run
                            before any cache exists

The daily scanner always calls get_universe() which handles the priority logic.
"""

import logging
from typing import List
from universe_builder import load_cached_universe

logger = logging.getLogger(__name__)

# ── Static fallback universe (~476 tickers) ───────────────────────────────────
# Used only if no cache file exists (first deployment, before first weekly refresh).
# After the first universe refresh this list is no longer used.

STATIC_UNIVERSE = [
    # Mega-cap tech
    "AAPL", "MSFT", "NVDA", "GOOGL", "GOOG", "AMZN", "META", "TSLA",
    "AVGO", "ORCL", "ADBE", "CRM", "NOW", "INTU", "SNPS", "CDNS",
    # Semiconductors
    "AMD", "INTC", "QCOM", "TXN", "MU", "AMAT", "LRCX", "KLAC",
    "MRVL", "MCHP", "ON", "SWKS", "MPWR", "SMCI", "ARM", "ASML",
    # Cloud / SaaS / Internet
    "PANW", "CRWD", "ZS", "FTNT", "NET", "DDOG", "SNOW", "PLTR",
    "COIN", "MSTR", "UBER", "LYFT", "ABNB", "DASH", "RBLX", "HOOD",
    "SHOP", "SPOT", "PINS", "SNAP", "ROKU", "TWLO", "OKTA", "ZM",
    "MDB", "GTLB", "PATH",
    # Large-cap tech / hardware
    "IBM", "HPE", "HPQ", "DELL", "STX", "WDC", "ANET", "CSCO", "JNPR",
    # Financials — Banks
    "JPM", "BAC", "WFC", "C", "GS", "MS", "USB", "PNC", "TFC",
    "CFG", "FITB", "KEY", "RF", "HBAN", "MTB",
    # Financials — Investment / Insurance / Payments
    "BLK", "BX", "KKR", "APO", "SCHW", "AXP", "COF", "DFS", "SYF",
    "V", "MA", "PYPL", "SQ", "FI", "FIS", "GPN",
    "AIG", "MET", "PRU", "AFL", "ALL", "TRV", "CB", "HIG",
    # Healthcare — Large-cap pharma
    "JNJ", "PFE", "MRK", "ABBV", "LLY", "BMY", "AZN", "NVO", "GSK",
    # Healthcare — Biotech
    "AMGN", "GILD", "BIIB", "REGN", "VRTX", "MRNA", "BNTX",
    "ALNY", "IONS", "INCY", "EXEL", "ARWR", "SGEN",
    # Healthcare — Managed care / devices
    "UNH", "CVS", "CI", "HUM", "CNC", "ELV",
    "MDT", "ABT", "SYK", "BSX", "ZBH", "DXCM", "ISRG", "EW", "BDX", "RMD",
    # Consumer — Staples
    "PG", "KO", "PEP", "PM", "MO", "MDLZ", "KHC", "GIS",
    "CLX", "CL", "CHD", "KMB", "EL", "HSY",
    # Consumer — Discretionary / Retail
    "WMT", "TGT", "COST", "HD", "LOW", "BBY", "DG", "DLTR", "ROST", "TJX",
    "NKE", "LULU", "PVH", "RL", "TPR",
    "MCD", "SBUX", "CMG", "YUM", "DPZ", "QSR",
    "DIS", "NFLX", "WBD", "PARA", "LYV",
    "AZO", "ORLY", "GPC",
    # Autos
    "F", "GM", "RIVN", "LCID",
    # Airlines / Travel / Leisure
    "AAL", "DAL", "UAL", "LUV",
    "NCLH", "CCL", "RCL",
    "MGM", "WYNN", "LVS", "PENN", "DKNG",
    # Energy — E&P
    "XOM", "CVX", "COP", "OXY", "EOG", "DVN", "FANG", "APA", "HES", "MRO",
    "EQT", "AR", "RRC",
    # Energy — Services / Midstream / Refining
    "SLB", "HAL", "BKR", "MPC", "PSX", "VLO", "KMI", "WMB", "ET",
    # Industrials — Defense
    "BA", "LMT", "RTX", "NOC", "GD", "LDOS", "SAIC",
    # Industrials — Machinery / Conglomerates
    "CAT", "DE", "CMI", "PH", "EMR", "ETN", "ROK", "AME", "GNRC",
    "GE", "HON", "MMM", "ITW", "DOV", "XYL",
    # Industrials — Transport / Logistics
    "UNP", "CSX", "NSC", "UPS", "FDX", "JBHT", "CHRW",
    # Materials
    "LIN", "APD", "SHW", "ECL", "PPG",
    "NEM", "AEM", "WPM", "GOLD", "FCX", "AA", "ALB", "MP",
    # Real Estate
    "AMT", "CCI", "SBAC", "PLD", "EQIX", "DLR", "IRM",
    "O", "VICI", "GLPI", "SPG", "KIM", "REG",
    "EQR", "AVB", "ESS", "MAA", "PSA", "EXR",
    "VTR", "WELL", "MPW",
    # Utilities
    "NEE", "DUK", "SO", "D", "AEP", "EXC", "SRE", "PCG",
    "XEL", "WEC", "ETR", "CEG", "VST", "NRG",
    # Communications
    "T", "VZ", "TMUS", "CHTR", "CMCSA",
    # Chinese / International ADRs
    "BABA", "JD", "PDD", "BIDU", "NIO", "LI", "XPEV",
    "TCOM", "SE", "MELI", "NU",
    # Broad market ETFs
    "SPY", "QQQ", "IWM", "DIA", "VOO", "VTI", "RSP",
    # Factor / style ETFs
    "VTV", "VUG", "IWF", "IWD", "MTUM", "USMV", "IJR",
    # Sector ETFs
    "XLF", "XLK", "XLE", "XLV", "XLI", "XLY", "XLP",
    "XLU", "XLB", "XLRE", "XLC",
    "IBB", "XBI", "KBE", "KRE", "ITB", "XHB", "SMH",
    "ARKK", "ARKG",
    # International / Emerging ETFs
    "EEM", "EFA", "FXI", "KWEB", "EWJ", "EWZ", "VEA", "VWO",
    # Commodities
    "GLD", "IAU", "SLV", "GDX", "GDXJ", "USO", "UNG", "PDBC", "COPX",
    # Fixed income ETFs
    "TLT", "TBT", "TMF", "IEF", "SHY", "HYG", "JNK", "LQD", "BND", "AGG",
    # Leveraged / inverse ETFs
    "TQQQ", "SQQQ", "SPXL", "SPXS", "SPXU",
    "SOXL", "SOXS", "TNA", "TZA", "LABU", "LABD",
    "ERX", "ERY", "NUGT", "DUST",
    # Volatility products
    "UVXY", "SVXY", "VXX",
    # Misc
    "BRK-B", "WBA", "VFC",
    # Homebuilders
    "LEN", "DHI", "PHM", "TOL",
    # Clean energy
    "FSLR", "ENPH", "SEDG", "RUN", "CHPT", "BLNK", "EVGO",
    # Fintech
    "SOFI", "AFRM", "UPST", "BILL", "HUBS", "PCTY", "PAYC", "VEEV",
    # Ad tech / digital
    "APP", "TTD", "MGNI", "MTCH", "BMBL", "ETSY",
    # Genomics
    "ILMN", "PACB", "NTRA", "RGEN", "TXG", "NVAX", "VXRT",
    # Steel / metals
    "CLF", "NUE", "STLD", "X",
    # Chemicals
    "CF", "MOS", "NTR", "FMC", "CE", "OLN",
    # Hospitality / travel
    "HLT", "MAR", "H", "WH", "BKNG", "EXPE",
    # Industrial
    "CARR", "OTIS", "TT", "JCI",
    # Healthcare hospitals
    "HCA", "THC", "UHS",
    # Specialty REITs
    "STAG", "COLD", "REXR", "SUI", "ELS", "AMH", "INVH",
    # Utilities / pipelines
    "OKE", "LNG", "CQP", "LNT", "EVRG", "PNW",
    # Media
    "FOXA", "FOX", "IAC",
    # Misc large liquid
    "W", "CHWY", "DNUT", "QSR", "MARA",
]

# Deduplicate while preserving order
_seen: set = set()
STATIC_UNIVERSE = [t for t in STATIC_UNIVERSE if not (t in _seen or _seen.add(t))]


def get_universe() -> List[str]:
    """
    Return the current scan universe.
    Tries cache first, falls back to static list.
    """
    cached = load_cached_universe()
    if cached:
        logger.info(f"Using cached universe: {len(cached)} tickers")
        return cached
    logger.info(
        f"No universe cache found — using static fallback: "
        f"{len(STATIC_UNIVERSE)} tickers. "
        f"Run /refresh-universe to build a dynamic universe."
    )
    return list(STATIC_UNIVERSE)


# Keep UNIVERSE as a module-level alias for backwards compatibility
# (scanner.py imports UNIVERSE directly)
UNIVERSE = get_universe()
