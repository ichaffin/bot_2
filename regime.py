from dataclasses import dataclass
from enum import Enum

import pandas as pd


class Regime(Enum):
    BULL     = "ALCISTA"
    BEAR     = "BAJISTA"
    LATERAL  = "LATERAL"
    VOLATILE = "VOLATIL"


@dataclass
class MarketSnapshot:
    price: float
    rsi: float
    adx: float
    ma20: float
    ma50: float
    atr: float
    atr_avg: float
    atr_ratio: float
    range_high: float
    range_low: float
    price_pct: float    # 0 = piso del rango, 100 = techo
    regime: Regime


def _wilder(series: pd.Series, period: int) -> pd.Series:
    return series.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()


def _to_df(ohlcv: list) -> pd.DataFrame:
    return pd.DataFrame(ohlcv, columns=["ts", "open", "high", "low", "close", "volume"])


def _rsi(closes: pd.Series, period: int) -> float:
    delta = closes.diff()
    gain = _wilder(delta.clip(lower=0), period)
    loss = _wilder(-delta.clip(upper=0), period)
    rs = gain / loss.replace(0, float("nan"))
    return float((100 - 100 / (1 + rs)).iloc[-1])


def _adx(df: pd.DataFrame, period: int) -> float:
    h, l, c = df["high"], df["low"], df["close"]
    tr = pd.concat([h - l, (h - c.shift()).abs(), (l - c.shift()).abs()], axis=1).max(axis=1)
    up, dn = h.diff(), -l.diff()
    dm_plus  = up.where((up > dn) & (up > 0), 0.0)
    dm_minus = dn.where((dn > up) & (dn > 0), 0.0)
    atr_s    = _wilder(tr, period)
    di_plus  = 100 * _wilder(dm_plus,  period) / atr_s
    di_minus = 100 * _wilder(dm_minus, period) / atr_s
    denom    = (di_plus + di_minus).replace(0, float("nan"))
    dx       = 100 * (di_plus - di_minus).abs() / denom
    return float(_wilder(dx.fillna(0), period).iloc[-1])


def _atr(df: pd.DataFrame, period: int) -> tuple[float, float]:
    h, l, c = df["high"], df["low"], df["close"]
    tr  = pd.concat([h - l, (h - c.shift()).abs(), (l - c.shift()).abs()], axis=1).max(axis=1)
    atr = _wilder(tr, period)
    current = float(atr.iloc[-1])
    avg     = float(atr.iloc[-(period + 1):-1].mean()) if len(atr) > period + 1 else current
    return current, avg


def detect(
    ohlcv: list,
    rsi_period: int = 14,
    ma_short: int = 20,
    ma_long: int = 50,
    adx_period: int = 14,
    atr_period: int = 14,
    atr_mult: float = 1.5,
    range_candles: int = 24,
) -> MarketSnapshot:
    df     = _to_df(ohlcv)
    closes = df["close"]
    price  = float(closes.iloc[-1])

    rsi       = _rsi(closes, rsi_period)
    adx       = _adx(df, adx_period)
    ma20      = float(closes.rolling(ma_short).mean().iloc[-1])
    ma50      = float(closes.rolling(ma_long).mean().iloc[-1])
    atr, atr_avg = _atr(df, atr_period)
    atr_ratio = atr / atr_avg if atr_avg > 0 else 1.0

    recent     = closes.iloc[-range_candles:]
    range_high = float(recent.max())
    range_low  = float(recent.min())
    span       = range_high - range_low
    price_pct  = ((price - range_low) / span * 100) if span > 0 else 50.0

    # Prioridad: VOLÁTIL > TENDENCIA (ALCISTA/BAJISTA) > LATERAL
    if atr_ratio >= atr_mult:
        regime = Regime.VOLATILE
    elif adx >= 25:
        regime = Regime.BULL if ma20 > ma50 else Regime.BEAR
    else:
        regime = Regime.LATERAL

    return MarketSnapshot(
        price=price, rsi=rsi, adx=adx, ma20=ma20, ma50=ma50,
        atr=atr, atr_avg=atr_avg, atr_ratio=atr_ratio,
        range_high=range_high, range_low=range_low, price_pct=price_pct,
        regime=regime,
    )
