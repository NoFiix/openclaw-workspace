import { Router } from "express";
import { readFileSync, existsSync } from "fs";

const router = Router();
const WORKSPACE = process.env.WORKSPACE_DIR;

const DOCS = {
  trading_architecture: {
    label: "Trading Architecture",
    path:  `${WORKSPACE}/docs/TRADING_ARCHITECTURE.md`,
  },
  content_architecture: {
    label: "Content Factory Architecture",
    path:  `${WORKSPACE}/docs/CONTENT_FACTORY_ARCHITECTURE.md`,
  },
  infra: {
    label: "Infrastructure & Environnement",
    path:  `${WORKSPACE}/CONTEXT_BUNDLE_INFRA.md`,
  },
  trading_bundle: {
    label: "Context Bundle Trading",
    path:  `${WORKSPACE}/CONTEXT_BUNDLE_TRADING.md`,
  },
  content_bundle: {
    label: "Context Bundle Content",
    path:  `${WORKSPACE}/CONTEXT_BUNDLE_CONTENT.md`,
  },
};

// Liste des docs disponibles
router.get("/", (req, res) => {
  const list = Object.entries(DOCS).map(([id, doc]) => ({
    id,
    label:     doc.label,
    available: existsSync(doc.path),
  }));
  res.json({ ts: Date.now(), docs: list });
});

// Contenu d'un doc spécifique
router.get("/:id", (req, res) => {
  const doc = DOCS[req.params.id];
  if (!doc) return res.status(404).json({ error: "Document introuvable" });
  if (!existsSync(doc.path)) return res.status(404).json({ error: "Fichier absent sur le VPS" });

  try {
    const content = readFileSync(doc.path, "utf8");
    res.json({
      ts:      Date.now(),
      id:      req.params.id,
      label:   doc.label,
      content,
    });
  } catch (e) {
    res.status(500).json({ error: e.message });
  }
});

export default router;
