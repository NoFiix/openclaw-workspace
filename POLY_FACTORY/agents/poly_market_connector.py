"""
POLY_MARKET_CONNECTOR — Abstract base class for platform connectors.

Defines the unified interface that all prediction market connectors
(Polymarket, Kalshi, sportsbooks) must implement.
"""

from abc import ABC, abstractmethod


class PolyMarketConnector(ABC):
    """Abstract base class for prediction market platform connectors."""

    @abstractmethod
    def get_markets(self, filter_active=True):
        """Fetch available markets from the platform.

        Args:
            filter_active: If True, only return currently active/tradeable markets.

        Returns:
            List of market dicts with at minimum:
            {market_id, question, active, end_date, platform}
        """

    @abstractmethod
    def get_orderbook(self, market_id):
        """Fetch current orderbook/prices for a market.

        Args:
            market_id: Platform-specific market identifier.

        Returns:
            Dict with price data:
            {market_id, platform, yes_price, no_price,
             yes_ask, yes_bid, no_ask, no_bid, volume_24h}
        """

    @abstractmethod
    def place_order(self, market_id, side, size, price):
        """Place an order on the platform.

        Only used by live execution engine. Paper engine never calls this.

        Args:
            market_id: Platform-specific market identifier.
            side: "YES" or "NO".
            size: Order size in platform units.
            price: Limit price (0-1 for prediction markets).

        Returns:
            Dict with order result: {order_id, status, filled_size, avg_price}
        """

    @abstractmethod
    def get_positions(self, wallet):
        """Fetch current positions for a wallet/account.

        Args:
            wallet: Wallet address or account identifier.

        Returns:
            List of position dicts:
            [{market_id, side, size, avg_price}]
        """

    @abstractmethod
    def get_settlement(self, market_id):
        """Fetch settlement/resolution status for a market.

        Args:
            market_id: Platform-specific market identifier.

        Returns:
            Dict with resolution data or None if not yet resolved:
            {market_id, resolved, outcome, resolved_at}
        """

    @abstractmethod
    def get_platform(self):
        """Return the platform identifier string.

        Returns:
            Platform name string (e.g. "polymarket", "kalshi").
        """

    @abstractmethod
    def is_connected(self):
        """Check if the connector is healthy and receiving data.

        Returns:
            True if last successful data update was within acceptable threshold.
        """
