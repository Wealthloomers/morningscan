/**
 * UniverseModal.jsx
 *
 * A "View Universe" popup that fetches and displays the current scan universe.
 * Shows a searchable, alphabetically sorted grid of ticker symbols with total count,
 * source indicator (dynamic cache vs static fallback), and cache build date.
 *
 * Usage in App.jsx:
 *   import UniverseModal from './UniverseModal';
 *
 *   // In your component:
 *   const [showUniverse, setShowUniverse] = useState(false);
 *
 *   // In your JSX (next to the RUN SCAN / Refresh Universe buttons):
 *   <button onClick={() => setShowUniverse(true)}>☰ View Universe</button>
 *   <UniverseModal
 *     isOpen={showUniverse}
 *     onClose={() => setShowUniverse(false)}
 *     apiUrl={API_URL}
 *     apiKey={apiKey}
 *   />
 */

import { useState, useEffect, useRef, useMemo } from "react";

export default function UniverseModal({ isOpen, onClose, apiUrl, apiKey }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [search, setSearch] = useState("");
  const backdropRef = useRef(null);

  // Fetch universe when modal opens
  useEffect(() => {
    if (!isOpen) return;
    setLoading(true);
    setError(null);
    setSearch("");

    const headers = {};
    if (apiKey) headers["X-Api-Key"] = apiKey;

    fetch(`${apiUrl}/universe`, { headers })
      .then((res) => {
        if (!res.ok) throw new Error(`Server returned ${res.status}`);
        return res.json();
      })
      .then((json) => {
        setData(json);
        setLoading(false);
      })
      .catch((err) => {
        setError(err.message);
        setLoading(false);
      });
  }, [isOpen, apiUrl, apiKey]);

  // Close on Escape key
  useEffect(() => {
    if (!isOpen) return;
    const handler = (e) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [isOpen, onClose]);

  // Filter tickers by search
  const filtered = useMemo(() => {
    if (!data?.tickers) return [];
    if (!search.trim()) return data.tickers;
    const q = search.trim().toUpperCase();
    return data.tickers.filter((t) => t.includes(q));
  }, [data, search]);

  if (!isOpen) return null;

  // Format cache build date
  const buildDate = data?.cache_meta?.built_at
    ? new Date(data.cache_meta.built_at).toLocaleString("en-US", {
        weekday: "short",
        month: "short",
        day: "numeric",
        hour: "numeric",
        minute: "2-digit",
        hour12: true,
        timeZoneName: "short",
      })
    : null;

  return (
    <>
      <style>{`
        .um-backdrop {
          position: fixed;
          inset: 0;
          z-index: 9999;
          background: rgba(0, 0, 0, 0.65);
          backdrop-filter: blur(4px);
          display: flex;
          align-items: center;
          justify-content: center;
          animation: um-fadeIn 0.2s ease-out;
        }
        @keyframes um-fadeIn {
          from { opacity: 0; }
          to   { opacity: 1; }
        }
        @keyframes um-slideUp {
          from { opacity: 0; transform: translateY(24px) scale(0.97); }
          to   { opacity: 1; transform: translateY(0) scale(1); }
        }
        .um-modal {
          background: #1a1c20;
          border: 1px solid #2d3038;
          border-radius: 12px;
          width: 94vw;
          max-width: 720px;
          max-height: 85vh;
          display: flex;
          flex-direction: column;
          box-shadow: 0 24px 80px rgba(0,0,0,0.6);
          animation: um-slideUp 0.25s ease-out;
          overflow: hidden;
        }

        /* ── Header ── */
        .um-header {
          display: flex;
          align-items: center;
          justify-content: space-between;
          padding: 20px 24px 16px;
          border-bottom: 1px solid #2d3038;
          flex-shrink: 0;
        }
        .um-title {
          font-family: 'Georgia', serif;
          font-size: 20px;
          font-weight: 700;
          color: #e8e4de;
          margin: 0;
        }
        .um-close {
          background: none;
          border: 1px solid #3a3d44;
          border-radius: 6px;
          color: #8c8880;
          font-size: 18px;
          width: 32px;
          height: 32px;
          cursor: pointer;
          display: flex;
          align-items: center;
          justify-content: center;
          transition: all 0.15s;
        }
        .um-close:hover {
          background: #2d3038;
          color: #e8e4de;
          border-color: #4a4d55;
        }

        /* ── Info bar ── */
        .um-info {
          display: flex;
          align-items: center;
          gap: 12px;
          padding: 12px 24px;
          background: #15171a;
          border-bottom: 1px solid #2d3038;
          flex-wrap: wrap;
          flex-shrink: 0;
        }
        .um-badge {
          display: inline-flex;
          align-items: center;
          gap: 5px;
          padding: 4px 10px;
          border-radius: 4px;
          font-family: 'Arial', sans-serif;
          font-size: 12px;
          font-weight: 600;
          letter-spacing: 0.3px;
        }
        .um-badge-count {
          background: #2E75B6;
          color: #fff;
        }
        .um-badge-source {
          background: #1e3a2a;
          color: #4ade80;
          border: 1px solid #2d5a3d;
        }
        .um-badge-static {
          background: #3a2e1e;
          color: #f59e0b;
          border: 1px solid #5a4a2d;
        }
        .um-badge-date {
          color: #8c8880;
          font-size: 11px;
          font-weight: 400;
          margin-left: auto;
        }

        /* ── Search ── */
        .um-search-wrap {
          padding: 12px 24px;
          flex-shrink: 0;
        }
        .um-search {
          width: 100%;
          background: #12141a;
          border: 1px solid #2d3038;
          border-radius: 6px;
          color: #e8e4de;
          font-family: 'Arial', sans-serif;
          font-size: 14px;
          padding: 8px 12px 8px 34px;
          outline: none;
          transition: border-color 0.15s;
          box-sizing: border-box;
        }
        .um-search:focus {
          border-color: #2E75B6;
        }
        .um-search::placeholder {
          color: #555;
        }
        .um-search-icon {
          position: absolute;
          left: 34px;
          top: 50%;
          transform: translateY(-50%);
          color: #555;
          font-size: 14px;
          pointer-events: none;
        }

        /* ── Ticker grid ── */
        .um-body {
          overflow-y: auto;
          padding: 8px 24px 20px;
          flex: 1;
          min-height: 0;
        }
        .um-grid {
          display: grid;
          grid-template-columns: repeat(auto-fill, minmax(80px, 1fr));
          gap: 6px;
        }
        .um-ticker {
          background: #22242a;
          border: 1px solid #2d3038;
          border-radius: 4px;
          padding: 6px 4px;
          text-align: center;
          font-family: 'Courier New', monospace;
          font-size: 12.5px;
          font-weight: 600;
          color: #c8c4be;
          letter-spacing: 0.4px;
          transition: all 0.12s;
          cursor: default;
          user-select: all;
        }
        .um-ticker:hover {
          background: #2a2d34;
          border-color: #2E75B6;
          color: #e8e4de;
        }

        /* ── Match highlight ── */
        .um-match {
          color: #2E75B6;
          font-weight: 700;
        }

        /* ── States ── */
        .um-loading, .um-error, .um-empty {
          text-align: center;
          padding: 48px 24px;
          font-family: 'Arial', sans-serif;
          font-size: 14px;
          color: #8c8880;
        }
        .um-error {
          color: #ef4444;
        }
        .um-spinner {
          display: inline-block;
          width: 28px;
          height: 28px;
          border: 3px solid #2d3038;
          border-top-color: #2E75B6;
          border-radius: 50%;
          animation: um-spin 0.7s linear infinite;
          margin-bottom: 12px;
        }
        @keyframes um-spin {
          to { transform: rotate(360deg); }
        }

        /* ── Scrollbar ── */
        .um-body::-webkit-scrollbar { width: 6px; }
        .um-body::-webkit-scrollbar-track { background: transparent; }
        .um-body::-webkit-scrollbar-thumb { background: #3a3d44; border-radius: 3px; }
        .um-body::-webkit-scrollbar-thumb:hover { background: #4a4d55; }

        /* ── Footer ── */
        .um-footer {
          padding: 10px 24px;
          border-top: 1px solid #2d3038;
          display: flex;
          align-items: center;
          justify-content: space-between;
          flex-shrink: 0;
        }
        .um-footer-text {
          font-family: 'Arial', sans-serif;
          font-size: 11px;
          color: #555;
        }
      `}</style>

      <div
        className="um-backdrop"
        ref={backdropRef}
        onClick={(e) => {
          if (e.target === backdropRef.current) onClose();
        }}
      >
        <div className="um-modal" role="dialog" aria-label="Scan Universe">
          {/* Header */}
          <div className="um-header">
            <h2 className="um-title">Scan Universe</h2>
            <button className="um-close" onClick={onClose} title="Close">
              ✕
            </button>
          </div>

          {/* Loading state */}
          {loading && (
            <div className="um-loading">
              <div className="um-spinner" />
              <div>Loading universe&hellip;</div>
            </div>
          )}

          {/* Error state */}
          {error && (
            <div className="um-error">
              Failed to load universe: {error}
            </div>
          )}

          {/* Loaded state */}
          {!loading && !error && data && (
            <>
              {/* Info bar */}
              <div className="um-info">
                <span className="um-badge um-badge-count">
                  {data.count} assets
                </span>
                <span
                  className={`um-badge ${
                    data.source === "dynamic_cache"
                      ? "um-badge-source"
                      : "um-badge-static"
                  }`}
                >
                  {data.source === "dynamic_cache"
                    ? "⟳ Dynamic"
                    : "⊡ Static fallback"}
                </span>
                {buildDate && (
                  <span className="um-badge-date">
                    Built {buildDate}
                  </span>
                )}
              </div>

              {/* Search */}
              <div className="um-search-wrap" style={{ position: "relative" }}>
                <span className="um-search-icon">⌕</span>
                <input
                  className="um-search"
                  type="text"
                  placeholder="Search tickers…"
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                  autoFocus
                />
              </div>

              {/* Ticker grid */}
              <div className="um-body">
                {filtered.length === 0 ? (
                  <div className="um-empty">
                    No tickers match &ldquo;{search}&rdquo;
                  </div>
                ) : (
                  <div className="um-grid">
                    {filtered.map((ticker) => (
                      <div key={ticker} className="um-ticker">
                        {search.trim()
                          ? highlightMatch(ticker, search.trim().toUpperCase())
                          : ticker}
                      </div>
                    ))}
                  </div>
                )}
              </div>

              {/* Footer */}
              <div className="um-footer">
                <span className="um-footer-text">
                  {search.trim() && filtered.length !== data.count
                    ? `Showing ${filtered.length} of ${data.count}`
                    : `${data.count} tickers in scan universe`}
                </span>
                <span className="um-footer-text">
                  Press Esc to close
                </span>
              </div>
            </>
          )}
        </div>
      </div>
    </>
  );
}

/** Highlight matched substring in a ticker symbol */
function highlightMatch(ticker, query) {
  const idx = ticker.indexOf(query);
  if (idx === -1) return ticker;
  return (
    <>
      {ticker.slice(0, idx)}
      <span className="um-match">{ticker.slice(idx, idx + query.length)}</span>
      {ticker.slice(idx + query.length)}
    </>
  );
}
