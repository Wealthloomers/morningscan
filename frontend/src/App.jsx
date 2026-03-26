import { useState, useEffect, useCallback, useRef } from "react";
import UniverseModal from "./UniverseModal";

const API_URL = import.meta.env.VITE_API_URL || "http://localhost:8000";

const T = {
  bg:"#f5f4f0", bgAlt:"#efede8", white:"#ffffff",
  border:"#e2dfd8", borderMid:"#d0ccc4",
  text:"#1a1814", textMid:"#4a4740", textMuted:"#8c8880", textFaint:"#b8b4ae",
  green:"#1a6b3c", greenBg:"#eef6f1", greenBord:"#b8d9c4",
  red:"#8b1c2e", redBg:"#fdf0f2", redBord:"#ddb8bf",
  purple:"#4a2d7a", purpleBg:"#f2eef9", purpleBord:"#c8b8e8",
  amber:"#7a4f00", amberBg:"#fdf5e6", amberBord:"#e0c880",
  blue:"#1a3d6b", blueBg:"#eef3fb", blueBord:"#b8cce8",
};

const LISTS = [
  { key:"long_calls", label:"Long Calls", tag:"BUY CALL", srLabel:"Support", srType:"support", color:T.green, bg:T.greenBg, bord:T.greenBord },
  { key:"short_calls", label:"Short Calls", tag:"SELL CALL", srLabel:"Resistance", srType:"resistance", color:T.red, bg:T.redBg, bord:T.redBord },
  { key:"long_puts", label:"Long Puts", tag:"BUY PUT", srLabel:"Resistance", srType:"resistance", color:T.purple, bg:T.purpleBg, bord:T.purpleBord },
  { key:"short_puts", label:"Short Puts", tag:"SELL PUT", srLabel:"Support", srType:"support", color:T.amber, bg:T.amberBg, bord:T.amberBord },
];

const FACTORY_DEFAULTS = {
  universe_min_market_cap_b: 2.0,
  universe_min_dollar_vol_m: 50.0,
  universe_min_iv_pct: 30.0,
  universe_min_price: 5.0,
  universe_size: 500,
  dte_min: 30,
  dte_max: 90,
  min_atm_oi: 500,
  min_options_vol_usd: 500000,
  sr_min_touches: 2,
  sr_lookback_days: 30,
  sr_proximity_pct: 2.0,
  earnings_blackout_days: 21,
  lc_rsi_max: 35,
  lc_ivr_max: 35,
  lc_catalyst_min_days: 5,
  lc_catalyst_max_days: 21,
  lc_pc_ratio_min: 1.2,
  sc_rsi_min: 70,
  sc_ivr_min: 70,
  lp_rsi_min: 70,
  lp_ivr_max: 35,
  lp_cp_ratio_min: 1.5,
  lp_catalyst_min_days: 5,
  lp_catalyst_max_days: 21,
  sp_rsi_max: 35,
  sp_ivr_min: 70,
};

