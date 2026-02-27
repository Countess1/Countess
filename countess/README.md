![COUNTESS Banner](assets/banner.png)

# COUNTESS

Windows Terminal–style blackjack survival simulation. Simulation only. No real gambling integration.

## Quickstart

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
streamlit run app.py
```

## Features

- Windows desktop-themed Streamlit shell with taskbar, desktop icons, and window chrome.
- Split-pane UI: Windows Terminal-style logs on the left and cinematic blackjack table playback on the right.
- Simulation-only blackjack engine (6 decks, S17, 3:2 blackjack payout, splitting/doubling decisions, deterministic basic strategy).
- Survival economy loop with burn per hand, tax on positive profit, refill threshold behavior, and DEAD state when depleted.
- Fake LIVE HUD realism: viewers, ping, FPS, and uptime.

## Disclaimer

COUNTESS is a **simulation-only demo** intended for UI/engine experimentation and educational visualization.
It does **not** connect to real casinos, betting systems, scraping pipelines, or automation targets.
