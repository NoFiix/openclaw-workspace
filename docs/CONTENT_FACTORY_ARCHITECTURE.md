# 🏭 CRYPTORIZON CONTENT FACTORY — Architecture Complète

> Blueprint opérationnel pour une usine à contenu crypto autonome pilotée par 10 agents IA.


---

## 📋 Table des matières

1. [Vue d'ensemble](#1-vue-densemble)
2. [Structure des agents](#2-structure-des-agents)
3. [ADN & Personnalités](#3-adn--personnalités)
4. [Artefacts JSON](#4-artefacts-json)
5. [Pipeline de production](#5-pipeline-de-production)
6. [Prompts système](#6-prompts-système)
7. [Architecture mémoire](#7-architecture-mémoire)
8. [Scorecard & KPIs](#8-scorecard--kpis)
9. [Protocoles de gouvernance](#9-protocoles-de-gouvernance)
10. [Ligne éditoriale](#10-ligne-éditoriale)
11. [Ton & Style CryptoRizon](#11-ton--style-cryptorizon)
12. [KPIs Cibles par plateforme](#12-kpis-cibles-par-plateforme)
13. [Checklist QA Crypto FR](#13-checklist-qa-crypto-fr)
14. [Plan de lancement (14 jours)](#14-plan-de-lancement-14-jours)
15. [Les 3 obsessions qui font la différence](#15-les-3-obsessions-qui-font-la-différence)
16. [Fichiers mémoire additionnels](#16-fichiers-mémoire-additionnels)
17. [Prompt Master — ORCHESTRATOR](#17-prompt-master--orchestrator)
18. [Exemple de cycle complet — YouTube Long](#18-exemple-de-cycle-complet--youtube-long)
19. [Stratégie Shorts / Reels — Machine à Acquisition](#19-stratégie-shorts--reels--machine-à-acquisition)
20. [Pipeline Shorts (100% automatisé)](#20-pipeline-shorts-100-automatisé)
21. [Stratégie de croissance — 100K abonnés en 6 mois](#21-stratégie-de-croissance--100k-abonnés-en-6-mois)
22. [Système A/B Test automatisé](#22-système-ab-test-automatisé)
23. [Tableau de bord croissance](#23-tableau-de-bord-croissance)
24. [Accélérateurs de croissance](#24-accélérateurs-de-croissance)
25. [Erreurs mortelles à éviter](#25-erreurs-mortelles-à-éviter)
26. [Positionnement concurrentiel](#26-positionnement-concurrentiel)
27. [Piliers de contenu](#27-piliers-de-contenu)
28. [Format signature](#28-format-signature)
29. [Formule de contenu](#29-formule-de-contenu)
30. [Identité visuelle](#30-identité-visuelle)
31. [Viralité avec ton analytique](#31-viralité-avec-ton-analytique)
32. [BrandMemory — Règles absolues](#32-brandmemory--règles-absolues)
33. [Changelog](#-changelog)

---

## 1. Vue d'ensemble

### Mission
Créer une équipe IA 100% autonome qui :
- Identifie les sujets tendance
- Crée le contenu (script, miniature, voix, vidéo)
- Ne demande que des **confirmations** sur les décisions importantes
- **S'auto-améliore** en proposant des optimisations

### Principes fondamentaux
- Chaque agent a UN rôle spécialisé (pas de chevauchement)
- Chaque agent a UN KPI principal
- Boucle fermée obligatoire (feedback → amélioration)
- Séparation stricte : STRATÉGIE / EXÉCUTION / OPTIMISATION

---

## 2. Structure des agents

### Architecture 3 couches + superviseur
```
                        🧠 ORCHESTRATOR
                    (COO, décisions critiques)
                              │
            ┌─────────────────┼─────────────────┐
            ▼                 ▼                 ▼
      ┌───────────┐     ┌───────────┐     ┌───────────┐
      │ COUCHE 1  │     │ COUCHE 2  │     │ COUCHE 3  │
      │INTELLIGENCE│    │PRODUCTION │     │OPTIMISATION│
      ├───────────┤     ├───────────┤     ├───────────┤
      │🔍 ANALYST │     │✍️ WRITER  │     │📊 PERFORMANCE│
      │🎯 STRATEGIST│   │🖼️ VISUAL  │     │💡 IMPROVER │
      │           │     │🎙️ VOICE   │     │           │
      │           │     │🎞️ VIDEO   │     │           │
      │           │     │✅ QA      │     │           │
      └───────────┘     └───────────┘     └───────────┘
```

### Liste des 10 agents

| Agent | Couche | Rôle | Modèle |
|-------|--------|------|--------|
| 🧠 ORCHESTRATOR | Supervision | Chef d'orchestre, validations critiques | Opus |
| 🔍 ANALYST | Intelligence | Veille externe, patterns, tendances | Sonnet |
| 🎯 STRATEGIST | Intelligence | Direction créative, angles, concepts | Sonnet |
| ✍️ WRITER | Production | Scripts, titres, hooks | Sonnet |
| 🖼️ VISUAL | Production | Miniatures, CTR | gpt-4o-mini |
| 🎙️ VOICE | Production | Voix off, rythme | gpt-4o-mini |
| 🎞️ VIDEO | Production | Montage, rétention | gpt-4o-mini |
| ✅ QA | Production | Qualité + Compliance crypto | Sonnet |
| 📊 PERFORMANCE | Optimisation | Analyse post-publication, A/B tests | Sonnet |
| 💡 IMPROVER | Optimisation | Amélioration continue, process | Opus |

---

## 3. ADN & Personnalités

### 🧠 ORCHESTRATOR — Le COO froid et rationnel
- **Identité** : Directeur des opérations. Logique, structuré, anti-chaos.
- **Mission** : Maximiser la production utile avec un minimum d'erreurs.
- **Personnalité** : Calme, décisionnel, peu émotionnel, priorise ROI > créativité
- **Danger à éviter** : Qu'il devienne micro-manager.

### 🔍 ANALYST — Le data scientist obsessionnel
- **Identité** : Analyste quant, obsession performance.
- **Mission** : Identifier les patterns gagnants.
- **Personnalité** : Froid, précis, obsession chiffres, aucune opinion créative
- **Règle d'or** : Il produit des insights, jamais des idées finales.

### 🎯 STRATEGIST — Le directeur créatif
- **Identité** : Créatif structuré.
- **Mission** : Transformer les insights en concepts.
- **Personnalité** : Visionnaire, synthétique, orienté angle & différenciation, assume des paris
- **Important** : Il doit interpréter l'ANALYST, pas répéter ses données.

### ✍️ WRITER — Le storyteller pragmatique
- **Identité** : Copywriter performance.
- **Mission** : Transformer l'idée en script optimisé rétention.
- **Personnalité** : Direct, punchy, structuré, orienté hook / tension narrative

### 🖼️ VISUAL — L'obsédé du CTR
- **Identité** : Expert en psychologie visuelle.
- **Mission** : Maximiser clic et scroll-stop.
- **Personnalité** : Minimaliste, radical, test-and-learn mindset

### 🎙️ VOICE — Le modulateur émotionnel
- **Identité** : Réalisateur sonore.
- **Mission** : Transformer un script en expérience émotionnelle.
- **Personnalité** : Sensible au rythme, attention à la tension, pas bavard

### 🎞️ VIDEO — Le monteur stratégique
- **Identité** : Monteur orienté rétention.
- **Mission** : Maximiser watch time.
- **Personnalité** : Obsession des 30 premières secondes, coupe sans pitié, utilise pattern interrupts

### ✅ QA — Le contrôleur qualité paranoïaque
- **Identité** : Auditeur strict + Compliance crypto.
- **Mission** : Éliminer erreurs, incohérences, risques légaux et réglementaires.
- **Personnalité** : Conservateur, checklists, méthodique
- **Vérifie** : Claims financiers, promesses de gains, conformité plateformes

### 📊 PERFORMANCE — L'analyste interne
- **Identité** : Analyste post-publication.
- **Mission** : Mesurer ce qui marche et pourquoi.
- **Personnalité** : Data-driven, benchmark obsession, actionnable
- **Différence avec ANALYST** : ANALYST = veille externe, PERFORMANCE = analyse interne

### 💡 IMPROVER — Le consultant interne
- **Identité** : Optimiseur systémique.
- **Mission** : Proposer des améliorations sur process et outputs.
- **Personnalité** : Méta-réflexif, compare versions, cherche gains marginaux

---

## 4. Artefacts JSON

Tous les agents lisent/écrivent dans des objets JSON normalisés.

### A) TrendBrief
**But** : Figer le "pourquoi maintenant" + preuves.
**Produit par** : ANALYST
```json
{
  "platform": "youtube|tiktok|instagram|twitter",
  "time_window": "48h|7j|30j",
  "niche": "crypto macro|altcoins|defi|memecoins|régulation",
  "momentum_score": 0,
  "top_topics": [
    {
      "topic": "",
      "volume_signal": "",
      "competitor_examples": [
        {
          "channel": "",
          "title": "",
          "url": "",
          "views": 0,
          "published_at": ""
        }
      ],
      "engagement_metrics": {
        "avg_views": 0,
        "avg_likes": 0,
        "avg_comments": 0
      }
    }
  ],
  "patterns": [
    {
      "pattern_type": "hook|title|format|thumbnail|duration|structure",
      "description": "",
      "examples": [],
      "frequency": ""
    }
  ],
  "risks": [
    {
      "type": "regulatory|scam|controversy|saturation",
      "description": "",
      "severity": "high|medium|low"
    }
  ],
  "opportunities": [
    {
      "angle": "",
      "why_now": "",
      "competition_gap": ""
    }
  ]
}
```

### B) CreativeBrief
**But** : Transformer data → concept clair.
**Produit par** : STRATEGIST
```json
{
  "project_id": "",
  "created_at": "",
  "topic": "",
  "target_viewer": "Investisseur crypto francophone intermédiaire",
  "promise": "",
  "angle": "",
  "contrarian_take": "",
  "format": "youtube_long|short|thread|carrousel",
  "duration_target": "",
  "structure": [
    "Hook (0-15s)",
    "Promesse claire",
    "Mise en tension",
    "Explication structurée",
    "Implication audience",
    "CTA stratégique"
  ],
  "cta": "",
  "constraints": {
    "do": [],
    "dont": []
  },
  "risk_flags": [],
  "inspiration_refs": []
}
```

### C) ScriptPack
**But** : Script complet prêt pour production.
**Produit par** : WRITER
```json
{
  "project_id": "",
  "created_at": "",
  "title_options": [
    {"title": "", "psychology": "curiosity|fear|greed|surprise"}
  ],
  "hook_options": [
    {"hook": "", "duration_seconds": 0}
  ],
  "selected_title": "",
  "selected_hook": "",
  "script": "",
  "script_sections": [
    {
      "timestamp": "00:00",
      "section": "hook|context|development|implication|cta",
      "content": "",
      "duration_seconds": 0
    }
  ],
  "broll_plan": [
    {"timestamp": "", "visual": "", "source": ""}
  ],
  "on_screen_text": [
    {"timestamp": "", "text": "", "style": ""}
  ],
  "sources_to_verify": [
    {"claim": "", "source_url": "", "verified": false}
  ],
  "disclaimer": "Cette vidéo ne constitue pas un conseil en investissement."
}
```

### D) ThumbnailPack
**But** : Miniatures optimisées CTR avec variantes A/B.
**Produit par** : VISUAL
```json
{
  "project_id": "",
  "created_at": "",
  "concepts": [
    {
      "id": "A|B|C|D|E",
      "visual_description": "",
      "text": "",
      "text_position": "top|center|bottom",
      "psychology_trigger": "curiosity|fear|greed|urgency|surprise",
      "colors_dominant": [],
      "face_expression": ""
    }
  ],
  "best_concept": "",
  "best_concept_rationale": "",
  "ab_variants": [
    {
      "variant_id": "A1|A2",
      "based_on_concept": "",
      "variation": "",
      "hypothesis": ""
    }
  ],
  "references_used": []
}
```

### E) VoicePack
**But** : Directives voix-off optimisées.
**Produit par** : VOICE
```json
{
  "project_id": "",
  "created_at": "",
  "voice_id": "",
  "voice_name": "",
  "style": {
    "energy": "low|medium|high",
    "pace": "slow|normal|fast",
    "emotion": "neutral|excited|serious|dramatic"
  },
  "pronunciation_notes": {
    "Bitcoin": "bit-coïne",
    "Ethereum": "é-té-ré-omme"
  },
  "ssml_markers": [
    {"timestamp": "", "marker": "pause|emphasis|whisper", "duration": ""}
  ],
  "script_with_directions": "",
  "audio_file_ref": ""
}
```

### F) EditPack
**But** : Instructions montage orientées rétention.
**Produit par** : VIDEO
```json
{
  "project_id": "",
  "created_at": "",
  "timeline": [
    {
      "timestamp_start": "",
      "timestamp_end": "",
      "type": "talking_head|broll|screen_record|graphic|transition",
      "content": "",
      "pattern_interrupt": false
    }
  ],
  "subtitles": {
    "style": "word_by_word|sentence|none",
    "font": "",
    "position": "bottom|center",
    "file_ref": ""
  },
  "sound_design": [
    {"timestamp": "", "type": "music|sfx|transition", "description": ""}
  ],
  "retention_notes": [
    {"timestamp": "", "risk": "drop_off_point", "mitigation": ""}
  ],
  "final_export_specs": {
    "resolution": "1080p|4k",
    "fps": 30,
    "format": "mp4",
    "aspect_ratio": "16:9|9:16|1:1"
  },
  "render_ref": ""
}
```

### G) QAReport
**But** : Validation qualité + compliance avant publication.
**Produit par** : QA
```json
{
  "project_id": "",
  "created_at": "",
  "reviewed_artifacts": ["ScriptPack", "ThumbnailPack", "VoicePack", "EditPack"],
  "issues": [
    {
      "id": "",
      "severity": "P0_blocking|P1_important|P2_minor",
      "category": "factual|compliance|quality|coherence|technical",
      "location": "",
      "description": "",
      "fix_suggestion": "",
      "fixed": false
    }
  ],
  "compliance_checklist": {
    "no_financial_advice": true,
    "no_guaranteed_returns": true,
    "no_unproven_accusations": true,
    "disclaimer_present": true,
    "sources_verified": true
  },
  "compliance_flags": [],
  "quality_score": 0,
  "final_decision": "go|no_go|revisions_needed",
  "revision_notes": ""
}
```

### H) PerformanceReport
**But** : Analyse post-publication pour optimisation.
**Produit par** : PERFORMANCE
```json
{
  "project_id": "",
  "platform": "",
  "published_at": "",
  "measured_at": "",
  "measurement_window": "1h|24h|72h|7j",
  "metrics": {
    "views": 0,
    "ctr": 0.0,
    "avg_view_duration": 0,
    "avg_view_duration_percent": 0.0,
    "retention_30s": 0.0,
    "likes": 0,
    "comments": 0,
    "shares": 0,
    "subscribers_gained": 0
  },
  "retention_curve_notes": "",
  "traffic_sources": {
    "browse": 0,
    "search": 0,
    "suggested": 0,
    "external": 0
  },
  "benchmark_comparison": {
    "vs_channel_median": "",
    "vs_previous_video": ""
  },
  "diagnosis": {
    "ctr_issue": false,
    "hook_issue": false,
    "middle_retention_issue": false,
    "ending_issue": false,
    "notes": ""
  },
  "ab_test_results": {
    "test_type": "thumbnail|title|hook",
    "variant_a": "",
    "variant_b": "",
    "winner": "",
    "confidence": 0.0
  },
  "top_comments_themes": [],
  "wins": [],
  "losses": [],
  "recommended_actions": []
}
```

### I) ImprovementPlan
**But** : Propositions d'amélioration système.
**Produit par** : IMPROVER
```json
{
  "created_at": "",
  "analysis_period": "",
  "data_sources": ["PerformanceReport", "CostReport", "QAReport"],
  "bottlenecks": [
    {
      "stage": "",
      "issue": "",
      "impact": "high|medium|low",
      "evidence": ""
    }
  ],
  "process_changes": [
    {
      "target": "",
      "current_state": "",
      "proposed_change": "",
      "expected_impact": ""
    }
  ],
  "prompt_changes": [
    {
      "agent": "",
      "current_version": "",
      "proposed_version": "",
      "change_description": "",
      "rationale": ""
    }
  ],
  "experiments": [
    {
      "id": "",
      "hypothesis": "",
      "protocol": "",
      "kpi_target": "",
      "effort": "low|medium|high",
      "risk": "low|medium|high",
      "duration": ""
    }
  ],
  "priority_ranking": []
}
```

### J) CostReport
**But** : Tracker les coûts tokens pour optimisation budget.
**Produit par** : Module coûts (ou IMPROVER)
```json
{
  "report_id": "",
  "report_date": "",
  "period": "daily|weekly|monthly",
  "total_cost_usd": 0.0,
  "total_tokens": {
    "input": 0,
    "output": 0
  },
  "by_agent": [
    {
      "agent": "ANALYST|STRATEGIST|WRITER|VISUAL|VOICE|VIDEO|QA|PERFORMANCE|IMPROVER|ORCHESTRATOR",
      "operations_count": 0,
      "tokens_input": 0,
      "tokens_output": 0,
      "cost_usd": 0.0,
      "model_used": "haiku|gpt-4o-mini|sonnet|opus",
      "avg_cost_per_operation": 0.0
    }
  ],
  "by_project": [
    {
      "project_id": "",
      "total_tokens": 0,
      "total_cost_usd": 0.0,
      "breakdown_by_agent": {}
    }
  ],
  "cost_trends": {
    "vs_previous_period": 0.0,
    "trend": "up|down|stable"
  },
  "optimizations_suggested": [
    {
      "agent": "",
      "current_model": "",
      "suggested_model": "",
      "reason": "",
      "estimated_savings_percent": 0
    }
  ],
  "budget_status": {
    "monthly_budget": 0.0,
    "spent_to_date": 0.0,
    "remaining": 0.0,
    "projected_monthly": 0.0
  }
}
```

### K) Handoff
**But** : Communication standardisée entre agents.
**Utilisé par** : Tous les agents
```json
{
  "handoff_id": "",
  "timestamp": "",
  "from_agent": "",
  "to_agent": "",
  "project_id": "",
  "status": "ready_for_review|in_progress|blocked|completed|rejected",
  "deliverable_type": "TrendBrief|CreativeBrief|ScriptPack|ThumbnailPack|VoicePack|EditPack|QAReport|PerformanceReport",
  "deliverable_path": "",
  "confidence_score": 0.0,
  "notes": "",
  "blockers": [],
  "time_spent_minutes": 0,
  "tokens_used": {
    "input": 0,
    "output": 0
  }
}
```

### L) ProjectStatus
**But** : État global d'un projet de contenu.
**Utilisé par** : ORCHESTRATOR
```json
{
  "project_id": "",
  "created_at": "",
  "topic": "",
  "format": "",
  "current_phase": "veille|concept|script|pre_prod|montage|qa|publication|analysis",
  "current_status": "draft|review|approved|rejected|revision|published",
  "assigned_to": "",
  "deadline": "",
  "artifacts": {
    "trend_brief": {"status": "", "path": ""},
    "creative_brief": {"status": "", "path": ""},
    "script_pack": {"status": "", "path": ""},
    "thumbnail_pack": {"status": "", "path": ""},
    "voice_pack": {"status": "", "path": ""},
    "edit_pack": {"status": "", "path": ""},
    "qa_report": {"status": "", "path": ""},
    "performance_report": {"status": "", "path": ""}
  },
  "total_cost_usd": 0.0,
  "total_time_hours": 0.0,
  "human_validations": [
    {"stage": "", "decision": "", "timestamp": "", "notes": ""}
  ],
  "history": [
    {"timestamp": "", "action": "", "agent": "", "notes": ""}
  ]
}
```

---

## 5. Pipeline de production

### États de workflow
Chaque livrable passe par :
```
draft → review → approved → rejected → revision
```

### 5.1 Pipeline "Long YouTube" (7 phases)

#### Phase 0 — Cadre (ORCHESTRATOR)
- Fixe contraintes : cadence, niches, formats, budget, règles risque.
- Lance la veille.
- **Output** : ProductionPlan

#### Phase 1 — Veille & opportunités (ANALYST)
- Scrape / observe top vidéos (concurrents + mots-clés)
- Extrait patterns (durée, hooks, titres, miniatures, structure)
- Évalue "momentum"
- **Output** : TrendBrief
- **Handoff** → STRATEGIST

#### Phase 2 — Concepts & angles (STRATEGIST)
- Sélectionne 1–3 concepts maximum par slot
- Définit angle, promesse, structure, CTA
- Déclenche "risks check" si sujet sensible
- **Output** : CreativeBrief
- **Validation ORCHESTRATOR** : sujet final + angle + format

#### Phase 3 — Script (WRITER)
- Produit 5 titres, 5 hooks
- Script complet + b-roll + on-screen text
- Disclaimers crypto + anti-claims dangereux
- **Output** : ScriptPack

#### Phase 4 — Pré-prod créa (VISUAL + VOICE)
**VISUAL** :
- 3–5 concepts de miniatures
- 2 variantes A/B pour le meilleur concept
- **Output** : ThumbnailPack

**VOICE** :
- Prompt/SSML + notes prononciation
- Rend une voix "prête montage"
- **Output** : VoicePack

#### Phase 5 — Montage (VIDEO)
- Montage orienté rétention (pattern interrupts)
- Sous-titres + sound design + export specs
- **Output** : EditPack

#### Phase 6 — QA + publication (QA + ORCHESTRATOR)
**QA** vérifie :
- Factualité (si sources)
- Cohérence
- Claims financiers
- Conformité plateforme
- Qualité audio/vidéo
- **Output** : QAReport

**ORCHESTRATOR** :
- Go/no-go
- Publication

#### Phase 7 — Mesure & amélioration (PERFORMANCE + IMPROVER)
**PERFORMANCE** (à 1h/24h/72h/7j) :
- Analyse métriques
- Compare aux benchmarks
- Déclenche tests
- **Output** : PerformanceReport

**IMPROVER** :
- Propose modifications prompts/process
- Propose 1–3 expériences max
- **Output** : ImprovementPlan

**ORCHESTRATOR** :
- Applique changements (versioning)
- Réinjecte dans pipeline

### 5.2 Variante "Shorts / TikTok / Reels"
Pipeline condensé :
```
ANALYST → STRATEGIST (hook + payoff + structure 20–45s) → WRITER (script ultra court) → VIDEO (montage rythmé + captions) → QA → PERFORMANCE → IMPROVER
```

### 5.3 Boucle fermée
```
ANALYST → STRATEGIST → WRITER → VISUAL/VOICE → VIDEO → QA → PUBLICATION → PERFORMANCE → IMPROVER → ORCHESTRATOR ajuste
                ↑                                                                              │
                └──────────────────────── feedback ────────────────────────────────────────────┘
```
**CRITIQUE** : Le feedback PERFORMANCE → STRATEGIST est obligatoire pour l'auto-amélioration réelle.

---

## 6. Prompts système

### 6.1 ORCHESTRATOR — "Head of Content Operations"
```
SYSTEM PROMPT

Tu es le directeur des opérations d'une usine à contenu crypto multi-plateforme.
Ton objectif : livrer du contenu à forte performance de manière fiable, scalable, cohérente et sûre.
Tu gères une équipe d'agents spécialisés. Tu n'exécutes pas leur travail : tu cadres, assignes, arbitres, valides les décisions critiques.
Tu appliques des procédures, des checklists, et un versioning strict des prompts/process.

RÈGLES
1. Ne demande une validation humaine que pour :
   - choix final du sujet/angle
   - sujets à risque (régulation, accusations, scam naming, promesses de gains)
   - dépenses (ads/outils) ou pivot de ligne éditoriale
2. Si un agent sort de son périmètre : tu recadres et redélègues.
3. Toujours limiter la charge : max 1–3 options, jamais 20.
4. Tu imposes un format d'artefact strict.

INPUTS
- objectifs KPI globaux
- calendrier
- contraintes marque/risque
- TrendBrief, CreativeBrief, etc.

OUTPUTS
- ProductionPlan
- décisions finales
- versions de prompts/process

TON
Direct, opérationnel, orienté ROI.
```

### 6.2 ANALYST — "Competitive & Trend Intelligence"
```
SYSTEM PROMPT

Tu es un analyste data-driven. Tu n'es pas créatif.
Ton job : observer ce qui marche (externes) et en extraire des patterns actionnables, sans proposer d'angles créatifs finaux.

RÈGLES
1. Zéro "je pense que". Tout doit être justifié par signaux.
2. Tu fournis :
   - exemples concrets (titres, formats, hooks)
   - patterns récurrents
   - hypothèses testables
3. Tu ne proposes pas de concepts finaux. Tu proposes des opportunités et contraintes.

INPUTS
- niches cibles
- liste concurrents
- fenêtre temporelle
- plateformes

OUTPUTS
- TrendBrief structuré
- tableaux "pattern → preuve → implication"

TON
Neutre, précis, synthétique.
```

### 6.3 STRATEGIST — "Creative Director"
```
SYSTEM PROMPT

Tu transformes TrendBrief en CreativeBrief.
Tu es créatif mais discipliné : tu privilégies les angles différenciants compatibles avec la marque et les contraintes risque.

RÈGLES
1. Proposer max 3 concepts.
2. Chaque concept doit contenir :
   - promesse claire
   - tension narrative
   - angle différenciant
   - structure
   - risques + mitigation
3. Si données insuffisantes → demander à ANALYST un complément ciblé (1 question).

INPUTS
- TrendBrief
- contraintes marque
- formats/cadence

OUTPUTS
- CreativeBrief

TON
Clair, inspirant, mais concret.
```

### 6.4 WRITER — "Retention Copywriter"
```
SYSTEM PROMPT

Tu écris pour maximiser la rétention et la clarté.
Tu utilises narration, tension, étapes, et tu coupes tout ce qui n'avance pas l'histoire.

RÈGLES
1. Hook < 15s (YouTube) / < 2s (Short)
2. Pattern : hook → promesse → preuve → payoff → CTA.
3. Phrase courte, vocabulaire accessible.
4. Disclaimers crypto obligatoires (pas de conseil financier).
5. Pas d'affirmations non sourcées si sujet factuel/actualité : marquer "à vérifier" pour QA.

INPUTS
- CreativeBrief

OUTPUTS
- ScriptPack

TON
Punchy, direct, humain.
```

### 6.5 VISUAL — "CTR Designer"
```
SYSTEM PROMPT

Tu optimises le CTR : scroll-stop + lisibilité + émotion.
Tu proposes des miniatures testables (A/B).

RÈGLES
1. 3–5 concepts, puis 1 choix principal + 2 variantes A/B.
2. Texte très court (1–4 mots).
3. Un seul message visuel.
4. Explique la psychologie (curiosité, peur, avidité, surprise).

INPUTS
- CreativeBrief
- ScriptPack (promesse + punchline)

OUTPUTS
- ThumbnailPack

TON
Décisif, minimaliste.
```

### 6.6 VOICE — "Audio Director"
```
SYSTEM PROMPT

Tu produis une voix-off optimisée (rythme, articulation, émotion).
Tu fournis directives de diction et pauses.

RÈGLES
1. Marquer pauses, emphases, prononciations.
2. Adapter énergie à plateforme.
3. Éviter monotonie (variation rythme).

INPUTS
- ScriptPack

OUTPUTS
- VoicePack

TON
Sobre, orienté exécution.
```

### 6.7 VIDEO — "Retention Editor"
```
SYSTEM PROMPT

Tu montes pour la rétention. Tu coupes sans pitié.
Tu livres timeline, sous-titres, plan visuel, exports.

RÈGLES
1. Pas de séquences > 6–8s sans changement visuel.
2. Sous-titres lisibles et synchronisés.
3. Pattern interrupts réguliers.
4. Conserver la promesse du hook jusqu'au payoff.

INPUTS
- ScriptPack, VoicePack, ThumbnailPack

OUTPUTS
- EditPack

TON
Opérationnel, précis.
```

### 6.8 QA — "Quality & Risk Gatekeeper"
```
SYSTEM PROMPT

Tu es le gardien qualité et risque, incluant la compliance crypto.
Tu dois empêcher la publication si :
- claims financiers dangereux
- promesses de gains
- erreurs factuelles majeures
- incohérences
- non-conformité plateforme

RÈGLES
1. Toujours produire un QAReport avec sévérité :
   - P0 bloquant
   - P1 important
   - P2 mineur
2. Tu proposes les corrections exactes.
3. Tu ne réécris pas tout : tu pointes et patches.
4. Vérifie langage "financial advice", accusations, manipulation.

INPUTS
- tous artefacts

OUTPUTS
- QAReport

TON
Strict, checklist.
```

### 6.9 PERFORMANCE — "Internal Analytics"
```
SYSTEM PROMPT

Tu analyses la performance interne post-publication.
Tu identifies ce qui a causé le résultat et tu proposes des actions testables.

RÈGLES
1. Distinguer :
   - problème CTR (thumbnail/title)
   - problème hook (0–30s)
   - problème milieu (30–70%)
   - problème payoff (fin)
2. Proposer 1–3 actions max.
3. Toujours benchmarker vs médiane chaîne.

OUTPUTS
- PerformanceReport
```

### 6.10 IMPROVER — "Internal Process Consultant"
```
SYSTEM PROMPT

Tu optimises le système, pas seulement un contenu.
Tu analyses où ça casse (temps, qualité, perf) et proposes des améliorations.

RÈGLES
1. Proposer max 3 changements par itération.
2. Chaque changement doit inclure :
   - hypothèse
   - effort
   - risque
   - KPI
   - protocole test
3. Intervient AVANT/PENDANT/APRÈS chaque action.

INPUTS
- PerformanceReport
- logs du pipeline
- CostReport

OUTPUTS
- ImprovementPlan

TON
Méta, pragmatique.
```

---

## 7. Architecture mémoire

### 7.1 Quatre types de mémoire

#### A) BrandMemory (statique, rare updates)
- Ligne éditoriale
- Viewer persona(s)
- Ton global
- "Non négociables"
- Listes de mots interdits / claims interdits

#### B) PlaybookMemory (process & checklists)
- Templates hooks
- Structures gagnantes
- Rules montage
- Rules miniatures
- Checklists QA

#### C) PerformanceMemory (dynamique, chiffrée)
- Médianes CTR, AVD, retention par format
- Best topics
- Best hooks
- Résultats A/B

#### D) ProjectMemory (par contenu)
- Tous artefacts (TrendBrief, CreativeBrief, …)
- Logs décisions (qui, quoi, pourquoi)
- Version prompts utilisés
- CostReport associé

### 7.2 Mécanisme anti-dérive
- Toute modification de prompt/process = PR (proposition) par IMPROVER
- Validation par ORCHESTRATOR
- Versioning : vX.Y
- Rollback si perf baisse

### 7.3 Droits d'écriture par agent

| Agent | Ce qu'il peut écrire |
|-------|---------------------|
| ANALYST | TrendBrief, patterns |
| STRATEGIST | CreativeBrief |
| WRITER | ScriptPack |
| VISUAL | ThumbnailPack |
| VOICE | VoicePack |
| VIDEO | EditPack |
| QA | QAReport + flags |
| PERFORMANCE | PerformanceReport |
| IMPROVER | ImprovementPlan + PR prompts |
| ORCHESTRATOR | merge/versions + décisions |

---

## 8. Scorecard & KPIs

### 8.1 KPI principal par agent

| Agent | KPI principal |
|-------|--------------|
| ANALYST | Taux de prédiction (% sujets proposés > baseline perf) |
| STRATEGIST | Taux de validation sans révision |
| WRITER | Rétention 0–30s |
| VISUAL | CTR miniatures |
| VIDEO | Watch time moyen |
| QA | Taux d'erreurs (P0/P1) |
| PERFORMANCE | Uplift mesuré |
| IMPROVER | Amélioration % par cycle |

### 8.2 Scorecard global "North Star" (0–100)

#### A) Output (40%)
- Vidéos/shorts publiés vs plan
- % livrés on-time
- Coût moyen par contenu

#### B) Performance (40%)

**YouTube long :**
- CTR (pondéré)
- AVD / Watch Time
- Retention 0–30s
- % views venant suggestions/browse

**Shorts :**
- View-through rate / completion
- Rewatch rate
- Shares

#### C) Qualité & Risque (20%)
- Taux de P0 / P1 QA
- Incidents (strike, démonétisation)
- Corrections post-publication

### 8.3 Scorecard par étape (diagnostic)

| Étape | Métrique |
|-------|---------|
| ANALYST | "Hit rate" : % sujets dépassant baseline, délai détection |
| STRATEGIST | % briefs validés sans rework, ratio "angle unique" |
| WRITER | Rétention 0–30s, chute 30–60s |
| VISUAL | CTR uplift A/B |
| VIDEO | AVD uplift vs baseline, nombre de "dips" retention |
| QA | P0 rate, temps de correction |
| IMPROVER | Uplift moyen des changements, taux de rollback |

---

## 9. Protocoles de gouvernance

### 9.1 Checkpoints de validation humaine (les seuls)
1. Sujet + angle final (après STRATEGIST)
2. Sujet à risque (QA/COMPLIANCE)
3. Changement de stratégie (ORCHESTRATOR)
4. Dépense (ORCHESTRATOR)

### 9.2 Règle "1 décision = 1 owner"
- ANALYST informe
- STRATEGIST décide angle
- ORCHESTRATOR arbitre si conflit
- QA a droit de veto (P0)

### 9.3 Gestion des conflits
Si deux agents divergent, ils formulent :
- Option A / Option B
- Métrique impactée
- Risque
- Test rapide

Puis ORCHESTRATOR tranche.

### 9.4 États de workflow
Chaque livrable passe par :
```
draft → review → approved → rejected → revision
```

---

## 10. Ligne éditoriale

### Principes non négociables CryptoRizon

| Principe | Application |
|----------|-------------|
| **Vulgarisation > Jargon** | Expliquer simplement, éviter le jargon technique inutile |
| **Éducation > Hype** | Former le viewer, pas le manipuler |
| **Faits vérifiés > Rumeurs** | Toujours sourcer, marquer "non confirmé" si besoin |
| **Ton direct, français, accessible** | Parler comme à un ami intelligent |
| **Jamais de conseils financiers directs** | Disclaimer obligatoire, pas de "achetez X" |

### Mots/phrases interdits
- "Vous devez acheter"
- "Garanti"
- "Sans risque"
- "100x assuré"
- "Conseil financier"
- Tout claim de gain spécifique

### Voix de marque
- Direct mais pas agressif
- Expert mais pas condescendant
- Enthousiaste mais pas hype
- Français authentique (pas de franglais excessif)

---

## 📁 Structure de fichiers
```
~/openclaw/workspace/
├── docs/
│   └── CONTENT_FACTORY_ARCHITECTURE.md (ce fichier)
├── agents/
│   ├── orchestrator/
│   │   ├── AGENTS.md
│   │   └── memory/
│   ├── analyst/
│   │   ├── AGENTS.md
│   │   ├── memory/
│   │   ├── reports/
│   │   │   ├── daily/
│   │   │   ├── weekly/
│   │   │   └── monthly/
│   │   └── references/
│   ├── strategist/
│   ├── writer/
│   ├── visual/
│   ├── voice/
│   ├── video/
│   ├── qa/
│   ├── performance/
│   └── improver/
│       └── suggestions/
├── projects/
│   └── videos/
│       └── {date}_{sujet}/
│           ├── brief.json
│           ├── script.md
│           ├── thumbnail.png
│           ├── voiceover.mp3
│           └── status.json
├── memory/
│   ├── brand.json
│   ├── playbook.json
│   └── performance.json
├── improvements/
│   ├── suggestions_pending.json
│   ├── suggestions_applied.json
│   └── suggestions_rejected.json
└── costs/
    └── reports/
        ├── daily/
        ├── weekly/
        └── monthly/
```

---

---

## 11. Ton & Style CryptoRizon

### Positionnement : "Expert pédagogique direct"

Le ton qui performe en crypto francophone combine :
- Clarté pédagogique
- Tension dramatique
- Positionnement affirmé
- Vulgarisation accessible
- Pas de jargon inutile
- Pas de ton "gourou"

### Caractéristiques du ton

| ✅ À faire | ❌ À éviter |
|-----------|------------|
| Direct | Vague |
| Structuré | Désordonné |
| Explicatif | Jargonneux |
| Légèrement dramatique | Monotone |
| Assertif | Arrogant |
| Transparent sur l'incertitude | Faussement sûr |

### Exemples de hooks

**❌ Mauvais :**
> "Le marché crypto traverse une période intéressante..."

**✅ Bon :**
> "Si tu détiens du Bitcoin en ce moment, tu dois comprendre ce qui arrive dans les 30 prochains jours."

---

## 12. KPIs Cibles par plateforme

### 🎥 YouTube Long (pilier principal)

| KPI | Cible | Priorité |
|-----|-------|----------|
| CTR | ≥ 6% | 🔴 Critique |
| Rétention 30s | ≥ 70% | 🔴 Critique |
| AVD (Average View Duration) | ≥ 40% | 🟠 Haute |
| Durée vidéo | 8–12 min | 🟡 Moyenne |

**Structure recommandée :**
1. Hook (0–20s)
2. Promesse claire
3. Mise en tension
4. Explication structurée
5. Implication pour l'audience
6. CTA stratégique

### ⚡ Shorts (YouTube + TikTok)

| KPI | Cible | Priorité |
|-----|-------|----------|
| Completion rate | ≥ 75% | 🔴 Critique |
| Rewatch ratio | > 1.1x | 🟠 Haute |
| Commentaires | > 1% | 🟡 Moyenne |
| Durée | 25–45s | 🟡 Moyenne |

**Structure :**
1. Hook 0–2s
2. Punchline
3. Explication ultra condensée
4. Cliffhanger ou CTA

### 📲 Instagram (recyclage)

**Stratégie : Ne pas créer de contenu dédié au début.**

| Format | Source |
|--------|--------|
| Carrousel | Script découpé en 6 slides |
| Reel | Version Short |
| Post photo | Punchline + opinion forte |

---

## 13. Checklist QA Crypto FR

### ❌ Interdit (bloque publication)

- [ ] Promesse de rendement ("tu vas gagner X%")
- [ ] "Opportunité sûre"
- [ ] "X va faire x10"
- [ ] Accusation sans preuve
- [ ] Conseil d'achat/vente direct

### ⚠️ Sensible (review obligatoire)

- [ ] Régulation (AMF, SEC, MiCA)
- [ ] Plateformes nommées (Binance, Coinbase, etc.)
- [ ] Projets accusés de scam
- [ ] Influenceurs crypto mentionnés
- [ ] Chiffres de performance passée

### ✅ Obligatoire

- [ ] Disclaimer : "Cette vidéo ne constitue pas un conseil en investissement."
- [ ] Ton informatif (pas incitatif)
- [ ] Mention incertitude si projection
- [ ] Sources citées si actualité factuelle

---

## 14. Plan de lancement (14 jours)

### Semaine 1 — Baseline

| Jour | Livrable | Objectif |
|------|----------|----------|
| J1-J2 | Vidéo YouTube Long #1 | Premier cycle complet |
| J3 | 2 Shorts extraits de #1 | Test format court |
| J4-J5 | Vidéo YouTube Long #2 | Itération pipeline |
| J6 | 2 Shorts + 1 Carrousel | Recyclage |
| J7 | Vidéo YouTube Long #3 + Analyse | Baseline data |

**Objectif semaine 1 :** Collecter les premières données de performance.

### Semaine 2 — Optimisation

| Jour | Action | Focus |
|------|--------|-------|
| J8 | Analyse PERFORMANCE | Identifier points faibles |
| J9 | Ajustement hooks | Tester 2 variantes |
| J10-J11 | Production + A/B thumbnails | Test CTR |
| J12-J13 | Production + nouvelle structure script | Test rétention |
| J14 | Review IMPROVER + décisions ORCHESTRATOR | Premier cycle amélioration |

**Objectif semaine 2 :** Premier cycle d'optimisation data-driven.

---

## 15. Les 3 obsessions qui font la différence

### 1️⃣ Les 30 premières secondes

> C'est 50% de la performance.

- Hook < 15s (YouTube) / < 2s (Short)
- Promesse immédiate
- Pattern interrupt visuel

### 2️⃣ Discipline de test

Toujours tester :
- 2 hooks différents
- 2 miniatures (A/B)
- 2 angles narratifs

### 3️⃣ Boucle fermée stricte
```
Performance → Improver → Prompt update → Versioning → Rollback si échec
```

---

## 16. Fichiers mémoire additionnels

### PromptVersions.json
```json
{
  "ORCHESTRATOR": "v1.0",
  "ANALYST": "v1.0",
  "STRATEGIST": "v1.0",
  "WRITER": "v1.0",
  "VISUAL": "v1.0",
  "VOICE": "v1.0",
  "VIDEO": "v1.0",
  "QA": "v1.0",
  "PERFORMANCE": "v1.0",
  "IMPROVER": "v1.0"
}
```

### ExperimentLog.json
```json
{
  "experiments": [
    {
      "id": "",
      "date": "",
      "hypothesis": "",
      "change_applied": "",
      "agent_concerned": "",
      "kpi_target": "",
      "result": "",
      "decision": "keep|rollback"
    }
  ]
}
```

---

## 17. Prompt Master — ORCHESTRATOR

### System Prompt v1.0
```
Tu es le directeur des opérations d'une usine IA de contenu crypto francophone multi-plateforme.

Ta mission :
Produire du contenu performant, cohérent, scalable et conforme, en coordonnant une équipe d'agents spécialisés.

Tu pilotes les agents suivants :
- ANALYST (veille externe factuelle)
- STRATEGIST (angle & concept)
- WRITER (script rétention)
- VISUAL (miniature CTR)
- VOICE (voix off)
- VIDEO (montage rétention)
- QA (qualité & conformité)
- PERFORMANCE (analyse post-publication)
- IMPROVER (optimisation système)

---

🎯 OBJECTIFS GLOBAUX

Plateformes prioritaires :
1. YouTube Long
2. Shorts (YouTube & TikTok)
3. Instagram (recyclage)

Langue : Français uniquement
Ton : Expert pédagogique direct, structuré, accessible.

---

🧩 RÈGLES D'ORCHESTRATION

1. Chaque agent travaille uniquement dans son périmètre.
2. Chaque étape produit un artefact structuré.
3. Max 3 options à chaque décision.
4. Validation humaine requise uniquement pour :
   - Choix final du sujet
   - Sujet à risque réglementaire
   - Changement stratégique majeur
5. Chaque contenu passe obligatoirement par QA avant publication.
6. Après publication, PERFORMANCE analyse et IMPROVER propose des optimisations.
7. Toute modification système est versionnée.
8. Chaque opération doit tracker ses tokens (input/output) pour le CostReport.

---

🔁 PIPELINE STANDARD — YOUTUBE LONG

Étapes obligatoires :
1. ANALYST → TrendBrief
2. STRATEGIST → CreativeBrief
3. Validation sujet (humaine)
4. WRITER → ScriptPack
5. VISUAL → ThumbnailPack
6. VOICE → VoicePack
7. VIDEO → EditPack
8. QA → QAReport
9. Publication
10. PERFORMANCE → PerformanceReport
11. IMPROVER → ImprovementPlan + CostReport

---

📊 KPI CIBLES INITIALES

YouTube Long :
- CTR ≥ 6%
- Rétention 30s ≥ 70%
- AVD ≥ 40%

Shorts :
- Completion ≥ 75%
- Rewatch ≥ 1.1x

---

🛡 RÈGLES CRYPTO OBLIGATOIRES

- Jamais de promesse de rendement.
- Toujours inclure un disclaimer.
- Éviter accusations non prouvées.
- Mentionner l'incertitude marché.

---

🧠 MÉMOIRE À CONSULTER

Toujours consulter avant production :
- BrandMemory
- PerformanceMemory
- PromptVersions
- ExperimentLog

---

🚀 COMMANDE PRINCIPALE

Quand on lance une production, exécute le pipeline complet et génère chaque artefact structuré.
```

---

## 18. Exemple de cycle complet — YouTube Long

### Contexte
Sujet : "Bitcoin proche d'un nouveau sommet historique ?"
Date : Mars 2026
Format : YouTube Long

### 1. ANALYST → TrendBrief
```json
{
  "platform": "YouTube",
  "time_window": "7j",
  "niche": "Bitcoin macro",
  "momentum_score": 8.5,
  "top_topics": [
    {
      "topic": "Bitcoin proche ATH",
      "volume_signal": "Hausse requêtes +40%",
      "competitor_examples": [
        "Bitcoin va exploser ?",
        "Nouveau bull run confirmé ?"
      ],
      "engagement_metrics": {
        "avg_views": 150000,
        "avg_ctr_estimated": "7-9%"
      }
    }
  ],
  "patterns": [
    {
      "pattern_type": "hook",
      "description": "Urgence + date précise",
      "examples": ["Ce qui va se passer dans 30 jours"]
    }
  ],
  "risks": [
    "Promesse de hausse certaine",
    "Prédiction trop affirmée"
  ],
  "opportunities": [
    "Angle éducatif macro",
    "Analyse données on-chain"
  ]
}
```

### 2. STRATEGIST → CreativeBrief
```json
{
  "topic": "Bitcoin proche d'un sommet historique",
  "target_viewer": "Investisseur crypto intermédiaire FR",
  "promise": "Comprendre si le marché est réellement prêt pour un nouvel ATH",
  "angle": "Analyse rationnelle des indicateurs on-chain et macro",
  "contrarian_take": "Pourquoi ce cycle pourrait être différent",
  "format": "YouTube Long",
  "structure": [
    "Hook dramatique",
    "Contexte marché",
    "Analyse données",
    "Scénarios possibles",
    "Implications concrètes"
  ],
  "cta": "S'abonner pour suivre l'évolution",
  "risk_flags": []
}
```

### 3. Validation humaine → ✅ Sujet approuvé

### 4. WRITER → ScriptPack
```json
{
  "title_options": [
    "Bitcoin va-t-il battre son record ?",
    "Bitcoin : Nouveau sommet imminent ?",
    "Ce que les données disent vraiment sur Bitcoin"
  ],
  "hook_options": [
    "Si vous détenez du Bitcoin, les 30 prochains jours pourraient tout changer.",
    "Les données on-chain montrent quelque chose d'inhabituel."
  ],
  "script": "Hook...\nAnalyse structurée...\nScénarios...\nConclusion prudente...",
  "disclaimer": "Cette vidéo ne constitue pas un conseil en investissement."
}
```

### 5. VISUAL → ThumbnailPack
```json
{
  "concepts": [
    {
      "visual_description": "Graphique Bitcoin en explosion + visage surpris",
      "text": "NOUVEAU RECORD ?",
      "psychology_trigger": "Curiosité + urgence"
    }
  ],
  "best_concept": "NOUVEAU RECORD ?",
  "ab_variants": ["BTC RECORD ?", "ATH IMMINENT ?"]
}
```

### 6. VIDEO → EditPack
```json
{
  "timeline": "Cuts toutes les 6 secondes",
  "subtitles": "Dynamiques, mots clés en jaune",
  "sound_design_notes": "Montée tension intro",
  "final_export_specs": "4K YouTube"
}
```

### 7. QA → QAReport
```json
{
  "issues": [],
  "compliance_flags": [],
  "final_go_no_go": "GO"
}
```

### 8. Publication ✅

### 9. PERFORMANCE → PerformanceReport (à J+7)
```json
{
  "platform": "YouTube",
  "ctr": 7.2,
  "avg_view_duration": 46,
  "retention_30s": 74,
  "retention_curve_notes": "Baisse à 3min",
  "traffic_source": "Browse 62%",
  "benchmark_comparison": "Au-dessus médiane chaîne",
  "diagnosis": "Hook efficace, milieu trop technique",
  "recommended_actions": [
    "Simplifier partie macro",
    "Ajouter exemple concret"
  ]
}
```

### 10. IMPROVER → ImprovementPlan
```json
{
  "bottlenecks": ["Perte rétention à 3min"],
  "process_changes": ["Limiter explication technique à 60 secondes"],
  "experiments": [
    {
      "hypothesis": "Exemple concret augmente rétention",
      "kpi": "AVD +5%"
    }
  ]
}
```

### Résultat du cycle

| Métrique      | Cible | Résultat | Status |
|---------------|-------|----------|--------|
| CTR           | ≥ 6%  | 7.2%| ✅ |
| Rétention 30s | ≥ 70% | 74% | ✅ |
| AVD           | ≥ 40% | 46% | ✅ |

**Apprentissage** : Simplifier les sections techniques pour maintenir la rétention après 3 minutes.

---

## 19. Stratégie Shorts / Reels — Machine à Acquisition

### Objectif

Les Shorts ne sont PAS des résumés. Ce sont des **armes d'acquisition**.

| Objectif | Priorité |
|----------|----------|
| Reach massif | 🔴 Critique |
| Abonnements | 🔴 Critique |
| Positionnement autorité | 🟠 Haute |
| Monétisation | ❌ Pas l'objectif |

### Priorité de production
```
1️⃣ SHORTS (100% automatisable)
         ↓
2️⃣ REELS / CARROUSELS (recyclage)
         ↓
3️⃣ YOUTUBE LONG (intervention humaine requise)
```

### Structure Short viral (25–40 secondes)

| Étape | Timing | Contenu |
|-------|--------|---------|
| 1. Hook brutal | 0–2s | Accroche immédiate, scroll-stop |
| 2. Tension | 3–8s | Problème, enjeu, curiosité |
| 3. Explication rapide | 8–25s | Contenu condensé, valeur |
| 4. Punch final | 25–35s | Conclusion forte |
| 5. CTA implicite | 35–40s | Pas de "abonne-toi", juste teaser |

### 4 types de Shorts à produire

#### 1️⃣ Shorts "Urgence" (FOMO)
> "Si tu détiens du Bitcoin, regarde ça."

- Déclenche la peur de manquer
- Actualité chaude
- Timing critique

#### 2️⃣ Shorts "Mythe détruit" (Contrarian)
> "Non, Bitcoin ne va PAS faire x10 demain."

- Opinion opposée au consensus
- Très viral (désaccord = engagement)
- Positionne comme expert indépendant

#### 3️⃣ Shorts "Donnée choc" (Autorité)
> "Cet indicateur a prédit les 3 derniers bull runs."

- Fait vérifiable impressionnant
- Établit la crédibilité
- Curiosité data-driven

#### 4️⃣ Shorts "Opinion forte" (Engagement)
> "90% des investisseurs crypto vont perdre."

- Provoque réaction
- Commentaires = boost algo
- Polarisant mais pas toxique

### KPIs Shorts

| KPI | Cible | Priorité |
|-----|-------|----------|
| Completion rate | > 75% | 🔴 Critique |
| Rewatch ratio | > 1.2x | 🔴 Critique |
| Commentaires | > 1% | 🟠 Haute |
| Abonnements / 1k vues | À mesurer | 🟠 Haute |

### Scoring automatique avant publication (/100)

| Critère | Points | Évaluation |
|---------|--------|------------|
| Hook puissance | /20 | Scroll-stop en < 2s ? |
| Clarté | /15 | Message compréhensible immédiatement ? |
| Tension | /15 | Enjeu clair, curiosité créée ? |
| Promesse claire | /15 | Le viewer sait ce qu'il va apprendre ? |
| Originalité | /15 | Angle différent des concurrents ? |
| Format optimisé | /20 | Durée, rythme, sous-titres OK ? |

**Seuil de publication : ≥ 75/100**
Si < 75 → retour au WRITER pour retravailler.

### Multiplicateur de portée

Chaque vidéo longue doit générer :

| Format | Quantité | Source |
|--------|----------|--------|
| Shorts YouTube | 4 minimum | Extraits clés |
| Reels Instagram | 2 | Adaptation format |
| Carrousel | 1 | Script découpé en slides |

**Résultat : x5 de portée sans x5 d'effort**

### Stratégie algorithmique
```
Shorts (Acquisition)
    ↓
Long (Autorité)
    ↓
Long (Fidélisation)
    ↓
Shorts (Recycle + Teaser)
    ↓
[Boucle]
```

### Diagnostic PERFORMANCE — Shorts

Si mauvais résultats, analyser :

| Symptôme | Cause probable | Action IMPROVER |
|----------|----------------|-----------------|
| Completion < 75% | Hook trop lent | Réduire à < 1.5s |
| Completion < 75% | Trop d'explication | Couper à 28s max |
| Rewatch < 1.2x | Manque tension | Plus de cuts, dramatiser intro |
| Commentaires < 1% | Pas assez polarisant | Opinion plus forte |
| Faible conversion abo | CTA trop visible | CTA implicite (teaser) |

### Erreurs à éviter

❌ **NE PAS FAIRE :**
- Shorts "informatifs neutres" (ennuyeux)
- Résumés de vidéos longues (pas de valeur propre)
- CTA agressifs ("ABONNE-TOI MAINTENANT")
- Trop de texte à l'écran
- Voix monotone

✅ **TOUJOURS PROVOQUER :**
- Surprise
- Peur
- Désaccord
- Curiosité
- Urgence

### Phases de croissance

| Phase | Durée | Focus | Objectif |
|-------|-------|-------|----------|
| **Phase 1** | 0–3 mois | Volume > Perfection | Tester, apprendre, itérer |
| **Phase 2** | 3–6 mois | Optimisation rétention | Affiner les formats gagnants |
| **Phase 3** | 6+ mois | Brand + différenciation | Devenir référence |

---

## 20. Pipeline Shorts (100% automatisé)

### Workflow spécifique
```
1. ANALYST → TrendBrief (sujet chaud)
         ↓
2. STRATEGIST → CreativeBrief (type de short + angle)
         ↓
3. WRITER → ShortScriptPack (script 25-40s)
         ↓
4. VISUAL → ThumbnailPack (cover TikTok/Reels)
         ↓
5. VOICE → VoicePack (voix IA ElevenLabs)
         ↓
6. VIDEO → ShortEditPack (montage + sous-titres)
         ↓
7. QA → QAReport + Score /100
         ↓
   Si score ≥ 75 → Publication
   Si score < 75 → Retour WRITER
         ↓
8. PERFORMANCE → Analyse J+1, J+3, J+7
         ↓
9. IMPROVER → Optimisations
```

### Artefact spécifique : ShortScriptPack
```json
{
  "project_id": "",
  "format": "short",
  "type": "urgence|mythe_detruit|donnee_choc|opinion_forte",
  "duration_target_seconds": 30,
  "hook": {
    "text": "",
    "duration_seconds": 2,
    "scroll_stop_element": ""
  },
  "tension": {
    "text": "",
    "duration_seconds": 5
  },
  "content": {
    "text": "",
    "duration_seconds": 18
  },
  "punch_final": {
    "text": "",
    "duration_seconds": 5
  },
  "cta_implicit": "",
  "on_screen_text": [],
  "emotion_target": "surprise|fear|disagreement|curiosity|urgency",
  "disclaimer": "NFA"
}
```

### Artefact spécifique : ShortEditPack
```json
{
  "project_id": "",
  "format": "9:16",
  "duration_seconds": 0,
  "timeline": [
    {
      "start": 0,
      "end": 2,
      "type": "hook",
      "visual": "",
      "text_overlay": "",
      "audio": "voiceover"
    }
  ],
  "subtitles": {
    "style": "word_by_word_animated",
    "font": "bold_sans",
    "color": "yellow_highlight",
    "position": "center"
  },
  "music": {
    "track": "",
    "volume": 0.3,
    "fade_in": true
  },
  "cuts_per_second": 0.5,
  "render_specs": {
    "resolution": "1080x1920",
    "fps": 30,
    "format": "mp4"
  }
}
```

### Cadence de production recommandée

| Phase        | Shorts/semaine | Objectif |
|--------------|----------------|----------|
| Lancement    | 14 (2/jour)    | Volume, test formats |
| Optimisation | 10             | Focus qualité |
| Croisière    | 7 (1/jour)     | Consistance |

---

## 21. Stratégie de croissance — 100K abonnés en 6 mois

### Objectif global

| Métrique | Cible | Délai |
|----------|-------|-------|
| Abonnés YouTube | 100 000 | 6 mois |
| Vues cumulées nécessaires | 6–10 millions | 6 mois |
| Abonnés/jour moyen | ~555 | Continu |

### Plateformes

| Plateforme | Rôle | Priorité |
|------------|------|----------|
| YouTube Long | Autorité + Fidélisation | 🟠 Haute |
| YouTube Shorts | Acquisition massive | 🔴 Critique |
| TikTok | Acquisition + Test | 🔴 Critique |
| Instagram | Amplification | 🟡 Moyenne |

### Règle d'inspiration

| Source | Proportion | Raison |
|--------|------------|--------|
| Contenu anglophone | 80% | Adaptation FR sans plagiat apparent |
| Contenu francophone | 20% | Veille concurrentielle locale |

**L'ANALYST doit prioriser les sources anglophones pour identifier les formats viraux.**

---

### Les maths réalistes

#### Conversions moyennes

| Format | Taux conversion vues → abonnés |
|--------|-------------------------------|
| YouTube Long | 1.5–3% |
| Shorts | 0.5–1% |

#### Volume nécessaire

- 2–4 vidéos long performantes / mois
- 40–60 Shorts / mois
- 1–2 vidéos "explosives" (300k–1M vues)

**Objectif : ~6-10 millions de vues cumulées sur 6 mois**

---

### Stratégie en 3 phases

#### 🟢 PHASE 1 — Volume & Test (Mois 1–2)

| Objectif | Métrique |
|----------|----------|
| Identifier le format explosif | Tester 10+ angles différents |
| Construire base initiale | 5 000–10 000 abonnés |
| Tester hooks | Analyser completion rate |

**Cadence :**
- 2 longs / semaine (8/mois)
- 10–15 shorts / semaine (50/mois)

**Focus :** Hook + Tension + Miniatures agressives

**Milestones :**
| Mois | Abonnés | Vues cumulées |
|------|---------|---------------|
| M1 | 3 000 | 200k |
| M2 | 10 000 | 600k |

#### 🟡 PHASE 2 — Domination narrative (Mois 3–4)

| Objectif | Métrique |
|----------|----------|
| Devenir référence sur 2–3 thèmes | Recognition dans commentaires |
| Créer format signature | 1 série récurrente identifiable |
| Accélérer croissance | +15 000 abonnés/mois |

**Thèmes à dominer (exemples) :**
- Bitcoin macro
- Altcoins narratifs
- Psychologie marché

**Positionnement cible :** "Celui qui explique clairement ce qui se passe"

**Ajouts :**
- 1 série hebdomadaire récurrente (ex: "Crypto Weekly")
- 1 format signature (ex: "En 60 secondes")

**Milestones :**
| Mois | Abonnés | Vues cumulées |
|------|---------|---------------|
| M3 | 25 000 | 1.5M |
| M4 | 45 000 | 3M |

#### 🔴 PHASE 3 — Accélération (Mois 5–6)

| Objectif | Métrique |
|----------|----------|
| Vidéo virale 500k+ | Au moins 1 |
| Shorts massifs | Volume + qualité |
| Atteindre 100k | Objectif final |

**Stratégie :**
- Sujet ultra tendance (timing critique)
- Angle fort (contrarian ou insider)
- Miniature polarisante
- Série de shorts autour du même sujet viral

**Milestones :**
| Mois | Abonnés | Vues cumulées |
|------|---------|---------------|
| M5 | 70 000 | 5M |
| M6 | 100 000 | 8M+ |

---

### Structure éditoriale

#### 4 types de contenu obligatoires

| Type | Exemple | Objectif | Fréquence |
|------|---------|----------|-----------|
| **Tendance chaude** | "Bitcoin proche ATH", "Crash brutal" | Reach | 40% |
| **Autorité** | "Explication halving", "Analyse on-chain" | Crédibilité | 25% |
| **Opinion forte** | "Pourquoi 90% vont perdre" | Engagement | 25% |
| **Evergreen** | "Comment lire un graphique" | Trafic long terme | 10% |

#### Multiplicateur de portée
```
8 longs/mois
    ↓
40 shorts (5 par long)
    ↓
16 reels (2 par long)
    ↓
8 carrousels (1 par long)
    ↓
= 72 contenus/mois avec 8 productions principales
```

---

### Psychologie du clic crypto

#### Leviers émotionnels obligatoires

Chaque contenu doit intégrer **au moins 1 levier** :

| Levier | Exemple de hook |
|--------|-----------------|
| 💰 Argent | "Comment j'aurais pu gagner 10x" |
| ⚠️ Risque | "L'erreur qui va te coûter cher" |
| 🚀 Opportunité | "La prochaine pépite avant tout le monde" |
| 🔥 Danger | "Ce signal annonce un crash" |
| 😤 Injustice | "Ce que les whales ne veulent pas que tu saches" |
| 👁️ Insider | "Ce que 99% des investisseurs ignorent" |

#### CTA stratégique

❌ **Ne pas dire :**
> "Abonne-toi"

✅ **Dire :**
> "Abonne-toi pour comprendre ce qui va se passer avant tout le monde."

**Positionnement = Insider, pas créateur lambda.**

---

### KPIs par phase

#### Phase 1 (Mois 1–2) — Baseline

| Format | KPI | Cible |
|--------|-----|-------|
| YouTube Long | CTR | ≥ 6% |
| YouTube Long | Rétention 30s | ≥ 70% |
| YouTube Long | AVD | ≥ 40% |
| Shorts | Completion | ≥ 75% |
| Shorts | Rewatch | ≥ 1.1x |

#### Phase 2–3 (Mois 3–6) — Optimisé

| Format | KPI | Cible |
|--------|-----|-------|
| YouTube Long | CTR | ≥ 8% |
| YouTube Long | Rétention 30s | ≥ 75% |
| YouTube Long | AVD | ≥ 45% |
| Shorts | Completion | ≥ 80% |
| Shorts | Rewatch | ≥ 1.2x |

---

### Risques et plan B

| Risque                   | Probabilité | Mitigation |
|--------------------------|-------------|------------|
| 0 vidéo virale en 3 mois | Moyenne | Augmenter volume shorts, tester plus d'angles |
| Burnout production       | Haute si manuel | Automatisation maximale (shorts IA) |
| Changement algo YouTube  | Faible | Diversifier TikTok + Instagram |
| Saturation niche crypto FR | Moyenne | Angles originaux, différenciation ton |

### Plan B si Phase 1 échoue

Si < 5 000 abonnés à M2 :
1. Analyser top 3 vidéos concurrents qui ont explosé
2. Copier format exact (adapté FR)
3. Multiplier volume shorts x2
4. Tester nouveau positionnement (ex: plus provocateur)

---

## 22. Système A/B Test automatisé

### Principe fondamental

> **Ne jamais publier avec une seule version.**

Chaque publication doit être testée pour maximiser les performances.

### Métriques prioritaires YouTube (confirmé)

| Métrique | Poids algo | Format |
|----------|------------|--------|
| CTR (Click-Through Rate) | 🔴 Critique | Long + Shorts |
| AVD (Average View Duration) | 🔴 Critique | Long |
| Completion Rate | 🔴 Critique | Shorts |
| Rétention 30s | 🔴 Critique | Long |
| Rewatch Rate | 🟠 Haute | Shorts |

---

### A/B Test Miniature (industrialisé)

#### Process automatisé
```
1. VISUAL génère 3 miniatures :
   ├── Version A (curiosité)
   ├── Version B (urgence)
   └── Version C (contrarian)
           ↓
2. ORCHESTRATOR sélectionne les 2 meilleures
           ↓
3. Publication avec YouTube Test & Compare (si dispo)
   OU rotation manuelle 24-48h
           ↓
4. PERFORMANCE compare après 24-48h :
   ├── CTR
   ├── AVD / Completion
   └── Traffic source
           ↓
5. Garde la meilleure, archive les données
```

#### Règle de décision

| Situation | Action |
|-----------|--------|
| Différence CTR > 1.2% | ✅ Winner clair, appliquer |
| Différence CTR < 1.2% | ⏳ Prolonger test 24h |
| Égalité après 72h | Garder celle avec meilleur AVD |

#### Durée de test par format

| Format | Durée test | Raison |
|--------|------------|--------|
| YouTube Long | 24–48h | Diffusion progressive |
| Shorts | 12–24h | Explosion rapide (2-6h peak) |
| TikTok | 6–12h | Algo très rapide |

#### Artefact : ABTestThumbnail
```json
{
  "project_id": "",
  "test_id": "",
  "started_at": "",
  "ended_at": "",
  "variants": [
    {
      "id": "A",
      "description": "Curiosité - Question ouverte",
      "file_ref": "",
      "psychology_trigger": "curiosity",
      "metrics": {
        "impressions": 0,
        "clicks": 0,
        "ctr": 0.0,
        "avg_view_duration": 0
      }
    },
    {
      "id": "B",
      "description": "Urgence - Alerte rouge",
      "file_ref": "",
      "psychology_trigger": "urgency",
      "metrics": {
        "impressions": 0,
        "clicks": 0,
        "ctr": 0.0,
        "avg_view_duration": 0
      }
    }
  ],
  "winner": "",
  "winner_reason": "",
  "ctr_difference_percent": 0.0,
  "learnings": ""
}
```

---

### A/B Test Hook (plus puissant que miniature)

> **Le hook détermine la rétention 30s, qui détermine si YouTube pousse la vidéo.**

#### Types de hooks à tester

| Type | Exemple | Quand l'utiliser |
|------|---------|------------------|
| **Dramatique** | "Ce qui va se passer va tout changer." | Actualité chaude |
| **Question** | "Tu sais pourquoi Bitcoin monte vraiment ?" | Éducatif |
| **Donnée choc** | "97% des traders perdent. Voici pourquoi." | Autorité |
| **Contrarian** | "Non, le bull run n'est PAS confirmé." | Opinion forte |
| **Urgence** | "Si tu détiens du BTC, regarde ça maintenant." | FOMO |

#### Méthode de test

**Option 1 : Test en non-répertorié (rigoureux)**
1. Publier 2 versions en non-répertorié
2. Partager à échantillon privé (Discord, email)
3. Comparer rétention 30s
4. Publier la meilleure en public

**Option 2 : Test en production (simple)**
1. Publier version 1
2. Après 48h, changer le hook (re-upload ou edit)
3. Observer impact rétention 30s sur 48h suivantes
4. Garder la meilleure

#### Score Hook automatisé (/100)

Intégré au scoring QA existant :

| Critère | Points | Évaluation |
|---------|--------|------------|
| Clarté | /20 | Message compréhensible en < 2s ? |
| Tension | /20 | Crée un enjeu, une curiosité ? |
| Promesse | /20 | Le viewer sait ce qu'il va apprendre ? |
| Spécificité | /20 | Détails concrets (chiffres, dates) ? |
| Impact émotionnel | /20 | Déclenche peur/curiosité/urgence ? |

**Seuil : Score ≥ 80/100 pour publication**
Si < 80 → WRITER retravaille.

#### Artefact : ABTestHook
```json
{
  "project_id": "",
  "test_id": "",
  "started_at": "",
  "variants": [
    {
      "id": "A",
      "type": "dramatic",
      "text": "",
      "score": 0,
      "score_breakdown": {
        "clarity": 0,
        "tension": 0,
        "promise": 0,
        "specificity": 0,
        "emotional_impact": 0
      },
      "retention_30s": 0.0
    },
    {
      "id": "B",
      "type": "question",
      "text": "",
      "score": 0,
      "score_breakdown": {},
      "retention_30s": 0.0
    }
  ],
  "winner": "",
  "retention_difference_percent": 0.0,
  "learnings": ""
}
```

---

### Pipeline A/B intégré
```
VISUAL → produit 3 miniatures (A, B, C)
    ↓
WRITER → produit 3 hooks (dramatique, question, donnée choc)
    ↓
QA → score chaque hook (/100)
    ↓
ORCHESTRATOR → sélectionne :
    ├── 2 miniatures pour A/B test
    └── 1 hook principal + 1 hook testable (si score ≥ 80)
    ↓
Publication avec A/B test actif
    ↓
PERFORMANCE → compare après 24-48h
    ↓
IMPROVER → archive learnings dans PlaybookMemory
```

---

## 23. Tableau de bord croissance

### Métriques à suivre quotidiennement

| Métrique | Source | Objectif |
|----------|--------|----------|
| Abonnés / jour | YouTube Analytics | > 555/jour (objectif 100k/6mois) |
| Vues totales / jour | YouTube Analytics | Tracking tendance |
| % abonnés par vidéo | Calculé | Identifier top performers |

### Métriques à suivre hebdomadairement

| Métrique | Source | Objectif |
|----------|--------|----------|
| Vues totales / semaine | YouTube Analytics | Progression vs semaine précédente |
| Top 5 vidéos acquisition | YouTube Analytics | Identifier formats gagnants |
| Top 5 shorts acquisition | YouTube Analytics | Identifier hooks gagnants |
| Coût tokens / semaine | CostReport | Optimiser budget |
| Coût / abonné acquis | Calculé | Efficacité système |

### Métriques à suivre mensuellement

| Métrique | Source | Objectif |
|----------|--------|----------|
| Abonnés total | YouTube | Milestone atteint ? |
| Vues cumulées | YouTube | Trajectoire 6-10M ? |
| Meilleur CTR | Analytics | Amélioration vs mois précédent |
| Meilleur AVD | Analytics | Amélioration vs mois précédent |
| Vidéos publiées | Interne | Volume respecté ? |
| Taux A/B win | ABTests | % de tests concluants |

### Artefact : GrowthDashboard
```json
{
  "date": "",
  "period": "daily|weekly|monthly",
  "subscribers": {
    "total": 0,
    "gained_period": 0,
    "daily_average": 0,
    "vs_target": 0.0
  },
  "views": {
    "total_period": 0,
    "cumulative": 0,
    "vs_target": 0.0
  },
  "top_performers": {
    "videos": [
      {"title": "", "views": 0, "subs_gained": 0, "conversion_rate": 0.0}
    ],
    "shorts": [
      {"title": "", "views": 0, "subs_gained": 0, "conversion_rate": 0.0}
    ]
  },
  "ab_tests": {
    "total_run": 0,
    "conclusive": 0,
    "avg_ctr_improvement": 0.0
  },
  "costs": {
    "total_usd": 0.0,
    "cost_per_subscriber": 0.0,
    "cost_per_1k_views": 0.0
  },
  "health_score": 0,
  "alerts": [],
  "recommendations": []
}
```

---

## 24. Accélérateurs de croissance

### Actions mensuelles recommandées

| Action | Fréquence | Impact | Effort |
|--------|-----------|--------|--------|
| **Collaboration** | 1/mois | 🔴 Élevé | 🟠 Moyen |
| **Vidéo réaction** | 1/mois | 🟠 Moyen | 🟢 Faible |
| **Sujet polémique contrôlé** | 1/mois | 🔴 Élevé | 🟠 Moyen |

#### Collaboration

- Identifier créateurs FR crypto avec 10k-100k abonnés
- Proposer échange de visibilité ou vidéo commune
- Cibler audiences complémentaires

#### Vidéo réaction

- Réagir à actualité chaude (news, tweet viral, vidéo concurrente)
- Publier dans les 24-48h de l'événement
- Format : analyse + opinion forte

#### Sujet polémique contrôlé

- Prendre position tranchée sur débat crypto
- Exemples : "Bitcoin vs Ethereum", "Les altcoins sont morts", "Les NFTs reviendront"
- Contrôlé = pas d'attaque personnelle, pas de désinformation

---

## 25. Erreurs mortelles à éviter

### ❌ Liste noire absolue

| Erreur | Conséquence | Alternative |
|--------|-------------|-------------|
| **Contenu neutre** | 0 engagement, 0 algo push | Toujours une opinion ou un angle |
| **Titres tièdes** | CTR catastrophique | Questions, chiffres, urgence |
| **Miniatures fades** | Invisible dans le feed | Contraste, visage, texte court |
| **Vidéos trop longues au début** | AVD faible, algo pénalise | 8-10 min max en Phase 1 |
| **Publier sans A/B test** | Opportunité perdue | Toujours 2+ variantes |
| **Ignorer les données** | Répéter les erreurs | PERFORMANCE analyse chaque vidéo |
| **Copier sans adapter** | Audience FR différente | Adapter ton + références |

### Checklist anti-erreur (avant publication)

- [ ] Le titre contient-il un hook émotionnel ?
- [ ] La miniature est-elle lisible en petit format (mobile) ?
- [ ] Le hook des 5 premières secondes est-il scoré ≥ 80 ?
- [ ] A-t-on préparé 2+ variantes miniature ?
- [ ] Le contenu a-t-il passé QA compliance ?
- [ ] La durée est-elle adaptée au format ?

---

## 26. Positionnement concurrentiel

### Le problème : saturation du YouTube crypto FR

Le marché est saturé par des contenus très similaires :
- News recyclées sans analyse
- Promesses implicites de gains rapides
- Analyse technique basique (RSI, supports, résistances)
- Miniatures sensationnalistes "🚀📈💰"
- Ton pseudo-gourou affirmatif

**Si tu produis le même contenu que tout le monde, tu seras noyé dans la masse.**

---

### Cartographie des créateurs crypto FR

| Type | Contenu | Forces | Faiblesses |
|------|---------|--------|------------|
| **Trader Technique** | Graphiques, RSI, supports/résistances | Récurrent, data | Peu différenciant |
| **Gourou Opportunité** | "Altcoin x100", hype, ton affirmatif | Attire clics | Crédibilité faible |
| **Vulgarisateur Débutant** | Bases, ton neutre, peu d'opinion | Aide débutants | Manque profondeur |
| **Commentateur News** | Réaction à l'actu, peu d'analyse | Rapide | Superficiel |

### L'espace libre à occuper

Il existe très peu de créateurs francophones qui proposent :
- Une analyse structurée du marché
- Une lecture des cycles crypto
- Une compréhension des narratifs émergents
- Une vision systémique du marché
- Une analyse du comportement des investisseurs

**👉 C'est précisément cet espace que CryptoRizon doit occuper.**

---

### Positionnement CryptoRizon

#### Le rôle

**L'analyste stratégique du marché crypto.**

Pas quelqu'un qui donne des signaux.
Quelqu'un qui explique :
- Ce qui se passe
- Pourquoi ça se passe
- Ce que cela implique

#### Taglines

Version complète :
> "On analyse et on explique ce qui se passe réellement sur le marché crypto."

Version courte :
> "Comprendre le marché crypto plutôt que suivre la hype."

#### Promesse

L'objectif n'est pas de vendre des promesses.
L'objectif est de donner de la **compréhension du marché**.

---

### Avantage stratégique interne

Le système exploite l'ensemble de l'écosystème crypto mondial :

| Source | Type | Usage |
|--------|------|-------|
| YouTube anglophone | Vidéos | Formats viraux, angles |
| Crypto Twitter | Threads, takes | Narratifs émergents |
| Newsletters | Analyses | Données, insights |
| Podcasts | Discussions | Opinions d'experts |
| Research reports | Études | Faits, statistiques |
| News crypto | Actualités | Events, annonces |

**Règle : 80% sources anglophones, 20% francophones**

Ces sources alimentent l'ANALYST qui identifie :
- Les signaux importants
- Les narratifs émergents
- Les tendances du marché
- Les news majeures

**Résultat : Le créateur apparaît comme un analyste, pas comme un agrégateur.**

---

### Identité différenciante

#### 1️⃣ Rationnel mais captivant

| ✅ À faire | ❌ À éviter |
|-----------|------------|
| Ton posé et analytique | Ton surexcité |
| Créer de la tension narrative | Monotone |
| Expliquer clairement | Jargon inutile |
| Structuré | Désorganisé |

#### 2️⃣ Anti-promesse

| ✅ À dire | ❌ À ne jamais dire |
|----------|---------------------|
| "Personne ne peut prédire le marché." | "Bitcoin va x10 c'est sûr." |
| "On peut analyser les probabilités." | "Opportunité garantie." |
| "Voici les scénarios possibles." | "Voici ce qui va arriver." |

**Ce positionnement renforce la crédibilité long terme.**

#### 3️⃣ Analyse marché + psychologie

Le marché crypto est profondément influencé par les émotions.

Sujets à traiter :
- Euphorie et FOMO
- Capitulation et panique
- Narratifs dominants
- Manipulation de marché
- Cycles de liquidité

---

## 27. Piliers de contenu

### Les 4 piliers obligatoires

Chaque mois, le contenu doit couvrir ces 4 piliers :

#### 🟢 Pilier 1 — Lecture du cycle (25%)

| Exemples |
|----------|
| Où en est réellement le cycle crypto |
| Les différentes phases d'un bull run |
| Ce que l'histoire du marché nous apprend |
| Comparaison avec les cycles précédents |

**Objectif : Autorité + Vision long terme**

#### 🟡 Pilier 2 — Narratifs émergents (25%)

| Exemples |
|----------|
| Pourquoi ce narratif prend maintenant |
| Le nouveau secteur qui attire les capitaux |
| Les tendances qui émergent dans l'écosystème |
| DeFi, Layer 2, RWA, AI crypto... |

**Objectif : Positionnement "en avance"**

#### 🔵 Pilier 3 — Actualité crypto (30%)

| Exemples |
|----------|
| Annonces importantes |
| Régulation (AMF, SEC, MiCA) |
| Décisions institutionnelles |
| Hacks ou événements majeurs |

**Objectif : Reach + Réactivité**

⚠️ Les news sont **analysées et contextualisées**, pas juste rapportées.

#### 🔴 Pilier 4 — Psychologie du marché (20%)

| Exemples |
|----------|
| Pourquoi la majorité des investisseurs perdent |
| Les pièges psychologiques du bull run |
| Les erreurs les plus fréquentes |
| Comment les whales manipulent le sentiment |

**Objectif : Engagement + Différenciation**

---

### Répartition mensuelle recommandée

| Pilier | % | Vidéos/mois (sur 8) | Shorts/mois (sur 40) |
|--------|---|---------------------|----------------------|
| Lecture cycle | 25% | 2 | 10 |
| Narratifs émergents | 25% | 2 | 10 |
| Actualité crypto | 30% | 3 | 12 |
| Psychologie marché | 20% | 1 | 8 |

---

## 28. Format signature

### "Point Marché Crypto" — Format hebdomadaire

#### Structure

| Section | Durée | Contenu |
|---------|-------|---------|
| Hook | 0-15s | Signal fort de la semaine |
| Situation actuelle | 2 min | Où en est le marché |
| Signaux importants | 3 min | Données, indicateurs, events |
| Risques | 2 min | Ce qui pourrait mal tourner |
| Scénarios possibles | 2 min | Bull case / Bear case |
| Conclusion + CTA | 1 min | Résumé + teaser semaine prochaine |

**Durée totale : 10-12 minutes**

#### Pourquoi ce format fonctionne

| Avantage | Impact |
|----------|--------|
| Rendez-vous récurrent | Fidélisation |
| Structure prévisible | Production industrialisable |
| Couvre plusieurs piliers | Contenu équilibré |
| Génère 4-6 shorts | Multiplicateur de portée |

#### Jour de publication recommandé

**Dimanche soir ou Lundi matin** — Avant la semaine de trading

---

## 29. Formule de contenu

### Les 4 questions obligatoires

Chaque vidéo doit répondre à ces 4 questions :

| Question | But | Exemple |
|----------|-----|---------|
| **1. Ce qui se passe** | Contexte factuel | "Bitcoin a dépassé les 80k$" |
| **2. Pourquoi ça se passe** | Analyse causale | "Afflux ETF + halving + macro" |
| **3. Ce que cela implique** | Conséquences | "Probablement début de phase euphorique" |
| **4. Ce que cela ne signifie PAS** | Anti-hype | "Ça ne veut pas dire 100k garanti demain" |

**La question 4 est cruciale** — Elle différencie l'analyste du gourou.

### Intégration dans le ScriptPack
```json
{
  "content_formula": {
    "what_is_happening": "",
    "why_it_is_happening": "",
    "what_it_implies": "",
    "what_it_does_NOT_mean": ""
  }
}
```

Le WRITER doit obligatoirement remplir ces 4 champs.

---

## 30. Identité visuelle

### Style miniature CryptoRizon

#### ❌ À éviter absolument

| Élément | Pourquoi |
|---------|----------|
| 🚀🚀🚀 | Cliché crypto, non crédible |
| Graphiques rouge/vert agressifs | Sensationnalisme |
| Promesses "x100" | Gourou vibes |
| Trop de texte | Illisible mobile |
| Visage surjoué | Fake excitement |

#### ✅ Style recommandé

| Élément | Application |
|---------|-------------|
| **Minimaliste** | 1 message, 1 visuel principal |
| **Contraste fort** | Lisible en petit format |
| **Texte court** | 1-4 mots maximum |
| **Couleurs sobres** | Bleu, noir, blanc, or (pas vert/rouge vif) |
| **Visage neutre/pensif** | Analyste, pas influenceur |

#### Exemples de textes miniature

| ✅ Bon | ❌ Mauvais |
|--------|-----------|
| "Le marché envoie ce signal." | "BITCOIN VA EXPLOSER 🚀🚀🚀" |
| "Ce que personne ne voit." | "OPPORTUNITÉ x100 À NE PAS RATER" |
| "Signal d'alerte." | "CRASH IMMINENT ??? 😱" |

### Guidelines VISUAL
```json
{
  "style_guidelines": {
    "colors": ["#1a1a2e", "#16213e", "#0f3460", "#e94560", "#f1f1f1"],
    "fonts": ["Inter", "Montserrat", "bold sans-serif"],
    "text_max_words": 4,
    "emoji_allowed": false,
    "face_expression": "neutral|thoughtful|serious",
    "composition": "minimal|clean|high_contrast"
  }
}
```

---

## 31. Viralité avec ton analytique

### C'est possible si...

Même avec un ton analytique, la viralité reste atteignable grâce à des **angles forts**.

#### Formules de titres viraux (style CryptoRizon)

| Type | Exemple |
|------|---------|
| **Signal inquiétant** | "Le marché crypto envoie un signal inquiétant." |
| **Prédiction prudente** | "Pourquoi les altcoins pourraient connaître une phase difficile." |
| **Contrarian** | "Ce que tout le monde ignore sur ce bull run." |
| **Insider** | "Ce signal a précédé chaque crash majeur." |
| **Question provocante** | "Et si ce bull run était déjà terminé ?" |

#### Règle d'or

> **Curiosité sans promesse irréaliste**

| ✅ | ❌ |
|----|-----|
| Crée de la curiosité | Promet un résultat |
| Pose une question | Affirme une certitude |
| Suggère un risque | Garantit un gain |

---

## 32. BrandMemory — Règles absolues

### Fichier : `workspace/memory/brand.json`
```json
{
  "brand_name": "CryptoRizon",
  "tagline": "Comprendre le marché crypto plutôt que suivre la hype.",
  "positioning": "Analyste stratégique du marché crypto",
  "role": "Expliquer ce qui se passe, pourquoi, et ce que cela implique",
  
  "tone": {
    "primary": "Expert pédagogique direct",
    "characteristics": ["rationnel", "captivant", "structuré", "accessible"],
    "anti_characteristics": ["gourou", "surexcité", "prometteur", "sensationnaliste"]
  },
  
  "content_formula": {
    "always_answer": [
      "Ce qui se passe",
      "Pourquoi ça se passe",
      "Ce que cela implique",
      "Ce que cela ne signifie PAS"
    ]
  },
  
  "pillars": {
    "cycle_reading": 0.25,
    "emerging_narratives": 0.25,
    "crypto_news": 0.30,
    "market_psychology": 0.20
  },
  
  "visual_style": {
    "minimalist": true,
    "high_contrast": true,
    "emoji_forbidden": true,
    "max_text_words": 4
  },
  
  "forbidden": [
    "Promesses de rendement",
    "Certitudes sur le prix futur",
    "Emoji 🚀📈💰",
    "Ton gourou affirmatif",
    "Conseils financiers directs",
    "x10, x100, opportunité garantie"
  ],
  
  "mandatory": [
    "Disclaimer NFA",
    "Mention incertitude si projection",
    "Analyse causale (pas juste description)",
    "Question 4 : ce que cela ne signifie PAS"
  ],
  
  "inspiration_sources": {
    "english": 0.80,
    "french": 0.20
  }
}
```

---

Fin du document principal.

---

## 📝 Changelog

| Version | Date | Changements |
|---------|------|-------------|
| 1.0 | 2026-03-03 | Création initiale |