const PARAM_GROUPS = [
  {
    label:"Universe Pre-Filter", color:"#1a1814", bg:"#f5f4f0", bord:"#d0ccc4",
    fields:[
      { key:"universe_min_market_cap_b", label:"Min Market Cap", unit:"$ Billion", min:0.5, max:20, step:0.5, tip:"Minimum company market cap. Filters out micro-caps with thin options markets." },
      { key:"universe_min_dollar_vol_m", label:"Min Dollar Volume", unit:"$ Million/day", min:10, max:500, step:10, tip:"30-day average daily dollar volume (price x shares). More meaningful than share count alone." },
      { key:"universe_min_iv_pct", label:"Min 30-day IV", unit:"% annualised", min:10, max:80, step:5, tip:"Minimum 30-day implied volatility. Filters out sluggish stocks with unattractive premiums." },
      { key:"universe_min_price", label:"Min Stock Price", unit:"USD per share", min:1, max:50, step:1, tip:"Minimum stock price. Low-priced stocks have wide spreads and tiny premiums." },
      { key:"universe_size", label:"Universe Size", unit:"top N tickers", min:100, max:1000, step:50, tip:"Final universe size, ranked by options dollar volume (most liquid first)." },
    ],
  },
  {
    label:"Global Filters", color:T.blue, bg:T.blueBg, bord:T.blueBord,
    fields:[
      { key:"dte_min", label:"DTE Minimum", unit:"days to expiry", min:7, max:60, step:1, tip:"Minimum days to expiry for options scanned. 30 DTE gives access to liquid monthly contracts." },
      { key:"dte_max", label:"DTE Maximum", unit:"days to expiry", min:30, max:180, step:5, tip:"Maximum days to expiry. 90 DTE covers one full quarterly cycle." },
      { key:"min_atm_oi", label:"Min ATM OI", unit:"contracts", min:100, max:5000, step:100, tip:"Minimum open interest at ATM strike." },
      { key:"min_options_vol_usd", label:"Min Options Volume", unit:"USD/day", min:100000, max:2000000, step:100000, tip:"Minimum daily options dollar volume." },
      { key:"sr_min_touches", label:"S/R Min Touches", unit:"touches", min:0, max:500, step:1, tip:"Minimum times price tested the S/R level." },
      { key:"sr_lookback_days", label:"S/R Recency", unit:"days", min:0, max:500, step:1, tip:"At least one touch must be within this many days." },
      { key:"sr_proximity_pct", label:"S/R Proximity", unit:"% from level", min:0, max:500, step:0.25, tip:"Price must be within this % of the S/R level." },
      { key:"earnings_blackout_days",label:"Earnings Blackout", unit:"days", min:0, max:500, step:1, tip:"Short strategies excluded if earnings fall within N days." },
    ],
  },
  {
    label:"Long Calls", color:T.green, bg:T.greenBg, bord:T.greenBord,
    fields:[
      { key:"lc_rsi_max", label:"RSI Maximum", unit:"weekly", min:20, max:45, step:1, tip:"Weekly RSI must be below this (oversold)." },
      { key:"lc_ivr_max", label:"IVR Maximum", unit:"IVP %", min:10, max:50, step:1, tip:"IV Rank below this = cheap options." },
      { key:"lc_catalyst_min_days", label:"Catalyst Min", unit:"days to earn", min:0, max:500, step:1, tip:"Earnings bonus window start." },
      { key:"lc_catalyst_max_days", label:"Catalyst Max", unit:"days to earn", min:0, max:500, step:1, tip:"Earnings bonus window end." },
      { key:"lc_pc_ratio_min", label:"P/C Ratio Min", unit:"ratio", min:0.8, max:2.5, step:0.1, tip:"Put/Call ratio above this = contrarian bullish." },
    ],
  },
  {
    label:"Short Calls", color:T.red, bg:T.redBg, bord:T.redBord,
    fields:[
      { key:"sc_rsi_min", label:"RSI Minimum", unit:"weekly", min:60, max:85, step:1, tip:"Weekly RSI must be above this (overbought)." },
      { key:"sc_ivr_min", label:"IVR Minimum", unit:"IVP %", min:55, max:90, step:1, tip:"IV Rank above this = expensive premium to sell." },
    ],
  },
  {
    label:"Long Puts", color:T.purple, bg:T.purpleBg, bord:T.purpleBord,
    fields:[
      { key:"lp_rsi_min", label:"RSI Minimum", unit:"weekly", min:60, max:85, step:1, tip:"Weekly RSI must be above this (overbought)." },
      { key:"lp_ivr_max", label:"IVR Maximum", unit:"IVP %", min:10, max:50, step:1, tip:"IV Rank below this = cheap puts (complacency)." },
      { key:"lp_cp_ratio_min", label:"C/P Ratio Min", unit:"ratio", min:0.8, max:3.0, step:0.1, tip:"Call/Put ratio above this = contrarian bearish." },
      { key:"lp_catalyst_min_days", label:"Catalyst Min", unit:"days to earn", min:0, max:500, step:1, tip:"Earnings bonus window start." },
      { key:"lp_catalyst_max_days", label:"Catalyst Max", unit:"days to earn", min:0, max:500, step:1, tip:"Earnings bonus window end." },
    ],
  },
  {
    label:"Short Puts", color:T.amber, bg:T.amberBg, bord:T.amberBord,
    fields:[
      { key:"sp_rsi_max", label:"RSI Maximum", unit:"weekly", min:20, max:45, step:1, tip:"Weekly RSI must be below this (oversold)." },
      { key:"sp_ivr_min", label:"IVR Minimum", unit:"IVP %", min:55, max:90, step:1, tip:"IV Rank above this = rich premium to collect." },
    ],
  },
];

const f = (n, d=2) => (n != null && !isNaN(n)) ? Number(n).toFixed(d) : "\u2014";

function ScoreBar({ score, color }) {
  const [w, setW] = useState(0);
  useEffect(() => { const t = setTimeout(() => setW(score), 100); return () => clearTimeout(t); }, [score]);
  return (
    <div style={{ display:"flex", alignItems:"center", gap:8 }}>
      <div style={{ width:70, height:5, background:T.bgAlt, borderRadius:3, overflow:"hidden", border:`1px solid ${T.border}` }}>
        <div style={{ width:`${w}%`, height:"100%", background:color, borderRadius:3, transition:"width 1.2s ease", opacity:0.85 }} />
      </div>
      <span style={{ fontSize:11, color:T.textMuted, fontFamily:"monospace", minWidth:22 }}>{f(score,0)}</span>
    </div>
  );
}

