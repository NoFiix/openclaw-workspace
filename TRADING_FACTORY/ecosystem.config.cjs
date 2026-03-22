module.exports = {
  apps: [{
    name:          'trading-poller',
    script:        'poller.js',
    cwd:           '/home/openclawadmin/openclaw/workspace/TRADING_FACTORY',
    autorestart:   true,
    restart_delay: 3000,
    max_restarts:  10,
    min_uptime:    '5s',
    out_file:      '/home/openclawadmin/openclaw/workspace/state/trading/poller.log',
    error_file:    '/home/openclawadmin/openclaw/workspace/state/trading/poller.log',
    merge_logs:    true,
    env: {
      STATE_DIR:     '/home/openclawadmin/openclaw/workspace/state/trading',
      WORKSPACE_DIR: '/home/openclawadmin/openclaw/workspace',
      TRADING_ENV:   'paper',
    },
  }]
};
