import os

import ccxt
from dotenv import load_dotenv

load_dotenv()


class MarketData:
    def __init__(self, exchange_id: str = "binance"):
        exchange_class = getattr(ccxt, exchange_id)
        api_key    = os.getenv("BINANCE_API_KEY")
        api_secret = os.getenv("BINANCE_API_SECRET")
        self.exchange = exchange_class({
            "apiKey": api_key,
            "secret": api_secret,
        } if api_key and api_secret else {})

    def get_price(self, symbol: str) -> float:
        ticker = self.exchange.fetch_ticker(symbol)
        return float(ticker["last"])

    def get_ohlcv(self, symbol: str, timeframe: str = "1h", limit: int = 100) -> list:
        return self.exchange.fetch_ohlcv(symbol, timeframe, limit=limit)

    def get_spot_balance(self) -> dict[str, float]:
        """Retorna saldos libres de USDT y ETH en SPOT."""
        balance = self.exchange.fetch_balance()
        return {
            "USDT": float(balance["free"].get("USDT", 0.0)),
            "ETH":  float(balance["free"].get("ETH",  0.0)),
        }

    def place_order(self, symbol: str, side: str, amount_usdt: float = 0, amount_eth: float = 0) -> dict:
        """Ejecuta orden real en Binance.
        Compra: pasar amount_usdt (gasta exactamente ese USDT).
        Venta:  pasar amount_eth  (vende exactamente ese ETH).
        """
        if side == "buy":
            order = self.exchange.create_order(
                symbol, "market", "buy", 0, None,
                {"quoteOrderQty": amount_usdt}
            )
        else:
            order = self.exchange.create_order(
                symbol, "market", "sell", amount_eth
            )
        return order
