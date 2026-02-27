# app.py
# COUNTESS — Windows Desktop + Windows Terminal (Simulation Only)
# Streamlit app that renders a fake Windows desktop + a “Windows Terminal” pane + blackjack table.
#
# Run:
#   pip install streamlit numpy
#   streamlit run app.py

from __future__ import annotations

import json
import time
import datetime
from dataclasses import dataclass
from pathlib import Path
from typing import List, Tuple, Optional

import numpy as np
import streamlit as st


# =========================
# BRAND / LORE
# =========================
PROJECT_NAME = "COUNTESS"
TAGLINE = "If I can't out-earn my own operating costs, I deserve to be shut down."
ENGINE_TAG = "countess-engine"
SIM_NOTE = "SIMULATION ONLY"


# =========================
# CONFIG
# =========================
@dataclass(frozen=True)
class Rules:
    decks: int = 6
    dealer_stands_soft_17: bool = True  # S17
    double_after_split: bool = True     # DAS
    allow_resplit_aces: bool = False
    max_splits: int = 3
    blackjack_payout: float = 1.5       # 3:2
    penetration: float = 0.75           # reshuffle when remaining < (1-penetration)


@dataclass
class SurvivalEconomy:
    initial_credits: float = 50.0
    burn_per_hand: float = 0.0005
    tax_rate_on_positive_profit: float = 0.20
    refill_threshold: float = 5.0
    refill_amount: float = 20.0
    death_threshold: float = 0.0


@dataclass
class RunConfig:
    seed: int = 7
    hands_cap: int = 500_000
    base_bet: float = 1.0
    initial_bankroll: float = 500.0


# =========================
# CARDS / SHOE
# =========================
SUITS = ["♠", "♥", "♦", "♣"]
RANKS = ["A", "2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K"]


def rank_value(rank: str) -> int:
    if rank == "A":
        return 1
    if rank in ["J", "Q", "K"]:
        return 10
    return int(rank)


def make_shoe_cards(decks: int) -> List[Tuple[str, str, int]]:
    cards = []
    for _ in range(decks):
        for suit in SUITS:
            for rank in RANKS:
                cards.append((rank, suit, rank_value(rank)))
    return cards


class Shoe:
    def __init__(self, decks: int, rng: np.random.Generator):
        self.decks = decks
        self.rng = rng
        self.cards = make_shoe_cards(decks)
        self.shuffle()

    def shuffle(self) -> None:
        self.rng.shuffle(self.cards)
        self.i = 0

    def remaining(self) -> int:
        return len(self.cards) - self.i

    def deal(self) -> Tuple[str, str, int]:
        c = self.cards[self.i]
        self.i += 1
        return c

    def needs_reshuffle(self, penetration: float) -> bool:
        return self.remaining() < int(len(self.cards) * (1 - penetration))


# =========================
# HAND UTILS
# =========================
@dataclass
class Hand:
    cards: List[Tuple[str, str, int]]
    doubled: bool = False
    is_split_aces: bool = False

    def add(self, card: Tuple[str, str, int]) -> None:
        self.cards.append(card)


def cards_values(cards: List[Tuple[str, str, int]]) -> List[int]:
    return [c[2] for c in cards]


def hand_value(cards: List[Tuple[str, str, int]]) -> Tuple[int, bool]:
    vals = cards_values(cards)
    total = sum(vals)
    aces = sum(1 for v in vals if v == 1)
    is_soft = False
    while aces > 0 and total + 10 <= 21:
        total += 10
        aces -= 1
        is_soft = True
    return total, is_soft


def is_blackjack(cards: List[Tuple[str, str, int]]) -> bool:
    if len(cards) != 2:
        return False
    vals = cards_values(cards)
    return (1 in vals) and (10 in vals)


def is_pair(cards: List[Tuple[str, str, int]]) -> bool:
    if len(cards) != 2:
        return False
    return cards[0][2] == cards[1][2]


def card_str(card: Tuple[str, str, int]) -> str:
    r, s, _ = card
    return f"{r}{s}"


# =========================
# BASIC STRATEGY (S17 + DAS-ish)
# =========================
def basic_strategy(player_cards: List[Tuple[str, str, int]], dealer_upcard: Tuple[str, str, int]) -> str:
    up = dealer_upcard[2] if dealer_upcard[2] != 1 else 1

    # Pairs
    if is_pair(player_cards):
        v = player_cards[0][2]
        if v == 1:
            return "P"  # AA
        if v == 8:
            return "P"  # 88
        if v == 10:
            return "S"  # TT
        if v == 9:
            return "P" if up in [2, 3, 4, 5, 6, 8, 9] else "S"
        if v == 7:
            return "P" if up in [2, 3, 4, 5, 6, 7] else "H"
        if v == 6:
            return "P" if up in [2, 3, 4, 5, 6] else "H"
        if v == 5:
            return "D" if up in [2, 3, 4, 5, 6, 7, 8, 9] else "H"
        if v == 4:
            return "P" if up in [5, 6] else "H"
        if v in [2, 3]:
            return "P" if up in [2, 3, 4, 5, 6, 7] else "H"

    total, soft = hand_value(player_cards)

    # Soft totals
    if soft:
        if total <= 17:
            if total in [13, 14]:
                return "D" if up in [5, 6] else "H"
            if total in [15, 16]:
                return "D" if up in [4, 5, 6] else "H"
            if total == 17:
                return "D" if up in [3, 4, 5, 6] else "H"
        if total == 18:
            if up in [3, 4, 5, 6]:
                return "D"
            if up in [2, 7, 8]:
                return "S"
            return "H"
        return "S"

    # Hard totals
    if total <= 8:
        return "H"
    if total == 9:
        return "D" if up in [3, 4, 5, 6] else "H"
    if total == 10:
        return "D" if up in [2, 3, 4, 5, 6, 7, 8, 9] else "H"
    if total == 11:
        return "D" if up != 1 else "H"
    if total == 12:
        return "S" if up in [4, 5, 6] else "H"
    if total in [13, 14, 15, 16]:
        return "S" if up in [2, 3, 4, 5, 6] else "H"
    return "S"


