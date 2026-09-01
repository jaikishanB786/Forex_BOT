# Forex AI Bot 🤖

Automated Forex trading bot powered by MetaTrader 5 and Python.

> ⚠️ **This bot starts in DRY_RUN mode.** No real trades are placed until you explicitly enable LIVE mode.

## Features

- **MT5 Integration** — Direct connection to MetaTrader 5 terminal
- **Pluggable Strategies** — Swap trading strategies via config
- **Risk Management** — Per-trade sizing, max drawdown, SL/TP
- **DRY_RUN Mode** — Test everything without risking real money
- **Structured Logging** — Colored console + rotating file logs
- **Config-Driven** — All parameters in YAML, secrets in `.env`

## Quick Start

### Prerequisites

- **Python 3.11+** (64-bit)
- **MetaTrader 5** terminal installed — [Download](https://www.metatrader5.com/en/download)
- A broker demo account inside MT5

### Setup

```bash
# 1. Clone the repo
git clone https://github.com/jaikishanB786/Forex_BOT.git
cd Forex_AI_BOT

# 2. Create virtual environment
python -m venv .venv
.venv\Scripts\activate        # Windows
# source .venv/bin/activate   # Linux/Mac

# 3. Install dependencies
pip install -r requirements.txt

# 4. Configure credentials
cp .env.example .env
# Edit .env with your MT5 login, password, and server

# 5. (Optional) Customize trading settings
# Edit config/settings.yaml
```

### Run

```bash
python -m src.main
```

## Project Structure

```
Forex_AI_BOT/
├── config/
│   ├── settings.yaml           # Trading & risk parameters
│   └── settings.example.yaml   # Example config (safe to commit)
├── src/
│   ├── __init__.py
│   ├── main.py                 # Entry point
│   ├── config.py               # Configuration loader
│   ├── logger.py               # Logging infrastructure
│   ├── mt5_connector.py        # MT5 connection (Phase 2)
│   ├── data_fetcher.py         # Market data (Phase 3)
│   ├── risk_manager.py         # Risk controls (Phase 4)
│   ├── trade_executor.py       # Order execution (Phase 5)
│   ├── portfolio.py            # Position tracking (Phase 5)
│   ├── notifier.py             # Alerts (Phase 7)
│   └── strategy/
│       ├── base_strategy.py    # Abstract strategy interface
│       └── moving_average.py   # MA crossover strategy
├── tests/
├── logs/                       # Runtime logs (git-ignored)
├── .env.example                # Credential template
├── .gitignore
├── requirements.txt
└── README.md
```

## Configuration

| Source | Purpose | Committed to Git? |
|---|---|---|
| `config/settings.yaml` | Trading params, risk, schedule | ✅ Yes |
| `.env` | MT5 credentials, secrets | ❌ No |

Environment variables in `.env` override `settings.yaml` values where applicable.

## Trading Modes

| Mode | Description |
|---|---|
| `DRY_RUN` | Logs signals and would-be orders without executing | 
| `LIVE` | Places real orders via MT5 — **use with caution** |

Set via `TRADING_MODE` in `.env` or `trading.mode` in `settings.yaml`.

## Testing

```bash
python -m pytest tests/ -v
```

## License

Private — All rights reserved.

## Disclaimer

This software is for **educational purposes only**. Forex trading carries significant risk. The authors are not responsible for any financial losses incurred through the use of this bot. Always test thoroughly in DRY_RUN mode and with demo accounts before considering live trading.
