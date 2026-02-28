/**
 * pending.js - Gestion de l'état d'attente de sélection
 *
 * Workflow :
 * 1. scraper.js appelle saveWaitingSelection(items) après envoi Telegram
 * 2. L'agent détecte un message de type "1,2,4" et appelle getWaitingSelection()
 * 3. Les articles sélectionnés sont transmis au copywriter
 * 4. clearWaitingSelection() nettoie après traitement
 */

const fs   = require("fs");
const path = require("path");

const WORKSPACE  = "/home/node/.openclaw/workspace";
const STATE_FILE = path.join(WORKSPACE, "state", "waiting_selection.json");

/**
 * Sauvegarde les articles en attente de sélection
 */
function saveWaitingSelection(items) {
  const state = {
    savedAt:  new Date().toISOString(),
    expiresAt: new Date(Date.now() + 20 * 60 * 60 * 1000).toISOString(), // expire dans 20h
    count:    items.length,
    items,
  };
  fs.writeFileSync(STATE_FILE, JSON.stringify(state, null, 2));
  console.log(`[pending] ${items.length} articles sauvegardés → waiting_selection.json`);
}

/**
 * Récupère les articles en attente (null si expiré ou inexistant)
 */
function getWaitingSelection() {
  try {
    if (!fs.existsSync(STATE_FILE)) return null;
    const state = JSON.parse(fs.readFileSync(STATE_FILE, "utf8"));

    // Vérification expiration
    if (new Date() > new Date(state.expiresAt)) {
      console.log("[pending] Session expirée, nettoyage");
      clearWaitingSelection();
      return null;
    }

    return state;
  } catch (e) {
    console.error("[pending] Erreur lecture:", e.message);
    return null;
  }
}

/**
 * Parse les numéros sélectionnés par Daniel ("1,2,4" ou "1 2 4" ou "1, 2, 4")
 */
function parseSelection(text) {
  const nums = text.match(/\d+/g);
  if (!nums) return [];
  return [...new Set(nums.map(Number))].sort((a, b) => a - b);
}

/**
 * Retourne les articles correspondant aux numéros sélectionnés
 */
function getSelectedArticles(text) {
  const state = getWaitingSelection();
  if (!state) return null;

  const indices  = parseSelection(text);
  if (!indices.length) return null;

  const selected = indices
    .filter(n => n >= 1 && n <= state.items.length)
    .map(n => ({ index: n, ...state.items[n - 1] }));

  return { selected, total: state.items.length };
}

/**
 * Vérifie si un message ressemble à une sélection de numéros
 */
function isSelectionMessage(text) {
  if (!text) return false;
  const cleaned = text.trim();
  // Matche "1,2,4" ou "1 2 4" ou "1, 2, 4" ou "1" seul
  return /^[\d\s,]+$/.test(cleaned) && /\d/.test(cleaned);
}

/**
 * Supprime le fichier d'attente après traitement
 */
function clearWaitingSelection() {
  try {
    if (fs.existsSync(STATE_FILE)) {
      fs.unlinkSync(STATE_FILE);
      console.log("[pending] waiting_selection.json supprimé");
    }
  } catch (e) {
    console.error("[pending] Erreur suppression:", e.message);
  }
}

module.exports = {
  saveWaitingSelection,
  getWaitingSelection,
  getSelectedArticles,
  isSelectionMessage,
  clearWaitingSelection,
};
