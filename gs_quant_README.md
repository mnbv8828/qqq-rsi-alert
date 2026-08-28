# GS Quant Stock Analyzer

Independent stock-selection and entry-timing system.

## Purpose

This project is intentionally separate from the existing QQQ/SPY RSI + divergence alert system.

### Universe
- All Nasdaq-100 constituents
- QQQ is the benchmark
- SPY is not used as a ranked stock

### Output rules
1. Analyze every Nasdaq-100 constituent.
2. Show only stocks with Stock Ranking >= 70.
3. Show Entry Timing for every displayed stock.
4. Entry Timing has no separate display cutoff.
5. Bullish-divergence logic from the existing project is NOT used.

## Environment variables

```text
BOT_TOKEN_GS_QUANT
CHAT_ID_GS_QUANT
TEST_MODE=true
```

## TEST_MODE

- `TEST_MODE=true`: runs the full analysis and sends **one Telegram message labeled `🧪 GS QUANT TEST MODE`**.
- `TEST_MODE=false`: runs the full analysis and sends the normal live Telegram message.

This is intentionally different from a dry-run: test mode verifies the complete Telegram delivery path.

## Run

```bash
pip install -r "gs_quant_requirements.txt"
python "gs_quant_main.py"
```

## GitHub Actions

Use a separate workflow so this system cannot interfere with the existing RSI workflow.
