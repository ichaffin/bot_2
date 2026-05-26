# Bot DCA + RSI — ETH/USDT (Paper Trading)

## Qué es

Bot de trading automatizado para el par ETH/USDT que combina dos estrategias:

- **DCA (Dollar Cost Averaging)**: compra una cantidad fija de ETH a intervalos regulares, promediando el precio de entrada a lo largo del tiempo.
- **RSI (Relative Strength Index)**: ajusta el comportamiento según si el mercado está sobrevendido o sobrecomprado.

Corre en modo **paper trading** (dinero simulado) para validar la estrategia antes de arriesgar capital real.

---

## Cómo funciona

Cada 59 minutos el bot ejecuta un ciclo:

1. Descarga las últimas velas de ETH/USDT desde Binance (API pública, sin API key)
2. Calcula el RSI de 14 períodos
3. Decide la acción según el RSI:

| RSI | Acción |
|---|---|
| < 30 (sobrevendido) | Compra doble ($100) — dip agresivo |
| 30 – 70 (neutral) | Compra normal ($50) |
| > 70 (sobrecomprado) | Vende el 15% del ETH acumulado |

4. Respeta siempre una **reserva mínima de $300 USDT** (30% del capital) — nunca toca ese colchón
5. Guarda el estado en `state.json` y registra todo en `bot.log`

---

## Configuración actual

| Parámetro | Valor |
|---|---|
| Par | ETH/USDT |
| Capital inicial | $1,000 USDT |
| Reserva mínima | $300 USDT (30%) |
| Capital operable | $700 USDT |
| DCA base por ciclo | $50 |
| DCA boost (RSI < 30) | $100 (x2) |
| Venta en sobrecompra | 15% del ETH cuando RSI > 70 |
| Intervalo | 59 minutos (Task Scheduler) |
| Exchange datos | Binance (público) |

---

## Archivos

| Archivo | Descripción |
|---|---|
| `main.py` | Entry point. `--once` para un ciclo, sin flag para bucle continuo |
| `strategy.py` | Lógica DCA + RSI |
| `portfolio.py` | Portfolio simulado con compra, venta y métricas |
| `market.py` | Conexión a Binance para precios y velas |
| `config.py` | Todos los parámetros ajustables |
| `state.json` | Estado persistente del portfolio entre ciclos |
| `bot.log` | Historial completo de operaciones |

---

## Cómo correrlo

```powershell
# Un ciclo manual
.\venv\Scripts\python.exe main.py --once

# Bucle continuo (manual, Ctrl+C para detener)
.\venv\Scripts\python.exe main.py
```

El Task Scheduler ya está configurado para correrlo automáticamente cada 59 minutos con la tarea `DCA_RSI_Bot`.

```powershell
# Ver estado de la tarea
Get-ScheduledTask -TaskName "DCA_RSI_Bot"

# Correr ahora manualmente
Start-ScheduledTask -TaskName "DCA_RSI_Bot"

# Pausar
Disable-ScheduledTask -TaskName "DCA_RSI_Bot"
```

---

## Qué esperamos de esta prueba

### Hipótesis
La combinación de DCA con señales RSI debería superar a un DCA puro en mercados volátiles, comprando más en caídas y recuperando capital en subidas.

### Métricas a evaluar (próximas semanas)

- **P&L total** al cabo de 30 días
- **Precio promedio de compra** vs precio de mercado — queremos que la estrategia acumule por debajo del precio spot
- **Cuántas veces se activó el boost** (RSI < 30) y si coincidieron con pisos de precio
- **Cuántas ventas** se ejecutaron y si mejoraron el P&L vs hold puro
- **Uso de la reserva** — ¿alcanzó el límite de $300? ¿cuántas veces?

### Señales de que funciona bien
- Avg compra < precio de mercado a fin del período
- P&L positivo o menor pérdida que un hold puro desde el mismo punto de entrada
- Las ventas (RSI > 70) coinciden con techos de precio

### Señales de que hay que ajustar
- Se queda sin capital operable muy rápido sin que el precio suba
- Las ventas cortan tendencias alcistas demasiado pronto
- El RSI no genera señales útiles en mercado lateral prolongado

---

## Aprendizajes de la primera semana (16–25 mayo 2026)

La prueba anterior (sin reserva ni venta) reveló dos problemas:

1. **Agotó el capital en ~20 horas** comprando cada ciclo sin límite, quedando sin USDT justo antes de que ETH bajara.
2. **Sin lógica de venta**: detectaba sobrecompra pero no aprovechaba para tomar ganancia. Resultado: -3.6% al cierre.

Ambos problemas están corregidos en la versión actual.
