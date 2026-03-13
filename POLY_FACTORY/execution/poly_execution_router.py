"""
POLY_EXECUTION_ROUTER — Routes validated trade signals to the correct execution engine.

Reads strategy status from POLY_STRATEGY_REGISTRY and publishes the signal
to either execute:paper or execute:live. Contains NO execution logic.
"""

from core.poly_event_bus import PolyEventBus
from core.poly_audit_log import PolyAuditLog
from core.poly_strategy_registry import PolyStrategyRegistry


CONSUMER_ID = "POLY_EXECUTION_ROUTER"

# Registry status → target topic
STATUS_ROUTE = {
    "paper_testing": "execute:paper",
    "live":          "execute:live",
}


class PolyExecutionRouter:
    """Routes trade:validated signals to execute:paper or execute:live."""

    def __init__(self, base_path="state"):
        self.bus = PolyEventBus(base_path=base_path)
        self.audit = PolyAuditLog(base_path=base_path)
        self.registry = PolyStrategyRegistry(base_path=base_path)

    def route(self, payload: dict) -> dict | None:
        """Route a single validated signal to the appropriate execution engine.

        Args:
            payload: The trade:validated event payload.

        Returns:
            dict with topic, strategy, and payload on success; None on error.
        """
        strategy = payload.get("strategy")

        # 1. Look up the strategy in the registry
        entry = self.registry.get(strategy)
        if entry is None:
            self.audit.log_event(
                topic="router:error",
                producer=CONSUMER_ID,
                payload={"error": "strategy_not_in_registry", "strategy": strategy},
            )
            return None

        # 2. Resolve the target topic from the strategy's status
        status = entry["status"]
        topic = STATUS_ROUTE.get(status)
        if topic is None:
            self.audit.log_event(
                topic="router:error",
                producer=CONSUMER_ID,
                payload={"error": f"unroutable_status:{status}", "strategy": strategy, "status": status},
            )
            return None

        # 3. Build the execute payload
        execute_payload = {
            "execution_mode": "paper" if topic == "execute:paper" else "live",
            "strategy":        payload["strategy"],
            "account_id":      payload["account_id"],
            "market_id":       payload["market_id"],
            "platform":        payload.get("platform", "polymarket"),
            "direction":       payload["direction"],
            "size_eur":        payload["validated_size_eur"],
            "tranches":        payload.get("tranches", []),
            "slippage_estimated": payload.get("slippage_estimated"),
        }

        # 4. Publish to the execution topic
        self.bus.publish(topic, CONSUMER_ID, execute_payload)

        # 5. Audit the routing decision
        self.audit.log_event(
            topic="signal:routed",
            producer=CONSUMER_ID,
            payload={"topic": topic, "strategy": strategy},
        )

        return {"topic": topic, "strategy": strategy, "payload": execute_payload}

    def run_once(self) -> list:
        """Poll trade:validated events and route each one.

        Returns:
            List of routing result dicts (or {"topic": None, "strategy": ...} on error).
        """
        events = self.bus.poll(CONSUMER_ID, topics=["trade:validated"])
        actions = []

        for event in events:
            payload = event.get("payload", {})
            result = self.route(payload)
            if result is not None:
                actions.append(result)
            else:
                actions.append({"topic": None, "strategy": payload.get("strategy")})

        # Ack all events regardless of routing outcome
        for event in events:
            self.bus.ack(CONSUMER_ID, event["event_id"])

        return actions