function Row({ s, list, i }) {
  const [vis, setVis] = useState(false);
  useEffect(() => { const t = setTimeout(() => setVis(true), i*50+80); return () => clearTimeout(t); }, []);
  const srPrice = list.srType==="support" ? s.support?.price : s.resistance?.price;
  const srDist = list.srType==="support" ? s.support?.distance_pct : s.resistance?.distance_pct;
  const srTouches = list.srType==="support" ? s.support?.touches : s.resistance?.touches;
  const up = (s.change_pct ?? 0) >= 0;
  const os = (s.weekly_rsi ?? 50) < 35;
  const ob = (s.weekly_rsi ?? 50) > 70;
  return (
    <tr style={{ borderBottom:`1px solid ${T.border}`, opacity:vis?1:0, transform:vis?"none":"translateY(5px)", transition:"opacity 0.3s, transform 0.3s, background 0.1s" }}
      onMouseEnter={e => e.currentTarget.style.background = T.bgAlt}
      onMouseLeave={e => e.currentTarget.style.background = "transparent"}>
      <td style={{ padding:"11px 8px 11px 16px", width:28 }}>
        <span style={{ display:"inline-flex", alignItems:"center", justifyContent:"center", width:20, height:20, borderRadius:"50%", background:s.rank<=3?list.bg:"transparent", border:s.rank<=3?`1px solid ${list.bord}`:"none", fontSize:10, fontWeight:700, color:s.rank<=3?list.color:T.textFaint, fontFamily:"monospace" }}>{s.rank}</span>
      </td>
      <td style={{ padding:"11px 10px", minWidth:100 }}>
        <div style={{ fontFamily:"monospace", fontWeight:700, fontSize:14, color:T.text, letterSpacing:"0.04em" }}>{s.ticker}</div>
        <div style={{ fontSize:10, color:T.textMuted, marginTop:1, maxWidth:120, overflow:"hidden", textOverflow:"ellipsis", whiteSpace:"nowrap" }}>{s.name||s.ticker}</div>
      </td>
      <td style={{ padding:"11px 10px" }}>
        <div style={{ fontFamily:"monospace", fontSize:12, color:T.text }}>${f(s.price)}</div>
        <span style={{ display:"inline-block", marginTop:3, fontSize:10, padding:"1px 5px", borderRadius:3, fontFamily:"monospace", background:up?T.greenBg:T.redBg, color:up?T.green:T.red, border:`1px solid ${up?T.greenBord:T.redBord}` }}>{up?"+":""}{f(s.change_pct)}%</span>
      </td>
      <td style={{ padding:"11px 10px" }}>
        <div style={{ display:"inline-flex", flexDirection:"column", alignItems:"center", padding:"3px 8px", borderRadius:5, background:os?T.greenBg:ob?T.redBg:T.amberBg, border:`1px solid ${os?T.greenBord:ob?T.redBord:T.amberBord}` }}>
          <span style={{ fontFamily:"monospace", fontSize:12, fontWeight:700, color:os?T.green:ob?T.red:T.amber }}>{f(s.weekly_rsi,1)}</span>
          <span style={{ fontSize:8, color:os?T.green:ob?T.red:T.amber, letterSpacing:"0.06em" }}>{os?"OVERSOLD":ob?"OVERBOUGHT":"NEUTRAL"}</span>
        </div>
      </td>
      <td style={{ padding:"11px 10px" }}>
        <div style={{ display:"inline-flex", alignItems:"center", justifyContent:"center", width:34, height:34, borderRadius:"50%", background:list.bg, border:`1.5px solid ${list.bord}`, fontFamily:"monospace", fontWeight:700, fontSize:11, color:list.color }}>{f(s.iv_rank,0)}</div>
      </td>
      <td style={{ padding:"11px 10px", minWidth:115 }}>
        {srPrice!=null
          ? <div><div style={{ fontFamily:"monospace", fontSize:12, fontWeight:600, color:T.text }}>${f(srPrice)}</div><div style={{ fontSize:10, color:T.textMuted, marginTop:1 }}>{f(srDist,1)}% · {srTouches}x tested</div></div>
          : <span style={{ color:T.textFaint }}>{"\u2014"}</span>}
      </td>
      <td style={{ padding:"11px 10px" }}>
        {s.days_to_earnings!=null
          ? <span style={{ fontSize:10, padding:"2px 6px", borderRadius:3, fontFamily:"monospace", background:s.days_to_earnings<=14?T.amberBg:T.bgAlt, color:s.days_to_earnings<=14?T.amber:T.textMuted, border:`1px solid ${s.days_to_earnings<=14?T.amberBord:T.border}` }}>{s.days_to_earnings}d</span>
          : <span style={{ color:T.textFaint, fontSize:11 }}>{"\u2014"}</span>}
      </td>
      <td style={{ padding:"11px 10px" }}>
        <div style={{ display:"flex", gap:4 }}>
          {s.unusual_activity && <span style={{ fontSize:9, padding:"2px 5px", borderRadius:3, background:T.amberBg, color:T.amber, border:`1px solid ${T.amberBord}`, fontWeight:700, fontFamily:"monospace" }}>UOA</span>}
          {s.wick_rejection && <span style={{ fontSize:9, padding:"2px 5px", borderRadius:3, background:list.bg, color:list.color, border:`1px solid ${list.bord}`, fontWeight:700, fontFamily:"monospace" }}>WR</span>}
        </div>
      </td>
      <td style={{ padding:"11px 16px 11px 10px" }}><ScoreBar score={s.score} color={list.color} /></td>
    </tr>
  );
}

