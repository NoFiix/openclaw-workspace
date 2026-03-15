# AUDITS — OpenClaw Platform Audits

Ce répertoire contient les audits techniques de la plateforme OpenClaw.

## Structure

Chaque audit est dans un sous-dossier nommé `{date}_{slug}` :

```
AUDITS/
├── README.md
├── CHANGELOG.md
└── 2026-03-15_full-platform-audit/
    ├── 00_index.md
    ├── 01_global_environment/
    ├── 02_content_factory/
    ├── 03_trading_factory/
    ├── 04_poly_factory/
    ├── 05_shared_components/
    ├── 06_cross_system_analysis/
    └── 99_appendices/
```

## Convention de tags

| Tag | Signification |
|-----|---------------|
| `[OBSERVÉ]` | Constaté directement (commande, fichier, log) |
| `[DÉDUIT]` | Déduit logiquement de données observées |
| `[SUPPOSÉ]` | Hypothèse non vérifiée |
| `[INCONNU]` | Information manquante ou non découvrable |

## Classification des composants

| Type | Description |
|------|-------------|
| TYPE_1 | Critique — impacte le trading ou la sécurité |
| TYPE_2 | Important — impacte les opérations courantes |
| TYPE_3 | Support — infrastructure, monitoring |
| TYPE_4 | Legacy/dormant — inactif ou en cours de remplacement |

## Sévérité des conflits

| Niveau | Description |
|--------|-------------|
| CRITICAL | Perte de données ou d'argent possible |
| HIGH | Comportement incorrect probable |
| MEDIUM | Inefficacité ou confusion |
| LOW | Cosmétique ou mineur |
