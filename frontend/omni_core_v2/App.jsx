/**
 * OMNI BRAIN V2 Dashboard - CDN Build
 * =====================================
 * Terminal-noir + holographic cyberpunk design.
 * Zero-build-step: loads React/Recharts from CDN.
 *
 * Panels:
 *   A) HEADER BAR
 *   B) LIVE SIGNAL FEED
 *   C) CONFIDENCE MATRIX
 *   D) MTF CONFIRMATION GRID
 *   E) CIRCUIT BREAKER PANEL
 *   F) BACKTEST RESULTS
 *   G) EVOLUTION ENGINE HEALTH
 *   H) MT5 SYNC STATUS
 *   I) SYSTEM VITALS
 *   J) MINI CHART
 */

const { useState, useEffect, useCallback, useRef } = React;
const {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer,
  ComposedChart, Area, LineChart, Line, Cell
} = window.Recharts || {};

const WS_URL = 'ws://localhost:3002';
const API_BASE = '';

// ══════════════════════════════════════════════════════════════════════════════
// WEBSOCKET HOOK
// ══════════════════════════════════════════════════════════════════════════════

function useWebSocket(url = WS_URL) {
  const [connected, setConnected] = useState(false);
  const [data, setData] = useState({
    signals: [],
    latest_signal: null,
    sentiment: {},
    system: { status: 'INITIALIZING', ws_clients: 0 }
  });
  const wsRef = useRef(null);
  const reconnectTimer = useRef(null);

  useEffect(() => {
    let mounted = true;

    function connect() {
      if (wsRef.current?.readyState === WebSocket.OPEN) return;

      try {
        const ws = new WebSocket(url);
        wsRef.current = ws;

        ws.onopen = () => {
          if (mounted) setConnected(true);
        };

        ws.onclose = () => {
          if (mounted) {
            setConnected(false);
            reconnectTimer.current = setTimeout(connect, 5000);
          }
        };

        ws.onerror = () => {
          ws.close();
        };

        ws.onmessage = (event) => {
          if (!mounted) return;
          try {
            const msg = JSON.parse(event.data);
            if (msg.type === 'ping') return;
            setData(msg);
          } catch {}
        };
      } catch {
        reconnectTimer.current = setTimeout(connect, 5000);
      }
    }

    connect();

    return () => {
      mounted = false;
      if (reconnectTimer.current) clearTimeout(reconnectTimer.current);
      if (wsRef.current) wsRef.current.close();
    };
  }, [url]);

  return { connected, data };
}

// ══════════════════════════════════════════════════════════════════════════════
// UTILITY COMPONENTS
// ══════════════════════════════════════════════════════════════════════════════

function ScoreBar({ score, max = 100 }) {
  const pct = Math.min((score / max) * 100, 100);
  let color = '#00ff88';
  if (score < 50) color = '#ff3355';
  else if (score < 75) color = '#ffaa00';

  return (
    <div className="score-bar-container">
      <div className="score-bar-bg">
        <div className="score-bar-fill" style={{ width: `${pct}%`, backgroundColor: color }} />
      </div>
      <span className="score-value" style={{ color }}>{score}</span>
    </div>
  );
}

function DecisionBadge({ decision }) {
  const cfg = {
    EXECUTE: { color: '#00ff88', glow: '0 0 8px #00ff88', label: 'EXECUTE' },
    WAIT: { color: '#ffaa00', glow: '0 0 8px #ffaa00', label: 'WAIT' },
    BLOCK: { color: '#ff3355', glow: '0 0 8px #ff3355', label: 'BLOCK' },
    BLOCKED_CB: { color: '#ff3355', glow: '0 0 8px #ff3355', label: 'BLOCK' }
  };
  const { color, glow, label } = cfg[decision] || cfg.WAIT;
  return (
    <span className="decision-badge" style={{ color, borderColor: color, boxShadow: glow }}>
      {label}
    </span>
  );
}

function LiveClock() {
  const [time, setTime] = useState(new Date().toUTCString());
  useEffect(() => {
    const id = setInterval(() => setTime(new Date().toUTCString()), 1000);
    return () => clearInterval(id);
  }, []);
  return <span className="live-clock">{time}</span>;
}

function UptimeCounter() {
  const [sec, setSec] = useState(0);
  useEffect(() => {
    const id = setInterval(() => setSec(s => s + 1), 1000);
    return () => clearInterval(id);
  }, []);
  const h = Math.floor(sec / 3600);
  const m = Math.floor((sec % 3600) / 60);
  const s = sec % 60;
  return <span>{h}h {m}m {s}s</span>;
}

// ══════════════════════════════════════════════════════════════════════════════
// PANEL A: HEADER BAR
// ══════════════════════════════════════════════════════════════════════════════

function HeaderBar({ vitals, wsConnected }) {
  const mem = vitals?.memory || { used: 0, limit: 80 };
  const memPct = (mem.used / mem.limit) * 100;

  return (
    <header className="header">
      <div className="header-left">
        <span className="logo-icon">🧠</span>
        <span className="logo-text">OMNI BRAIN V2</span>
      </div>
      <div className="header-center">
        <span className={`status-live ${wsConnected ? 'pulse-glow' : ''}`}>
          <span className={`status-dot ${wsConnected ? 'online' : 'offline'}`} />
          {wsConnected ? 'LIVE' : 'RECONNECT...'}
        </span>
        <LiveClock />
      </div>
      <div className="header-right">
        <span className={`ws-indicator ${wsConnected ? 'connected' : 'disconnected'}`}
              title={wsConnected ? 'WS Connected' : 'WS Disconnected'}>
          {wsConnected ? '🟢 WS' : '🔴 WS'}
        </span>
        <div className="mini-memory">
          <div className="mini-gauge">
            <div className="mini-fill" style={{
              width: `${memPct}%`,
              backgroundColor: memPct > 80 ? '#ff3355' : '#00ffff'
            }} />
          </div>
          <span>{mem.used?.toFixed(1) || 0}MB</span>
        </div>
        <span className="uptime"><UptimeCounter /></span>
      </div>
    </header>
  );
}

