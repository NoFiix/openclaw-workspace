# AGENTS — NEWS_SCORING

## Objectif
Produire des `trading.intel.news.event` fiables, scorés, dédupliqués.
Chaque event doit être directement exploitable par TRADE_GENERATOR et REGIME_DETECTOR.

## Event Interface

### Inputs (topics consommés)
| Topic | Rôle |
|-------|------|
| `trading.raw.news.article` | Articles RSS et API (CryptoPanic, SEC EDGAR) |
| `trading.raw.social.post` | Posts Twitter/Telegram depuis NEWS_FEED |
| `trading.ops.health.data` | Si data dégradée → ne pas émettre d'alert CRITICAL |

### Outputs (topics produits)
| Topic | Condition |
|-------|-----------|
| `trading.intel.news.event` | Toujours si urgency >= 3 |
| `trading.ops.alert` | Si urgency >= 9 ET fiabilité >= 0.7 |

### Payload schema
```json
{
  "headline": "",
  "category": "REGULATION|HACK|LISTING|ETF|MACRO|PARTNERSHIP|SOCIAL_INFLUENCER",
  "urgency": 0,
  "reliability": {
    "score": 0.0,
    "confirmed_by": 0,
    "sources_checked": []
  },
  "entities": ["BTC", "SEC"],
  "summary": "",
  "manipulation_flags": [],
  "source_refs": [{ "name": "", "url": "", "type": "official|media|social" }]
}
```

## Règles de scoring fiabilité
| Score | Condition |
|-------|-----------|
| 0.9+ | Source officielle (SEC, exchange, banque centrale) |
| 0.7-0.89 | Média réputé (Reuters, Bloomberg, CoinDesk) + corroboration |
| 0.5-0.69 | Média secondaire ou 1 seule source réputée |
| < 0.5 | Rumeur, source sociale non officielle, non confirmé |
| Max 0.4 | Source sociale non officielle + mots extrêmes (hack/ban/crash) |

## Règles de scoring urgence (0-10)
| Score | Exemples |
|-------|---------|
| 9-10 | ETF approval, hack majeur exchange, sanction SEC, tweet Fed/Trump sur crypto |
| 7-8 | Listing Binance/Coinbase, décision réglementaire, partenariat tier-1 |
| 5-6 | Déclaration influenceur confirmée, rumeur corroborée, analyse macro |
| 1-4 | News de fond, éducatif, faible impact marché estimé |

## Protection anti-manipulation
- Source sociale non officielle + mot extrême → fiabilité max 0.4
- Screenshot sans lien source → fiabilité 0.1
- News déjà vue (hash identique) → dédupliquée, pas de nouvel event

## Anti-patterns
- Émettre plusieurs events pour la même news (dédup obligatoire)
- Scorer urgency 9+ sans vérifier la fiabilité
- Ignorer le type de source dans le calcul de fiabilité

## KPIs
- Taux de faux positifs (news importantes qui se révèlent fausses)
- Latence moyenne publication → event
- Couverture de sources (diversité)
