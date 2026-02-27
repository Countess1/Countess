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

## Go Live on Your Main Page

### Option A: Streamlit Community Cloud (fastest)
1. Push this repo to GitHub.
2. Go to [share.streamlit.io](https://share.streamlit.io) and click **New app**.
3. Select:
   - **Repository**: your repo
   - **Branch**: `main`
   - **Main file path**: `countess/app.py`
4. Click **Deploy**.

Your app URL will be your public main page (for example: `https://your-app-name.streamlit.app`).

### Option B: Self-host on a VM/server
```bash
cd countess
pip install -r requirements.txt
streamlit run app.py --server.port 8501 --server.address 0.0.0.0
```
Then put Nginx/Caddy in front and map your domain root (`/`) to the Streamlit service.

### GitHub main page note
GitHub repository pages (`github.com/<user>/<repo>`) cannot run Streamlit apps directly.
Use Streamlit Community Cloud (or your own server) and link that URL from your repo profile/README.
