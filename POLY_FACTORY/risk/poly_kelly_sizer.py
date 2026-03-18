"""
POLY_KELLY_SIZER — Position sizing via the Kelly Criterion.

Filter 3 in the 7-filter pre-trade risk chain.
Computes optimal position size for binary prediction market contracts.

Modes:
  half    (default) — Half-Kelly, reduces variance while retaining edge
  quarter           — Quarter-Kelly for high-variance signals
  full              — Full Kelly (not recommended for live trading)

Hard cap: 3% of available account capital, regardless of Kelly fraction.

Pure math module — no state, no I/O, no audit log.
"""


MAX_POSITION_PCT = 0.03  # 3% hard cap on any single position

KELLY_MODES = {
    "half":    0.5,
    "quarter": 0.25,
    "full":    1.0,
}


class PolyKellySizer:
    """Stateless Kelly-based position sizer for binary prediction markets."""

    def kelly_fraction(self, confidence: float, price: float) -> float:
        """Compute the full Kelly fraction for a binary prediction market bet.

        For a contract bought at `price` that pays $1 on resolution:
            f* = (confidence - price) / (1 - price)

        Args:
            confidence: Our estimated probability of winning (0 < confidence <= 1).
            price:      Market price of the contract (0 < price < 1).

        Returns:
            Kelly fraction in [0, 1], or 0.0 if there is no edge or inputs are invalid.
        """
        if not (0 < price < 1):
            return 0.0
        if not (0 < confidence <= 1):
            return 0.0
        if confidence <= price:
            return 0.0
        return (confidence - price) / (1.0 - price)

    def compute(self, confidence: float, price: float,
                current_capital: float, mode: str = "half") -> float:
        """Compute the position size in EUR for a given signal.

        Args:
            confidence:      Estimated win probability (0 < confidence <= 1).
            price:           Market price of the contract (0 < price < 1).
            current_capital: Available capital from the strategy account (EUR).
            mode:            Kelly mode — "half" (default), "quarter", or "full".

        Returns:
            Position size in EUR, capped at MAX_POSITION_PCT of current_capital.
            Returns 0.0 if there is no edge, inputs are invalid, or capital is zero.

        Raises:
            ValueError: If mode is not one of the known KELLY_MODES.
        """
        if mode not in KELLY_MODES:
            raise ValueError(
                f"Unknown Kelly mode '{mode}'. Must be one of {list(KELLY_MODES)}"
            )

        if current_capital <= 0:
            return 0.0

        fraction = self.kelly_fraction(confidence, price)
        if fraction <= 0:
            return 0.0

        multiplier = KELLY_MODES[mode]
        raw_size = fraction * multiplier * current_capital
        max_size = current_capital * MAX_POSITION_PCT

        return min(raw_size, max_size)