# =========================
# ENGINE
# =========================
@dataclass
class RoundResult:
    profit: float
    bet: float
    outcome: str
    dealer_total: int
    player_hands: int


class BlackjackEnv:
    def __init__(self, rules: Rules, rng: np.random.Generator):
        self.rules = rules
        self.rng = rng
        self.shoe = Shoe(rules.decks, rng)

    def _dealer_play(self, dealer_cards: List[Tuple[str, str, int]], trace: List[dict]) -> int:
        while True:
            total, soft = hand_value(dealer_cards)
            if total > 21:
                return total
            if total > 17:
                return total
            if total == 17 and soft and not self.rules.dealer_stands_soft_17:
                c = self.shoe.deal()
                dealer_cards.append(c)
                trace.append({"actor": "dealer", "action": "HIT", "card": card_str(c)})
                continue
            if total == 17 and soft and self.rules.dealer_stands_soft_17:
                return total
            if total < 17:
                c = self.shoe.deal()
                dealer_cards.append(c)
                trace.append({"actor": "dealer", "action": "HIT", "card": card_str(c)})
                continue

    def _settle_hand(self, hand: Hand, dealer_total: int, bet: float, dealer_bj: bool) -> Tuple[float, str]:
        total, _ = hand_value(hand.cards)
        if total > 21:
            return -bet, "LOSE"

        player_bj = is_blackjack(hand.cards) and not hand.is_split_aces
        if player_bj and not dealer_bj:
            return bet * self.rules.blackjack_payout, "BJ"
        if dealer_bj and not player_bj:
            return -bet, "LOSE"

        if dealer_total > 21:
            return bet, "WIN"
        if total > dealer_total:
            return bet, "WIN"
        if total < dealer_total:
            return -bet, "LOSE"
        return 0.0, "PUSH"

    def play_round_verbose(self, bet: float) -> Tuple[RoundResult, dict]:
        trace: List[dict] = []

        reshuffle = False
        if self.shoe.needs_reshuffle(self.rules.penetration):
            reshuffle = True
            self.shoe.shuffle()
            trace.append({"actor": "shoe", "action": "SHUFFLE"})

        p1 = self.shoe.deal()
        d1 = self.shoe.deal()
        p2 = self.shoe.deal()
        d2 = self.shoe.deal()

        player = Hand([p1, p2])
        dealer_cards = [d1, d2]
        dealer_up = d1
        dealer_bj = is_blackjack(dealer_cards)

        trace.append({"actor": "shoe", "action": "DEAL", "to": "player", "card": card_str(p1)})
        trace.append({"actor": "shoe", "action": "DEAL", "to": "dealer", "card": card_str(d1)})
        trace.append({"actor": "shoe", "action": "DEAL", "to": "player", "card": card_str(p2)})
        trace.append({"actor": "shoe", "action": "DEAL", "to": "dealer", "card": "🂠"})

        hands: List[Hand] = [player]
        split_count = 0

        i = 0
        while i < len(hands):
            h = hands[i]

            # Split aces: one card only (typical rules)
            if h.is_split_aces and len(h.cards) >= 2:
                i += 1
                continue

            while True:
                total, _ = hand_value(h.cards)
                if total >= 21:
                    break

                action = basic_strategy(h.cards, dealer_up)

                # Split
                if (
                    action == "P"
                    and split_count < self.rules.max_splits
                    and len(h.cards) == 2
                    and is_pair(h.cards)
                ):
                    split_count += 1
                    c0 = h.cards[0]
                    c1 = h.cards[1]
                    trace.append({"actor": "player", "action": "SPLIT"})

                    h.cards = [c0, self.shoe.deal()]
                    trace.append({"actor": "shoe", "action": "DEAL", "to": f"hand_{i+1}", "card": card_str(h.cards[1])})

                    new_hand = Hand([c1, self.shoe.deal()])
                    trace.append({"actor": "shoe", "action": "DEAL", "to": f"hand_{len(hands)+1}", "card": card_str(new_hand.cards[1])})

                    if c0[2] == 1:
                        h.is_split_aces = True
                        new_hand.is_split_aces = True

                    hands.append(new_hand)
                    continue

                # Double
                if action == "D" and len(h.cards) == 2:
                    h.doubled = True
                    trace.append({"actor": "player", "action": "DOUBLE", "hand": i + 1})
                    c = self.shoe.deal()
                    h.add(c)
                    trace.append({"actor": "shoe", "action": "DEAL", "to": f"hand_{i+1}", "card": card_str(c)})
                    break

                # Stand
                if action == "S":
                    trace.append({"actor": "player", "action": "STAND", "hand": i + 1})
                    break

                # Hit
                trace.append({"actor": "player", "action": "HIT", "hand": i + 1})
                c = self.shoe.deal()
                h.add(c)
                trace.append({"actor": "shoe", "action": "DEAL", "to": f"hand_{i+1}", "card": card_str(c)})

            i += 1

        trace.append({"actor": "dealer", "action": "REVEAL", "card": card_str(d2)})
        dealer_total = self._dealer_play(dealer_cards, trace)

        profit_total = 0.0
        outcomes = []
        for h in hands:
            hb = bet * (2.0 if h.doubled else 1.0)
            p, out = self._settle_hand(h, dealer_total, hb, dealer_bj)
            profit_total += p
            outcomes.append(out)

        outcome = "PUSH"
        if "LOSE" in outcomes and "WIN" not in outcomes and "BJ" not in outcomes:
            outcome = "LOSE"
        if "WIN" in outcomes:
            outcome = "WIN"
        if "BJ" in outcomes:
            outcome = "BJ"

        trace.append({"actor": "settle", "action": outcome, "pnl": float(profit_total)})

        rr = RoundResult(
            profit=float(profit_total),
            bet=float(bet),
            outcome=outcome,
            dealer_total=int(dealer_total),
            player_hands=len(hands),
        )

        payload = {
            "dealer_cards_ui": [card_str(d1), card_str(d2)],
            "player_hands_ui": [[card_str(c) for c in h.cards] for h in hands],
            "trace": trace,
            "shoe_remaining": int(self.shoe.remaining()),
            "reshuffle": bool(reshuffle),
        }
        return rr, payload


