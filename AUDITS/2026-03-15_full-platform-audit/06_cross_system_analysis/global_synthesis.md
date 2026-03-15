# global_synthesis.md — Synthèse globale de l'audit OpenClaw

**Date** : 2026-03-15
**Scope** : Audit complet de l'environnement OpenClaw — 6 phases, 42 fichiers

---

## 1. État actuel du système

L'environnement OpenClaw est un **système de trading multi-stratégie** opérant sur un VPS unique (Ubuntu 22.04, 8 Go RAM, 97 Go disque). Trois sous-systèmes coexistent :

| Système | Langage | Runtime | Agents | État | Mode | Tag |
|---------|---------|---------|--------|------|------|-----|
| Content Factory | JavaScript | Docker container | 3 actifs + 4 modules | **Opérationnel** | Production (publication Twitter/Telegram) | [OBSERVÉ] |
| Trading Factory | JavaScript | Docker container + PM2 | 24 agents | **Partiellement défaillant** | Paper/Testnet (4 trades exécutés) | [OBSERVÉ] |
| POLY_FACTORY | Python 3.11 | PM2 | 19 agents | **En cours de stabilisation** | Paper (0 trades → fix appliqués) | [OBSERVÉ] |

### Métriques clés au moment de l'audit

| Métrique | Valeur | Tag |
|----------|--------|-----|
| Uptime VPS | Continu (pas de reboot récent) | [OBSERVÉ] |
| CPU poly-orchestrator | 98% → en cours de résolution | [OBSERVÉ] |
| Disque utilisé | 17% (81 Go libre) | [OBSERVÉ] |
| Trades POLY | 0 (1.5 jours, pre-fix) | [OBSERVÉ] |
| Trades Trading (testnet) | 4 (+$864.82 PnL fictif) | [OBSERVÉ] |
| Kill switch Trading | ARMED (mais guardian défaillant C-07) | [OBSERVÉ] |
| Kill switch POLY | ARMED (fonctionnel) | [OBSERVÉ] |
| Agents POLY disabled | 11/19 → fixé à 19/19 active | [OBSERVÉ] |
| Coûts LLM estimés | $1.10-2.10/jour ($33-63/mois) | [DÉDUIT] |
| Alertes Telegram | 14 émetteurs → 1 seul canal | [OBSERVÉ] |

---

## 2. Top 10 risques classés par criticité

| Rang | Risque | Sévérité | Système | Statut | Tag |
|------|--------|----------|---------|--------|-----|
| 1 | **POLY .env world-readable (664) avec wallet private key** | CRITIQUE | POLY | ⚠️ Non corrigé (P0) | [OBSERVÉ] |
| 2 | **KILL_SWITCH_GUARDIAN défaillant** (27k erreurs, 115% error rate) | CRITIQUE | Trading | ⚠️ Non corrigé | [OBSERVÉ] |
| 3 | **Ports Docker exposés sur Internet** (18789/18790 sur 0.0.0.0) | ÉLEVÉ | Infra | ⚠️ Script prêt, nécessite sudo | [OBSERVÉ] |
| 4 | **Dashboard HTTP sans TLS** — API key en clair | ÉLEVÉ | Dashboard | ⚠️ Non corrigé | [OBSERVÉ] |
| 5 | **Backups stales (12j) et locaux** (même disque, state non sauvegardé) | ÉLEVÉ | Infra | ⚠️ Non corrigé | [OBSERVÉ] |
| 6 | **SYSTEM_WATCHDOG non supervisé** (SPOF monitoring) | ÉLEVÉ | Shared | ✅ Fix appliqué (heartbeat + meta-watchdog) | [OBSERVÉ] |
| 7 | **Human approval non fonctionnel** (95 ordres expirés, 100%) | ÉLEVÉ | Trading | ⚠️ Non corrigé | [OBSERVÉ] |
| 8 | **Content Factory LLM costs non trackés** (~30% invisible) | MOYEN | Content | ⚠️ Non corrigé | [OBSERVÉ] |
| 9 | **14 émetteurs Telegram → 1 canal** (alertes CRIT noyées) | MOYEN | Shared | ⚠️ Non corrigé | [OBSERVÉ] |
| 10 | **Dépendance unique Anthropic API** (3 systèmes, 1 clé) | MOYEN | Cross | ⚠️ Non mitigé | [DÉDUIT] |

