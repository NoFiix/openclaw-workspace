# infrastructure_security.md — Infrastructure & Sécurité

**Date** : 2026-03-15
**Scope** : Réseau, données, dépendances, logs, processus, SPOFs, backups

---

## Résumé exécutif

L'infrastructure OpenClaw tourne sur un VPS Ubuntu 22.04 (8 Go RAM, 97 Go disque, 83% libre). Le système est fonctionnel mais présente **3 failles de sécurité critiques** : clés privées en clair dans un fichier world-readable, pas de HTTPS sur le dashboard, et des ports Docker exposés sur 0.0.0.0. Les backups sont manuels et datent de 12+ jours. [OBSERVÉ]

---

## 1. Réseau

### Ports exposés

| Port | Service | Bind | Exposition | Tag |
|------|---------|------|-----------|-----|
| 22 | SSH | 0.0.0.0 + [::] | Internet | [OBSERVÉ] |
| 80 | nginx (dashboard) | [2a02:4780:7:c72f::1] | IPv6 public | [OBSERVÉ] |
| 3001 | dashboard-api (Express) | 127.0.0.1 | Localhost only | [OBSERVÉ] |
| 18789 | Docker gateway (p2p) | 0.0.0.0 | **Internet** | [OBSERVÉ] |
| 18790 | Docker gateway (p2p) | 0.0.0.0 | **Internet** | [OBSERVÉ] |

### Firewall

| Aspect | Statut | Tag |
|--------|--------|-----|
| UFW | **Non détecté** — pas de règles actives | [OBSERVÉ] |
| iptables | Règles Docker uniquement (FORWARD chain) | [DÉDUIT] |
| Filtrage applicatif | Aucun WAF | [OBSERVÉ] |

### nginx

| Propriété | Valeur | Tag |
|-----------|--------|-----|
| Config | `/etc/nginx/sites-enabled/dashboard-api` | [OBSERVÉ] |
| Bind | IPv6 only `[2a02:4780:7:c72f::1]:80` | [OBSERVÉ] |
| TLS/HTTPS | **Non** — HTTP seulement | [OBSERVÉ] |
| Headers sécurité | `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY` | [OBSERVÉ] |
| Timeouts | connect 5s, read 10s | [OBSERVÉ] |
| Proxy | `/api/` → `http://127.0.0.1:3001` | [OBSERVÉ] |
| Static | `/home/openclawadmin/openclaw/workspace/dashboard/web/dist` | [OBSERVÉ] |

---

## 2. Sécurité des données

### Fichiers sensibles

| Fichier | Permissions | Contenu critique | Risque | Tag |
|---------|------------|-----------------|--------|-----|
| `POLY_FACTORY/.env` | **-rw-rw-r-- (664)** | WALLET_PRIVATE_KEY, POLYMARKET_API_KEY/SECRET, BINANCE_API_KEY/SECRET, ANTHROPIC_API_KEY | **CRITIQUE** — world-readable | [OBSERVÉ] |
| `dashboard/api/.env` | -rw------- (600) | DASHBOARD_API_KEY | OK | [OBSERVÉ] |
| Container .env | Dans Docker (non visible host) | ANTHROPIC_API_KEY, Telegram tokens, Twitter OAuth | OK (isolé) | [DÉDUIT] |

### Secrets en clair

| Secret | Localisation | Chiffrement | Tag |
|--------|-------------|-------------|-----|
| EVM private key (wallet) | POLY_FACTORY/.env | **Aucun** — plaintext | [OBSERVÉ] |
| Polymarket API key/secret/passphrase | POLY_FACTORY/.env | **Aucun** | [OBSERVÉ] |
| Binance API key/secret | POLY_FACTORY/.env | **Aucun** | [OBSERVÉ] |
| Polygon RPC URL (avec auth token) | POLY_FACTORY/.env | **Aucun** | [OBSERVÉ] |
| Anthropic API key | POLY_FACTORY/.env + container | **Aucun** | [OBSERVÉ] |
| Twitter OAuth tokens | Container | **Aucun** | [DÉDUIT] |
| Dashboard API key | dashboard/api/.env | **Aucun** (mais perms 600) | [OBSERVÉ] |

---

## 3. Processus et supervision

### PM2

| Process | ID | Uptime | RAM | Restarts | Mode | Tag |
|---------|----|----|-----|----------|------|-----|
| dashboard-api | 3 | 44h | 94 Mo | 2 | fork | [OBSERVÉ] |
| poly-orchestrator | 5 | 30m | 95.5 Mo | 3 | fork | [OBSERVÉ] |

### Docker

| Container | Image | Status | Ports | User | Tag |
|-----------|-------|--------|-------|------|-----|
| openclaw-gateway-1 | v2026.3.2 | Up 47h, healthy | 18789-18790 | node | [OBSERVÉ] |
| openclaw-cli-1 | — | **Exited (1)** | — | — | [OBSERVÉ] |

