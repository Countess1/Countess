# Architecture

## Overview

COUNTESS is a Streamlit application that combines:
1. A deterministic blackjack simulation engine
2. A survival economy subsystem
3. A cinematic UI playback renderer in a Windows desktop motif

## Core Components

- `Rules`, `RunConfig`, `SurvivalEconomy`: immutable/mutable configuration dataclasses.
- `Shoe`, `Hand`, and strategy helpers: card model and policy logic.
- `BlackjackEnv`: game loop, dealer behavior, splits/doubles, settlement.
- `CreditManager`: burn/tax/refill/death credit lifecycle.
- UI renderers (`term_html`, `table_html`, desktop/window wrappers): themed front-end structure.

## Survival Loop

Each hand follows:
1. Place base bet.
2. Simulate blackjack round and compute PnL.
3. Apply economy step:
   - subtract `burn_per_hand`
   - add `tax_rate_on_positive_profit * profit` when profit > 0
   - auto-refill below `refill_threshold`
   - if at/below `death_threshold`, transition to permanent `DEAD`
4. Append structured logs and optional JSONL trace.

## Cinematic Playback

Round execution produces a verbose trace of discrete actions (`DEAL`, `HIT`, `STAND`, `DOUBLE`, `SPLIT`, `REVEAL`, `settle`).
The playback reducer (`apply_trace_step`) advances state frame-by-frame for visual narration.

## UI Structure

- Desktop background + icons + taskbar scaffold the environment.
- A centered faux-window hosts split content:
  - Left: terminal-style event stream
  - Right: blackjack table visualization
- HUD overlays realism-only metrics (viewers/ping/FPS/uptime).
