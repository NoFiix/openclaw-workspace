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
        POLY_MODE: "paper"
      },
      log_date_format: "YYYY-MM-DD HH:mm:ss",
      out_file: "./logs/pm2-out.log",
      error_file: "./logs/pm2-err.log",
      merge_logs: true
    }
  ]
}
