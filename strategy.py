import logging

import config
from market import MarketData
from portfolio import Portfolio
from regime import MarketSnapshot, Regime, detect

logger = logging.getLogger(__name__)


class MultiRegimeStrategy:
    def __init__(self, market: MarketData, portfolio: Portfolio):
        self.market    = market
        self.portfolio = portfolio

    def run_once(self) -> dict:
        ohlcv = self.market.get_ohlcv(config.SYMBOL, config.TIMEFRAME, limit=config.REGIME_CANDLES)
        snap  = detect(
            ohlcv,
            rsi_period=config.RSI_PERIOD,
            ma_short=config.REGIME_MA_SHORT,
            ma_long=config.REGIME_MA_LONG,
            adx_period=config.REGIME_ADX_PERIOD,
            atr_period=config.REGIME_ATR_PERIOD,
            atr_mult=config.REGIME_ATR_MULTIPLIER,
            range_candles=config.LATERAL_RANGE_CANDLES,
        )

        logger.info(
            f"ETH/USDT: ${snap.price:.2f} | RSI: {snap.rsi:.1f} | ADX: {snap.adx:.1f} | "
            f"MA20/50: ${snap.ma20:.0f}/${snap.ma50:.0f} | ATR ratio: {snap.atr_ratio:.2f} | "
            f"Régimen: [{snap.regime.value}]"
        )

        handlers = {
            Regime.BULL:     self._run_bull,
            Regime.BEAR:     self._run_bear,
            Regime.LATERAL:  self._run_lateral,
            Regime.VOLATILE: self._run_volatile,
        }
        return handlers[snap.regime](snap)

    # ── Helpers ───────────────────────────────────────────────────────────

    def _available(self, reserve_pct: float) -> float:
        return max(0.0, self.portfolio.usdt - config.INITIAL_USDT * reserve_pct)

    def _buy(self, price: float, pct: float, available: float) -> bool:
        """Compra pct% del capital disponible sobre la reserva."""
        amount = available * pct
        if amount < 1.0:
            logger.info(f"Disponible insuficiente (${available:.2f}) para comprar")
            return False
        return self.portfolio.buy(price, amount) is not None

    def _sell(self, price: float, pct: float) -> bool:
        """Vende pct% del ETH vendible, respetando el piso mínimo de ETH."""
        floor_eth = (config.INITIAL_USDT * config.MIN_ETH_FLOOR_PCT) / price
        sellable = max(0.0, self.portfolio.eth - floor_eth)
        if sellable < 0.000001:
            logger.info(f"ETH en piso minimo (${config.INITIAL_USDT * config.MIN_ETH_FLOOR_PCT:.0f} equiv.) — no se vende")
            return False
        return self.portfolio.sell(price, sellable * pct) is not None

    def _status(self, snap: MarketSnapshot):
        logger.info(self.portfolio.status(snap.price, config.INITIAL_USDT))

    # ── ALCISTA: Trend Rider ──────────────────────────────────────────────

    def _run_bull(self, snap: MarketSnapshot) -> dict:
        available = self._available(config.BULL_RESERVE_PCT)

        # Tendencia rota: precio cruza bajo MA20 → vender
        if snap.price < snap.ma20 and self.portfolio.eth > 0:
            logger.info(
                f"[ALCISTA] Precio ${snap.price:.2f} rompe MA20 ${snap.ma20:.2f} — "
                f"tendencia rota, vendiendo {config.BULL_SELL_PCT*100:.0f}%"
            )
            self._sell(snap.price, config.BULL_SELL_PCT)
            self._status(snap)
            return {"regime": "bull", "action": "sell_ma_break"}

        # Comprar en pullback (RSI en zona 40-50)
        if config.BULL_RSI_BUY_MIN <= snap.rsi <= config.BULL_RSI_BUY_MAX:
            logger.info(
                f"[ALCISTA] RSI {snap.rsi:.1f} en pullback — comprando {config.BULL_BUY_PCT*100:.0f}% disponible (${available * config.BULL_BUY_PCT:.2f})"
            )
            self._buy(snap.price, config.BULL_BUY_PCT, available)
            self._status(snap)
            return {"regime": "bull", "action": "buy"}

        logger.info(f"[ALCISTA] RSI {snap.rsi:.1f} fuera de zona pullback — esperando")
        self._status(snap)
        return {"regime": "bull", "action": "wait"}

    # ── BAJISTA: Defensive DCA ────────────────────────────────────────────

    def _run_bear(self, snap: MarketSnapshot) -> dict:
        available = self._available(config.BEAR_RESERVE_PCT)

        # Vender en rebote (threshold bajo en bear)
        if snap.rsi > config.BEAR_RSI_OVERBOUGHT and self.portfolio.eth > 0:
            logger.info(
                f"[BAJISTA] RSI {snap.rsi:.1f} > {config.BEAR_RSI_OVERBOUGHT} — rebote, "
                f"vendiendo {config.BEAR_SELL_PCT*100:.0f}%"
            )
            self._sell(snap.price, config.BEAR_SELL_PCT)
            self._status(snap)
            return {"regime": "bear", "action": "sell"}

        if available <= 0:
            logger.info(f"[BAJISTA] Reserva activa (${config.INITIAL_USDT * config.BEAR_RESERVE_PCT:.0f}) — esperando")
            self._status(snap)
            return {"regime": "bear", "action": "skip_reserve"}

        if snap.rsi < config.BEAR_RSI_OVERSOLD:
            pct = min(config.BEAR_BUY_PCT * config.BEAR_BUY_BOOST, 1.0)
            logger.info(f"[BAJISTA] RSI {snap.rsi:.1f} < {config.BEAR_RSI_OVERSOLD} — sobrevendido, boost {pct*100:.0f}% disponible (${available * pct:.2f})")
        else:
            pct = config.BEAR_BUY_PCT
            logger.info(f"[BAJISTA] RSI {snap.rsi:.1f} neutro — {pct*100:.0f}% disponible (${available * pct:.2f})")

        self._buy(snap.price, pct, available)
        self._status(snap)
        return {"regime": "bear", "action": "buy"}

    # ── LATERAL: Range Trader ─────────────────────────────────────────────

    def _run_lateral(self, snap: MarketSnapshot) -> dict:
        available = self._available(config.LATERAL_RESERVE_PCT)

        logger.info(
            f"[LATERAL] Rango ${snap.range_low:.0f}–${snap.range_high:.0f} | "
            f"Precio en {snap.price_pct:.0f}% del rango"
        )

        # Techo del rango: vender
        if snap.price_pct >= config.LATERAL_PRICE_SELL_PCT and snap.rsi > config.LATERAL_RSI_SELL:
            logger.info(
                f"[LATERAL] Techo de rango (RSI {snap.rsi:.1f} > {config.LATERAL_RSI_SELL}) — "
                f"vendiendo {config.LATERAL_SELL_PCT*100:.0f}%"
            )
            self._sell(snap.price, config.LATERAL_SELL_PCT)
            self._status(snap)
            return {"regime": "lateral", "action": "sell"}

        # Piso del rango: comprar
        if snap.price_pct <= config.LATERAL_PRICE_BUY_PCT and snap.rsi < config.LATERAL_RSI_BUY:
            logger.info(
                f"[LATERAL] Piso de rango (RSI {snap.rsi:.1f} < {config.LATERAL_RSI_BUY}) — "
                f"comprando {config.LATERAL_BUY_PCT*100:.0f}% disponible (${available * config.LATERAL_BUY_PCT:.2f})"
            )
            self._buy(snap.price, config.LATERAL_BUY_PCT, available)
            self._status(snap)
            return {"regime": "lateral", "action": "buy"}

        logger.info("[LATERAL] Zona neutral — esperando piso o techo")
        self._status(snap)
        return {"regime": "lateral", "action": "wait"}

    # ── VOLÁTIL: Wait & Strike ────────────────────────────────────────────

    def _run_volatile(self, snap: MarketSnapshot) -> dict:
        available    = self._available(config.VOLATILE_RESERVE_PCT)
        eth_value    = self.portfolio.eth * snap.price
        max_eth_val  = config.INITIAL_USDT * config.VOLATILE_MAX_EXPOSURE

        # RSI extremo alto: vender
        if snap.rsi > config.VOLATILE_RSI_SELL and self.portfolio.eth > 0:
            logger.info(
                f"[VOLATIL] RSI {snap.rsi:.1f} > {config.VOLATILE_RSI_SELL} — "
                f"strike venta {config.VOLATILE_SELL_PCT*100:.0f}%"
            )
            self._sell(snap.price, config.VOLATILE_SELL_PCT)
            self._status(snap)
            return {"regime": "volatile", "action": "sell"}

        # RSI extremo bajo: comprar (respetando exposición máxima)
        if snap.rsi < config.VOLATILE_RSI_BUY:
            if eth_value >= max_eth_val:
                logger.info(
                    f"[VOLATIL] RSI {snap.rsi:.1f} bajo pero exposición máxima alcanzada "
                    f"(${eth_value:.0f} / ${max_eth_val:.0f})"
                )
            elif available > 0:
                pct = min(config.VOLATILE_BUY_PCT * config.VOLATILE_BUY_BOOST, 1.0)
                cap = min(available, max_eth_val - eth_value)
                amount = cap * pct
                logger.info(f"[VOLATIL] RSI {snap.rsi:.1f} < {config.VOLATILE_RSI_BUY} — strike compra {pct*100:.0f}% disponible (${amount:.2f})")
                self._buy(snap.price, pct, cap)
                self._status(snap)
                return {"regime": "volatile", "action": "buy"}

        logger.info(
            f"[VOLATIL] Esperando extremo — compra RSI < {config.VOLATILE_RSI_BUY}, "
            f"venta RSI > {config.VOLATILE_RSI_SELL} (actual: {snap.rsi:.1f})"
        )
        self._status(snap)
        return {"regime": "volatile", "action": "wait"}
