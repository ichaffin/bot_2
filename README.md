# Bot DCA + Multi-Régimen — ETH/USDT (Live Trading)

## Qué es

Bot de trading automatizado para el par ETH/USDT que combina DCA con detección de régimen de mercado y protecciones activas. Corre en **live trading** sobre Binance SPOT.

---

## Cómo funciona

Cada 59 minutos el bot ejecuta un ciclo:

1. Descarga las últimas velas de ETH/USDT desde Binance
2. Detecta el régimen de mercado actual (ALCISTA / BAJISTA / LATERAL / VOLÁTIL)
3. Ejecuta la estrategia correspondiente
4. Verifica stop-loss y trailing stop antes de cualquier acción
5. Ejecuta la orden real en Binance SPOT
6. Guarda el estado en `state.json` y registra todo en `bot_real.log`

### Regímenes y lógica

| Régimen | Condición | Compra | Vende |
|---|---|---|---|
| ALCISTA | ADX ≥ 25 + MA20 > MA50 | 8% disponible si RSI 40–50 | 15% si precio rompe MA20 |
| BAJISTA | ADX ≥ 25 + MA20 < MA50 | 10–20% disponible según RSI | 15% si RSI > 65 (rebote) |
| LATERAL | ADX < 25 | 8% en piso de rango (RSI < 45) | 20% en techo de rango (RSI > 60) |
| VOLÁTIL | ATR actual > 1.5× ATR promedio | 45% en RSI < 25 | 20% si RSI > 75 |

### Protecciones globales (pre-régimen)

| Protección | Trigger | Acción |
|---|---|---|
| Stop-loss | Precio 12% bajo avg compra | Vende 30%, pausa compras |
| Trailing stop | Precio cae 8% desde el pico | Vende 25%, pausa compras |

---

## Archivos

| Archivo | Descripción |
|---|---|
| `main.py` | Entry point. Flags: `--once`, `--live-init` |
| `strategy.py` | Lógica multi-régimen + stop-loss + trailing stop |
| `portfolio.py` | Estado del portfolio, P&L realizado, avg compra |
| `market.py` | Conexión a Binance (datos + órdenes reales) |
| `regime.py` | Detección de régimen (RSI, ADX, ATR, MA) |
| `config.py` | Todos los parámetros ajustables |
| `backtest.py` | Backtest histórico. Flags: `--horas N`, `--split` |
| `state.json` | Estado persistente del portfolio entre ciclos |
| `bot_real.log` | Log de operaciones en vivo |
| `.env` | API keys de Binance (no commitear) |
| `run.sh` | Script de arranque manual |

---

## Setup inicial (primera vez)

```bash
# 1. Crear entorno virtual e instalar dependencias
python3 -m venv venv
venv/bin/pip install -r requirements.txt

# 2. Configurar API keys
cp .env.example .env
# Editar .env con las keys de Binance

# 3. Leer saldo real de Binance SPOT y crear state.json
venv/bin/python3 main.py --live-init

# 4. Registrar en launchd para arranque automático
launchctl load ~/Library/LaunchAgents/com.bot.eth.plist
```

---

## Comandos rápidos

### Bot

```bash
# Ver si el bot está corriendo
launchctl list | grep com.bot.eth

# Ver log en vivo
tail -f bot_real.log

# Correr un ciclo manual ahora (sin tocar el loop)
venv/bin/python3 main.py --once

# Ver estado actual del portfolio
tail -1 bot_real.log | grep Portfolio
```

### Arranque y parada

```bash
# Iniciar bot (y activar arranque automático al login)
launchctl load ~/Library/LaunchAgents/com.bot.eth.plist

# Parar bot (y desactivar arranque automático)
launchctl unload ~/Library/LaunchAgents/com.bot.eth.plist

# Reiniciar bot (tras cambios en el código)
launchctl unload ~/Library/LaunchAgents/com.bot.eth.plist
launchctl load   ~/Library/LaunchAgents/com.bot.eth.plist
```

### Reset y re-sincronización

```bash
# Re-leer saldo real de Binance (tras transferencias o cambios manuales)
launchctl unload ~/Library/LaunchAgents/com.bot.eth.plist
rm state.json
venv/bin/python3 main.py --live-init
launchctl load ~/Library/LaunchAgents/com.bot.eth.plist
```

### Backtest

```bash
# Últimas 96 horas desde cero (100% USDT)
venv/bin/python3 backtest.py --horas 96

# Últimas 96 horas con ETH pre-existente (50/50)
venv/bin/python3 backtest.py --horas 96 --split
```

---

## Aprendizajes

### Primera semana (16–25 mayo 2026) — versión sin protecciones
1. **Agotó el capital en ~20 horas** comprando cada ciclo sin límite.
2. **Sin lógica de venta**: detectaba sobrecompra pero no actuaba. Resultado: -3.6%.

### Versión actual (desde 26 mayo 2026) — mejoras implementadas
- **P&L realizado**: al vender se ajusta el cost basis → avg compra siempre correcto
- **Stop-loss global**: corta pérdidas si el precio cae >12% bajo el avg de compra
- **Trailing stop**: protege ganancias si el precio cae >8% desde el pico
- **Piso de venta ALCISTA**: evita drenar la posición en cascada al romper MA20
- **Live trading**: órdenes reales ejecutadas en Binance SPOT via API
- **Arranque automático**: launchd reinicia el bot tras reboot de Mac respetando el intervalo
