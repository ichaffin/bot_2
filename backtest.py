"""
Backtest multi-régimen sobre velas históricas reales.
Uso: python backtest.py --horas 72
"""
import argparse
from datetime import datetime, timezone

import config
from market import MarketData
from portfolio import Portfolio
from regime import Regime, detect

WARMUP = config.REGIME_CANDLES   # velas de calentamiento para MA50/ADX/ATR


def run_backtest(horas: int, split: bool = False):
    modo = "50% USDT + 50% ETH" if split else "100% USDT"
    print(f"\n{'='*70}")
    print(f"  BACKTEST MULTI-RÉGIMEN — ETH/USDT — últimas {horas}h  [{modo}]")
    print(f"{'='*70}")
    print(f"  Capital inicial : ${config.INITIAL_USDT:.2f} USDT")
    print(f"  Velas calentamiento: {WARMUP} (MA50 + ADX + ATR)")
    print(f"{'='*70}\n")

    market = MarketData(config.EXCHANGE_ID)
    total  = horas + WARMUP
    print(f"Descargando {total} velas de 1h desde Binance...")
    ohlcv  = market.get_ohlcv(config.SYMBOL, config.TIMEFRAME, limit=total)
    print(f"Velas obtenidas: {len(ohlcv)}\n")

    first_price = ohlcv[WARMUP][4]
    if split:
        mitad       = config.INITIAL_USDT / 2
        eth_inicial = mitad / first_price
        portfolio   = Portfolio(
            usdt=mitad,
            eth=eth_inicial,
            total_usdt_invested=0.0,   # ETH pre-existente, no comprado por el bot
            total_eth_bought=0.0,
            price_peak=first_price,    # trailing stop activo desde el arranque
        )
        print(f"Inicio 50/50: ${mitad:.2f} USDT + {eth_inicial:.6f} ETH pre-existente @ ${first_price:.2f}\n")
    else:
        portfolio   = Portfolio(usdt=config.INITIAL_USDT)
    last_price  = ohlcv[-1][4]
    regime_counts = {r: 0 for r in Regime}
    price_peak  = 0.0

    header = f"{'Timestamp':<20} {'Precio':>8} {'RSI':>5} {'ADX':>5} {'ATRr':>5}  {'Régimen':<9} {'Acción':<30} {'USDT':>8} {'ETH':>9} {'Total':>8} {'P&L':>8}"
    print(header)
    print("-" * len(header))

    for i in range(WARMUP, len(ohlcv)):
        window = ohlcv[: i + 1]
        snap   = detect(
            window,
            rsi_period=config.RSI_PERIOD,
            ma_short=config.REGIME_MA_SHORT,
            ma_long=config.REGIME_MA_LONG,
            adx_period=config.REGIME_ADX_PERIOD,
            atr_period=config.REGIME_ATR_PERIOD,
            atr_mult=config.REGIME_ATR_MULTIPLIER,
            range_candles=config.LATERAL_RANGE_CANDLES,
        )
        ts    = datetime.fromtimestamp(ohlcv[i][0] / 1000, tz=timezone.utc).strftime("%Y-%m-%d %H:%M")
        price = snap.price
        regime_counts[snap.regime] += 1
        action_str = ""

        floor_eth = (config.INITIAL_USDT * config.MIN_ETH_FLOOR_PCT) / price

        def do_buy(pct, avail):
            amt = avail * pct
            if amt < 1.0:
                return f"skip (disponible ${avail:.0f})"
            portfolio.buy(price, amt)
            return f"COMPRA {pct*100:.0f}% (${amt:.0f})"

        def do_sell(pct, floor_pct=config.MIN_ETH_FLOOR_PCT):
            f_eth = (config.INITIAL_USDT * floor_pct) / price
            sellable = max(0.0, portfolio.eth - f_eth)
            if sellable < 0.000001:
                return "piso ETH — no vende"
            eth_sell = sellable * pct
            portfolio.sell(price, eth_sell)
            return f"VENTA {pct*100:.0f}% ({eth_sell:.4f}ETH)"

        # ── Actualizar pico ───────────────────────────────────────────────
        if portfolio.eth <= 0.000001:
            price_peak = 0.0
        elif price > price_peak:
            price_peak = price

        # ── Stop-loss global ──────────────────────────────────────────────
        triggered = False
        avg = portfolio.avg_buy_price()
        if avg and portfolio.eth > 0.000001:
            drawdown = (avg - price) / avg
            if drawdown >= config.STOP_LOSS_TRIGGER_PCT:
                action_str  = "STOP-LOSS: " + do_sell(config.STOP_LOSS_SELL_PCT)
                triggered   = True

        # ── Trailing stop global ──────────────────────────────────────────
        if not triggered and price_peak > 0 and portfolio.eth > 0.000001:
            drop = (price_peak - price) / price_peak
            if drop >= config.TRAILING_STOP_PCT:
                action_str = "TRAIL-STOP: " + do_sell(config.TRAILING_STOP_SELL_PCT)
                triggered  = True

        # ── Regímenes (solo si no disparó ningún stop) ────────────────────
        if not triggered:
            # ALCISTA
            if snap.regime == Regime.BULL:
                avail = max(0.0, portfolio.usdt - config.INITIAL_USDT * config.BULL_RESERVE_PCT)
                if price < snap.ma20 and portfolio.eth > floor_eth:
                    action_str = "MA break: " + do_sell(config.BULL_SELL_PCT, floor_pct=config.BULL_ETH_FLOOR_PCT)
                elif config.BULL_RSI_BUY_MIN <= snap.rsi <= config.BULL_RSI_BUY_MAX and avail > 0:
                    action_str = do_buy(config.BULL_BUY_PCT, avail)
                else:
                    action_str = "espera"

            # BAJISTA
            elif snap.regime == Regime.BEAR:
                avail = max(0.0, portfolio.usdt - config.INITIAL_USDT * config.BEAR_RESERVE_PCT)
                if snap.rsi > config.BEAR_RSI_OVERBOUGHT and portfolio.eth > floor_eth:
                    action_str = "rebote: " + do_sell(config.BEAR_SELL_PCT)
                elif avail <= 0:
                    action_str = "skip reserva"
                else:
                    pct = config.BEAR_BUY_PCT * config.BEAR_BUY_BOOST if snap.rsi < config.BEAR_RSI_OVERSOLD else config.BEAR_BUY_PCT
                    action_str = do_buy(pct, avail)

            # LATERAL
            elif snap.regime == Regime.LATERAL:
                avail = max(0.0, portfolio.usdt - config.INITIAL_USDT * config.LATERAL_RESERVE_PCT)
                if snap.price_pct >= config.LATERAL_PRICE_SELL_PCT and snap.rsi > config.LATERAL_RSI_SELL and portfolio.eth > floor_eth:
                    action_str = "techo: " + do_sell(config.LATERAL_SELL_PCT)
                elif snap.price_pct <= config.LATERAL_PRICE_BUY_PCT and snap.rsi < config.LATERAL_RSI_BUY and avail > 0:
                    action_str = do_buy(config.LATERAL_BUY_PCT, avail)
                else:
                    action_str = f"espera {snap.price_pct:.0f}% rango"

            # VOLÁTIL
            elif snap.regime == Regime.VOLATILE:
                avail       = max(0.0, portfolio.usdt - config.INITIAL_USDT * config.VOLATILE_RESERVE_PCT)
                eth_val     = portfolio.eth * price
                max_eth_val = config.INITIAL_USDT * config.VOLATILE_MAX_EXPOSURE
                if snap.rsi > config.VOLATILE_RSI_SELL and portfolio.eth > floor_eth:
                    action_str = "strike: " + do_sell(config.VOLATILE_SELL_PCT)
                elif snap.rsi < config.VOLATILE_RSI_BUY and eth_val < max_eth_val and avail > 0:
                    cap = min(avail, max_eth_val - eth_val)
                    action_str = do_buy(config.VOLATILE_BUY_PCT * config.VOLATILE_BUY_BOOST, cap)
                else:
                    action_str = f"espera RSI {snap.rsi:.0f}"

        total = portfolio.usdt + portfolio.eth * price
        pnl   = total - config.INITIAL_USDT
        regime_tag = snap.regime.value
        print(
            f"{ts:<20} ${price:>7.2f} {snap.rsi:>5.1f} {snap.adx:>5.1f} {snap.atr_ratio:>5.2f}  "
            f"{regime_tag:<9} {action_str:<30} ${portfolio.usdt:>7.2f} {portfolio.eth:>9.5f} ${total:>7.2f} ${pnl:>+7.2f}"
        )

    # ── Resumen ───────────────────────────────────────────────────────────
    final    = portfolio.usdt + portfolio.eth * last_price
    pnl_bot  = final - config.INITIAL_USDT
    avg      = portfolio.avg_buy_price()

    if split:
        mitad       = config.INITIAL_USDT / 2
        eth_hold    = mitad / first_price          # el ETH que ya tenías
        pnl_hold    = (mitad + eth_hold * last_price) - config.INITIAL_USDT
        hold_label  = "Hold ETH + cash ($500 USDT sin tocar)"
    else:
        eth_hold   = config.INITIAL_USDT / first_price
        pnl_hold   = eth_hold * last_price - config.INITIAL_USDT
        hold_label = "Hold puro (comprar todo al inicio)"

    print(f"\n{'='*70}")
    print(f"  RESUMEN — {horas}h")
    print(f"{'='*70}")
    print(f"  Precio inicial  : ${first_price:.2f}  >>  final: ${last_price:.2f}  ({(last_price/first_price-1)*100:+.2f}%)")
    print()
    print(f"  Regimenes detectados:")
    for r, n in regime_counts.items():
        pct = n / horas * 100
        bar = "|" * int(pct / 5)
        print(f"    {r.value:<9} {n:>3} ciclos ({pct:>5.1f}%)  {bar}")
    print()
    print(f"  Bot multi-regimen:")
    print(f"    Avg precio compra : {'$'+f'{avg:.2f}' if avg else 'N/A'}")
    print(f"    USDT final        : ${portfolio.usdt:.2f}")
    print(f"    ETH final         : {portfolio.eth:.6f}")
    print(f"    Total             : ${final:.2f}")
    print(f"    P&L total         : ${pnl_bot:+.2f} ({pnl_bot/config.INITIAL_USDT*100:+.2f}%)")
    print(f"    P&L realizado     : ${portfolio.realized_pnl:+.2f}")
    print()
    print(f"  {hold_label}:")
    print(f"    ETH               : {eth_hold:.6f} @ ${first_price:.2f}")
    if split:
        print(f"    USDT cash         : ${mitad:.2f}")
    print(f"    Total             : ${(mitad if split else 0) + eth_hold * last_price:.2f}")
    print(f"    P&L               : ${pnl_hold:+.2f} ({pnl_hold/config.INITIAL_USDT*100:+.2f}%)")
    print()
    diff = pnl_bot - pnl_hold
    winner = "Bot" if diff >= 0 else "Hold"
    print(f"  >> {winner} gana por ${abs(diff):.2f}")
    print(f"{'='*70}\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--horas", type=int, default=72, help="Horas a simular (default: 72)")
    parser.add_argument("--split", action="store_true", help="Arrancar 50%% USDT + 50%% ETH")
    args = parser.parse_args()
    run_backtest(args.horas, split=args.split)