function Panel({ list, stocks }) {
  const [open, setOpen] = useState(true);
  return (
    <div style={{ background:T.white, border:`1px solid ${T.border}`, borderRadius:10, overflow:"hidden", marginBottom:12, boxShadow:"0 1px 4px rgba(0,0,0,0.05)", borderLeft:`3px solid ${list.color}` }}>
      <div onClick={()=>setOpen(o=>!o)} style={{ display:"flex", alignItems:"center", justifyContent:"space-between", padding:"13px 18px", borderBottom:open?`1px solid ${T.border}`:"none", cursor:"pointer", userSelect:"none", background:T.bgAlt }}
        onMouseEnter={e=>e.currentTarget.style.background="#eae8e2"}
        onMouseLeave={e=>e.currentTarget.style.background=T.bgAlt}>
        <div style={{ display:"flex", alignItems:"center", gap:12 }}>
          <div style={{ padding:"5px 11px", borderRadius:5, background:list.bg, border:`1px solid ${list.bord}`, fontFamily:"monospace", fontWeight:700, fontSize:11, color:list.color, letterSpacing:"0.06em" }}>{list.tag}</div>
          <div>
            <span style={{ fontFamily:"Georgia, serif", fontWeight:700, fontSize:16, color:T.text }}>{list.label}</span>
            <span style={{ marginLeft:10, fontSize:11, color:T.textMuted }}>{stocks?.length||0} candidates</span>
          </div>
        </div>
        <div style={{ display:"flex", alignItems:"center", gap:14 }}>
          {stocks?.[0] && <div style={{ textAlign:"right" }}><div style={{ fontSize:9, color:T.textFaint, fontFamily:"monospace", letterSpacing:"0.08em" }}>TOP SCORE</div><div style={{ fontFamily:"monospace", fontSize:17, fontWeight:700, color:list.color }}>{f(stocks[0].score,0)}</div></div>}
          <div style={{ width:24, height:24, borderRadius:4, border:`1px solid ${T.border}`, display:"flex", alignItems:"center", justifyContent:"center", color:T.textMuted, fontSize:10, background:T.white }}>{open?"\u25B2":"\u25BC"}</div>
        </div>
      </div>
      {open && (
        <div style={{ overflowX:"auto" }}>
          <table style={{ width:"100%", borderCollapse:"collapse", minWidth:840 }}>
            <thead>
              <tr style={{ background:T.bg, borderBottom:`1px solid ${T.border}` }}>
                {["","Ticker","Price","RSI (W)","IVR",list.srLabel,"Earn","Flags","Score"].map((h,i)=>(
                  <th key={i} style={{ padding:"7px 10px", paddingLeft:i===0?16:10, paddingRight:i===9?16:10, textAlign:"left", fontSize:9, color:T.textMuted, fontWeight:600, letterSpacing:"0.1em", textTransform:"uppercase", whiteSpace:"nowrap", fontFamily:"monospace" }}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>{(stocks||[]).map((s,i)=><Row key={s.ticker} s={s} list={list} i={i}/>)}</tbody>
          </table>
        </div>
      )}
    </div>
  );
}

function ParamField({ field, value, savedValue, onChange }) {
  const isModified = value !== savedValue;
  return (
    <div title={field.tip} style={{ background:T.white, border:`1px solid ${isModified?T.amberBord:T.border}`, borderRadius:7, padding:"10px 12px", transition:"border-color 0.15s" }}>
      <div style={{ display:"flex", justifyContent:"space-between", marginBottom:7 }}>
        <span style={{ fontSize:10, color:T.textMid, fontFamily:"monospace", fontWeight:600 }}>{field.label}{isModified&&<span style={{ color:T.amber, marginLeft:4 }}>{"\u25CF"}</span>}</span>
        <span style={{ fontSize:9, color:T.textFaint, fontFamily:"monospace" }}>{field.unit}</span>
      </div>
      <div style={{ display:"flex", alignItems:"center", gap:8 }}>
        <input type="range" min={field.min} max={field.max} step={field.step} value={value}
          onChange={e=>onChange(field.key, parseFloat(e.target.value))}
          style={{ flex:1, accentColor:isModified?T.amber:T.textMid, cursor:"pointer", height:3 }} />
        <input type="number" min={field.min} max={field.max} step={field.step} value={value}
          onChange={e=>{ const v=parseFloat(e.target.value); if(!isNaN(v)&&v>=field.min&&v<=field.max) onChange(field.key,v); }}
          style={{ width:58, padding:"3px 6px", borderRadius:4, border:`1px solid ${T.border}`, fontFamily:"monospace", fontSize:12, fontWeight:600, color:isModified?T.amber:T.text, background:T.bgAlt, textAlign:"right", outline:"none" }} />
      </div>
      <div style={{ display:"flex", justifyContent:"space-between", marginTop:3 }}>
        <span style={{ fontSize:8, color:T.textFaint, fontFamily:"monospace" }}>{field.min}</span>
        <span style={{ fontSize:8, color:T.textFaint, fontFamily:"monospace" }}>{field.max}</span>
      </div>
    </div>
  );
}

export default function App() {
  const [saved, setSaved] = useState({...FACTORY_DEFAULTS});
  const [params, setParams] = useState({...FACTORY_DEFAULTS});
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [paramsOpen, setParamsOpen] = useState(true);
  const [flashSave, setFlashSave] = useState(false);
  const [apiKey, setApiKey] = useState("");
  const [showKeyInput, setShowKeyInput] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [refreshMsg, setRefreshMsg] = useState(null);
  const [showUniverse, setShowUniverse] = useState(false);
  const pollRef = useRef(null);

  const unsaved = Object.keys(params).filter(k => params[k] !== saved[k]).length;
  const fromFactory = Object.keys(params).filter(k => params[k] !== FACTORY_DEFAULTS[k]).length;
  const change = useCallback((key, val) => setParams(p => ({...p, [key]:val})), []);

  const handleSave = () => {
    setSaved({...params});
    setFlashSave(true);
    setTimeout(() => setFlashSave(false), 2000);
  };

  useEffect(() => { fetchResults(); }, []);

  const fetchResults = async () => {
    try {
      const res = await fetch(`${API_URL}/results`);
      if (!res.ok) return;
      const json = await res.json();
      if (json.status === "ok") setData(json);
      return json;
    } catch(e) {}
  };

  const stopPolling = () => {
    if (pollRef.current) { clearInterval(pollRef.current); pollRef.current = null; }
    setLoading(false);
  };

  const startPolling = () => {
    pollRef.current = setInterval(async () => {
      const json = await fetchResults();
      if (json?.status === "ok" && !json?.is_scanning) {
        stopPolling();
        setParamsOpen(false);
      }
    }, 4000);
  };

  const triggerScan = async () => {
    setError(null); setLoading(true);
    try {
      const res = await fetch(`${API_URL}/scan`, {
        method:"POST",
        headers:{ "Content-Type":"application/json", "X-Api-Key":apiKey },
        body: JSON.stringify(params),
      });
      if (res.status === 401) { setError("Invalid API key. Enter your SCAN_API_KEY below."); setShowKeyInput(true); setLoading(false); return; }
      if (!res.ok) { const b = await res.json().catch(()=>{}); setError(b?.detail||`Server error ${res.status}`); setLoading(false); return; }
      startPolling();
    } catch(e) { setError(`Cannot reach backend at ${API_URL}. Check VITE_API_URL.`); setLoading(false); }
  };

  const triggerRefresh = async () => {
    setRefreshing(true); setRefreshMsg(null);
    try {
      const res = await fetch(`${API_URL}/refresh-universe`, {
        method:"POST",
        headers:{ "Content-Type":"application/json", "X-Api-Key":apiKey },
        body: JSON.stringify(params),
      });
      if (res.status === 401) { setRefreshMsg("Invalid API key."); setShowKeyInput(true); setRefreshing(false); return; }
      const json = await res.json();
      setRefreshMsg(json.message || "Universe refresh started (~15 min).");
      const poll = setInterval(async () => {
        try {
          const sr = await fetch(`${API_URL}/status`);
          const sj = await sr.json();
          if (!sj.is_refreshing) {
            clearInterval(poll); setRefreshing(false);
            const cnt = sj?.universe_cache?.count || 0;
            setRefreshMsg(cnt > 0 ? `Done \u2014 ${cnt} tickers in new universe` : "Refresh complete");
          }
        } catch(e) { clearInterval(poll); setRefreshing(false); }
      }, 10000);
    } catch(e) { setRefreshMsg(`Cannot reach backend: ${e.message}`); setRefreshing(false); }
  };

  useEffect(() => () => stopPolling(), []);

  const total = data ? ["long_calls","short_calls","long_puts","short_puts"].reduce((a,k)=>a+(data[k]?.length||0),0) : 0;

  return (
    <div style={{ minHeight:"100vh", background:T.bg, color:T.text }}>
      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=DM+Mono:wght@400;500;600&display=swap');
        *{box-sizing:border-box;margin:0;padding:0}
        @keyframes spin{to{transform:rotate(360deg)}}
        @keyframes up{from{opacity:0;transform:translateY(-5px)}to{opacity:1;transform:translateY(0)}}
        @keyframes scanSlide{0%{transform:translateX(-100%)}100%{transform:translateX(200%)}}
        ::-webkit-scrollbar{width:4px;height:4px}
        ::-webkit-scrollbar-thumb{background:${T.borderMid};border-radius:2px}
        input[type=number]::-webkit-inner-spin-button{opacity:0.4}
      `}</style>

      {/* Nav */}
      <div style={{ background:T.white, borderBottom:`1px solid ${T.border}`, padding:"0 28px", height:54, display:"flex", alignItems:"center", justifyContent:"space-between", boxShadow:"0 1px 3px rgba(0,0,0,0.04)" }}>
        <div style={{ display:"flex", alignItems:"center", gap:14 }}>
          <div style={{ width:30, height:30, borderRadius:7, background:T.text, display:"flex", alignItems:"center", justifyContent:"center" }}>
            <span style={{ color:T.white, fontSize:11, fontFamily:"monospace", fontWeight:700 }}>MS</span>
          </div>
          <span style={{ fontSize:18, fontWeight:700, color:T.text, letterSpacing:"-0.01em", fontFamily:"Georgia, serif" }}>MorningScan</span>
          <div style={{ width:1, height:16, background:T.border }} />
          <span style={{ fontSize:10, color:T.textMuted, fontFamily:"monospace", letterSpacing:"0.06em" }}>OPTIONS SCANNER · US EQUITIES</span>
        </div>
        <div style={{ display:"flex", alignItems:"center", gap:10 }}>
          {data && <span style={{ fontSize:11, color:T.textMuted, fontFamily:"monospace" }}>{new Date(data.scan_time).toLocaleTimeString([],{hour:"2-digit",minute:"2-digit"})} ET · {data.scanned} scanned · {total} candidates</span>}
          <button onClick={triggerScan} disabled={loading} style={{ background:loading?T.bgAlt:T.text, color:loading?T.textMuted:T.white, border:`1px solid ${loading?T.border:T.text}`, borderRadius:6, cursor:loading?"not-allowed":"pointer", padding:"8px 18px", fontFamily:"monospace", fontWeight:600, fontSize:11, letterSpacing:"0.06em", display:"flex", alignItems:"center", gap:8, boxShadow:loading?"none":"0 1px 3px rgba(0,0,0,0.1)" }}>
            {loading ? <><div style={{ width:10, height:10, border:`1.5px solid ${T.borderMid}`, borderTopColor:T.textMid, borderRadius:"50%", animation:"spin 0.8s linear infinite" }}/>SCANNING...</> : "\u25B6 RUN SCAN"}
          </button>
        </div>
      </div>

      <div style={{ maxWidth:1160, margin:"0 auto", padding:"24px 20px" }}>
        <div style={{ marginBottom:20 }}>
          <h1 style={{ fontSize:24, fontWeight:700, color:T.text, letterSpacing:"-0.02em", marginBottom:3, fontFamily:"Georgia, serif" }}>Pre-Market Options Scan</h1>
          <p style={{ fontSize:11, color:T.textMuted, fontFamily:"monospace" }}>
            {new Date().toLocaleDateString("en-US",{weekday:"long",year:"numeric",month:"long",day:"numeric"})}
            &nbsp;·&nbsp;DTE {params.dte_min}\u2013{params.dte_max}&nbsp;·&nbsp;4 strategies
          </p>
        </div>

        {showKeyInput && (
          <div style={{ background:T.amberBg, border:`1px solid ${T.amberBord}`, borderRadius:8, padding:"12px 16px", marginBottom:14, display:"flex", gap:10, alignItems:"center", flexWrap:"wrap" }}>
            <span style={{ fontSize:11, color:T.amber, fontFamily:"monospace", fontWeight:600 }}>Enter SCAN_API_KEY:</span>
            <input type="password" value={apiKey} onChange={e=>setApiKey(e.target.value)} placeholder="your-scan-api-key"
              style={{ flex:1, minWidth:200, padding:"6px 10px", borderRadius:5, border:`1px solid ${T.amberBord}`, fontFamily:"monospace", fontSize:12, background:T.white, outline:"none" }} />
            <button onClick={()=>{ setShowKeyInput(false); setError(null); triggerScan(); }}
              style={{ padding:"6px 14px", borderRadius:5, background:T.amber, color:T.white, border:"none", cursor:"pointer", fontFamily:"monospace", fontSize:11, fontWeight:700 }}>Retry</button>
          </div>
        )}

        {/* Parameters panel */}
        <div style={{ background:T.white, border:`1px solid ${T.border}`, borderRadius:10, marginBottom:14, boxShadow:"0 1px 4px rgba(0,0,0,0.04)", overflow:"hidden" }}>
          <div style={{ display:"flex", alignItems:"flex-start", justifyContent:"space-between", padding:"12px 18px", background:T.bgAlt, borderBottom:paramsOpen?`1px solid ${T.border}`:"none", flexWrap:"wrap", gap:10 }}>
            <div style={{ display:"flex", alignItems:"center", gap:10, cursor:"pointer", paddingTop:3 }} onClick={()=>setParamsOpen(o=>!o)}>
              <span style={{ fontSize:15, fontWeight:700, color:T.text, fontFamily:"Georgia, serif" }}>Scan Parameters</span>
              {unsaved>0 && <span style={{ fontSize:10, padding:"2px 8px", borderRadius:10, background:T.amberBg, color:T.amber, border:`1px solid ${T.amberBord}`, fontFamily:"monospace" }}>{unsaved} unsaved</span>}
              {unsaved===0 && fromFactory>0 && <span style={{ fontSize:10, padding:"2px 8px", borderRadius:10, background:T.greenBg, color:T.green, border:`1px solid ${T.greenBord}`, fontFamily:"monospace" }}>custom defaults</span>}
              <span style={{ color:T.textFaint, fontSize:11 }}>{paramsOpen?"\u25B2":"\u25BC"}</span>
            </div>
            <div style={{ display:"flex", alignItems:"flex-start", gap:8, flexWrap:"wrap" }}>
              {/* Refresh Universe */}
              <div style={{ display:"flex", flexDirection:"column", gap:4 }}>
                <button onClick={triggerRefresh} disabled={refreshing} style={{ padding:"5px 12px", borderRadius:5, cursor:refreshing?"not-allowed":"pointer", fontFamily:"monospace", fontSize:10, fontWeight:600, background:refreshing?T.bgAlt:T.blueBg, color:refreshing?T.textMuted:T.blue, border:`1px solid ${refreshing?T.border:T.blueBord}`, display:"flex", alignItems:"center", gap:6, whiteSpace:"nowrap" }}>
                  {refreshing
                    ? <><div style={{ width:8, height:8, border:`1.5px solid ${T.borderMid}`, borderTopColor:T.blue, borderRadius:"50%", animation:"spin 0.8s linear infinite" }}/>REFRESHING...</>
                    : "\u21BB Refresh Universe"}
                </button>
                <span style={{ fontSize:8, color:T.textFaint, fontFamily:"monospace", maxWidth:210, lineHeight:1.4 }}>
                  {refreshMsg || "~15 min \u00B7 analyzes 5,000+ assets to redefine universe"}
                </span>
              </div>
              {/* View Universe */}
              <button onClick={() => setShowUniverse(true)} style={{ padding:"5px 12px", borderRadius:5, cursor:"pointer", fontFamily:"monospace", fontSize:10, fontWeight:600, background:T.white, color:T.textMid, border:`1px solid ${T.border}`, whiteSpace:"nowrap" }}>
                {"\u2630"} View Universe
              </button>
              <div style={{ width:1, height:28, background:T.border }} />
              {unsaved>0 && <button onClick={()=>setParams({...saved})} style={{ padding:"5px 12px", borderRadius:5, cursor:"pointer", fontFamily:"monospace", fontSize:10, fontWeight:600, background:T.white, color:T.textMid, border:`1px solid ${T.border}` }}>{"\u21BA"} Revert</button>}
              <button onClick={()=>{ setParams({...FACTORY_DEFAULTS}); setSaved({...FACTORY_DEFAULTS}); }} style={{ padding:"5px 12px", borderRadius:5, cursor:"pointer", fontFamily:"monospace", fontSize:10, fontWeight:600, background:T.white, color:T.textMuted, border:`1px solid ${T.border}` }}>{"\u2298"} Factory Reset</button>
              <button onClick={handleSave} style={{ padding:"5px 14px", borderRadius:5, cursor:"pointer", fontFamily:"monospace", fontSize:10, fontWeight:700, background:flashSave?T.greenBg:T.text, color:flashSave?T.green:T.white, border:`1px solid ${flashSave?T.greenBord:T.text}`, transition:"all 0.2s", boxShadow:flashSave?"none":"0 1px 3px rgba(0,0,0,0.1)" }}>
                {flashSave ? "\u2713 Saved!" : "\u2B06 Save as Default"}
              </button>
            </div>
          </div>

          {paramsOpen && (
            <div style={{ padding:"14px 16px", display:"flex", flexDirection:"column", gap:10 }}>
              {/* Summary */}
              <div style={{ padding:"8px 14px", background:T.bgAlt, borderRadius:6, border:`1px solid ${T.border}`, display:"flex", flexWrap:"wrap", gap:"4px 16px" }}>
                {[
                  `Universe: Top${params.universe_size} \u00B7 IV>${params.universe_min_iv_pct}% \u00B7 Cap>$${params.universe_min_market_cap_b}B \u00B7 Vol>$${params.universe_min_dollar_vol_m}M \u00B7 Price>$${params.universe_min_price}`,
                  `DTE:${params.dte_min}\u2013${params.dte_max}d`,
                  `OI\u2265${params.min_atm_oi}`,
                  `S/R:${params.sr_min_touches}+/${params.sr_lookback_days}d`,
                  `Blackout:${params.earnings_blackout_days}d`,
                  `LC:RSI<${params.lc_rsi_max} IVR<${params.lc_ivr_max}`,
                  `SC:RSI>${params.sc_rsi_min} IVR>${params.sc_ivr_min}`,
                  `LP:RSI>${params.lp_rsi_min} IVR<${params.lp_ivr_max}`,
                  `SP:RSI<${params.sp_rsi_max} IVR>${params.sp_ivr_min}`,
                ].map((s,i) => <span key={i} style={{ fontSize:10, fontFamily:"monospace", color:T.textMid }}>{s}</span>)}
              </div>

              {PARAM_GROUPS.map(g => (
                <div key={g.label} style={{ border:`1px solid ${T.border}`, borderRadius:8, overflow:"hidden", borderLeft:`3px solid ${g.color}` }}>
                  <div style={{ padding:"8px 14px", background:T.bgAlt, borderBottom:`1px solid ${T.border}`, display:"flex", alignItems:"center", gap:10 }}>
                    <span style={{ fontSize:9, fontWeight:700, padding:"2px 8px", borderRadius:3, background:g.bg, color:g.color, border:`1px solid ${g.bord}`, fontFamily:"monospace", letterSpacing:"0.08em" }}>{g.label.toUpperCase()}</span>
                    {g.fields.filter(fd => params[fd.key] !== saved[fd.key]).length > 0 && (
                      <span style={{ fontSize:9, padding:"1px 6px", borderRadius:10, background:T.amberBg, color:T.amber, border:`1px solid ${T.amberBord}`, fontFamily:"monospace" }}>
                        {g.fields.filter(fd => params[fd.key] !== saved[fd.key]).length} modified
                      </span>
                    )}
                  </div>
                  <div style={{ padding:"12px 14px", display:"grid", gridTemplateColumns:"repeat(auto-fill, minmax(195px, 1fr))", gap:10, background:T.white }}>
                    {g.fields.map(field => <ParamField key={field.key} field={field} value={params[field.key]} savedValue={saved[field.key]} onChange={change} />)}
                  </div>
                </div>
              ))}

              <div style={{ padding:"8px 14px", background:T.bgAlt, borderRadius:6, border:`1px solid ${T.border}` }}>
                <span style={{ fontSize:10, color:T.textMuted, fontFamily:"monospace" }}>
                  {"\u2139"}&nbsp; Universe Pre-Filter settings take effect on the next <strong>{"\u21BB"} Refresh Universe</strong> run (auto: every Sunday midnight ET). Changes here do not affect the current scan universe until a refresh is triggered.
                </span>
              </div>
            </div>
          )}
        </div>

        {error && <div style={{ padding:"12px 16px", borderRadius:7, marginBottom:14, background:T.redBg, border:`1px solid ${T.redBord}`, color:T.red, fontSize:12, fontFamily:"monospace" }}>{"\u26A0"} {error}</div>}

        {loading && (
          <div style={{ background:T.white, border:`1px solid ${T.border}`, borderRadius:10, padding:"28px 24px", marginBottom:14 }}>
            <div style={{ display:"flex", alignItems:"center", gap:12, marginBottom:18 }}>
              <div style={{ width:14, height:14, border:`2px solid ${T.border}`, borderTopColor:T.textMid, borderRadius:"50%", animation:"spin 0.9s linear infinite" }} />
              <span style={{ fontSize:13, color:T.text, fontFamily:"monospace" }}>Scanning universe {"\u2014"} this takes 3{"\u2013"}5 minutes{"\u2026"}</span>
            </div>
            {LISTS.map((l,i) => (
              <div key={l.key} style={{ display:"flex", alignItems:"center", gap:12, marginBottom:8 }}>
                <span style={{ fontSize:10, width:68, flexShrink:0, fontFamily:"monospace", color:T.textMuted }}>{l.tag}</span>
                <div style={{ flex:1, height:4, background:T.bgAlt, borderRadius:2, border:`1px solid ${T.border}`, overflow:"hidden", position:"relative" }}>
                  <div style={{ position:"absolute", top:0, left:0, width:"40%", height:"100%", background:`linear-gradient(90deg, transparent, ${l.color}, transparent)`, borderRadius:2, opacity:0.6, animation:`scanSlide ${[1.8, 2.2, 1.6, 2.0][i]}s ease-in-out infinite`, animationDelay:`${i * 0.2}s` }} />
                </div>
              </div>
            ))}
          </div>
        )}

        {!loading && !data && !error && (
          <div style={{ background:T.white, border:`1px solid ${T.border}`, borderRadius:10, padding:"70px 40px", textAlign:"center" }}>
            <div style={{ width:48, height:48, borderRadius:10, background:T.bgAlt, border:`1px solid ${T.border}`, display:"flex", alignItems:"center", justifyContent:"center", margin:"0 auto 16px", fontSize:20, color:T.textFaint }}>{"\u2B21"}</div>
            <p style={{ fontSize:16, fontWeight:700, color:T.text, marginBottom:6, fontFamily:"Georgia, serif" }}>No scan results yet</p>
            <p style={{ fontSize:11, color:T.textMuted, marginBottom:24, fontFamily:"monospace" }}>Configure parameters above · Auto-runs daily at 8:30 am ET</p>
            <button onClick={triggerScan} style={{ background:T.text, color:T.white, border:"none", borderRadius:7, padding:"11px 26px", cursor:"pointer", fontFamily:"monospace", fontWeight:600, fontSize:12, letterSpacing:"0.06em", boxShadow:"0 2px 6px rgba(0,0,0,0.12)" }}>{"\u25B6"} RUN SCAN NOW</button>
          </div>
        )}

        {data && (
          <div style={{ display:"grid", gridTemplateColumns:"repeat(4,1fr)", gap:10, marginBottom:14, animation:"up 0.4s ease" }}>
            {[
              { l:"Universe Scanned", v:data.scanned, s:"liquid US equities + ETFs" },
              { l:"Total Candidates", v:total, s:"across all 4 strategies" },
              { l:"Scan Time", v:new Date(data.scan_time).toLocaleTimeString([],{hour:"2-digit",minute:"2-digit"}), s:"Eastern Time" },
              { l:"Parameters", v:fromFactory>0?"Custom":"Default", s:fromFactory>0?`${fromFactory} fields modified`:"factory defaults" },
            ].map(s => (
              <div key={s.l} style={{ padding:"13px 16px", background:T.white, border:`1px solid ${T.border}`, borderRadius:8, boxShadow:"0 1px 3px rgba(0,0,0,0.04)" }}>
                <div style={{ fontSize:9, color:T.textMuted, letterSpacing:"0.1em", textTransform:"uppercase", fontFamily:"monospace", marginBottom:4 }}>{s.l}</div>
                <div style={{ fontSize:20, fontWeight:700, color:T.text, fontFamily:"monospace", lineHeight:1 }}>{s.v}</div>
                <div style={{ fontSize:10, color:T.textFaint, marginTop:4, fontFamily:"monospace" }}>{s.s}</div>
              </div>
            ))}
          </div>
        )}

        {data && (
          <div style={{ animation:"up 0.35s ease" }}>
            {LISTS.map(l => <Panel key={l.key} list={l} stocks={data[l.key]||[]} />)}
            <div style={{ marginTop:8, padding:"10px 18px", background:T.white, border:`1px solid ${T.border}`, borderRadius:8, display:"flex", justifyContent:"space-between", flexWrap:"wrap", gap:8 }}>
              <span style={{ fontSize:10, color:T.textMuted, fontFamily:"monospace" }}>UOA = Unusual Options Activity · WR = Wick Rejection · Earnings blackout: short strategies only</span>
              <span style={{ fontSize:10, color:T.textFaint, fontFamily:"monospace" }}>Data via Polygon.io · Not financial advice</span>
            </div>
          </div>
        )}
      </div>

      {/* Universe Modal */}
      <UniverseModal
        isOpen={showUniverse}
        onClose={() => setShowUniverse(false)}
        apiUrl={API_URL}
        apiKey={apiKey}
      />
    </div>
  );
}