### Cron

| Schedule | Script | Système | Tag |
|----------|--------|---------|-----|
| `*/15 * * * *` | run_watchdog.sh | Monitoring | [OBSERVÉ] |
| `0 7-23 * * *` | hourly_scraper.js | Content | [OBSERVÉ] |
| `15 19 * * *` | scraper.js | Content | [OBSERVÉ] |
| `@reboot` | poller.js (daemon) | Content | [OBSERVÉ] |
| `@reboot` | trading poller | Trading | [OBSERVÉ] |
| `0 3 * * *` | bus_rotation.js | Trading | [OBSERVÉ] |
| `30 3 * * *` | bus_cleanup_trading.js | Trading | [OBSERVÉ] |
| `0 2 * * *` | bus_cleanup_trading.js | Trading | [OBSERVÉ] |

### Supervision globale

| Composant | Superviseur | Restart auto | Tag |
|-----------|-------------|-------------|-----|
| dashboard-api | PM2 | ✅ | [OBSERVÉ] |
| poly-orchestrator | PM2 | ✅ | [OBSERVÉ] |
| Content poller | `@reboot` cron (daemon) | ❌ Seulement au boot | [OBSERVÉ] |
| Trading poller | `@reboot` cron (docker exec) | ❌ Seulement au boot | [OBSERVÉ] |
| SYSTEM_WATCHDOG | Cron */15 | ✅ (exécution ponctuelle) | [OBSERVÉ] |
| Container Docker | Docker daemon | ✅ (restart policy) | [DÉDUIT] |

---

## 4. Disque et logs

### Usage disque

| Chemin | Taille | Tag |
|--------|--------|-----|
| Workspace total | ~17 Go | [OBSERVÉ] |
| Libre | 81 Go (83%) | [OBSERVÉ] |
| `state/trading/` | 355 Mo | [OBSERVÉ] |
| `POLY_FACTORY/state/bus/` | 9.7 Mo | [OBSERVÉ] |
| `state/trading/poller.log` | **48 Mo** (468k lignes) | [OBSERVÉ] |
| `state/hourly_scraper.log` | 183 Ko | [OBSERVÉ] |
| PM2 logs total | ~8 Ko | [OBSERVÉ] |

### Fichiers à croissance illimitée

| Fichier | Taille actuelle | Rotation | Risque | Tag |
|---------|----------------|----------|--------|-----|
| `state/trading/poller.log` | 48 Mo | **Aucune** | ÉLEVÉ — approche seuil watchdog 50 Mo | [OBSERVÉ] |
| `state/trading/bus/trading_intel_market_features.jsonl` | 72 Mo | **Aucune** | ÉLEVÉ — plus gros fichier du workspace | [OBSERVÉ] |
| `state/learning/token_costs.jsonl` | 1.6 Ko | **Aucune** | FAIBLE (croissance lente) | [OBSERVÉ] |
| `POLY_FACTORY/state/bus/pending_events.jsonl` | 6.9 Mo | Compaction (fix récent) | MOYEN — dépend de la compaction | [OBSERVÉ] |
| `POLY_FACTORY/state/bus/processed_events.jsonl` | 2.9 Mo | **Aucune** | MOYEN — croissance continue | [OBSERVÉ] |

### Seuils watchdog (config.json)

| Métrique | Seuil WARN | Seuil CRIT | Actuel | Statut | Tag |
|----------|-----------|-----------|--------|--------|-----|
| poller.log | 50 Mo | — | 48 Mo | ⚠️ IMMINENT | [OBSERVÉ] |
| bus_dir | 400 Mo | — | 9.7 Mo | ✅ OK | [OBSERVÉ] |
| state_dir | 800 Mo | — | 355 Mo | ✅ OK | [OBSERVÉ] |
| disk_free_pct | 20% | 10% | 83% | ✅ OK | [OBSERVÉ] |

---

## 5. Backups

### État actuel

| Backup | Date | Taille | Type | Tag |
|--------|------|--------|------|-----|
| `backups/openclaw-20260303-125831/` | 2026-03-03 | 1.5 Mo | Auto | [OBSERVÉ] |
| `openclaw.backup.2026.2.24/` | 2026-02-24 | 80 Ko | Manuel | [OBSERVÉ] |
| `openclaw.workspace.backup/` | ~2026-02 | 72 Ko | Manuel | [OBSERVÉ] |
| `openclaw.files.backup/` | ~2026-02 | 56 Ko | Manuel | [OBSERVÉ] |

### Lacunes

