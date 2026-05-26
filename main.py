import json
import logging
import sys
import time
from pathlib import Path

import config
from market import MarketData
from portfolio import Portfolio
from strategy import MultiRegimeStrategy

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("bot.log"),
    ],
)
logger = logging.getLogger(__name__)

STATE_FILE = Path("state.json")


def load_portfolio() -> Portfolio:
    if STATE_FILE.exists():
        data = json.loads(STATE_FILE.read_text())
        p = Portfolio(
            usdt=data["usdt"],
            eth=data["eth"],
            total_usdt_invested=data.get("total_usdt_invested", 0.0),
            total_eth_bought=data.get("total_eth_bought", 0.0),
        )
        logger.info(f"Estado restaurado — USDT: ${p.usdt:.2f} | ETH: {p.eth:.6f}")
        return p
    return Portfolio(usdt=config.INITIAL_USDT)


def save_portfolio(portfolio: Portfolio):
    STATE_FILE.write_text(json.dumps({
        "usdt": portfolio.usdt,
        "eth": portfolio.eth,
        "total_usdt_invested": portfolio.total_usdt_invested,
        "total_eth_bought": portfolio.total_eth_bought,
    }))


def run_once():
    """Ejecuta un solo ciclo y sale. Ideal para Task Scheduler."""
    logger.info("=== Ciclo único DCA+RSI ===")
    market = MarketData(config.EXCHANGE_ID)
    portfolio = load_portfolio()
    strategy = MultiRegimeStrategy(market, portfolio)

    try:
        strategy.run_once()
        save_portfolio(portfolio)
    except Exception as e:
        logger.error(f"Error en ciclo: {e}")
        sys.exit(1)


def run_loop():
    """Bucle continuo. Útil para correrlo a mano."""
    logger.info("=== Bot DCA+RSI iniciando (paper trading) ===")
    logger.info(
        f"Par: {config.SYMBOL} | Capital: ${config.INITIAL_USDT} USDT | "
        f"DCA base: ${config.DCA_AMOUNT_USDT} cada {config.DCA_INTERVAL_MINUTES} min"
    )
    logger.info("Presioná Ctrl+C para detener")

    market = MarketData(config.EXCHANGE_ID)
    portfolio = load_portfolio()
    strategy = MultiRegimeStrategy(market, portfolio)

    try:
        while True:
            try:
                strategy.run_once()
                save_portfolio(portfolio)
            except Exception as e:
                logger.error(f"Error en ciclo: {e}")

            logger.info(f"Próximo ciclo en {config.DCA_INTERVAL_MINUTES} minutos...")
            time.sleep(config.DCA_INTERVAL_MINUTES * 60)

    except KeyboardInterrupt:
        logger.info("Deteniendo bot...")

    try:
        price = market.get_price(config.SYMBOL)
        logger.info("=== Estado final ===")
        logger.info(portfolio.status(price, config.INITIAL_USDT))
    except Exception:
        pass

    logger.info("Bot detenido.")


if __name__ == "__main__":
    if "--once" in sys.argv:
        run_once()
    else:
        run_loop()