### Risques corrigés pendant l'audit

| Risque | Sévérité | Fix | Tag |
|--------|----------|-----|-----|
| C-10 : 11 agents POLY disabled | CRITIQUE | ping() revive, MAX_RESTARTS 3→10 | [OBSERVÉ] |
| C-11 : Bus 70k events, 98% CPU | ÉLEVÉ | Compaction disk-based + age purge | [OBSERVÉ] |
| U-13 : 0 trade:signal | ÉLEVÉ | Seuils stratégies relaxés | [OBSERVÉ] |
| C-02 : Double trading poller | MOYEN | trading-poller retiré de PM2 | [OBSERVÉ] |
| C-15 : Watchdog non supervisé | ÉLEVÉ | Heartbeat + meta-watchdog cron | [OBSERVÉ] |
| poller.log 48 Mo | MOYEN | Script rotation + cron quotidien | [OBSERVÉ] |

---

## 3. Top 5 quick wins (fixes < 1h)

| # | Action | Effort | Impact | Tag |
|---|--------|--------|--------|-----|
| 1 | `chmod 600 POLY_FACTORY/.env` | 1 min | Élimine le risque sécurité #1 | [OBSERVÉ] |
| 2 | `sudo bash setup_ufw.sh` | 15 min | Bloque ports Docker exposés | [OBSERVÉ] |
| 3 | Scheduler cleanup.js (`0 3 * * 0` dans crontab) | 15 min | Purge mémoire agents Content | [OBSERVÉ] |
| 4 | Désactiver PREDICTOR (`enabled: false`) | 2 min | Élimine 11k runs orphelins | [OBSERVÉ] |
| 5 | Supprimer doublon bus_cleanup (cron 02:00) | 2 min | Clarifie maintenance bus | [OBSERVÉ] |

---

## 4. Carte ASCII des systèmes

