# telegram_bots.md — Inventaire des bots Telegram

**Date** : 2026-03-15
**Scope** : Tous les bots Telegram utilisés par l'environnement OpenClaw

---

## Résumé exécutif

L'environnement utilise **4 variables bot distinctes** pour **3 canaux logiques** : Content (Builder), Trading, et System Monitoring. Au total, **14 fichiers JS/PY** envoient des messages Telegram. Les bots Trading et System partagent potentiellement le même canal. [OBSERVÉ]

---

## Inventaire complet

| Bot (env var) | Canal (env var) | Qui envoie | Types de messages | Fréquence |
|---|---|---|---|---|
| `BUILDER_TELEGRAM_BOT_TOKEN` | `BUILDER_TELEGRAM_CHAT_ID` | hourly_scraper.js | Drafts horaires (article + boutons) | ~17×/jour (7h-23h) |
| | | scraper.js | Liste quotidienne articles (sélection) | 1×/jour |
| | | poller.js | Réponses aux actions (publish/modify/cancel) | On-demand |
| | | drafts.js | Envoi draft + boutons inline | On-demand |
| `TRADER_TELEGRAM_BOT_TOKEN` | `TRADER_TELEGRAM_CHAT_ID` | TRADING_PUBLISHER | Daily P&L + trades résumé | 1×/jour 20h |
| | | GLOBAL_TOKEN_TRACKER | Daily token costs report | 1×/jour 20h |
| | | GLOBAL_TOKEN_ANALYST | Analyse IA bi-hebdomadaire | 2×/semaine (Lun+Jeu 08h) |
| | | KILL_SWITCH_GUARDIAN | Alerte kill switch tripped | On-event |
| | | STRATEGY_GATEKEEPER | Ordres HUMAN_APPROVAL_REQUIRED | On-event |
| | | TRADING_ORCHESTRATOR | Trade execution notifications | On-event |
| | | NEWS_SCORING | High-impact news alerts | On-event |
| | | TRADE_STRATEGY_TUNER | Parameter optimization reports | On-event |
| `TELEGRAM_BOT_TOKEN` | `TELEGRAM_CHAT_ID` | SYSTEM_WATCHDOG | Alertes CRIT/WARN + rapport 08h | */15 min + 1×/jour |
| `POLY_TELEGRAM_BOT_TOKEN` | `POLY_TELEGRAM_CHAT_ID` | POLY_TRADING_PUBLISHER | Daily POLY report 20h, paper/live trades | 1×/jour + on-trade |

---

## Canaux distincts vs partagés

| Canal logique | Variable | Usage | Distinct ? | Tag |
|---|---|---|---|---|
| Content Builder | `BUILDER_TELEGRAM_CHAT_ID` | Drafts, sélections, publications | ✅ Canal dédié | [OBSERVÉ] |
| Trading | `TRADER_TELEGRAM_CHAT_ID` | Trades, P&L, token costs, approvals | ✅ Canal dédié | [OBSERVÉ] |
| System | `TELEGRAM_CHAT_ID` | Alertes système, rapport 08h | ⚠️ Possiblement le même que TRADER | [INCONNU] |
| POLY | `POLY_TELEGRAM_CHAT_ID` | Reports POLY, paper trades | ✅ Canal dédié | [OBSERVÉ] |

---

## Risques

### R-01 : Canal Trading surchargé (8 émetteurs)

**Sévérité** : MOYEN

Le canal TRADER reçoit des messages de 8 agents différents. En période active : daily report + token report + kill switch alerts + trade notifications + news alerts + strategy tuner + gatekeeper approvals. Risque de spam et de confusion. [DÉDUIT]

### R-02 : Confusion SYSTEM vs TRADER canal

**Sévérité** : FAIBLE

Si `TELEGRAM_CHAT_ID` et `TRADER_TELEGRAM_CHAT_ID` pointent vers le même canal, les alertes système se mélangent avec les rapports trading. [INCONNU]

### R-03 : Messages dupliqués possibles

**Sévérité** : FAIBLE

GLOBAL_TOKEN_TRACKER utilise `token_tracker_sent.json` pour la déduplication. SYSTEM_WATCHDOG utilise un incident tracker avec cooldowns. POLY_TRADING_PUBLISHER a sa propre dédup. Ces mécanismes sont indépendants — pas de risque de conflit, mais pas de coordination non plus. [OBSERVÉ]

### R-04 : Révocation d'un token = perte partielle

**Sévérité** : ÉLEVÉ

| Token révoqué | Impact |
|---|---|
| BUILDER | Content pipeline entier down (drafts, publications, sélections) |
| TRADER | 8 agents muets (P&L, kills, trades, tokens, news, tuning, approvals) |
| TELEGRAM (System) | Monitoring silencieux — pannes non détectées |
| POLY | Reports POLY silencieux |

Aucun fallback (email, SMS, webhook) n'existe. [DÉDUIT]

---

## Recommandations

| # | Action | Priorité |
|---|--------|----------|
| 1 | Documenter quel chat_id pointe vers quel canal/groupe | P1 |
| 2 | Séparer les alertes CRIT (canal dédié urgent) des rapports quotidiens | P2 |
| 3 | Ajouter un fallback (webhook Discord/Slack) pour les alertes CRIT | P3 |
| 4 | Limiter le nombre d'émetteurs par canal à 3-4 max | P3 |
