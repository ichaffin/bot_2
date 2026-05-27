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

        self._update_peak(snap.price)

        if self._check_stop_loss(snap):
            return {"regime": snap.regime.value, "action": "stop_loss"}

        if self._check_trailing_stop(snap):
            return {"regime": snap.regime.value, "action": "trailing_stop"}

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
        if amount < config.MIN_ORDER_USDT:
            logger.info(f"Orden muy pequeña (${amount:.2f} < ${config.MIN_ORDER_USDT}) — skip")
            return False
        if config.LIVE_TRADING:
            try:
                order = self.market.place_order(config.SYMBOL, "buy", amount_usdt=amount)
                fill_price  = float(order.get("average") or price)
                fill_cost   = float(order.get("cost")    or amount)
                logger.info(f"Orden real ejecutada — ID: {order['id']} | fill: ${fill_price:.2f} | costo: ${fill_cost:.2f}")
                return self.portfolio.buy(fill_price, fill_cost) is not None
            except Exception as e:
                logger.error(f"Error orden real (buy): {e}")
                return False
        return self.portfolio.buy(price, amount) is not None

    def _sell(self, price: float, pct: float, floor_pct: float = config.MIN_ETH_FLOOR_PCT) -> bool:
        """Vende pct% del ETH vendible, respetando el piso indicado (default: MIN_ETH_FLOOR_PCT)."""
        floor_eth = (config.INITIAL_USDT * floor_pct) / price
        sellable  = max(0.0, self.portfolio.eth - floor_eth)
        if sellable < 0.000001:
            logger.info(f"ETH en piso (${config.INITIAL_USDT * floor_pct:.0f} equiv.) — no se vende")
            return False
        eth_amount = sellable * pct
        if eth_amount * price < config.MIN_ORDER_USDT:
            logger.info(f"Orden muy pequeña (${eth_amount * price:.2f} < ${config.MIN_ORDER_USDT}) — skip")
            return False
        if config.LIVE_TRADING:
            try:
                order = self.market.place_order(config.SYMBOL, "sell", amount_eth=eth_amount)
                fill_price = float(order.get("average") or price)
                fill_eth   = float(order.get("filled")  or eth_amount)
                logger.info(f"Orden real ejecutada — ID: {order['id']} | fill: ${fill_price:.2f} | ETH: {fill_eth:.6f}")
                return self.portfolio.sell(fill_price, fill_eth) is not None
            except Exception as e:
                logger.error(f"Error orden real (sell): {e}")
                return False
        return self.portfolio.sell(price, eth_amount) is not None

    def _status(self, snap: MarketSnapshot):
        logger.info(self.portfolio.status(snap.price, config.INITIAL_USDT))

    # ── Stop-loss y Trailing stop globales ───────────────────────────────

    def _update_peak(self, price: float):
        if self.portfolio.eth <= 0.000001:
            self.portfolio.price_peak = 0.0
            return
        if price > self.portfolio.price_peak:
            self.portfolio.price_peak = price

    def _check_stop_loss(self, snap: MarketSnapshot) -> bool:
        avg = self.portfolio.avg_buy_price()
        if avg is None:
            return False
        drawdown = (avg - snap.price) / avg
        if drawdown < config.STOP_LOSS_TRIGGER_PCT:
            return False
        logger.warning(
            f"[STOP-LOSS] Precio ${snap.price:.2f} está {drawdown*100:.1f}% bajo avg compra ${avg:.2f} "
            f"— vendiendo {config.STOP_LOSS_SELL_PCT*100:.0f}% y pausando compras este ciclo"
        )
        self._sell(snap.price, config.STOP_LOSS_SELL_PCT)
        self._status(snap)
        return True

    def _check_trailing_stop(self, snap: MarketSnapshot) -> bool:
        if self.portfolio.price_peak <= 0 or self.portfolio.eth <= 0.000001:
            return False
        drop = (self.portfolio.price_peak - snap.price) / self.portfolio.price_peak
        if drop < config.TRAILING_STOP_PCT:
            return False
        logger.warning(
            f"[TRAILING-STOP] Precio ${snap.price:.2f} cayó {drop*100:.1f}% desde pico "
            f"${self.portfolio.price_peak:.2f} — vendiendo {config.TRAILING_STOP_SELL_PCT*100:.0f}%"
        )
        self._sell(snap.price, config.TRAILING_STOP_SELL_PCT)
        self._status(snap)
        return True

    # ── ALCISTA: Trend Rider ──────────────────────────────────────────────

    def _run_bull(self, snap: MarketSnapshot) -> dict:
        available = self._available(config.BULL_RESERVE_PCT)

        # Tendencia rota: precio cruza bajo MA20 → vender (piso alto para no drenar la posición)
        if snap.price < snap.ma20 and self.portfolio.eth > 0:
            logger.info(
                f"[ALCISTA] Precio ${snap.price:.2f} rompe MA20 ${snap.ma20:.2f} — "
                f"tendencia rota, vendiendo {config.BULL_SELL_PCT*100:.0f}% (piso ${config.INITIAL_USDT * config.BULL_ETH_FLOOR_PCT:.0f} equiv.)"
            )
            self._sell(snap.price, config.BULL_SELL_PCT, floor_pct=config.BULL_ETH_FLOOR_PCT)
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
