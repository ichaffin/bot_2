import os
from dotenv import load_dotenv
load_dotenv()

LIVE_TRADING = os.getenv("LIVE_TRADING", "false").lower() == "true"
MIN_ORDER_USDT = 10.0  # mínimo notional Binance ETH/USDT

SYMBOL = "ETH/USDT"
TIMEFRAME = "1h"
INITIAL_USDT = 1000

# --- Detección de régimen ---
RSI_PERIOD = 14
REGIME_MA_SHORT = 20
REGIME_MA_LONG = 50
REGIME_ADX_PERIOD = 14
REGIME_ATR_PERIOD = 14
REGIME_ATR_MULTIPLIER = 1.5   # ATR actual > 1.5x ATR promedio → VOLÁTIL
REGIME_CANDLES = 70            # velas necesarias para detectar régimen con buffer
LATERAL_RANGE_CANDLES = 24    # velas para calcular rango de precio en lateral

EXCHANGE_ID = "binance"
DCA_INTERVAL_MINUTES = 59

# --- Stop-loss global ---
STOP_LOSS_TRIGGER_PCT = 0.12   # dispara si precio cae 12% bajo el avg_buy_price
STOP_LOSS_SELL_PCT    = 0.30   # vende 30% del ETH vendible al disparar

# --- Trailing stop global ---
TRAILING_STOP_PCT      = 0.08  # dispara si precio cae 8% desde el pico
TRAILING_STOP_SELL_PCT = 0.25  # vende 25% del ETH vendible al disparar

# --- Position sizing porcentual ---
# Todas las compras usan % del capital disponible (por encima de la reserva).
# Decaimiento geométrico: cada compra es más chica que la anterior → nunca agota el capital.
# Todas las ventas respetan un piso mínimo de ETH para siempre mantener posición.
MIN_ETH_FLOOR_PCT = 0.05       # piso absoluto: nunca vender por debajo de este % del capital inicial en valor ETH

# --- ALCISTA: Trend Rider ---
BULL_RESERVE_PCT = 0.20
BULL_BUY_PCT = 0.08            # compra 8% del disponible en cada pullback (conservador en tendencia)
BULL_RSI_BUY_MIN = 40
BULL_RSI_BUY_MAX = 50
BULL_SELL_PCT = 0.15           # vende 15% del ETH vendible si precio rompe MA20
BULL_ETH_FLOOR_PCT = 0.25      # piso de venta en MA break: siempre deja 25% del capital inicial equiv en ETH

# --- BAJISTA: Defensive DCA ---
BEAR_RESERVE_PCT = 0.40
BEAR_BUY_PCT = 0.10            # compra 10% del disponible por ciclo
BEAR_BUY_BOOST = 2.0           # x2 cuando RSI < RSI_OVERSOLD (compra 20%)
BEAR_RSI_OVERSOLD = 30
BEAR_RSI_OVERBOUGHT = 65
BEAR_SELL_PCT = 0.15           # vende 15% del ETH vendible en rebotes

# --- LATERAL: Range Trader ---
LATERAL_RESERVE_PCT = 0.25
LATERAL_BUY_PCT = 0.08         # compra 8% del disponible en piso de rango
LATERAL_RSI_BUY = 45
LATERAL_RSI_SELL = 60
LATERAL_PRICE_BUY_PCT = 30
LATERAL_PRICE_SELL_PCT = 75
LATERAL_SELL_PCT = 0.20        # vende 20% del ETH vendible en techo de rango

# --- VOLÁTIL: Wait & Strike ---
VOLATILE_RESERVE_PCT = 0.50
VOLATILE_BUY_PCT = 0.15        # compra 15% del disponible en extremo sobrevendido
VOLATILE_BUY_BOOST = 3.0       # x3 cuando RSI < VOLATILE_RSI_BUY (compra 45%)
VOLATILE_RSI_BUY = 25
VOLATILE_RSI_SELL = 75
VOLATILE_SELL_PCT = 0.20
VOLATILE_MAX_EXPOSURE = 0.30
