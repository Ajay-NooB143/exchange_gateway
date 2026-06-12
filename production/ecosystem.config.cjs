// ══════════════════════════════════════════════════════════════════════════════
// PM2 ECOSYSTEM — Production Configuration
// Usage: pm2 start ecosystem.config.cjs
// ══════════════════════════════════════════════════════════════════════════════

const fs = require('fs');
const path = require('path');

// Load .env file
function loadEnv(filePath) {
  const env = {};
  try {
    const content = fs.readFileSync(filePath, 'utf8');
    content.split('\n').forEach(line => {
      const trimmed = line.trim();
      if (!trimmed || trimmed.startsWith('#')) return;
      const eqIndex = trimmed.indexOf('=');
      if (eqIndex > 0) {
        const key = trimmed.substring(0, eqIndex).trim();
        const value = trimmed.substring(eqIndex + 1).trim();
        env[key] = value;
      }
    });
  } catch (e) {
    console.error('Warning: Could not load .env file');
  }
  return env;
}

const envFile = loadEnv(path.join(__dirname, '.env.production'));

module.exports = {
  apps: [
    {
      // --- Identity ---
      name: 'trading-bridge',
      script: './production_bridge.mjs',

      // --- Cluster Mode (one process per CPU core) ---
      instances: 2,
      exec_mode: 'cluster',

      // --- Memory Management ---
      max_memory_restart: '256M',
      node_args: '--max-old-space-size=256',

      // --- Auto-Restart Policy ---
      autorestart: true,
      restart_delay: 1000,
      max_restarts: 50,
      min_uptime: '5s',
      restart_count: 5,

      // --- Watch (disabled in production) ---
      watch: false,

      // --- Environment Variables (loaded from .env.production) ---
      env: {
        NODE_ENV: 'production',
        PORT: envFile.PORT || 3000,
        WEBHOOK_SECRET: envFile.WEBHOOK_SECRET || 'CHANGE-ME',
        BROKER_API_KEY: envFile.BROKER_API_KEY || '',
        BROKER_BASE_URL: envFile.BROKER_BASE_URL || '',
        ALLOWED_SYMBOLS: envFile.ALLOWED_SYMBOLS || 'XAUUSD',
        MAX_POSITION_SIZE: parseInt(envFile.MAX_POSITION_SIZE) || 10,
        MAX_DAILY_TRADES: parseInt(envFile.MAX_DAILY_TRADES) || 20,
        DEAD_MAN_TIMEOUT: parseInt(envFile.DEAD_MAN_TIMEOUT) || 3600000,
        DEAD_MAN_CHECK: parseInt(envFile.DEAD_MAN_CHECK) || 60000,
        ALERT_WEBHOOK_URL: envFile.ALERT_WEBHOOK_URL || '',
        MAX_DRAWDOWN: parseFloat(envFile.MAX_DRAWDOWN) || 3.0,
        DAILY_LOSS_LIMIT: parseFloat(envFile.DAILY_LOSS_LIMIT) || 300,
      },

      // --- Logging ---
      error_file: './logs/pm2-error.log',
      out_file: './logs/pm2-out.log',
      merge_logs: true,
      log_date_format: 'YYYY-MM-DD HH:mm:ss.SSS',
      log_type: 'json',

      // --- Graceful Shutdown ---
      kill_timeout: 5000,
      listen_timeout: 10000,
      shutdown_with_message: true,

      // --- Health Check ---
      health_check_grace_period: 10000,
    },
  ],
};
