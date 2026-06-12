// ══════════════════════════════════════════════════════════════════════════════
// PM2 ECOSYSTEM CONFIG — Production Cluster Mode
// Usage: pm2 start ecosystem.config.cjs
// ══════════════════════════════════════════════════════════════════════════════

module.exports = {
  apps: [
    {
      name: 'webhook-bridge',
      script: './low_latency_bridge.mjs',
      instances: 'max',          // one per CPU core
      exec_mode: 'cluster',      // enable PM2 cluster mode
      max_memory_restart: '256M',
      
      // Performance tuning
      node_args: [
        '--max-old-space-size=256',
        '--optimize-for-size',
        '--gc-interval=100',
      ].join(' '),

      // Environment
      env: {
        NODE_ENV: 'production',
        PORT: 3000,
        WEBHOOK_SECRET: 'your-secret-here',
        MAX_POSITION_SIZE: 10,
        ALLOWED_SYMBOLS: 'XAUUSD',
        WEBWORKERS: 0,  // 0 = auto-detect CPU count
      },

      // Logging
      error_file: './logs/pm2-error.log',
      out_file: './logs/pm2-out.log',
      merge_logs: true,
      log_date_format: 'YYYY-MM-DD HH:mm:ss.SSS',

      // Restart policy
      restart_delay: 1000,
      max_restarts: 10,
      min_uptime: '5s',
      autorestart: true,

      // Graceful shutdown
      kill_timeout: 5000,
      listen_timeout: 10000,

      // Watch (dev only — disable in production)
      watch: false,
      ignore_watch: ['node_modules', 'logs', '*.log'],
    }
  ]
};