| Aspect | Statut | Tag |
|--------|--------|-----|
| Backup automatique régulier | **Non** — dernier il y a 12 jours | [OBSERVÉ] |
| Backup offsite (S3, GCS, rsync) | **Non** — tout sur le même disque | [OBSERVÉ] |
| Backup base de données | N/A (pas de DB, fichiers plats) | [OBSERVÉ] |
| Backup state/ (trading + POLY) | **Non** — state non inclus dans backups | [DÉDUIT] |
| Restore testé | **Inconnu** | [INCONNU] |
| RPO (Recovery Point Objective) | **12+ jours** (inacceptable) | [DÉDUIT] |

---

## 6. Single Points of Failure (SPOFs)

| SPOF | Impact si défaillant | Détection | Tag |
|------|---------------------|-----------|-----|
| VPS unique (srv1425899) | **Tout est down** | Aucune (pas de monitoring externe) | [OBSERVÉ] |
| SYSTEM_WATCHDOG | Monitoring global perdu | **Aucune** — le watchdog n'est pas supervisé | [OBSERVÉ] |
| Disque /dev/sda1 | Perte totale (data + backups sur même disque) | Watchdog check disk % | [OBSERVÉ] |
| Container Docker gateway | Content Factory + Trading poller down | Watchdog check PID | [OBSERVÉ] |
| Anthropic API key (unique) | Tous les LLM calls échouent (3 systèmes) | Aucune alerte spécifique | [DÉDUIT] |
| Telegram bot tokens | Alertes/publications muettes | Aucune alerte (catch silencieux) | [DÉDUIT] |

---

## 7. Modèle utilisateur

| User | Rôle | Processus | Tag |
|------|------|-----------|-----|
| `openclawadmin` | Owner workspace, PM2, cron | poly-orchestrator, dashboard-api, watchdog | [OBSERVÉ] |
| `ubuntu` | Docker, container init | Container gateway | [OBSERVÉ] |
| `node` | User dans container Docker | Content scripts, trading poller | [OBSERVÉ] |
| `www-data` | nginx worker | Reverse proxy | [OBSERVÉ] |
| `root` | nginx master, dockerd | Daemons système | [OBSERVÉ] |

---

## Risques

### R-01 : WALLET_PRIVATE_KEY en clair dans fichier world-readable

**Sévérité** : CRITIQUE

`POLY_FACTORY/.env` (permissions 664) contient la clé privée EVM en plaintext. Tout utilisateur local peut la lire. Un compromis de n'importe quel process sur le VPS expose le wallet. [OBSERVÉ]

### R-02 : Dashboard HTTP sans TLS

**Sévérité** : ÉLEVÉ

La clé API du dashboard transite en clair sur HTTP (port 80). Interception possible par tout intermédiaire réseau. [OBSERVÉ]

### R-03 : Ports Docker exposés sur Internet

**Sévérité** : ÉLEVÉ

Ports 18789/18790 bindés sur 0.0.0.0 sans firewall. Exposent le gateway p2p à Internet. [OBSERVÉ]

### R-04 : Pas de firewall (UFW)

**Sévérité** : ÉLEVÉ

Aucun firewall applicatif détecté. Seules les règles iptables Docker sont actives. [OBSERVÉ]

### R-05 : Backups stales et locaux

**Sévérité** : ÉLEVÉ

Dernier backup automatique : 12 jours. Pas de backup offsite. State/ non sauvegardé. RPO inacceptable pour un système de trading. [OBSERVÉ]

### R-06 : poller.log à 48 Mo, seuil 50 Mo

**Sévérité** : MOYEN

Le fichier va déclencher une alerte watchdog imminemment. Pas de rotation automatique. [OBSERVÉ]

### R-07 : trading_intel_market_features.jsonl à 72 Mo

**Sévérité** : MOYEN

Plus gros fichier du workspace, croissance illimitée, pas de rotation. [OBSERVÉ]

### R-08 : Container CLI en état failed

**Sévérité** : FAIBLE

`openclaw-cli-1` est exited avec code 1. Impact inconnu mais container non fonctionnel. [OBSERVÉ]

---

## Recommandations

| # | Action | Priorité |
|---|--------|----------|
| 1 | **Corriger permissions POLY_FACTORY/.env** : `chmod 600` | P0 |
| 2 | **Activer UFW** : autoriser 22, 80, bloquer 18789/18790 si non nécessaires | P0 |
| 3 | **Activer HTTPS** : Let's Encrypt + certbot sur nginx | P1 |
| 4 | **Backup automatique quotidien** : script cron + rsync offsite ou S3 | P1 |
| 5 | **Rotation poller.log** : logrotate ou script dédié | P1 |
| 6 | Purger ou archiver trading_intel_market_features.jsonl (72 Mo) | P2 |
| 7 | Ajouter monitoring watchdog-du-watchdog (cron externe vérifiant heartbeat) | P2 |
| 8 | Envisager un secrets manager (Vault, AWS SSM, ou au minimum gpg) | P3 |
