/**
 * OMNI BRAIN V2 - Live Stats API Client
 * Fetches real-time stats from the VPS pipeline API.
 * Updates the landing page hero section every 30 seconds.
 * Graceful fallback if API is offline.
 */

const API_BASE = window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1'
  ? 'http://localhost:3000'
  : `http://${window.location.hostname}:3000`;

let cachedData = null;
let lastFetch = 0;
const CACHE_TTL = 15000;

async function fetchMonetizationStats() {
  const now = Date.now();
  if (cachedData && now - lastFetch < CACHE_TTL) {
    return cachedData;
  }

  try {
    const resp = await fetch(`${API_BASE}/api/monetization`, {
      signal: AbortSignal.timeout(5000)
    });
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    cachedData = await resp.json();
    lastFetch = now;
    return cachedData;
  } catch (err) {
    console.warn('[API] Fetch failed:', err.message);
    return null;
  }
}

async function fetchOmniStatus() {
  try {
    const resp = await fetch(`${API_BASE}/api/omni-status`, {
      signal: AbortSignal.timeout(5000)
    });
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    return await resp.json();
  } catch {
    return null;
  }
}

function timeAgo(isoString) {
  if (!isoString) return 'N/A';
  const seconds = Math.floor((Date.now() - new Date(isoString).getTime()) / 1000);
  if (seconds < 60) return `${seconds}s ago`;
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`;
  if (seconds < 86400) return `${Math.floor(seconds / 3600)}h ago`;
  return `${Math.floor(seconds / 86400)}d ago`;
}

async function updateHeroStats() {
  const statusEl = document.getElementById('system-status');
  const signalsEl = document.getElementById('signals-today');
  const winRateEl = document.getElementById('win-rate-7d');
  const lastSignalEl = document.getElementById('last-signal');
  const liveCountEl = document.getElementById('live-count');
  const signalCardsEl = document.getElementById('signal-cards');

  const monetization = await fetchMonetizationStats();
  const omniStatus = await fetchOmniStatus();

  if (statusEl) {
    const online = omniStatus?.status === 'OPERATIONAL';
    statusEl.innerHTML = online
      ? '<span class="stat-dot online"></span> ONLINE'
      : '<span class="stat-dot offline"></span> CHECKING';
    statusEl.style.color = online ? '#00ff88' : '#ffaa00';
  }

  if (signalsEl && monetization?.paper_trading) {
    const total = monetization.paper_trading.total_closed || 0;
    signalsEl.textContent = total;
  }

  if (winRateEl && monetization?.paper_trading) {
    const wr = monetization.paper_trading.win_rate || 0;
    winRateEl.textContent = `${wr.toFixed(1)}%`;
    winRateEl.style.color = wr >= 60 ? '#00ff88' : wr >= 40 ? '#ffaa00' : '#ff3355';
  }

  if (lastSignalEl && omniStatus?.last_signal_time) {
    lastSignalEl.textContent = timeAgo(omniStatus.last_signal_time);
  }

  if (liveCountEl && monetization?.subscribers) {
    const total = (monetization.subscribers.free || 0) + (monetization.subscribers.vip || 0);
    liveCountEl.textContent = total || '0';
  }

  if (signalCardsEl && monetization?.paper_trading?.recent_signals) {
    const signals = monetization.paper_trading.recent_signals.slice(0, 5);
    if (signals.length > 0) {
      signalCardsEl.innerHTML = signals.map(s => `
        <div class="signal-card-mini">
          <span class="sc-symbol">${s.symbol || '--'}</span>
          <span class="sc-dir ${(s.direction || '').toLowerCase()}">${s.direction || '--'}</span>
          <span class="sc-score">${s.score || 0}</span>
        </div>
      `).join('');
    }
  }
}

function initStatsRefresh() {
  updateHeroStats();
  setInterval(updateHeroStats, 30000);
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', initStatsRefresh);
} else {
  initStatsRefresh();
}
