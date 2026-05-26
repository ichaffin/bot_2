import ccxt


class MarketData:
    def __init__(self, exchange_id: str = "binance"):
        exchange_class = getattr(ccxt, exchange_id)
        self.exchange = exchange_class()

    def get_price(self, symbol: str) -> float:
        ticker = self.exchange.fetch_ticker(symbol)
        return float(ticker["last"])

    def get_ohlcv(self, symbol: str, timeframe: str = "1h", limit: int = 100) -> list:
        return self.exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
