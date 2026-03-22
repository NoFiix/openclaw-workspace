import fs   from "fs";
import path from "path";

/**
 * Bus JSONL file-based.
 * Chaque topic = un fichier .jsonl dans state/trading/bus/
 * Cursor = numéro de ligne (offset).
 */
export class FileBus {
  constructor(stateDir) {
    this.busDir = path.join(stateDir, "bus");
    fs.mkdirSync(this.busDir, { recursive: true });
  }

  _topicPath(topic) {
    return path.join(this.busDir, topic.replaceAll(".", "_") + ".jsonl");
  }

  publish(topic, event) {
    fs.appendFileSync(
      this._topicPath(topic),
      JSON.stringify(event) + "\n",
      "utf-8"
    );
  }

  readSince(topic, cursor = 0, limit = 500) {
    const p = this._topicPath(topic);
    if (!fs.existsSync(p)) return { events: [], nextCursor: cursor };
    const lines = fs.readFileSync(p, "utf-8").split("\n").filter(Boolean);
    const slice = lines.slice(cursor, cursor + limit);
    const events = slice
      .map(l => { try { return JSON.parse(l); } catch { return null; } })
      .filter(Boolean);
    return { events, nextCursor: cursor + events.length };
  }

  /** Nombre total de lignes (pour métriques) */
  count(topic) {
    const p = this._topicPath(topic);
    if (!fs.existsSync(p)) return 0;
    return fs.readFileSync(p, "utf-8").split("\n").filter(Boolean).length;
  }
}
