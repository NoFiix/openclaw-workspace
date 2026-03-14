"""
POLY_WALLET_TRACKER — Enriched wallet signal agent for POLY_FACTORY.

Consumes `feed:wallet_update` events and produces per-wallet signals:
  - ev_score: size-weighted expected value proxy (0-1)
  - specialization_score: directional concentration (0-1)
  - blacklisted: spam/dust wallet flag

When 3+ non-blacklisted wallets hold the same (market_id, direction),
publishes `signal:wallet_convergence` for POLY_CONVERGENCE_STRAT to consume.

State written to state/feeds/wallet_signals.json.
Pure deterministic logic, no external APIs.
"""

import json
import logging
import os
from datetime import datetime, timezone

from core.poly_data_store import PolyDataStore
from core.poly_event_bus import PolyEventBus

logger = logging.getLogger("POLY_WALLET_TRACKER")

CONSUMER_ID = "POLY_WALLET_TRACKER"
STATE_FILE = "feeds/wallet_signals.json"
BLACKLIST_RULES_FILE = "references/wallet_blacklist_rules.json"
CONVERGENCE_THRESHOLD = 3


class PolyWalletTracker:
    """Enriched wallet signal agent: EV scoring, specialization, convergence detection."""

    def __init__(self, base_path="state", rules_path=None):
        """Initialize the wallet tracker.

        Args:
            base_path: Base path for state files.
            rules_path: Path to wallet_blacklist_rules.json. Defaults to
                references/wallet_blacklist_rules.json relative to project root.
        """
        self.store = PolyDataStore(base_path=base_path)
        self.bus = PolyEventBus(base_path=base_path)

        if rules_path is None:
            project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            rules_path = os.path.join(project_root, BLACKLIST_RULES_FILE)

        with open(rules_path, "r", encoding="utf-8") as f:
            self.rules = json.load(f)

        # wallet → last signal dict
        self._wallet_cache = {}

        # (market_id, direction) → {wallet: per_position_ev_score}
        self._convergence_positions = {}

    # ------------------------------------------------------------------
    # Pure computation methods
    # ------------------------------------------------------------------

    def _compute_ev_score(self, positions):
        """Size-weighted EV score across all positions.

        EV proxy: (1 - avg_price) for each position, regardless of side.
        Cheap positions have high upside potential.

        Args:
            positions: List of position dicts with keys size, avg_price.

        Returns:
            Float in [0, 1]. 0.0 for empty positions.
        """
        if not positions:
            return 0.0
        total_size = sum(float(p.get("size", 0)) for p in positions)
        if total_size == 0:
            return 0.0
        weighted = sum(
            float(p.get("size", 0)) * (1.0 - float(p.get("avg_price", 0.5)))
            for p in positions
        )
        return max(0.0, min(1.0, weighted / total_size))

    def _compute_specialization(self, positions):
        """Directional concentration score.

        Args:
            positions: List of position dicts with keys side, size.

        Returns:
            Tuple (score: float, dominant_direction: str).
            score 1.0 = fully concentrated, 0.5 = balanced.
            dominant_direction is "YES", "NO", or "NONE" if empty.
        """
        if not positions:
            return (0.0, "NONE")

        yes_size = sum(
            float(p.get("size", 0)) for p in positions if p.get("side", "YES") == "YES"
        )
        no_size = sum(
            float(p.get("size", 0)) for p in positions if p.get("side", "YES") == "NO"
        )
        total = yes_size + no_size
        if total == 0:
            return (0.0, "NONE")

        score = max(yes_size, no_size) / total
        dominant = "YES" if yes_size >= no_size else "NO"
        return (score, dominant)

    def _is_blacklisted(self, positions, rules):
        """Check if a wallet should be blacklisted based on its positions.

        Rules applied in order:
        1. Too many positions (spam pattern)
        2. Average position size below minimum (dust positions)

        Args:
            positions: List of position dicts.
            rules: Dict with max_positions and min_avg_position_size.

        Returns:
            Tuple (blacklisted: bool, reason: str | None).
        """
        max_positions = rules.get("max_positions", 100)
        min_avg_size = rules.get("min_avg_position_size", 5.0)

        if len(positions) > max_positions:
            return (True, "too_many_positions")

        if positions:
            avg_size = sum(float(p.get("size", 0)) for p in positions) / len(positions)
            if avg_size < min_avg_size:
                return (True, "dust_positions")

        return (False, None)

    # ------------------------------------------------------------------
    # Pipeline methods
    # ------------------------------------------------------------------

    def process_wallet(self, wallet_payload):
        """Compute enriched wallet signal from a feed:wallet_update payload.

        Args:
            wallet_payload: Dict with wallet, positions, data_status.

        Returns:
            Signal dict with all computed fields.
        """
        wallet = wallet_payload.get("wallet", "")
        positions = wallet_payload.get("positions", [])

        ev_score = self._compute_ev_score(positions)
        spec_score, dominant = self._compute_specialization(positions)
        blacklisted, reason = self._is_blacklisted(positions, self.rules)

        total_size = sum(float(p.get("size", 0)) for p in positions)
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

        return {
            "wallet": wallet,
            "ev_score": round(ev_score, 6),
            "specialization_score": round(spec_score, 6),
            "dominant_direction": dominant,
            "position_count": len(positions),
            "total_size_usd": total_size,
            "blacklisted": blacklisted,
            "blacklist_reason": reason,
            "last_updated": now,
        }

    def _update_convergence_index(self, wallet, positions, blacklisted):
        """Update the convergence tracking index and return payloads to emit.

        Steps:
        1. Remove this wallet's stale entries from all tracked pairs.
        2. If not blacklisted: add new per-position EV entries.
        3. Return convergence payloads for all pairs where this wallet
           is present and count >= CONVERGENCE_THRESHOLD.

        Args:
            wallet: Wallet address string.
            positions: List of position dicts.
            blacklisted: Whether this wallet is blacklisted.

        Returns:
            List of convergence payload dicts (may be empty).
        """
        # Step 1: remove stale entries for this wallet
        empty_keys = []
        for key, wallets_dict in self._convergence_positions.items():
            if wallet in wallets_dict:
                del wallets_dict[wallet]
            if not wallets_dict:
                empty_keys.append(key)
        for key in empty_keys:
            del self._convergence_positions[key]

        # Step 2: add new entries if not blacklisted
        if not blacklisted:
            for pos in positions:
                market_id = pos.get("market_id", "")
                direction = pos.get("side", "YES")
                avg_price = float(pos.get("avg_price", 0.5))
                ev_i = 1.0 - avg_price
                key = (market_id, direction)
                if key not in self._convergence_positions:
                    self._convergence_positions[key] = {}
                # If wallet has multiple positions on same market/side, use latest
                self._convergence_positions[key][wallet] = ev_i

        # Step 3: collect convergence payloads for pairs this wallet now contributes to
        convergence_payloads = []
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

        for key, wallets_dict in self._convergence_positions.items():
            if wallet in wallets_dict and len(wallets_dict) >= CONVERGENCE_THRESHOLD:
                market_id, direction = key
                convergent_wallets = list(wallets_dict.keys())
                avg_ev = sum(wallets_dict.values()) / len(wallets_dict)
                convergence_payloads.append({
                    "market_id": market_id,
                    "direction": direction,
                    "convergent_wallets": convergent_wallets,
                    "wallet_count": len(convergent_wallets),
                    "avg_ev_score": round(avg_ev, 6),
                    "detection_timestamp": now,
                })

        return convergence_payloads

    def update(self, wallet, signal, positions):
        """Persist wallet signal and publish convergence events if triggered.

        Args:
            wallet: Wallet address string.
            signal: Signal dict from process_wallet().
            positions: Original positions list (needed for convergence index).
        """
        self._wallet_cache[wallet] = signal
        self.store.write_json(STATE_FILE, self._wallet_cache)

        convergence_payloads = self._update_convergence_index(
            wallet, positions, signal["blacklisted"]
        )

        for payload in convergence_payloads:
            logger.info(
                "CONVERGENCE detected %s/%s — %d wallets, avg_ev=%.3f",
                payload["market_id"],
                payload["direction"],
                payload["wallet_count"],
                payload["avg_ev_score"],
            )
            self.bus.publish(
                topic="signal:wallet_convergence",
                producer="POLY_WALLET_TRACKER",
                payload=payload,
                priority="normal",
            )

    def process_event(self, wallet_payload):
        """Full pipeline: compute signal, update state, publish convergence events.

        Args:
            wallet_payload: Dict from a feed:wallet_update bus event payload.

        Returns:
            Signal dict for this wallet.
        """
        signal = self.process_wallet(wallet_payload)
        positions = wallet_payload.get("positions", [])
        self.update(signal["wallet"], signal, positions)
        return signal

    def run_once(self):
        """Poll feed:wallet_update events and process each wallet.

        The orchestrator does not subscribe to feed:wallet_update, so bus acking
        here does not conflict with orchestrator's price cache.

        Returns:
            List of wallet signal dicts processed this cycle.
        """
        events = self.bus.poll(CONSUMER_ID, topics=["feed:wallet_update"])
        results = []
        for evt in events:
            event_id = evt.get("event_id")
            try:
                results.append(self.process_event(evt.get("payload", {})))
            except Exception:
                logger.exception("Failed to process wallet event %s", event_id)
            finally:
                self.bus.ack(CONSUMER_ID, event_id)
        return results