# =========================
# SURVIVAL ECONOMY
# =========================
class ExperimentOverError(RuntimeError):
    pass


class CreditManager:
    def __init__(self, econ: SurvivalEconomy):
        self.econ = econ
        self.credits = float(econ.initial_credits)

    def step(self, profit: float) -> dict:
        self.credits -= self.econ.burn_per_hand

        if profit > 0:
            self.credits += profit * self.econ.tax_rate_on_positive_profit

        refill = False
        if self.credits <= self.econ.refill_threshold:
            self.credits += self.econ.refill_amount
            refill = True

        if self.credits <= self.econ.death_threshold:
            raise ExperimentOverError("Credits depleted. The experiment ends.")

        return {"credits": self.credits, "refill": refill}


# =========================
# OPTIONAL LOGGING
# =========================
def append_jsonl(log_path: Optional[str], record: dict) -> None:
    if not log_path:
        return
    p = Path(log_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


# =========================
# WINDOWS DESKTOP + TERMINAL CSS
# =========================
def css_windows_desktop_terminal() -> str:
    return """
<style>
html, body, [class*="stApp"]{
  background: #0C0C0C !important;
  color: rgba(255,255,255,0.92) !important;
  font-family: "Segoe UI", system-ui, -apple-system, Arial, sans-serif !important;
}
code, pre, textarea, .stMarkdown, .stText, .stCodeBlock {
  font-family: "Cascadia Mono", "Cascadia Code", ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", monospace !important;
}
.block-container { max-width: 1650px; padding-top: 0.55rem; padding-bottom: 0.9rem; }
#MainMenu, footer { visibility: hidden; }
header[data-testid="stHeader"] { background: transparent !important; }
section[data-testid="stSidebar"] { display:none !important; }
div[data-testid="stToolbar"] { visibility:hidden; height:0; position:fixed; }
div[data-testid="stDecoration"] { visibility:hidden; height:0; position:fixed; }

button, div[role="button"] {
  border-radius: 10px !important;
  border: 1px solid rgba(255,255,255,0.14) !important;
  background: rgba(255,255,255,0.05) !important;
  color: rgba(255,255,255,0.90) !important;
}
button:hover { background: rgba(255,255,255,0.07) !important; }
input, .stNumberInput input {
  border-radius: 10px !important;
  border: 1px solid rgba(255,255,255,0.12) !important;
  background: rgba(255,255,255,0.04) !important;
  color: rgba(255,255,255,0.92) !important;
}
label { color: rgba(255,255,255,0.75) !important; }

/* Windows desktop */
.win-desktop{
  position: relative;
  width: 100%;
  min-height: 88vh;
  border-radius: 18px;
  overflow: hidden;
  background:
    radial-gradient(1200px 800px at 20% 20%, rgba(0,120,212,0.28), transparent 55%),
    radial-gradient(1100px 700px at 80% 30%, rgba(124,255,178,0.14), transparent 60%),
    radial-gradient(900px 900px at 65% 90%, rgba(255,215,100,0.08), transparent 55%),
    linear-gradient(135deg, #0b1220, #06080f);
  border: 1px solid rgba(255,255,255,0.10);
  box-shadow: 0 30px 120px rgba(0,0,0,0.75);
}
.desktop-icons{
  position:absolute;
  left: 18px;
  top: 16px;
  display:flex;
  flex-direction: column;
  gap: 14px;
  z-index: 2;
}
.dicon{
  width: 86px;
  display:flex;
  flex-direction: column;
  align-items:center;
  gap: 6px;
  color: rgba(255,255,255,0.80);
  font-size: 11px;
  user-select:none;
}
.dicon .ico{
  width: 42px; height: 42px;
  border-radius: 12px;
  background: rgba(255,255,255,0.06);
  border: 1px solid rgba(255,255,255,0.10);
  display:flex; align-items:center; justify-content:center;
  font-weight: 900;
}

/* Taskbar */
.taskbar{
  position:absolute;
  left:0; right:0; bottom:0;
  height: 54px;
  background: rgba(20,20,20,0.78);
  backdrop-filter: blur(18px);
  border-top: 1px solid rgba(255,255,255,0.10);
  display:flex;
  align-items:center;
  justify-content:space-between;
  padding: 0 14px;
  z-index: 3;
}
.tb-left, .tb-right{ display:flex; gap:10px; align-items:center; }
.tb-icon{
  width: 34px; height: 34px; border-radius: 10px;
  background: rgba(255,255,255,0.06);
  border: 1px solid rgba(255,255,255,0.10);
  display:flex; align-items:center; justify-content:center;
  color: rgba(255,255,255,0.85);
  font-weight: 900;
  user-select:none;
}
.tb-time{
  color: rgba(255,255,255,0.78);
  font-size: 12px;
  line-height: 1.1;
  text-align: right;
  user-select:none;
}

/* Window */
.win-window{
  position:absolute;
  left: 7%;
  top: 7%;
  width: 86%;
  height: 79%;
  border-radius: 14px;
  overflow: hidden;
  background: rgba(20,20,20,0.60);
  backdrop-filter: blur(18px);
  border: 1px solid rgba(255,255,255,0.12);
  box-shadow: 0 24px 90px rgba(0,0,0,0.75);
  z-index: 5;
}

/* Titlebar */
.win-titlebar{
  height: 44px;
  display:flex;
  align-items:center;
  justify-content:space-between;
  padding: 0 10px;
  background: rgba(30,30,30,0.78);
  border-bottom: 1px solid rgba(255,255,255,0.08);
}
.win-title-left{ display:flex; gap:10px; align-items:center; }
.win-appicon{
  width: 18px; height: 18px; border-radius: 6px;
  background: linear-gradient(135deg, #0078D4, #7FBA00);
  border: 1px solid rgba(255,255,255,0.12);
}
.win-title{
  color: rgba(255,255,255,0.82);
  font-size: 12px;
  font-family: "Segoe UI", system-ui, -apple-system, Arial, sans-serif;
}
.win-controls{ display:flex; gap:6px; align-items:center; }
.win-btn{
  width: 38px; height: 28px; border-radius: 9px;
  background: rgba(255,255,255,0.06);
  border: 1px solid rgba(255,255,255,0.10);
  display:flex; align-items:center; justify-content:center;
  color: rgba(255,255,255,0.78);
  font-size: 12px;
  user-select:none;
}
.win-btn.close{ background: rgba(255, 80, 80, 0.18); }

/* Content area inside window */
.win-content{
  height: calc(100% - 44px);
  padding: 12px;
  overflow: hidden;
}

/* Windows Terminal panel */
.wt {
  height: 100%;
  border-radius: 12px;
  overflow: hidden;
  border: 1px solid rgba(255,255,255,0.12);
  background: rgba(20,20,20,0.55);
  box-shadow: 0 24px 80px rgba(0,0,0,0.65);
  backdrop-filter: blur(18px);
}
.wtbar {
  display:flex; align-items:center; justify-content:space-between;
  padding: 8px 10px;
  background: rgba(30,30,30,0.70);
  border-bottom: 1px solid rgba(255,255,255,0.08);
}
.wt-left { display:flex; align-items:center; gap:10px; }
.wt-app {
  width: 18px; height: 18px; border-radius: 6px;
  background: linear-gradient(135deg, #0078D4, #7FBA00);
  border: 1px solid rgba(255,255,255,0.12);
}
.wt-title {
  font-size: 12px;
  color: rgba(255,255,255,0.78);
  letter-spacing: 0.01em;
}
.wt-winbtns { display:flex; gap:8px; opacity:0.85; }
.wt-winbtn { width: 10px; height: 10px; border-radius: 50%; background: rgba(255,255,255,0.18); }

/* Tabs */
.wttabs{
  display:flex; align-items:center; gap:8px;
  padding: 8px 10px 0 10px;
  background: rgba(30,30,30,0.55);
}
.wttab{
  font-family: "Segoe UI", system-ui, -apple-system, Arial, sans-serif !important;
  font-size: 12px;
  padding: 7px 10px;
  border-radius: 10px 10px 0 0;
  background: rgba(255,255,255,0.06);
  border: 1px solid rgba(255,255,255,0.10);
  border-bottom: none;
  color: rgba(255,255,255,0.82);
}
.wttab.active{
  background: rgba(12,12,12,0.95);
  border-color: rgba(255,255,255,0.14);
  color: rgba(255,255,255,0.92);
}

/* Terminal body */
.wtbody{
  height: calc(100% - 86px);
  background: rgba(12,12,12,0.95);
  padding: 12px 14px 14px 14px;
  overflow:auto;
  font-size: 12px;
  line-height: 1.45;
}
.wtbody::-webkit-scrollbar { width: 10px; }
.wtbody::-webkit-scrollbar-thumb { background: rgba(255,255,255,0.10); border-radius: 10px; }
.wtbody::-webkit-scrollbar-thumb:hover { background: rgba(255,255,255,0.16); }

.wtline { display:flex; gap:10px; align-items:flex-start; margin-bottom: 6px; }
.wtts { color: rgba(255,255,255,0.45); min-width: 56px; font-variant-numeric: tabular-nums; }
.wttag { color: rgba(255,255,255,0.70); min-width: 92px; }
.wtmsg { color: rgba(255,255,255,0.88); }
.ok { color: #7CFFB2; }
.warn { color: #FFD764; }
.bad { color: #FF7C7C; }
.dim { color: rgba(255,255,255,0.58); }

/* Prompt line */
.prompt { margin-top: 10px; display:flex; gap:10px; align-items:center; flex-wrap: wrap; }
.ps-seg { padding: 2px 6px; border-radius: 8px; border: 1px solid rgba(255,255,255,0.12); background: rgba(255,255,255,0.05); }
.ps-a { color: rgba(255,255,255,0.88); }
.ps-b { color: rgba(124,255,178,0.95); }
.ps-c { color: rgba(0,120,212,0.95); }
.ps-d { color: rgba(255,215,100,0.95); }
.cursor {
  width: 10px; height: 16px;
  background: rgba(255,255,255,0.78);
  display:inline-block;
  animation: blink 1.0s step-end infinite;
}
@keyframes blink { 50% { opacity: 0; } }

/* Table panel */
.table-wrap {
  height: 100%;
  border-radius: 12px;
  overflow:hidden;
  border: 1px solid rgba(255,255,255,0.12);
  background: rgba(20,20,20,0.55);
  box-shadow: 0 24px 80px rgba(0,0,0,0.65);
  backdrop-filter: blur(18px);
  padding: 10px;
}
.casino-table {
  height: 100%;
  background: radial-gradient(circle at 50% 25%, #1f7a43, #0d3a1f 70%);
  border-radius: 14px;
  padding: 16px 16px 18px 16px;
  border: 1px solid rgba(255,255,255,0.14);
  box-shadow: 0 16px 40px rgba(0,0,0,0.40);
}
.table-rail {
  border-radius: 14px;
  padding: 12px;
  background: linear-gradient(180deg, rgba(0,0,0,0.20), rgba(255,255,255,0.03));
  border: 1px solid rgba(255,255,255,0.10);
  height: 100%;
}
.label {
  color: rgba(255,255,255,0.86);
  font-size: 12px;
  font-weight: 800;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  margin-bottom: 8px;
}
.cards-row { display:flex; gap: 10px; align-items:center; flex-wrap: wrap; }
.card {
  width: 64px; height: 92px; border-radius: 10px;
  border: 1px solid rgba(0,0,0,0.15);
  background: #fff; padding: 8px;
  box-shadow: 0 2px 10px rgba(0,0,0,0.18);
  display:flex; flex-direction:column; justify-content:space-between;
}
.card.back {
  background: linear-gradient(135deg, #1c2b4a, #3a5a8a);
  border: 1px solid rgba(255,255,255,0.18);
  color: rgba(255,255,255,0.92);
  align-items:center; justify-content:center;
  font-weight:900; font-size: 22px;
}
.corner { font-weight: 900; font-size: 14px; line-height: 1; }
.corner.bottom { text-align: right; }
.suit { font-weight: 900; font-size: 28px; text-align:center; margin-top: -4px; }
.hand-block { margin-top: 12px; }
.hand-title { color: rgba(255,255,255,0.82); font-size: 12px; margin-bottom: 6px; font-weight: 700; }
.chips { display:flex; gap:8px; align-items:center; margin-top: 10px; color: rgba(255,255,255,0.85); font-size: 12px; flex-wrap: wrap; }
.chip {
  width: 18px; height: 18px; border-radius: 50%;
  background: radial-gradient(circle at 30% 30%, rgba(255,255,255,0.55), rgba(255,255,255,0.08));
  border: 1px solid rgba(255,255,255,0.25);
}

/* Minimal top control strip */
.ctrlwrap{
  border-radius: 14px;
  border: 1px solid rgba(255,255,255,0.10);
  background: rgba(255,255,255,0.03);
  padding: 10px 12px;
}
</style>
"""


# =========================
# WINDOWS DESKTOP WRAPPER
# =========================
def windows_shell_frame(inner_html: str, title: str) -> str:
    now = datetime.datetime.now()
    t1 = now.strftime("%H:%M")
    t2 = now.strftime("%d.%m.%Y")

    return f"""
<div class="win-desktop">
  <div class="desktop-icons">
    <div class="dicon"><div class="ico">🗂</div><div>This PC</div></div>
    <div class="dicon"><div class="ico">🧾</div><div>Logs</div></div>
    <div class="dicon"><div class="ico">⚙</div><div>Settings</div></div>
  </div>

  <div class="win-window">
    <div class="win-titlebar">
      <div class="win-title-left">
        <div class="win-appicon"></div>
        <div class="win-title">{title}</div>
      </div>
      <div class="win-controls">
        <div class="win-btn">—</div>
        <div class="win-btn">▢</div>
        <div class="win-btn close">✕</div>
      </div>
    </div>
    <div class="win-content">
      {inner_html}
    </div>
  </div>

  <div class="taskbar">
    <div class="tb-left">
      <div class="tb-icon">⊞</div>
      <div class="tb-icon">🔎</div>
      <div class="tb-icon">🗔</div>
      <div class="tb-icon">🧾</div>
      <div class="tb-icon">🖥</div>
    </div>
    <div class="tb-right">
      <div class="tb-icon">🔊</div>
      <div class="tb-icon">📶</div>
      <div class="tb-time">{t1}<br/>{t2}</div>
    </div>
  </div>
</div>
"""


# =========================
# WINDOWS TERMINAL HTML
# =========================
def term_html(lines: list[dict], title: str, tab_label: str = "PowerShell", cwd: str = r"C:\countess") -> str:
    rows = []
    for x in lines[-80:]:
        lvl = x.get("level", "")
        msg_cls = "wtmsg"
        if lvl == "ok":
            msg_cls += " ok"
        elif lvl == "warn":
            msg_cls += " warn"
        elif lvl == "bad":
            msg_cls += " bad"
        elif lvl == "dim":
            msg_cls += " dim"

        rows.append(
            f"<div class='wtline'>"
            f"<div class='wtts'>{x.get('t','')}</div>"
            f"<div class='wttag'>{x.get('tag','')}</div>"
            f"<div class='{msg_cls}'>{x.get('msg','')}</div>"
            f"</div>"
        )

    body = "".join(rows) if rows else "<div class='wtmsg dim'>—</div>"
    host = title

    return f"""
<div class="wt">
  <div class="wtbar">
    <div class="wt-left">
      <div class="wt-app"></div>
      <div class="wt-title">{PROJECT_NAME} · {ENGINE_TAG} · {SIM_NOTE}</div>
    </div>
    <div class="wt-winbtns">
      <div class="wt-winbtn"></div><div class="wt-winbtn"></div><div class="wt-winbtn"></div>
    </div>
  </div>

  <div class="wttabs">
    <div class="wttab active">{tab_label}</div>
    <div class="wttab">cmd.exe</div>
    <div class="wttab">ssh</div>
  </div>

  <div class="wtbody">
    {body}
    <div class="prompt">
      <span class="ps-seg ps-a">PS</span>
      <span class="ps-seg ps-b">{host}</span>
      <span class="ps-seg ps-c">{cwd}</span>
      <span class="ps-seg ps-d">main</span>
      <span class="ps-a">&gt;</span>
      <span class="cursor"></span>
    </div>
  </div>
</div>
"""


def term_log(state: dict, tag: str, msg: str, level: str = "") -> None:
    state["term"].append({"t": time.strftime("%H:%M:%S"), "tag": tag, "msg": msg, "level": level})
    state["term"] = state["term"][-600:]


# =========================
# TABLE HTML
# =========================
def card_html(card: str, hidden: bool = False) -> str:
    if hidden:
        return '<div class="card back">🂠</div>'
    suit = card[-1]
    red = suit in ["♦", "♥"]
    color = "#d63333" if red else "#111"
    return f"""
<div class="card">
  <div class="corner" style="color:{color};">{card}</div>
  <div class="suit" style="color:{color};">{suit}</div>
  <div class="corner bottom" style="color:{color};">{card}</div>
</div>
"""


def cards_row_html(cards: List[str], hide_hole_second: bool = False) -> str:
    items = []
    for i, c in enumerate(cards):
        items.append(card_html(c, hidden=(hide_hole_second and i == 1)))
    return f'<div class="cards-row">{"".join(items)}</div>'


def table_html(
    dealer_cards: List[str],
    player_hands: List[List[str]],
    hide_dealer_hole: bool,
    bet: float,
    outcome: str,
    pnl: float,
) -> str:
    hands_html = ""
    for idx, hand in enumerate(player_hands):
        hands_html += f"""
        <div class="hand-block">
          <div class="hand-title">PLAYER HAND {idx+1}</div>
          {cards_row_html(hand, hide_hole_second=False)}
        </div>
        """

    pnl_color = "rgba(255,255,255,0.85)"
    if pnl > 0:
        pnl_color = "#7CFFB2"
    elif pnl < 0:
        pnl_color = "#FF7C7C"

    return f"""
<div class="table-wrap">
  <div class="casino-table">
    <div class="table-rail">
      <div class="label">DEALER</div>
      {cards_row_html(dealer_cards, hide_hole_second=hide_dealer_hole)}
      {hands_html}
      <div class="chips">
        <div class="chip"></div><div class="chip"></div><div class="chip"></div>
        <div style="margin-left:6px;">Bet: <b>${bet:.2f}</b></div>
        <div style="margin-left:16px;">Outcome: <b>{outcome}</b></div>
        <div style="margin-left:16px;color:{pnl_color};">PnL: <b>{pnl:+.2f}</b></div>
      </div>
    </div>
  </div>
</div>
"""


# =========================
# STATE / SIM
# =========================
def init_state(cfg: RunConfig, rules: Rules, econ: SurvivalEconomy) -> dict:
    rng = np.random.default_rng(cfg.seed)
    env = BlackjackEnv(rules, rng)
    credits = CreditManager(econ)

    state = {
        "rng": rng,
        "cfg": cfg,
        "rules": rules,
        "econ": econ,
        "env": env,
        "credits": credits,
        "bankroll": float(cfg.initial_bankroll),
        "net_profit": 0.0,
        "hand": 0,
        "peak_bankroll": float(cfg.initial_bankroll),
        "max_drawdown": 0.0,
        "wins": 0,
        "pushes": 0,
        "losses": 0,
        "bjs": 0,
        "status": "ALIVE",
        "events": [],
        "last_rr": None,
        "last_payload": None,
        "_cinematic_pause_s": 0.0,
        "term": [],
        "playback": {
            "active": False,
            "trace": [],
            "trace_i": 0,
            "dealer_cards": [],
            "dealer_visible": [],
            "player_hands": [[]],
            "hide_hole": True,
            "outcome": "—",
            "pnl": 0.0,
            "bet": 0.0,
            "reveal_at_end": True,
        },
        "ui": {
            "win_host": "DESKTOP-7K3M4",
            "cwd": r"C:\countess",
            "tab": "PowerShell",
            "fps": int(rng.choice([30, 60])),
            "ping": int(rng.integers(18, 70)),
            "viewers": int(rng.integers(80, 1100)),
            "viewers_target": int(rng.integers(120, 1800)),
            "started_at": time.time(),
        },
    }

    term_log(state, "BOOT", f"{ENGINE_TAG} starting…", "dim")
    term_log(state, "CFG", f"rules=S17,DAS decks={rules.decks} pen={rules.penetration:.2f}", "dim")
    term_log(state, "ECON", f"credits=${credits.credits:.2f} burn/hand=${econ.burn_per_hand:.4f} tax={econ.tax_rate_on_positive_profit:.2f}", "dim")
    term_log(state, "NOTE", TAGLINE, "dim")
    return state


def update_drawdown_and_counters(state: dict, outcome: str):
    state["peak_bankroll"] = max(state["peak_bankroll"], state["bankroll"])
    dd = state["peak_bankroll"] - state["bankroll"]
    state["max_drawdown"] = max(state["max_drawdown"], dd)

    if outcome == "WIN":
        state["wins"] += 1
    elif outcome == "PUSH":
        state["pushes"] += 1
    elif outcome == "LOSE":
        state["losses"] += 1
    elif outcome == "BJ":
        state["bjs"] += 1


def evolve_fake_net(state: dict, intensity: float = 1.0):
    ui = state["ui"]
    v = float(ui["viewers"])
    target = float(ui["viewers_target"])
    v += (target - v) * 0.025 * intensity
    v += np.random.normal(0, 3.0 * intensity)
    v = max(12.0, min(9999.0, v))
    ui["viewers"] = int(v)
    if np.random.random() < 0.03 * intensity:
        ui["viewers_target"] = int(max(20.0, min(6000.0, target + np.random.normal(0, 70.0))))

    base = float(ui["ping"])
    spike = np.random.uniform(20, 140) if np.random.random() < 0.02 * intensity else 0.0
    base = max(16.0, min(120.0, base + np.random.normal(0, 1.1) + 0.2 * intensity))
    ui["ping"] = int(max(12.0, min(240.0, base + spike)))


def compute_one_hand(state: dict, log_path: Optional[str]) -> None:
    cfg: RunConfig = state["cfg"]
    env: BlackjackEnv = state["env"]
    credits: CreditManager = state["credits"]

    if state["status"] == "DEAD" or state["hand"] >= cfg.hands_cap:
        return

    if state["bankroll"] <= 0:
        state["hand"] += 1
        term_log(state, "BANKROLL", "0.00 — cannot bet.", "bad")
        return

    bet = float(cfg.base_bet)
    rr, payload = env.play_round_verbose(bet=bet)

    state["bankroll"] += rr.profit
    state["net_profit"] += rr.profit
    state["hand"] += 1
    update_drawdown_and_counters(state, rr.outcome)

    refill = False
    try:
        cstat = credits.step(rr.profit)
        refill = bool(cstat["refill"])
        state["status"] = "ALIVE"
    except ExperimentOverError:
        state["status"] = "DEAD"

    state["last_rr"] = rr
    state["last_payload"] = payload

    rec = {
        "hand": state["hand"],
        "bankroll": state["bankroll"],
        "credits": float(credits.credits),
        "net_profit": state["net_profit"],
        "profit": rr.profit,
        "bet": rr.bet,
        "outcome": rr.outcome,
        "refill": refill,
        "status": state["status"],
        "shoe_remaining": payload.get("shoe_remaining"),
    }
    state["events"].append(rec)
    append_jsonl(log_path, rec)

    lvl = "ok" if rr.profit > 0 else "bad" if rr.profit < 0 else "dim"
    term_log(
        state,
        "HAND",
        f"#{state['hand']:>6} outcome={rr.outcome:<4} pnl={rr.profit:+.2f} bankroll={state['bankroll']:.2f}",
        lvl,
    )

    if payload.get("reshuffle"):
        term_log(state, "SHOE", f"reshuffle · remaining={payload.get('shoe_remaining')}", "warn")

    clvl = "warn" if float(credits.credits) < 8 else "dim"
    term_log(state, "CREDITS", f"{float(credits.credits):.2f} remaining", clvl)

    if refill:
        term_log(state, "REFILL", f"+{state['econ'].refill_amount:.2f} (auto top-up)", "warn")
    if state["status"] == "DEAD":
        term_log(state, "FATAL", "credits depleted — shutdown.", "bad")

    if refill or float(credits.credits) < 8:
        state["_cinematic_pause_s"] = 0.85
    elif rr.outcome == "BJ" or abs(rr.profit) >= 2:
        state["_cinematic_pause_s"] = 0.35
    else:
        state["_cinematic_pause_s"] = 0.0


def start_playback(state: dict, rr: RoundResult, payload: dict, reveal_at_end: bool = True):
    pb = state["playback"]
    pb["active"] = True
    pb["trace"] = payload["trace"]
    pb["trace_i"] = 0
    pb["dealer_cards"] = payload["dealer_cards_ui"][:]
    pb["dealer_visible"] = []
    pb["player_hands"] = [[]]
    pb["hide_hole"] = True
    pb["outcome"] = "—"
    pb["pnl"] = 0.0
    pb["bet"] = float(rr.bet)
    pb["reveal_at_end"] = bool(reveal_at_end)


def apply_trace_step(state: dict):
    pb = state["playback"]
    if not pb["active"]:
        return
    trace = pb["trace"]
    i = pb["trace_i"]
    if i >= len(trace):
        pb["active"] = False
        return

    ev = trace[i]
    pb["trace_i"] += 1

    actor = ev.get("actor")
    action = ev.get("action")

    if actor == "shoe" and action == "DEAL":
        to = ev.get("to", "")
        card = ev.get("card", "🂠")

        if to == "dealer":
            if card == "🂠":
                if len(pb["dealer_visible"]) == 1:
                    pb["dealer_visible"].append("🂠")
                elif len(pb["dealer_visible"]) == 0:
                    pb["dealer_visible"].append("🂠")
            else:
                pb["dealer_visible"].append(card)

        elif to == "player":
            pb["player_hands"][0].append(card)

        else:
            if isinstance(to, str) and to.startswith("hand_"):
                idx = int(to.split("_")[1]) - 1
                while len(pb["player_hands"]) <= idx:
                    pb["player_hands"].append([])
                pb["player_hands"][idx].append(card)

    elif actor == "player" and action == "SPLIT":
        if len(pb["player_hands"]) < 2:
            first = pb["player_hands"][0][0] if pb["player_hands"][0] else ""
            second = pb["player_hands"][0][1] if len(pb["player_hands"][0]) > 1 else ""
            pb["player_hands"][0] = [first] if first else []
            pb["player_hands"].append([second] if second else [])

    elif actor == "dealer" and action == "REVEAL":
        hole = ev.get("card", "")
        if len(pb["dealer_visible"]) == 0:
            pb["dealer_visible"] = [pb["dealer_cards"][0], hole]
        elif len(pb["dealer_visible"]) == 1:
            pb["dealer_visible"].append(hole)
        else:
            pb["dealer_visible"][1] = hole
        pb["hide_hole"] = False

    elif actor == "settle":
        pb["outcome"] = action
        pb["pnl"] = float(ev.get("pnl", 0.0))
        if pb.get("reveal_at_end", True):
            if len(pb["dealer_visible"]) >= 2 and pb["dealer_visible"][1] == "🂠":
                pb["dealer_visible"][1] = pb["dealer_cards"][1]
            pb["hide_hole"] = False


def render_table_html(state: dict, reveal: bool) -> str:
    pb = state["playback"]
    if pb["active"]:
        dealer_cards = pb["dealer_visible"][:] if pb["dealer_visible"] else []
        if not dealer_cards and pb["dealer_cards"]:
            dealer_cards = [pb["dealer_cards"][0]]
        if len(dealer_cards) == 1:
            dealer_cards = [dealer_cards[0], "🂠"]
        player_hands = pb["player_hands"][:] if pb["player_hands"] else [[]]
        hide_hole = (pb["hide_hole"] and not reveal)
        return table_html(dealer_cards, player_hands, hide_hole, pb["bet"], pb["outcome"], pb["pnl"])

    rr: Optional[RoundResult] = state.get("last_rr")
    payload = state.get("last_payload")
    if not rr or not payload:
        return """
<div class="table-wrap">
  <div class="wtbody"><span class="dim">No hand yet. Press DEAL or enable AUTOPLAY.</span></div>
</div>
"""
    dealer_cards = payload["dealer_cards_ui"]
    player_hands = payload["player_hands_ui"]
    hide_hole = not reveal
    return table_html(dealer_cards, player_hands, hide_hole, rr.bet, rr.outcome, rr.profit)


def microhud_text(state: dict) -> str:
    ui = state["ui"]
    uptime = int(time.time() - ui["started_at"])
    hh = uptime // 3600
    mm = (uptime % 3600) // 60
    ss = uptime % 60

    credits = float(state["credits"].credits)
    status = state["status"]
    shoe = state["last_payload"]["shoe_remaining"] if state.get("last_payload") else None
    shoe_txt = f"{shoe} cards" if shoe is not None else "—"

    return (
        f"LIVE {ui['viewers']:,} viewers · ping {ui['ping']}ms · {ui['fps']}fps · uptime {hh:02d}:{mm:02d}:{ss:02d} "
        f"| bankroll ${state['bankroll']:.2f} · hands {state['hand']:,} · maxDD ${state['max_drawdown']:.2f} "
        f"| credits {credits:.2f} · shoe {shoe_txt} · {status}"
    )


# =========================
# MAIN
# =========================
def main():
    st.set_page_config(page_title=f"{PROJECT_NAME} — Windows Desktop", layout="wide")
    st.markdown(css_windows_desktop_terminal(), unsafe_allow_html=True)

    # UI prefs
    if "autoplay" not in st.session_state:
        st.session_state.autoplay = False
    if "animate" not in st.session_state:
        st.session_state.animate = True
    if "reveal" not in st.session_state:
        st.session_state.reveal = False
    if "steps_per_sec" not in st.session_state:
        st.session_state.steps_per_sec = 11.0
    if "hands_per_sec" not in st.session_state:
        st.session_state.hands_per_sec = 3.0
    if "batch" not in st.session_state:
        st.session_state.batch = 60
    if "log_path" not in st.session_state:
        st.session_state.log_path = ""

    if "state" not in st.session_state:
        st.session_state.state = init_state(RunConfig(), Rules(), SurvivalEconomy())

    state = st.session_state.state

    # jitter always
    evolve_fake_net(state, intensity=0.7)

    # controls strip
    st.markdown("<div class='ctrlwrap'>", unsafe_allow_html=True)
    c1, c2, c3, c4, c5, c6, c7 = st.columns([1.1, 1.0, 1.0, 1.0, 1.0, 1.2, 2.4])
    with c1:
        st.session_state.autoplay = st.toggle("Autoplay", value=st.session_state.autoplay)
    with c2:
        st.session_state.animate = st.toggle("Animate", value=st.session_state.animate)
    with c3:
        st.session_state.reveal = st.toggle("Reveal hole", value=st.session_state.reveal)
    with c4:
        st.session_state.batch = int(st.number_input("Batch", 1, 5000, int(st.session_state.batch), 10))
    with c5:
        deal = st.button("DEAL 1", use_container_width=True, type="primary")
    with c6:
        reset = st.button("RESET RUN", use_container_width=True)
    with c7:
        st.caption(microhud_text(state))
    st.markdown("</div>", unsafe_allow_html=True)

    # reset
    if reset:
        st.session_state.state = init_state(RunConfig(), Rules(), SurvivalEconomy())
        st.session_state.autoplay = False
        st.rerun()

    # deal one
    if deal and state["status"] != "DEAD":
        lp = st.session_state.log_path.strip() or None
        compute_one_hand(state, lp)
        evolve_fake_net(state, intensity=1.2)
        if st.session_state.animate and state["last_rr"] and state["last_payload"]:
            start_playback(state, state["last_rr"], state["last_payload"], reveal_at_end=True)
        st.rerun()

    # inner HTML split layout
    host = state["ui"]["win_host"]
    tab = state["ui"]["tab"]
    cwd = state["ui"]["cwd"]

    term_panel = term_html(state["term"], title=host, tab_label=tab, cwd=cwd)
    table_panel = render_table_html(state, reveal=st.session_state.reveal)

    inner = f"""
<div style="display:grid; grid-template-columns: 1.0fr 1.25fr; gap: 12px; height: 100%;">
  <div style="min-width:0; height:100%; overflow:hidden;">{term_panel}</div>
  <div style="min-width:0; height:100%; overflow:hidden;">{table_panel}</div>
</div>
"""

    st.markdown(windows_shell_frame(inner, title=f"Windows Terminal — {PROJECT_NAME}"), unsafe_allow_html=True)

    # animation tick
    if state["playback"]["active"]:
        apply_trace_step(state)
        evolve_fake_net(state, intensity=0.9)
        time.sleep(1.0 / max(1.0, float(st.session_state.steps_per_sec)))
        st.rerun()

    # autoplay tick
    if st.session_state.autoplay and not state["playback"]["active"] and state["status"] != "DEAD":
        lp = st.session_state.log_path.strip() or None
        n = int(st.session_state.batch)

        intensity = min(2.0, 0.85 + n / 150.0)
        for _ in range(n):
            compute_one_hand(state, lp)
            evolve_fake_net(state, intensity=intensity)
            if state["status"] == "DEAD":
                break

        if st.session_state.animate and state["last_rr"] and state["last_payload"]:
            start_playback(state, state["last_rr"], state["last_payload"], reveal_at_end=True)

        pause = float(state.get("_cinematic_pause_s", 0.0))
        if pause > 0:
            time.sleep(pause)

        time.sleep(1.0 / max(0.5, float(st.session_state.hands_per_sec)))
        st.rerun()


if __name__ == "__main__":
    main()
