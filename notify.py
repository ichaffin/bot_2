import logging
import os
import smtplib
from email.mime.text import MIMEText
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

GMAIL_USER     = os.getenv("GMAIL_USER", "")
GMAIL_APP_PASS = os.getenv("GMAIL_APP_PASSWORD", "")
NOTIFY_EMAIL   = os.getenv("NOTIFY_EMAIL", "")
LOG_FILE       = Path("bot_real.log")


def _last_log_lines(n: int = 20) -> str:
    if not LOG_FILE.exists():
        return ""
    lines = LOG_FILE.read_text().splitlines()
    return "\n".join(lines[-n:])


def _detect_regime(log_tail: str) -> str:
    for regime in ["ALCISTA", "BAJISTA", "LATERAL", "VOLÁTIL"]:
        if f"[{regime}]" in log_tail:
            return regime
    return "—"


def _detect_action(log_tail: str) -> str:
    if "STOP-LOSS" in log_tail:
        return "STOP-LOSS"
    if "TRAILING STOP" in log_tail:
        return "TRAILING STOP"
    if "COMPRA " in log_tail:
        return "COMPRÓ"
    if "VENTA " in log_tail:
        return "VENDIÓ"
    return "sin orden"


def send_cycle_summary(portfolio, price: float, initial_capital: float) -> None:
    if not all([GMAIL_USER, GMAIL_APP_PASS, NOTIFY_EMAIL]):
        return

    total   = portfolio.usdt + portfolio.eth * price
    pnl     = total - initial_capital
    pnl_pct = (pnl / initial_capital * 100) if initial_capital > 0 else 0.0
    avg     = portfolio.avg_buy_price()
    avg_str = f"${avg:.2f}" if avg else "N/A"

    log_tail = _last_log_lines(20)
    regime   = _detect_regime(log_tail)
    action   = _detect_action(log_tail)

    subject = f"Bot ETH — [{regime}] ${total:.2f} | {action}"
    body = f"""Bot ETH/USDT — Resumen de ciclo

Régimen detectado : {regime}
Acción            : {action}

━━━ Portfolio ━━━
USDT              : ${portfolio.usdt:.2f}
ETH               : {portfolio.eth:.6f} (~${portfolio.eth * price:.2f})
Precio actual     : ${price:.2f}
Avg compra        : {avg_str}
Total             : ${total:.2f}
P&L               : ${pnl:+.2f} ({pnl_pct:+.2f}%)
P&L realizado     : ${portfolio.realized_pnl:+.2f}

━━━ Últimas líneas del log ━━━
{log_tail}
"""

    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"] = subject
    msg["From"]    = GMAIL_USER
    msg["To"]      = NOTIFY_EMAIL

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
            smtp.login(GMAIL_USER, GMAIL_APP_PASS)
            smtp.send_message(msg)
        logger.info(f"Mail enviado a {NOTIFY_EMAIL}")
    except Exception as e:
        logger.warning(f"Mail no enviado: {e}")
