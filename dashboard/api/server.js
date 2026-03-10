import express from "express";
import cors from "cors";
import dotenv from "dotenv";
import { readFileSync } from "fs";
import { join, dirname } from "path";
import { fileURLToPath } from "url";

dotenv.config();

const __dirname = dirname(fileURLToPath(import.meta.url));
const app = express();
const PORT = process.env.PORT || 3001;

// ── CORS ────────────────────────────────────────────────────────────────────
const ALLOWED_ORIGINS = [
  process.env.ALLOWED_ORIGIN,
  "http://localhost:5173",
  "http://localhost:4173",
].filter(Boolean);

app.use(cors({
  origin: (origin, cb) => {
    if (!origin || ALLOWED_ORIGINS.includes(origin)) return cb(null, true);
    cb(new Error("Origin non autorisée"));
  },
  methods: ["GET"],
  allowedHeaders: ["x-api-key", "Content-Type"],
}));

app.use(express.json());

// ── AUTH middleware ──────────────────────────────────────────────────────────
function auth(req, res, next) {
  const key = req.headers["x-api-key"];
  if (!key || key !== process.env.DASHBOARD_API_KEY) {
    return res.status(401).json({ error: "Non autorisé" });
  }
  next();
}

// ── Routes ───────────────────────────────────────────────────────────────────
import healthRouter   from "./routes/health.js";
import costsRouter    from "./routes/costs.js";
import tradingRouter  from "./routes/trading.js";
import contentRouter  from "./routes/content.js";
import storageRouter  from "./routes/storage.js";
import docsRouter     from "./routes/docs.js";

app.use("/api/health",   auth, healthRouter);
app.use("/api/costs",    auth, costsRouter);
app.use("/api/trading",  auth, tradingRouter);
app.use("/api/content",  auth, contentRouter);
app.use("/api/storage",  auth, storageRouter);
app.use("/api/docs",     auth, docsRouter);

// ── Sanity check ─────────────────────────────────────────────────────────────
app.get("/ping", (req, res) => res.json({ ok: true, ts: Date.now() }));

// ── Démarrage ────────────────────────────────────────────────────────────────
app.listen(PORT, "127.0.0.1", () => {
  console.log(`[dashboard-api] ✅ Serveur démarré sur port ${PORT}`);
});
