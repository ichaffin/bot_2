import json
import logging
import sys
import time
from pathlib import Path

import config
from market import MarketData
from notify import send_cycle_summary
from portfolio import Portfolio
from strategy import MultiRegimeStrategy

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("bot_real.log"),
    ],
)
logger = logging.getLogger(__name__)

STATE_FILE = Path("state.json")


def detect_reboot(last_cycle_ts: float) -> bool:
    """Retorna True si la Mac se reinició desde el último ciclo."""
    try:
        import re, subprocess
        out = subprocess.check_output(["sysctl", "-n", "kern.boottime"]).decode()
        boot_ts = int(re.search(r"sec = (\d+)", out).group(1))
        return boot_ts > last_cycle_ts
    except Exception:
        return False


def bootstrap_from_exchange(market: MarketData) -> Portfolio:
    """Lee saldos SPOT reales y crea el portfolio inicial. Correr una sola vez con --live-init."""
    balance = market.get_spot_balance()
    price   = market.get_price(config.SYMBOL)
    usdt    = balance["USDT"]
    eth     = balance["ETH"]
    total   = usdt + eth * price

    if total < 1.0:
        logger.error("Saldo SPOT insuficiente — verificá que tenés USDT o ETH en Spot (no en Earn/Staking)")
        sys.exit(1)

    # Actualizar capital de referencia con el saldo real
    config.INITIAL_USDT = total

    eth_value_pct = (eth * price) / total if total > 0 else 0.0

    if eth_value_pct > 0.01:  # ETH representa más del 1% del total → pre-existente
        portfolio = Portfolio(
            usdt=usdt,
            eth=eth,
            total_usdt_invested=0.0,  # ETH pre-existente, no comprado por el bot
            total_eth_bought=0.0,
            price_peak=price,
        )
        modo = f"50/50 — ${usdt:.2f} USDT + {eth:.6f} ETH pre-existente @ ${price:.2f} (${eth*price:.2f})"
    else:
        portfolio = Portfolio(usdt=usdt)
        modo = f"100% USDT — ${usdt:.2f} USDT"

    logger.info(f"Bootstrap desde Binance SPOT: {modo}")
    logger.info(f"Capital total de referencia : ${total:.2f} USDT")
    return portfolio


def load_portfolio() -> Portfolio:
    if STATE_FILE.exists():
        data = json.loads(STATE_FILE.read_text())
        if "initial_capital" in data:
            config.INITIAL_USDT = data["initial_capital"]
        p = Portfolio(
            usdt=data["usdt"],
            eth=data["eth"],
            total_usdt_invested=data.get("total_usdt_invested", 0.0),
            total_eth_bought=data.get("total_eth_bought", 0.0),
            realized_pnl=data.get("realized_pnl", 0.0),
            price_peak=data.get("price_peak", 0.0),
        )
        logger.info(f"Estado restaurado — USDT: ${p.usdt:.2f} | ETH: {p.eth:.6f} | Capital ref: ${config.INITIAL_USDT:.2f}")
        return p
    return Portfolio(usdt=config.INITIAL_USDT)


def save_portfolio(portfolio: Portfolio):
    STATE_FILE.write_text(json.dumps({
        "usdt": portfolio.usdt,
        "eth": portfolio.eth,
        "total_usdt_invested": portfolio.total_usdt_invested,
        "total_eth_bought": portfolio.total_eth_bought,
        "realized_pnl": portfolio.realized_pnl,
        "price_peak": portfolio.price_peak,
        "initial_capital": config.INITIAL_USDT,
        "last_cycle_ts": time.time(),
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
        price = market.get_price(config.SYMBOL)
        send_cycle_summary(portfolio, price, config.INITIAL_USDT)
    except Exception as e:
        logger.error(f"Error en ciclo: {e}")
        sys.exit(1)


def run_loop():
    """Bucle continuo. Útil para correrlo a mano."""
    modo = "LIVE TRADING" if config.LIVE_TRADING else "paper trading"
    logger.info(f"=== Bot DCA+RSI iniciando ({modo}) ===")
    logger.info(
        f"Par: {config.SYMBOL} | Capital: ${config.INITIAL_USDT} USDT | "
        f"Intervalo: {config.DCA_INTERVAL_MINUTES} min"
    )
    logger.info("Presioná Ctrl+C para detener")

    market = MarketData(config.EXCHANGE_ID)
    portfolio = load_portfolio()
    strategy = MultiRegimeStrategy(market, portfolio)

    # Respetar el intervalo si ya hubo un ciclo reciente (evita doble ejecución al reiniciar)
    interval_secs = config.DCA_INTERVAL_MINUTES * 60
    last_ts = json.loads(STATE_FILE.read_text()).get("last_cycle_ts", 0) if STATE_FILE.exists() else 0

    if last_ts > 0 and detect_reboot(last_ts):
        logger.warning("*** REINICIO DE MAC DETECTADO — retomando desde state.json ***")

    elapsed = time.time() - last_ts
    if elapsed < interval_secs:
        wait = int(interval_secs - elapsed)
        logger.info(f"Último ciclo hace {int(elapsed/60)}min — esperando {int(wait/60)}min {wait%60}s antes del próximo")
        time.sleep(wait)

    try:
        while True:
            try:
                strategy.run_once()
                save_portfolio(portfolio)
                price = market.get_price(config.SYMBOL)
                send_cycle_summary(portfolio, price, config.INITIAL_USDT)
            except Exception as e:
                logger.error(f"Error en ciclo: {e}")

            logger.info(f"Próximo ciclo en {config.DCA_INTERVAL_MINUTES} minutos...")
            time.sleep(interval_secs)

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
    if "--live-init" in sys.argv:
        logger.info("=== Bootstrap desde Binance SPOT ===")
        market    = MarketData(config.EXCHANGE_ID)
        portfolio = bootstrap_from_exchange(market)
        save_portfolio(portfolio)
        logger.info("state.json creado — corré el bot normalmente ahora.")
    elif "--once" in sys.argv:
        run_once()
    else:
        run_loop()
