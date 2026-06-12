/**
 * PM2 Ecosystem Configuration
 * ============================
 * Run: pm2 start ecosystem.config.cjs
 * 
 * This starts both:
 *   1. Node.js bridge (port 3000)
 *   2. Python execution engine (port 8080)
 */

module.exports = {
    apps: [
        {
            name: 'footprint-bridge',
            script: 'bridge.mjs',
            cwd: '/opt/trading-bridge/institutional_footprint',
            instances: 2,
            exec_mode: 'cluster',
            autorestart: true,
            watch: false,
            max_memory_restart: '100M',
            env: {
                NODE_ENV: 'production',
                BRIDGE_PORT: 3000,
                PYTHON_ENGINE_URL: 'http://localhost:8080'
            },
            // Load .env file
            env_file: '/opt/trading-bridge/institutional_footprint/.env',
            // Logging
            log_file: '/opt/trading-bridge/logs/bridge.log',
            error_file: '/opt/trading-bridge/logs/bridge_error.log',
            merge_logs: true,
            log_date_format: 'YYYY-MM-DD HH:mm:ss Z',
            // Restart policy
            restart_delay: 1000,
            max_restarts: 10,
            min_uptime: '10s'
        },
        {
            name: 'footprint-engine',
            script: 'python3',
            args: 'execution_engine.py',
            cwd: '/opt/trading-bridge/institutional_footprint',
            instances: 1,
            exec_mode: 'fork',
            autorestart: true,
            watch: false,
            max_memory_restart: '250M',
            env: {
                PYTHONUNBUFFERED: '1'
            },
            // Logging
            log_file: '/opt/trading-bridge/logs/engine.log',
            error_file: '/opt/trading-bridge/logs/engine_error.log',
            merge_logs: true,
            log_date_format: 'YYYY-MM-DD HH:mm:ss Z',
            // Restart policy
            restart_delay: 2000,
            max_restarts: 10,
            min_uptime: '10s'
        }
    ]
};
