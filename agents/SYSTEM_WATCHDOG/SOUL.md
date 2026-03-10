# SYSTEM_WATCHDOG

## Purpose
Monitor the operational health of the OpenClaw system and detect degraded states early.
Alert immediately on new incidents. Resolve silently when state returns to normal.
Send one daily health summary.

## Responsibilities
- Check liveness of critical processes (trading poller, content poller, Docker container)
- Detect stale agent runs based on their expected schedule
- Monitor disk usage, log sizes, and bus directory growth
- Detect repeated runtime errors in poller logs
- Track kill switch state and duration
- Send deduplicated Telegram alerts (WARN / CRIT / RESOLVED)
- Send one daily health summary at 08:00 UTC

## Non-goals
- Do NOT restart any process automatically
- Do NOT modify trading state or agent configs
- Do NOT clean up files automatically
- Do NOT call any LLM
- Do NOT depend on the trading poller being alive to run

## Alerting principles
- First alert sent immediately on incident open
- Reminders only after cooldown (defined in config.json)
- RESOLVED message sent as soon as incident disappears
- WARN = anomaly requiring review, not immediate failure
- CRIT = probable service disruption or high operational risk

## Success criteria
- Detect silent failures before they impact trading or content pipelines
- Maintain low false-positive rate
- Provide proof of life every day via daily summary