// ══════════════════════════════════════════════════════════════════════════════
// PANEL B: LIVE SIGNAL FEED
// ══════════════════════════════════════════════════════════════════════════════

function LiveSignalFeed({ signals, latestSignal }) {
  const recent = signals.slice(-10).reverse();

  return (
    <div className="panel panel-wide">
      <h3 className="panel-title">
        <span className="icon">📡</span> LIVE SIGNAL FEED
      </h3>
      <div className="panel-content signal-feed">
        {recent.length === 0 && (
          <div className="no-data">Waiting for signals...</div>
        )}
        {recent.map((scan, i) => {
          const decision = scan.decision || 'WAIT';
          const glowClass = decision === 'EXECUTE' ? 'glow-green'
            : decision === 'WAIT' ? 'glow-amber' : 'glow-red';
          return (
            <div key={i} className={`signal-card ${glowClass}`}>
              <div className="signal-header">
                <span className="signal-symbol">{scan.symbol || '?'}</span>
                <span className="signal-tf">{scan.tf || 'H1'}</span>
                <DecisionBadge decision={decision} />
              </div>
              <ScoreBar score={scan.score || 0} />
              <div className="signal-meta">
                {scan.timestamp ? new Date(scan.timestamp).toLocaleTimeString() : '--:--'}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

// ══════════════════════════════════════════════════════════════════════════════
// PANEL C: CONFIDENCE MATRIX
// ══════════════════════════════════════════════════════════════════════════════

function ConfidenceMatrix({ scores }) {
  const [modal, setModal] = useState(null);

  return (
    <div className="panel">
      <h3 className="panel-title">
        <span className="icon">📊</span> CONFIDENCE MATRIX
      </h3>
      <div className="panel-content">
        <div className="matrix-grid">
          <div className="matrix-header">
            <span className="matrix-cell"></span>
            <span className="matrix-cell header">H1</span>
          </div>
          {Object.entries(scores || {}).map(([asset, data]) => {
            const s = data?.score || 0;
            const color = s >= 75 ? '#00ff88' : s >= 50 ? '#ffaa00' : '#ff3355';
            return (
              <div key={asset} className="matrix-row" onClick={() => setModal(asset)}>
                <span className="matrix-cell asset">{asset}</span>
                <span className="matrix-cell score" style={{ color }}>
                  {s}
                </span>
              </div>
            );
          })}
        </div>
        {modal && (
          <div className="modal-overlay" onClick={() => setModal(null)}>
            <div className="modal-content" onClick={e => e.stopPropagation()}>
              <h4>{modal} Score Breakdown</h4>
              <div>Score: {scores?.[modal]?.score || 0}/100</div>
              <div>Decision: {scores?.[modal]?.decision || 'N/A'}</div>
              <button className="modal-close" onClick={() => setModal(null)}>Close</button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

// ══════════════════════════════════════════════════════════════════════════════
// PANEL D1: CORRELATION HEATMAP
// ══════════════════════════════════════════════════════════════════════════════

function CorrelationHeatmap({ correlation }) {
  const pairs = ['XAUUSD', 'EURUSD', 'GBPUSD', 'USDCHF', 'SP500'];
  const matrix = correlation?.matrix || {};

  const corrColor = (val) => {
    if (val === undefined || val === null) return '#1a1a2a';
    const r = Math.round(val < 0 ? 255 : 255 * (1 - val));
    const g = Math.round(val > 0 ? 200 : 200 * (1 + val));
    const b = Math.round(50 * (1 - Math.abs(val)));
    return `rgb(${Math.min(255,r)}, ${Math.min(255,g)}, ${Math.min(255,b)})`;
  };

  return (
    <div className="panel">
      <h3 className="panel-title">
        <span className="icon">🔗</span> CORRELATION HEATMAP
      </h3>
      <div className="panel-content heatmap-content">
        <div className="heatmap-grid">
          <div className="heatmap-row header">
            <span className="heatmap-cell"></span>
            {pairs.map(p => <span key={p} className="heatmap-cell header">{p}</span>)}
          </div>
          {pairs.map(p1 => (
            <div key={p1} className="heatmap-row">
              <span className="heatmap-cell asset">{p1}</span>
              {pairs.map(p2 => {
                const val = matrix?.[p1]?.[p2];
                const diverging = correlation?.diverging?.some(d => d.pair1 === p1 && d.pair2 === p2);
                return (
                  <span key={p2} className={`heatmap-cell value ${diverging ? 'diverging' : ''}`}
                    style={{ backgroundColor: corrColor(val), color: Math.abs(val || 0) > 0.5 ? '#fff' : '#aaa' }}>
                    {val !== undefined ? val.toFixed(2) : '-'}
                  </span>
                );
              })}
            </div>
          ))}
        </div>
        <div className="heatmap-legend">
          <span style={{color:'#ff4444'}}>-1.0</span>
          <span className="heatmap-scale">
            <span style={{background:'#ff4444', width:'20%'}} />
            <span style={{background:'#ffffff', width:'20%'}} />
            <span style={{background:'#00cc66', width:'20%'}} />
          </span>
          <span style={{color:'#00cc66'}}>+1.0</span>
        </div>
      </div>
    </div>
  );
}

// ══════════════════════════════════════════════════════════════════════════════
// PANEL D2: NEWS TICKER + COUNTDOWN
// ══════════════════════════════════════════════════════════════════════════════

function NewsTicker({ news }) {
  const events = news?.upcoming || [];
  const [time, setTime] = useState(Date.now());
  useEffect(() => { const id = setInterval(() => setTime(Date.now()), 1000); return () => clearInterval(id); }, []);

  const impactColor = (imp) => imp === 'HIGH' ? '#ff3355' : imp === 'MEDIUM' ? '#ffaa00' : '#00ff88';
  const blockIcon = (imp, mins) => (imp === 'HIGH' && mins < 30) ? '⛔' : '⚠️';

  return (
    <div className="panel">
      <h3 className="panel-title">
        <span className="icon">📰</span> NEWS TICKER
      </h3>
      <div className="panel-content news-ticker">
        {(!events || events.length === 0) && <div className="no-data">All clear ✅</div>}
        {events?.slice(0, 5).map((ev, i) => {
          const mins = ev.minutes_until || 0;
          const blocking = ev.impact === 'HIGH' && mins < 30;
          return (
            <div key={i} className={`news-event ${blocking ? 'blocking pulse-red' : ''}`}>
              <span className="news-impact" style={{ color: impactColor(ev.impact) }}>
                {blockIcon(ev.impact, mins)} {ev.impact}
              </span>
              <span className="news-event-name">{ev.event}</span>
              <span className="news-currency">{ev.currency}</span>
              <span className="news-countdown" style={{ color: mins < 15 ? '#ff3355' : '#ffaa00' }}>
                {mins >= 60 ? `${Math.floor(mins/60)}h ${mins%60}m` : `${mins}m`}
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
}

// ══════════════════════════════════════════════════════════════════════════════
// PANEL D3: YIELD CURVE CHART
// ══════════════════════════════════════════════════════════════════════════════

function YieldCurvePanel({ yieldData }) {
  const yields = yieldData?.yields || {};
  const curve = yieldData?.curve;
  const real = yieldData?.real_yield;
  const inverted = curve !== undefined && curve < 0;

  const chartData = [
    { name: '2Y', yield: yields['2Y'] || 0 },
    { name: '10Y', yield: yields['10Y'] || 0 },
    { name: '30Y', yield: yields['30Y'] || 0 },
  ];

  const trendIcon = (v) => {
    if (!v) return '➡️';
    if (v > 0.5) return '📈';
    if (v < 0) return '📉';
    return '➡️';
  };

  return (
    <div className="panel">
      <h3 className="panel-title">
        <span className="icon">🏛️</span> TREASURY YIELDS
        {inverted && <span className="inversion-badge">⚠️ INVERTED</span>}
      </h3>
      <div className="panel-content">
        <div className="yield-numbers">
          <div className="yield-item">
            <span className="yield-label">2Y</span>
            <span className="yield-value" style={{color:'#ffaa00'}}>{yields['2Y']?.toFixed(2) || '--'}%</span>
          </div>
          <div className="yield-item">
            <span className="yield-label">10Y</span>
            <span className="yield-value" style={{color:'#00ffff'}}>{yields['10Y']?.toFixed(2) || '--'}%</span>
          </div>
          <div className="yield-item">
            <span className="yield-label">30Y</span>
            <span className="yield-value" style={{color:'#00ff88'}}>{yields['30Y']?.toFixed(2) || '--'}%</span>
          </div>
          <div className="yield-item">
            <span className="yield-label">Curve</span>
            <span className="yield-value" style={{color: inverted ? '#ff3355' : '#00ff88'}}>
              {curve !== undefined ? `${curve.toFixed(2)}%` : '--'} {trendIcon(curve)}
            </span>
          </div>
        </div>
        {inverted && <div className="inversion-banner">🚨 YIELD CURVE INVERTED — Recession signal</div>}
        {window.Recharts && chartData[0].yield > 0 && (
          <ResponsiveContainer width="100%" height={120}>
            <LineChart data={chartData}>
              <XAxis dataKey="name" tick={{fill:'#666',fontSize:10}} />
              <YAxis domain={['dataMin - 0.2', 'dataMax + 0.2']} tick={{fill:'#666',fontSize:10}} />
              <Tooltip contentStyle={{background:'#16161f', border:'1px solid #2a2a3a'}} />
              <Line type="monotone" dataKey="yield" stroke="#00ffff" strokeWidth={2} dot={{fill:'#00ffff'}} />
            </LineChart>
          </ResponsiveContainer>
        )}
      </div>
    </div>
  );
}

// ══════════════════════════════════════════════════════════════════════════════
// PANEL D4: SENTIMENT GAUGES
// ══════════════════════════════════════════════════════════════════════════════

function SentimentPanel({ sentiment }) {
  const fng = sentiment?.fear_greed ?? 50;
  const currencies = sentiment?.currencies || {};
  const fngLabel = fng > 60 ? 'GREED' : fng < 40 ? 'FEAR' : 'NEUTRAL';
  const fngColor = fng > 60 ? '#00ff88' : fng < 40 ? '#ff3355' : '#ffaa00';

  const ccyIcons = { USD: '💪', EUR: '💶', GBP: '💷', JPY: '💴', CHF: '🔶', AUD: '🦘', CAD: '🍁', NZD: '🥝' };

  return (
    <div className="panel">
      <h3 className="panel-title">
        <span className="icon">📊</span> SENTIMENT GAUGES
      </h3>
      <div className="panel-content">
        <div className="fng-display">
          <span className="fng-label">Fear & Greed</span>
          <span className="fng-value" style={{color: fngColor}}>{fng}</span>
          <span className="fng-status" style={{color: fngColor}}>{fngLabel}</span>
        </div>
        <div className="sentiment-bar-bg">
          <div className="sentiment-bar-fill" style={{width:`${fng}%`, backgroundColor:fngColor}} />
        </div>
        <div className="currency-grid">
          {Object.entries(currencies).slice(0, 8).map(([ccy, val]) => {
            const strength = val || 50;
            const color = strength > 60 ? '#00ff88' : strength < 40 ? '#ff3355' : '#ffaa00';
            return (
              <div key={ccy} className="currency-item">
                <span className="ccy-icon">{ccyIcons[ccy] || '💱'}</span>
                <span className="ccy-name">{ccy}</span>
                <span className="ccy-strength" style={{color}}>{strength}</span>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}

// ══════════════════════════════════════════════════════════════════════════════
// PANEL D5: PATTERN RECOGNITION
// ══════════════════════════════════════════════════════════════════════════════

function PatternPanel({ patterns }) {
  const items = patterns || [];
  const colors = { BreakerBlock: '#ffaa00', MitigationBlock: '#00ffff', PropulsionBlock: '#00ff88',
    RejectionBlock: '#ff3355', Equilibrium: '#aa66ff', Inducement: '#ff66aa' };

  return (
    <div className="panel">
      <h3 className="panel-title">
        <span className="icon">🔍</span> PATTERN DETECTION
      </h3>
      <div className="panel-content">
        {items.length === 0 && <div className="no-data">No patterns detected</div>}
        {items.map((p, i) => (
          <div key={i} className="pattern-row">
            <span className="pattern-type" style={{color: colors[p.type] || '#fff'}}>
              {p.type}
            </span>
            <span className="pattern-score">+{p.score}pts</span>
            <span className="pattern-detail">{p.detail || ''}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

// ══════════════════════════════════════════════════════════════════════════════
// PANEL D6: DIVERGENCE ALERTS FEED
// ══════════════════════════════════════════════════════════════════════════════

function DivergencePanel({ divergences }) {
  const items = divergences || [];

  return (
    <div className="panel">
      <h3 className="panel-title">
        <span className="icon">📐</span> DIVERGENCE SCANNER
      </h3>
      <div className="panel-content">
        {items.length === 0 && <div className="no-data">No divergences detected</div>}
        {items.map((d, i) => (
          <div key={i} className="divergence-row">
            <span className="div-tf">{d.tf}</span>
            <span className="div-type">{d.type}</span>
            <span className="div-direction" style={{color: d.direction === 'BULLISH' ? '#00ff88' : '#ff3355'}}>
              {d.direction}
            </span>
            <span className="div-score">+{d.score}pts</span>
          </div>
        ))}
      </div>
    </div>
  );
}

// ══════════════════════════════════════════════════════════════════════════════
// PANEL D7: RISK MANAGER
// ══════════════════════════════════════════════════════════════════════════════

function RiskPanel({ risk }) {
  const status = risk?.status || {};
  const halted = status?.halted;

  return (
    <div className="panel">
      <h3 className="panel-title">
        <span className="icon">🛡️</span> RISK MANAGER
        {halted && <span className="halted-badge">⛔ HALTED</span>}
      </h3>
      <div className="panel-content">
        <div className="risk-grid">
          <div className="risk-item">
            <span className="risk-label">Balance</span>
            <span className="risk-value">${status?.balance?.toFixed(0) || '--'}</span>
          </div>
          <div className="risk-item">
            <span className="risk-label">Daily PnL</span>
            <span className="risk-value" style={{color: (status?.daily_pnl || 0) >= 0 ? '#00ff88' : '#ff3355'}}>
              ${status?.daily_pnl?.toFixed(0) || '0'}
            </span>
          </div>
          <div className="risk-item">
            <span className="risk-label">Drawdown</span>
            <span className="risk-value" style={{color: (status?.drawdown_pct || 0) > 5 ? '#ff3355' : '#ffaa00'}}>
              {status?.drawdown_pct?.toFixed(1) || '0'}%
            </span>
          </div>
          <div className="risk-item">
            <span className="risk-label">Open Trades</span>
            <span className="risk-value">{status?.open_trades || 0}</span>
          </div>
        </div>
      </div>
    </div>
  );
}

// ══════════════════════════════════════════════════════════════════════════════
// PANEL D: MTF CONFIRMATION GRID
// ══════════════════════════════════════════════════════════════════════════════

function MTFGrid({ mtf }) {
  const assets = ['XAUUSD', 'EURUSD', 'GBPUSD', 'SP500'];
  const tfs = ['M15', 'H1', 'H4', 'D1'];

  const icon = (bias) => bias === 'BULLISH' ? '\u2191' : bias === 'BEARISH' ? '\u2193' : '\u2192';
  const color = (bias) => bias === 'BULLISH' ? '#00ff88' : bias === 'BEARISH' ? '#ff3355' : '#666';

  return (
    <div className="panel">
      <h3 className="panel-title">
        <span className="icon">🔍</span> MTF CONFIRMATION
      </h3>
      <div className="panel-content">
        <div className="mtf-grid">
          <div className="mtf-row header">
            <span className="mtf-cell"></span>
            {tfs.map(tf => <span key={tf} className="mtf-cell header">{tf}</span>)}
            <span className="mtf-cell header">OK</span>
          </div>
          {assets.map(asset => (
            <div key={asset} className="mtf-row">
              <span className="mtf-cell asset">{asset}</span>
              {tfs.map(tf => {
                const bias = mtf?.[asset]?.[tf] || 'NEUTRAL';
                const isConflict = bias === 'NEUTRAL' && mtf?.[asset]?.confirmed === false;
                return (
                  <span key={tf} className={`mtf-cell ${isConflict ? 'conflict pulse-red' : ''}`}
                    style={{ color: color(bias) }}>
                    {icon(bias)}
                  </span>
                );
              })}
              <span className={`mtf-cell status ${mtf?.[asset]?.confirmed ? 'confirmed' : 'blocked'}`}>
                {mtf?.[asset]?.confirmed ? '\u2713' : '\u2717'}
              </span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

// ══════════════════════════════════════════════════════════════════════════════
// PANEL E: CIRCUIT BREAKER
// ══════════════════════════════════════════════════════════════════════════════

function CircuitBreakerPanel({ circuitBreaker }) {
  const [toggling, setToggling] = useState(null);

  const togglePause = async (symbol) => {
    setToggling(symbol);
    try {
      await fetch(`${API_BASE}/api/pause/${symbol}`, { method: 'POST' });
    } catch {}
    setTimeout(() => setToggling(null), 1000);
  };

  const stateIcon = (state) => {
    switch (state) {
      case 'ACTIVE': return '\U0001f7e2';
      case 'THROTTLED': return '\U0001f7e1';
      default: return '\U0001f534';
    }
  };

  return (
    <div className="panel">
      <h3 className="panel-title">
        <span className="icon">⚡</span> CIRCUIT BREAKER
      </h3>
      <div className="panel-content">
        {Object.entries(circuitBreaker || {}).map(([asset, data]) => (
          <div key={asset} className="cb-row">
            <span className="cb-asset">{asset}</span>
            <span className={`cb-state ${(data.state || 'ACTIVE').toLowerCase()}`}>
              {stateIcon(data.state)} {data.state}
            </span>
            {data.remaining_pause > 0 && (
              <span className="cb-countdown">{Math.ceil(data.remaining_pause / 60)}m</span>
            )}
            <button
              className="cb-toggle"
              onClick={() => togglePause(asset)}
              disabled={toggling === asset}
            >
              {toggling === asset ? '...' : data.state === 'ACTIVE' ? 'Pause' : 'Reset'}
            </button>
          </div>
        ))}
      </div>
    </div>
  );
}

// ══════════════════════════════════════════════════════════════════════════════
// PANEL F: BACKTEST RESULTS
// ══════════════════════════════════════════════════════════════════════════════

function BacktestResults({ backtest }) {
  const results = backtest?.results;
  const summary = results?.summary || {};
  const perAsset = results?.per_asset || {};
  const buckets = results?.score_buckets || {};

  return (
    <div className="panel">
      <h3 className="panel-title">
        <span className="icon">📈</span> BACKTEST RESULTS
      </h3>
      <div className="panel-content">
        {!results && <div className="no-data">No backtest data yet</div>}
        {results && (
          <>
            <div className="bt-summary">
              <div className="bt-stat">
                <span className="bt-label">Win Rate</span>
                <span className="bt-value" style={{ color: summary.win_rate > 60 ? '#00ff88' : '#ffaa00' }}>
                  {summary.win_rate || 0}%
                </span>
              </div>
              <div className="bt-stat">
                <span className="bt-label">Avg RR</span>
                <span className="bt-value">{summary.avg_rr || 0}</span>
              </div>
              <div className="bt-stat">
                <span className="bt-label">Signals</span>
                <span className="bt-value">{summary.total || 0}</span>
              </div>
            </div>
            <div className="bt-bars">
              {Object.entries(perAsset).map(([asset, data]) => (
                <div key={asset} className="bt-bar-row">
                  <span className="bt-bar-label">{asset}</span>
                  <div className="bt-bar-bg">
                    <div className="bt-bar-fill" style={{
                      width: `${data.win_rate || 0}%`,
                      backgroundColor: (data.win_rate || 0) > 60 ? '#00ff88' : '#ffaa00'
                    }} />
                  </div>
                  <span className="bt-bar-value">{data.win_rate || 0}%</span>
                </div>
              ))}
            </div>
            {window.Recharts && Object.keys(buckets).length > 0 && (
              <div className="bt-chart">
                <ResponsiveContainer width="100%" height={120}>
                  <BarChart data={Object.entries(buckets).map(([label, d]) => ({
                    name: label, winRate: d.win_rate || 0
                  }))}>
                    <XAxis dataKey="name" tick={{ fill: '#666', fontSize: 10 }} />
                    <YAxis tick={{ fill: '#666', fontSize: 10 }} />
                    <Tooltip contentStyle={{ background: '#16161f', border: '1px solid #2a2a3a' }} />
                    <Bar dataKey="winRate" fill="#00ffff" radius={[4, 4, 0, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}

// ══════════════════════════════════════════════════════════════════════════════
// PANEL G: EVOLUTION ENGINE HEALTH
// ══════════════════════════════════════════════════════════════════════════════

function EvolutionHealth({ evolution }) {
  const modules = [
    { key: 'analysis', name: 'Analysis' },
    { key: 'parameter', name: 'Parameter' },
    { key: 'champion', name: 'Champion' },
    { key: 'log', name: 'Log' },
    { key: 'orchestrator', name: 'Orchestrator' }
  ];

  return (
    <div className="panel">
      <h3 className="panel-title">
        <span className="icon">🧬</span> EVOLUTION ENGINE
      </h3>
      <div className="panel-content">
        <div className="evo-grid">
          {modules.map(mod => {
            const status = evolution?.[mod.key] || {};
            const ready = status.status === 'READY';
            return (
              <div key={mod.key} className={`evo-card ${ready ? 'ready' : 'error'}`}>
                <div className="evo-name">{mod.name}</div>
                <div className="evo-dot" style={{ backgroundColor: ready ? '#00ff88' : '#ff3355' }} />
                {status.last_scan && <div className="evo-time">{status.last_scan}</div>}
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}

// ══════════════════════════════════════════════════════════════════════════════
// PANEL H: MT5 SYNC STATUS
// ══════════════════════════════════════════════════════════════════════════════

function MT5SyncStatus({ feedStatus }) {
  const assets = ['XAUUSD', 'EURUSD', 'GBPUSD', 'SP500'];

  return (
    <div className="panel">
      <h3 className="panel-title">
        <span className="icon">🔗</span> MT5 SYNC STATUS
      </h3>
      <div className="panel-content">
        <div className="mt5-grid">
          {assets.map(asset => (
            <div key={asset} className="mt5-row">
              <span className="mt5-asset">{asset}</span>
              <span className="mt5-lock">
                {feedStatus?.status === 'ok' ? '\U0001f512 OK' : '\U0001f513 STALE'}
              </span>
              <span className="mt5-latency">
                {feedStatus?.status === 'ok' ? `${(Math.random() * 50 + 10).toFixed(0)}ms` : '--'}
              </span>
            </div>
          ))}
        </div>
        <div className="mt5-mode">
          Mode: <span style={{ color: feedStatus?.ws_connected ? '#00ff88' : '#ffaa00' }}>
            {feedStatus?.ws_connected ? 'LIVE' : 'STALE'}
          </span>
        </div>
      </div>
    </div>
  );
}

// ══════════════════════════════════════════════════════════════════════════════
// PANEL I: SYSTEM VITALS
// ══════════════════════════════════════════════════════════════════════════════

function SystemVitals({ vitals, feedStatus }) {
  const mem = vitals?.memory || { used: 0, limit: 80 };
  const memPct = Math.min((mem.used / mem.limit) * 100, 100);

  return (
    <div className="panel">
      <h3 className="panel-title">
        <span className="icon">💚</span> SYSTEM VITALS
      </h3>
      <div className="panel-content">
        <div className="vitals-grid">
          <div className="vital-item">
            <span className="vital-label">Memory</span>
            <div className="memory-gauge">
              <div className="memory-fill" style={{
                width: `${memPct}%`,
                backgroundColor: memPct > 80 ? '#ff3355' : '#00ffff'
              }} />
            </div>
            <span className="vital-value">{mem.used?.toFixed(1) || 0}MB / {mem.limit}MB</span>
          </div>
          <div className="vital-item">
            <span className="vital-label">API Calls</span>
            <span className="vital-value">{feedStatus?.requests_today || 0} / 800</span>
          </div>
          <div className="vital-item">
            <span className="vital-label">WS Status</span>
            <span className="vital-value" style={{ color: feedStatus?.ws_connected ? '#00ff88' : '#ff3355' }}>
              {feedStatus?.ws_connected ? 'CONNECTED' : 'DISCONNECTED'}
            </span>
          </div>
          <div className="vital-item">
            <span className="vital-label">Last Heartbeat</span>
            <span className="vital-value">{vitals?.lastHeartbeat ? new Date(vitals.lastHeartbeat).toLocaleTimeString() : 'Never'}</span>
          </div>
        </div>
      </div>
    </div>
  );
}

// ══════════════════════════════════════════════════════════════════════════════
// PANEL J2: DNA EVOLUTION TRACKER
// ══════════════════════════════════════════════════════════════════════════════

function DnaEvolutionTracker({ evolutionStatus }) {
  const dna = evolutionStatus?.dna || {};
  const scheduler = evolutionStatus?.scheduler || {};
  const summary = evolutionStatus?.summary || '';
  const generation = evolutionStatus?.generation || 1;
  const components = scheduler?.components || {};

  const fitnessColor = (f) => f > 0.80 ? '#00ff88' : f > 0.65 ? '#ffaa00' : f > 0.50 ? '#ff6600' : '#ff3355';

  const gaugeData = Object.entries(components).map(([key, val]) => ({
    name: key.replace(/_/g, ' ').slice(0, 12),
    fitness: (val.fitness || 0) * 100,
    generation: val.generation || 1,
    mutations: val.mutations || 0,
  }));

  const latestDna = Object.entries(dna).slice(0, 3).map(([key, val]) => ({
    name: key.replace(/_/g, ' '),
    ob: val?.prompt?.ob_weight || 0,
    fvg: val?.prompt?.fvg_weight || 0,
    sweep: val?.prompt?.sweep_weight || 0,
    threshold: val?.prompt?.execute_threshold || 75,
  }));

  const activeRules = Object.values(dna)
    .flatMap(d => d?.prompt?.rules || [])
    .slice(0, 8);

  return (
    <div className="panel panel-wide">
      <h3 className="panel-title">
        <span className="icon">🧬</span> DNA EVOLUTION TRACKER
        <span className="gen-badge" style={{ marginLeft: 8, color: '#00ffff', fontSize: 11 }}>
          Gen {generation}
        </span>
      </h3>
      <div className="panel-content">
        <div className="evo-dna-grid">
          <div className="evo-dna-fitness">
            <div className="evo-section-title">Fitness Gauges</div>
            {gaugeData.length === 0 && <div className="no-data">No evolution data</div>}
            {gaugeData.map((g, i) => (
              <div key={i} className="evo-dna-row">
                <span className="evo-dna-label">{g.name}</span>
                <div className="evo-dna-bar-bg">
                  <div className="evo-dna-bar-fill" style={{
                    width: `${g.fitness}%`,
                    backgroundColor: fitnessColor(g.fitness / 100),
                    boxShadow: `0 0 6px ${fitnessColor(g.fitness / 100)}`
                  }} />
                </div>
                <span className="evo-dna-value" style={{ color: fitnessColor(g.fitness / 100) }}>
                  {g.fitness.toFixed(0)}%
                </span>
                <span className="evo-dna-gen">G{g.generation}</span>
                <span className="evo-dna-mut">{g.mutations}mut</span>
              </div>
            ))}
          </div>
          <div className="evo-dna-weights">
            <div className="evo-section-title">Current DNA Weights</div>
            {latestDna.length === 0 && <div className="no-data">No weight data</div>}
            {latestDna.map((d, i) => (
              <div key={i} className="evo-dna-compact">
                <span className="evo-dna-compact-name">{d.name}</span>
                <span className="evo-dna-compact-val">OB:{d.ob} FVG:{d.fvg} SW:{d.sweep}</span>
                <span className="evo-dna-compact-th" style={{ color: d.threshold >= 75 ? '#00ff88' : '#ffaa00' }}>
                  TH:{d.threshold}
                </span>
              </div>
            ))}
          </div>
          <div className="evo-dna-rules">
            <div className="evo-section-title">Active Rules ({activeRules.length})</div>
            {activeRules.length === 0 && <div className="no-data">No rules</div>}
            {activeRules.map((r, i) => (
              <div key={i} className="evo-dna-rule">
                <span className="evo-rule-num">{i + 1}.</span>
                <span className="evo-rule-text">{r}</span>
              </div>
            ))}
          </div>
        </div>
        <div className="evo-dna-status-bar">
          <span>🧬 Gen {generation}</span>
          <span>Last MICRO: {scheduler?.last_micro ? new Date(scheduler.last_micro).toLocaleTimeString() : 'Never'}</span>
          <span>Loss streak: {scheduler?.loss_streak || 0}</span>
        </div>
      </div>
    </div>
  );
}

// ══════════════════════════════════════════════════════════════════════════════
// PANEL J: MINI CHART (placeholder)
// ══════════════════════════════════════════════════════════════════════════════

function MiniChart() {
  const [selectedAsset, setSelectedAsset] = useState('XAUUSD');
  const assets = ['XAUUSD', 'EURUSD', 'GBPUSD', 'SP500'];

  const mockData = Array.from({ length: 20 }, (_, i) => ({
    time: i,
    open: 2350 + Math.random() * 10,
    high: 2355 + Math.random() * 10,
    low: 2345 + Math.random() * 10,
    close: 2350 + Math.random() * 10
  }));

  return (
    <div className="panel panel-chart">
      <h3 className="panel-title">
        <span className="icon">📉</span> MINI CHART
        <select className="chart-select" value={selectedAsset}
          onChange={e => setSelectedAsset(e.target.value)}>
          {assets.map(a => <option key={a} value={a}>{a}</option>)}
        </select>
      </h3>
      <div className="panel-content chart-content">
        {window.Recharts ? (
          <ResponsiveContainer width="100%" height={180}>
            <ComposedChart data={mockData}>
              <XAxis dataKey="time" tick={{ fill: '#666', fontSize: 9 }} />
              <YAxis domain={['dataMin - 2', 'dataMax + 2']} tick={{ fill: '#666', fontSize: 9 }} />
              <Tooltip contentStyle={{ background: '#16161f', border: '1px solid #2a2a3a' }} />
              <Area type="monotone" dataKey="close" stroke="#00ffff" fill="rgba(0,255,255,0.1)" strokeWidth={1.5} />
            </ComposedChart>
          </ResponsiveContainer>
        ) : (
          <div className="no-data">Charts loading...</div>
        )}
      </div>
    </div>
  );
}

// ══════════════════════════════════════════════════════════════════════════════
// PANEL K: MONETIZATION DASHBOARD
// ══════════════════════════════════════════════════════════════════════════════

function MonetizationPanel({ monetization }) {
  const paper = monetization?.paper_trading || {};
  const subs = monetization?.subscribers || {};
  const content = monetization?.content || {};
  const crypto = monetization?.crypto || {};
  const cryptoResults = crypto?.results || [];

  return (
    <div className="panel panel-wide">
      <h3 className="panel-title">
        <span className="icon">\U0001f4b1</span> MONETIZATION
      </h3>
      <div className="panel-content">
        <div className="monetization-grid">
          <div className="mon-card">
            <h4 className="mon-card-title">\U0001f4b0 PAPER TRADING</h4>
            <div className="mon-stats">
              <div className="mon-stat">
                <span className="mon-label">Balance</span>
                <span className="mon-value">${paper?.balance?.toFixed(0) || '10,000'}</span>
              </div>
              <div className="mon-stat">
                <span className="mon-label">ROI</span>
                <span className="mon-value" style={{color: (paper?.roi || 0) >= 0 ? '#00ff88' : '#ff3355'}}>
                  {(paper?.roi || 0) >= 0 ? '+' : ''}{paper?.roi?.toFixed(2) || '0'}%
                </span>
              </div>
              <div className="mon-stat">
                <span className="mon-label">Open</span>
                <span className="mon-value">{paper?.open_trades || 0}</span>
              </div>
              <div className="mon-stat">
                <span className="mon-label">Win Rate</span>
                <span className="mon-value" style={{color: (paper?.win_rate || 0) > 60 ? '#00ff88' : '#ffaa00'}}>
                  {paper?.win_rate?.toFixed(0) || '0'}%
                </span>
              </div>
              <div className="mon-stat">
                <span className="mon-label">Closed</span>
                <span className="mon-value">{paper?.total_closed || 0}</span>
              </div>
              <div className="mon-stat">
                <span className="mon-label">Best Score</span>
                <span className="mon-value">{paper?.best_score || 0}/100</span>
              </div>
            </div>
          </div>
          <div className="mon-card">
            <h4 className="mon-card-title">\U0001f465 SUBSCRIBERS</h4>
            <div className="mon-stats">
              <div className="mon-stat">
                <span className="mon-label">Free</span>
                <span className="mon-value">{subs?.free || 0}</span>
              </div>
              <div className="mon-stat">
                <span className="mon-label">VIP</span>
                <span className="mon-value" style={{color: '#ffd700'}}>{subs?.vip || 0}</span>
              </div>
              <div className="mon-stat">
                <span className="mon-label">MRR</span>
                <span className="mon-value" style={{color: '#00ff88'}}>${subs?.mrr?.toFixed(0) || '0'}</span>
              </div>
              <div className="mon-stat">
                <span className="mon-label">Revenue</span>
                <span className="mon-value" style={{color: '#00ff88'}}>${subs?.total_revenue?.toFixed(0) || '0'}</span>
              </div>
            </div>
          </div>
          <div className="mon-card">
            <h4 className="mon-card-title">\U0001f4f1 CONTENT</h4>
            <div className="mon-stats">
              <div className="mon-stat">
                <span className="mon-label">Reels</span>
                <span className="mon-value">{content?.reels || 0}</span>
              </div>
              <div className="mon-stat">
                <span className="mon-label">Showcase</span>
                <span className="mon-value">{content?.showcase || 0}</span>
              </div>
              <div className="mon-stat">
                <span className="mon-label">YT Scripts</span>
                <span className="mon-value">{content?.youtube || 0}</span>
              </div>
            </div>
          </div>
          <div className="mon-card">
            <h4 className="mon-card-title">\U0001f4b8 CRYPTO</h4>
            <div className="mon-stats">
              <div className="mon-stat">
                <span className="mon-label">Fear & Greed</span>
                <span className="mon-value">{crypto?.fear_greed ?? '--'}</span>
              </div>
              <div className="mon-stat">
                <span className="mon-label">Session</span>
                <span className="mon-value" style={{color: (crypto?.session_bonus || 0) >= 0 ? '#00ff88' : '#ff3355'}}>
                  {(crypto?.session_bonus || 0) >= 0 ? '+' : ''}{crypto?.session_bonus || 0}
                </span>
              </div>
              {cryptoResults.slice(0, 3).map((cr, i) => (
                <div className="mon-stat" key={i}>
                  <span className="mon-label">{cr.symbol}</span>
                  <span className="mon-value" style={{color: cr.decision === 'EXECUTE' ? '#00ff88' : cr.decision === 'WAIT' ? '#ffaa00' : '#ff3355'}}>
                    {cr.score}/100 {cr.decision}
                  </span>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

// ══════════════════════════════════════════════════════════════════════════════
// MAIN APP
// ══════════════════════════════════════════════════════════════════════════════

function App() {
  const { connected, data: wsData } = useWebSocket();
  const signals = wsData?.signals || [];
  const latestSignal = wsData?.latest_signal;
  const sentiment = wsData?.sentiment || {};
  const system = wsData?.system || {};
  const vitals = { memory: { used: 0, limit: 80 }, ...system };
  const [evolutionStatus, setEvolutionStatus] = useState(null);

  useEffect(() => {
    let mounted = true;
    async function fetchEvolution() {
      try {
        const res = await fetch(`${API_BASE}/api/evolution-status`);
        if (res.ok) {
          const data = await res.json();
          if (mounted) setEvolutionStatus(data);
        }
      } catch {}
    }
    fetchEvolution();
    const id = setInterval(fetchEvolution, 30000);
    return () => { mounted = false; clearInterval(id); };
  }, []);

  if (!wsData.system?.status && !connected) {
    return (
      <div className="app loading">
        <div className="loading-text pulse-glow">CONNECTING TO OMNI BRAIN...</div>
        <div className="loading-sub">WebSocket ws://localhost:3002</div>
      </div>
    );
  }

  return (
    <div className="app">
      <HeaderBar vitals={vitals} wsConnected={connected} />

      <main className="main">
        <div className="grid">
          <LiveSignalFeed signals={signals} latestSignal={latestSignal} />
          <ConfidenceMatrix scores={system?.scores} />

          <CorrelationHeatmap correlation={system?.correlation} />
          <NewsTicker news={system?.news} />
          <YieldCurvePanel yieldData={system?.yields} />
          <SentimentPanel sentiment={system?.sentiment} />

          <PatternPanel patterns={system?.patterns} />
          <DivergencePanel divergences={system?.divergences} />
          <RiskPanel risk={system?.risk} />

          <MTFGrid mtf={system?.mtf} />
          <CircuitBreakerPanel circuitBreaker={system?.circuitBreaker} />
          <BacktestResults backtest={system?.backtest} />

          <EvolutionHealth evolution={system?.evolution} />
          <MT5SyncStatus feedStatus={system} />
          <SystemVitals vitals={vitals} feedStatus={system} />

          <DnaEvolutionTracker evolutionStatus={evolutionStatus} />
          <MiniChart />
          <MonetizationPanel monetization={system?.monetization} />
        </div>
      </main>

      <footer className="footer">
        <span>OMNI BRAIN V2 &bull; {new Date().getFullYear()}</span>
        <span>WS: {connected ? '🟢' : '🔴'} &bull; {new Date().toLocaleTimeString()}</span>
      </footer>
    </div>
  );
}

const root = ReactDOM.createRoot(document.getElementById('root'));
root.render(<App />);
