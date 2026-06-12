/**
 * OMNI BRAIN V2 — PM2 Ecosystem Config (Consolidated)
 * =====================================================
 * Single orchestrator entry point: app_wiring.py
 * Handles scanning, pipeline, alerts, and heartbeat in one process.
 *
 * Apps:
 *   1. omni-orchestrator → app_wiring.py (consolidated)
 *   2. omni-pipeline     → pipeline_orchestrator.py (API server)
 *   3. omni-telegram     → production/telegram_signals.py (signal alerts)
 *   4. omni-mcp-bridge   → mcp_bridge_server.py (FastAPI → OpenStock dashboard)
 *   5. omni-ws-bridge    → production/mcp_bridge.py (WebSocket → React dashboard)
 *   6. omni-status       → production/status_page.py (public health dashboard)
 *   7. omni-crypto       → production/crypto_scanner.py (crypto feed)
 *   8. omni-paper-trader → production/paper_trader.py (paper trading)
 */

module.exports = {
  apps: [
    // ════════════════════════════════════════════════════════════════════════════
    // CONSOLIDATED ORCHESTRATOR (scanner + pipeline + heartbeat)
    // ════════════════════════════════════════════════════════════════════════════
    {
      name: 'omni-orchestrator',
      script: 'python3',
      args: 'app_wiring.py',
      cwd: __dirname,
      autorestart: true,
      max_restarts: 10,
      exp_backoff_restart_delay: 100,
      error_file: 'logs/pm2/orchestrator_error.log',
      out_file: 'logs/pm2/orchestrator_out.log',
      time: true,
      env: {
        NODE_ENV: 'production',
        SCAN_INTERVAL_SECONDS: '60'
      }
    },

    // ════════════════════════════════════════════════════════════════════════════
    // API SERVER
    // ════════════════════════════════════════════════════════════════════════════
    {
      name: 'omni-pipeline',
      script: 'python3',
      args: 'pipeline_orchestrator.py',
      cwd: __dirname,
      autorestart: true,
      max_restarts: 10,
      exp_backoff_restart_delay: 100,
      error_file: 'logs/pm2/pipeline_error.log',
      out_file: 'logs/pm2/pipeline_out.log',
      time: true,
      env: {
        NODE_ENV: 'production',
        PORT: '3000'
      }
    },

    // ════════════════════════════════════════════════════════════════════════════
    // TELEGRAM SIGNAL SERVICE
    // ════════════════════════════════════════════════════════════════════════════
    {
      name: 'omni-telegram',
      script: 'python3',
      args: 'production/telegram_signals.py --background',
      cwd: __dirname,
      autorestart: true,
      max_restarts: 10,
      exp_backoff_restart_delay: 100,
      error_file: 'logs/pm2/telegram_error.log',
      out_file: 'logs/pm2/telegram_out.log',
      time: true,
      env: {
        NODE_ENV: 'production'
      }
    },

    // ════════════════════════════════════════════════════════════════════════════
    // MCP BRIDGE SERVER (FastAPI → OpenStock Dashboard)
    // ════════════════════════════════════════════════════════════════════════════
    {
      name: 'omni-mcp-bridge',
      script: 'python3',
      args: 'mcp_bridge_server.py',
      cwd: __dirname,
      autorestart: true,
      max_restarts: 10,
      exp_backoff_restart_delay: 100,
      error_file: 'logs/pm2/mcp_bridge_error.log',
      out_file: 'logs/pm2/mcp_bridge_out.log',
      time: true,
      env: {
        NODE_ENV: 'production',
        MCP_BRIDGE_PORT: '8081',
        TIDB_HOST: '',
        TIDB_USERNAME: '',
        TIDB_PASSWORD: '',
        TIDB_DATABASE: 'omni_brain',
        PERPLEXITY_API_KEY: '',
        FIRECRAWL_API_KEY: ''
      }
    },

    // ════════════════════════════════════════════════════════════════════════════
    // MCP WS BRIDGE (WebSocket → React Dashboard)
    // ════════════════════════════════════════════════════════════════════════════
    {
      name: 'omni-ws-bridge',
      script: 'python3',
      args: 'production/mcp_bridge.py',
      cwd: __dirname,
      autorestart: true,
      max_restarts: 10,
      exp_backoff_restart_delay: 100,
      error_file: 'logs/pm2/ws_bridge_error.log',
      out_file: 'logs/pm2/ws_bridge_out.log',
      time: true,
      env: {
        NODE_ENV: 'production',
        MCP_WS_PORT: '3002',
        MCP_HTTP_PORT: '3001'
      }
    },

    // ════════════════════════════════════════════════════════════════════════════
    // STATUS PAGE (Public Health Dashboard)
    // ════════════════════════════════════════════════════════════════════════════
    {
      name: 'omni-status',
      script: 'python3',
      args: 'production/status_page.py',
      cwd: __dirname,
      autorestart: true,
      max_restarts: 10,
      exp_backoff_restart_delay: 100,
      error_file: 'logs/pm2/status_error.log',
      out_file: 'logs/pm2/status_out.log',
      time: true,
      env: {
        NODE_ENV: 'production',
        STATUS_PORT: '8080'
      }
    },

    // ════════════════════════════════════════════════════════════════════════════
    // CRYPTO ASSET SCANNER (BTC, ETH, BNB, SOL, XRP)
    // ════════════════════════════════════════════════════════════════════════════
    {
      name: 'omni-crypto',
      script: 'python3',
      args: 'production/crypto_scanner.py',
      cwd: __dirname,
      autorestart: true,
      max_restarts: 10,
      exp_backoff_restart_delay: 100,
      error_file: 'logs/pm2/crypto_error.log',
      out_file: 'logs/pm2/crypto_out.log',
      time: true,
      env: {
        NODE_ENV: 'production',
        CRYPTO_SPREAD_MAX: '50'
      }
    },

    // ════════════════════════════════════════════════════════════════════════════
    // PAPER TRADER (Monetization Layer)
    // ════════════════════════════════════════════════════════════════════════════
    {
      name: 'omni-paper-trader',
      script: 'python3',
      args: 'production/paper_trader.py --background',
      cwd: __dirname,
      autorestart: true,
      max_restarts: 10,
      exp_backoff_restart_delay: 100,
      error_file: 'logs/pm2/paper_trader_error.log',
      out_file: 'logs/pm2/paper_trader_out.log',
      time: true,
      env: {
        NODE_ENV: 'production',
        PAPER_BALANCE: '10000'
      }
    }
  ]
};
