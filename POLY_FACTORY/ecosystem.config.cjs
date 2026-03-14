const fs = require('fs');
const path = require('path');

// Parse .env file and return key/value pairs (no external dependency needed)
function loadDotEnv(envPath) {
  try {
    const content = fs.readFileSync(envPath, 'utf8');
    const vars = {};
    for (const line of content.split('\n')) {
      const trimmed = line.trim();
      if (!trimmed || trimmed.startsWith('#')) continue;
      const idx = trimmed.indexOf('=');
      if (idx === -1) continue;
      const key = trimmed.slice(0, idx).trim();
      // Strip surrounding quotes if present
      const raw = trimmed.slice(idx + 1).trim();
      vars[key] = raw.replace(/^(['"])(.*)\1$/, '$2');
    }
    return vars;
  } catch (e) {
    return {};
  }
}

const dotEnvVars = loadDotEnv(path.join(__dirname, '.env'));

module.exports = {
  apps: [
    {
      name: "poly-orchestrator",
      script: "/home/openclawadmin/openclaw/workspace/POLY_FACTORY/.venv/bin/python",
      args: "run_orchestrator.py --mode paper",
      cwd: "/home/openclawadmin/openclaw/workspace/POLY_FACTORY",
      interpreter: "none",
      watch: false,
      autorestart: true,
      max_restarts: 10,
      restart_delay: 5000,
      env: {
        PYTHONUNBUFFERED: "1",
        POLY_MODE: "paper",
        ...dotEnvVars
      },
      log_date_format: "YYYY-MM-DD HH:mm:ss",
      out_file: "./logs/pm2-out.log",
      error_file: "./logs/pm2-err.log",
      merge_logs: true
    }
  ]
}
