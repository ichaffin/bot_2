import logging
from dataclasses import dataclass, field
from datetime import datetime

logger = logging.getLogger(__name__)


@dataclass
class Trade:
    timestamp: datetime
    side: str
    price: float
    amount_eth: float
    amount_usdt: float


@dataclass
class Portfolio:
    usdt: float
    eth: float = 0.0
    trades: list = field(default_factory=list)
    total_usdt_invested: float = 0.0  # acumulado entre sesiones para avg price
    total_eth_bought: float = 0.0

    def buy(self, price: float, usdt_amount: float) -> Trade | None:
        if usdt_amount > self.usdt:
            logger.warning(f"USDT insuficiente. Disponible: ${self.usdt:.2f}, requerido: ${usdt_amount:.2f}")
            return None
        eth_amount = usdt_amount / price
        self.usdt -= usdt_amount
        self.eth += eth_amount
        self.total_usdt_invested += usdt_amount
        self.total_eth_bought += eth_amount
        trade = Trade(
            timestamp=datetime.now(),
            side="buy",
            price=price,
            amount_eth=eth_amount,
            amount_usdt=usdt_amount,
        )
        self.trades.append(trade)
        logger.info(f"COMPRA  {eth_amount:.6f} ETH @ ${price:.2f} | gastado: ${usdt_amount:.2f} USDT")
        return trade

    def sell(self, price: float, eth_amount: float) -> Trade | None:
        if eth_amount > self.eth:
            logger.warning(f"ETH insuficiente. Disponible: {self.eth:.6f}, requerido: {eth_amount:.6f}")
            return None
        usdt_received = eth_amount * price
        self.eth -= eth_amount
        self.usdt += usdt_received
        trade = Trade(
            timestamp=datetime.now(),
            side="sell",
            price=price,
            amount_eth=eth_amount,
            amount_usdt=usdt_received,
        )
        self.trades.append(trade)
        logger.info(f"VENTA   {eth_amount:.6f} ETH @ ${price:.2f} | recibido: ${usdt_received:.2f} USDT")
        return trade

    def total_value(self, current_price: float) -> float:
        return self.usdt + self.eth * current_price

    def pnl(self, current_price: float, initial_capital: float) -> float:
        return self.total_value(current_price) - initial_capital

    def avg_buy_price(self) -> float | None:
        if self.total_eth_bought == 0:
            return None
        return self.total_usdt_invested / self.total_eth_bought

    def status(self, current_price: float, initial_capital: float) -> str:
        total = self.total_value(current_price)
        pnl = self.pnl(current_price, initial_capital)
        pnl_pct = pnl / initial_capital * 100
        avg = self.avg_buy_price()
        avg_str = f"${avg:.2f}" if avg else "N/A"
        return (
            f"[Portfolio] USDT: ${self.usdt:.2f} | ETH: {self.eth:.6f} | "
            f"Precio: ${current_price:.2f} | Avg compra: {avg_str} | "
            f"Total: ${total:.2f} | P&L: ${pnl:+.2f} ({pnl_pct:+.1f}%)"
        )
