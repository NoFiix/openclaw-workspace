# 🦞 OpenClaw Workspace — CryptoRizon AI Swarm

> AI agent SWARM for CryptoRizon — specialized agents (scraper, copywriter, publisher, trader, builder) running 24/7 on VPS, communicating via Telegram, self-improving through performance feedback loops.  
> Stack: Node.js · Anthropic API · OpenAI API · Twitter API · DeFi integrations *(in progress)*

---

## 🧠 Architecture

```
                        ┌─────────────────────┐
                        │     TELEGRAM         │
                        │  (command center)    │
                        └────────┬────────────┘
                                 │
                    ┌────────────▼────────────┐
                    │      OPENCLAW GATEWAY    │
                    │   Node.js · Port 18789   │
                    │   Intelligent Routing    │
                    └──┬──────┬──────┬────────┘
                       │      │      │
          ┌────────────▼┐ ┌───▼───┐ ┌▼───────────┐
          │   SCRAPER   │ │  COPY │ │  PUBLISHER │
          │  6 RSS feeds│ │WRITER │ │  Twitter   │
          │  + translate│ │Claude │ │  OAuth 1.0a│
          └─────────────┘ └───────┘ └────────────┘
                       │      │      │
          ┌────────────▼┐ ┌───▼───────────────┐
          │    EMAIL    │ │      BUILDER       │
          │   manager   │ │  self-improvement  │
          └─────────────┘ └────────────────────┘
```

---

## 🤖 Agents

| Agent | Rôle | Modèle |
|---|---|---|
| **Scraper** | Collecte 6 flux RSS crypto, déduplique, traduit EN→FR | Claude Haiku |
| **Copywriter** | Rédige les posts dans la voix CryptoRizon (Ogilvy / Halbert) | Claude Sonnet |
| **Publisher** | Publie sur Twitter @CryptoRizon via OAuth 1.0a | gpt-4o-mini |
| **Email** | Trie et résume les emails entrants | gpt-4o-mini |
| **Builder** | Améliore le code, propose des refactos | Claude Opus |

---

## ⚙️ Intelligent Model Routing

Chaque tâche est scorée et routée vers le modèle optimal :

```
Score 3-4  →  Claude Haiku       (notifications, tri, traductions)
Score 5-6  →  GPT-4o-mini        (contenu léger, résumés)
Score 7-8  →  GPT-4o             (tâches intermédiaires)
Score 9-11 →  Claude Sonnet      (copywriting CryptoRizon)
Score 12+  →  Claude Opus        (code, debug, raisonnement complexe)
```

**Objectif : performance maximale, tokens minimaux.**

---

## 🔄 Workflow Content (Daily)

```
[19:00] Scraper collecte 20 articles crypto (6 sources EN+FR)
   ↓
Traduction automatique EN→FR via Claude Haiku
   ↓
Liste numérotée envoyée sur Telegram
   ↓
Dan sélectionne les numéros qui l'intéressent
   ↓
Copywriter génère les posts dans la voix CryptoRizon
   ↓
Validation Telegram → Publication Twitter @CryptoRizon
```

---

## 🗂️ Structure

```
workspace/
├── SOUL.md              ← Identité & personnalité de l'agent
├── AGENTS.md            ← Instructions & comportement
├── MEMORY.md            ← Mémoire long terme
├── USER.md              ← Profil utilisateur
├── HEARTBEAT.md         ← Checklist monitoring
│
├── agents/              ← Sous-agents spécialisés
│   ├── scraper/
│   ├── copywriter/
│   ├── publisher/
│   ├── email/
│   └── builder/
│
├── recipes/             ← Automatisations planifiées (YAML)
├── skills_custom/       ← Modules JS
│   ├── router.js        ← Routing intelligent 5 modèles
│   ├── scraper.js       ← Scraping RSS + traduction
│   ├── twitter.js       ← Publication Twitter
│   └── cleanup.js       ← Purge mémoire
│
└── state/               ← État des jobs en cours
```

---

## 🛣️ Roadmap

- [x] Scraper multi-sources avec traduction automatique
- [x] Routing intelligent 5 modèles (coût optimisé)
- [x] Publication Twitter OAuth 1.0a
- [x] Validation humaine via Telegram avant publication
- [ ] **State machine Telegram** — réponses contextuelles par message
- [ ] **Progressive Disclosure** — chargement contexte à la demande
- [ ] **Agent QA** — validation automatique avant publication
- [ ] **Performance Loop** — métriques Twitter → optimisation automatique
- [ ] **Shorts/Reels** — automatisation vidéo TikTok + Instagram
- [ ] **Trading Agents** — DeFi, Polymarket, wallets autonomes

---

## 🔧 Stack

- **Runtime** : Node.js v22 · Docker · Ubuntu 22.04 (Hostinger VPS)
- **AI** : Anthropic API (Haiku / Sonnet / Opus) · OpenAI API (GPT-4o)
- **Distribution** : Twitter API v2 · Telegram Bot API
- **Infra** : Docker Compose · Git · Cron

---

## ⚠️ Sécurité

Ce repo contient uniquement la configuration et les scripts.  
Les secrets (`.env`, tokens API, clés Twitter) ne sont **jamais** committés.

---

*Built for [@CryptoRizon](https://twitter.com/CryptoRizon) — crypto education community 20k+ members*