```
┌─────────────────────────────────────────────────────────────────────┐
│                    VPS srv1425899 — Ubuntu 22.04                     │
│                   8 Go RAM · 97 Go disk · 17% used                   │
│                                                                      │
│  ┌═══════════════════════════════════════════════════════════════┐   │
│  ║              DOCKER CONTAINER (openclaw-gateway)              ║   │
│  ║                                                               ║   │
│  ║  ┌─────────────────┐    ┌──────────────────────────────┐     ║   │
│  ║  │ CONTENT FACTORY  │    │     TRADING FACTORY          │     ║   │
│  ║  │                  │    │                              │     ║   │
│  ║  │ scraper(×2)      │    │ 24 agents JS                │     ║   │
│  ║  │ poller (daemon)  │    │ poller.js (daemon)           │     ║   │
│  ║  │ drafts/pending   │    │ bus JSONL 170 Mo             │     ║   │
│  ║  │ twitter          │    │ KILL_SWITCH ⚠️ (27k err)     │     ║   │
│  ║  │                  │    │ HUMAN_APPROVAL ⚠️ (100% exp) │     ║   │
│  ║  │ → Twitter/X      │    │                              │     ║   │
│  ║  │ → Telegram       │    │ → Binance testnet            │     ║   │
│  ║  └─────────────────┘    └──────────────────────────────┘     ║   │
│  ║                                                               ║   │
│  ║  ┌──────────────────────────────────────────────────────┐    ║   │
│  ║  │ SHARED: SYSTEM_WATCHDOG (*/15) · TOKEN_TRACKER (1/h) │    ║   │
│  ║  │         TOKEN_ANALYST (2×/sem) · POLY_PUBLISHER      │    ║   │
│  ║  └──────────────────────────────────────────────────────┘    ║   │
│  ╚═══════════════════════════════════════════════════════════════╝   │
│                                                                      │
│  ┌──────────────────────────┐    ┌────────────────────────────┐     │
│  │     POLY_FACTORY (PM2)    │    │   DASHBOARD (PM2 + nginx)  │     │
│  │                           │    │                            │     │
│  │ 19 agents Python          │    │ Express :3001 (17 routes)  │     │
│  │ bus JSONL 10 Mo           │    │ React 8 pages              │     │
│  │ 9 stratégies (paper)      │    │ nginx :80 (⚠️ HTTP)        │     │
│  │ ⚠️ .env 664               │    │ x-api-key auth             │     │
│  │                           │    │                            │     │
│  │ → Polymarket (paper)      │    │ Lit: Trading + POLY +      │     │
│  │ → Binance (prices)        │    │      Content + infra       │     │
│  │ → NOAA (weather)          │    │                            │     │
│  └──────────────────────────┘    └────────────────────────────┘     │
│                                                                      │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │  TELEGRAM : 4 bots → 1 SEUL CANAL (14 émetteurs)            │   │
│  │  BACKUPS : stales 12j, locaux, state non inclus ⚠️           │   │
│  │  UFW : inactif ⚠️  ·  Ports 18789/18790 exposés ⚠️           │   │
│  └──────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 5. Questions ouvertes non résolues

| # | Question | Impact | Bloquant ? | Tag |
|---|----------|--------|-----------|-----|
| U-01 | Credentials Polymarket valides ? | Trading live impossible si expirés | Oui (live) | [INCONNU] |
| U-02 | WALLET_PRIVATE_KEY absent — METAMASK_PRIVATE_KEY est-elle la même ? | place_order() crash en live | Oui (live) | [OBSERVÉ] |
| U-09 | Cause exacte des 27k erreurs KILL_SWITCH_GUARDIAN | Sécurité capitale | Oui (live) | [INCONNU] |
| U-11 | Plan transition testnet → mainnet ? | Pas d'executor mainnet | Oui (live) | [INCONNU] |
| U-15 | Credentials POLY testées sur CLOB API réel ? | Possiblement invalides | Oui (live) | [INCONNU] |
| U-16 | TELEGRAM_CHAT_ID == TRADER_CHAT_ID ? | **Résolu** : OUI, les 4 sont identiques | Non | [OBSERVÉ] |
| U-17 | Container openclaw-cli-1 failed — rôle ? | Possiblement non critique | Non | [INCONNU] |
| U-18 | Restore backup fonctionnel ? | RPO réel inconnu | Non | [INCONNU] |

**Verdict** : 5 questions bloquent la transition vers le trading live. Aucune ne bloque le trading paper actuel. [DÉDUIT]

---

## 6. Recommandation stratégique

### Diagnostic global

L'environnement OpenClaw est **fonctionnel en mode paper** mais **pas prêt pour le trading live**. Les systèmes sont bien architecurés individuellement (séparation propre des state, bus distincts, agents modulaires) mais l'infrastructure manque de hardening (pas de TLS, pas de firewall, secrets exposés, backups stales).

### Priorité immédiate (48h)

1. **Sécuriser les secrets** : chmod 600 .env, activer UFW, bind Docker localhost — 20 min [OBSERVÉ]
2. **Activer HTTPS** : Let's Encrypt sur nginx — 30 min [OBSERVÉ]
3. **Backup quotidien** : script cron + destination offsite — 2h [DÉDUIT]

### Priorité court terme (1 semaine)

4. **Diagnostiquer KILL_SWITCH_GUARDIAN** — sécurité capitale Trading Factory [OBSERVÉ]
5. **logTokens Content Factory** — visibilité complète des coûts [OBSERVÉ]
6. **Séparer canaux Telegram** — ne pas noyer les alertes CRIT [OBSERVÉ]
7. **Stabiliser POLY_FACTORY** — observer les premiers paper trades après les fix [OBSERVÉ]

### Priorité moyen terme (1 mois)

8. **Valider credentials Polymarket** — prerequisite live [INCONNU]
9. **Implémenter human approval** — prerequisite live (trades > seuil) [OBSERVÉ]
10. **Créer mainnet executor** — prerequisite live Trading [DÉDUIT]

### Recommandation architecturale

Ne pas ajouter de nouveau système tant que les 3 existants ne sont pas stabilisés et les P0/P1 résolus. L'ajout de Kalshi (connector déjà créé) et du sportsbook connector devrait attendre que POLY_FACTORY ait exécuté au minimum 50 paper trades et que le kill switch Trading soit fonctionnel. [DÉDUIT]
