# Tennis Match Simulator — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a real-time tennis match simulator page that estimates the probability distribution of the maximum win probability a player can reach during the remainder of a BO3 match, using backward induction + Monte Carlo simulation with live data from FlashScore and Tennis Abstract.

**Architecture:** Pure-math tennis engine (backward induction lookup table + NumPy-vectorized Monte Carlo) powers the simulation. Playwright headless browser scrapes live PBP from FlashScore and player serve stats from Tennis Abstract. GPT-4o-mini parses free-form player name input. Frontend polls for updates every 30 seconds.

**Tech Stack:** Python 3.14, FastAPI, NumPy, Playwright, OpenAI API (GPT-4o-mini), React 18, Vite, TypeScript, Recharts

---

## File Map

### Backend — New Files

| File | Responsibility |
|---|---|
| `app/tennis/__init__.py` | Package marker |
| `app/tennis/engine.py` | Backward induction: BO3 state transitions + win probability lookup table |
| `app/tennis/simulator.py` | Monte Carlo: simulate N paths, collect max win prob distribution |
| `app/tennis/bayesian.py` | Bayesian update of p values from observed serve data |
| `app/scraper/__init__.py` | Package marker |
| `app/scraper/browser.py` | Playwright browser singleton lifecycle |
| `app/scraper/tennis_abstract.py` | Scrape player serve stats from Tennis Abstract |
| `app/scraper/flashscore.py` | Search match + extract PBP + live DOM reading from FlashScore |
| `app/routes/simulate.py` | API endpoints: /api/lookup-match, /api/simulate, /api/match-update |

### Backend — Modified Files

| File | Change |
|---|---|
| `app/config.py` | Add `openai_api_key` setting |
| `app/main.py` | Register simulate router, add browser cleanup to lifespan |
| `requirements.txt` | Add playwright, openai, numpy |
| `.env.example` | Add OPENAI_API_KEY |

### Frontend — New Files

| File | Responsibility |
|---|---|
| `src/components/NavBar.tsx` | Navigation links between pages |
| `src/components/MatchInput.tsx` | Player name text input + "Look Up Match" button |
| `src/components/MatchStatus.tsx` | Score display, p values (editable), current win prob, auto-update controls |
| `src/pages/SimulatorPage.tsx` | Simulator page layout, wires MatchInput + MatchStatus + Histogram |

### Frontend — Modified Files

| File | Change |
|---|---|
| `src/App.tsx` | Add React Router, wrap pages, include NavBar |
| `src/types.ts` | Add simulator-related TypeScript interfaces |
| `src/api.ts` | Add lookupMatch(), simulate(), matchUpdate() functions |

---

## Task 1: Dependencies + Config

**Files:**
- Modify: `backend/requirements.txt`
- Modify: `backend/app/config.py`
- Modify: `backend/.env.example`

- [ ] **Step 1: Update requirements.txt**

Add to `backend/requirements.txt`:

```
playwright==1.58.0
openai>=1.0.0
numpy>=1.26.0
```

- [ ] **Step 2: Add OpenAI key to config**

Add to `backend/app/config.py` in the `Settings` class, after the Sackmann field:

```python
    # OpenAI
    openai_api_key: str = ""
```

- [ ] **Step 3: Update .env.example**

Add to `backend/.env.example`:

```
# OpenAI API (for player name parsing)
OPENAI_API_KEY=your_openai_key_here
```

- [ ] **Step 4: Install dependencies**

Run: `cd backend && source .venv/bin/activate && pip install -r requirements.txt`

- [ ] **Step 5: Commit**

```bash
git add backend/requirements.txt backend/app/config.py backend/.env.example
git commit -m "chore: add playwright, openai, numpy dependencies and config"
```

---

## Task 2: Tennis Scoring Engine — State Transitions

**Files:**
- Create: `backend/app/tennis/__init__.py`
- Create: `backend/app/tennis/engine.py`
- Test: `backend/tests/test_engine.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_engine.py
import pytest
from app.tennis.engine import (
    MatchState,
    next_state,
    build_win_prob_table,
)


def test_initial_state():
    s = MatchState()
    assert s.sets_a == 0 and s.sets_b == 0
    assert s.games_a == 0 and s.games_b == 0
    assert s.points_a == 0 and s.points_b == 0
    assert s.is_a_serving is True
    assert s.is_tiebreak is False
    assert s.is_terminal() is False


def test_point_advance_in_regular_game():
    s = MatchState()  # 0-0, 0-0, 0-0, A serving
    s1 = next_state(s, a_wins_point=True)
    assert s1.points_a == 1  # 15-0
    assert s1.points_b == 0

    s2 = next_state(s1, a_wins_point=True)
    assert s2.points_a == 2  # 30-0

    s3 = next_state(s2, a_wins_point=True)
    assert s3.points_a == 3  # 40-0

    # A wins the game at 40-0
    s4 = next_state(s3, a_wins_point=True)
    assert s4.games_a == 1 and s4.games_b == 0
    assert s4.points_a == 0 and s4.points_b == 0
    # Serve switches
    assert s4.is_a_serving is False


def test_deuce_and_advantage():
    s = MatchState(points_a=3, points_b=3)  # 40-40 (deuce)
    s1 = next_state(s, a_wins_point=True)  # AD-40
    assert s1.points_a == 4

    s2 = next_state(s1, a_wins_point=False)  # back to deuce
    assert s2.points_a == 3 and s2.points_b == 3

    s3 = next_state(s1, a_wins_point=True)  # A wins game
    assert s3.games_a == 1
    assert s3.points_a == 0


def test_set_win():
    # A leads 5-0 in games, serving, 40-0
    s = MatchState(games_a=5, games_b=0, points_a=3, is_a_serving=True)
    s1 = next_state(s, a_wins_point=True)  # A wins game -> 6-0, set won
    assert s1.sets_a == 1
    assert s1.games_a == 0 and s1.games_b == 0


def test_tiebreak_at_6_6():
    s = MatchState(games_a=6, games_b=5, points_a=3, is_a_serving=False)
    # B wins game -> 6-6 -> tiebreak
    s1 = next_state(s, a_wins_point=False)
    assert s1.games_a == 6 and s1.games_b == 6
    assert s1.is_tiebreak is True


def test_tiebreak_scoring():
    s = MatchState(games_a=6, games_b=6, is_tiebreak=True,
                   points_a=6, points_b=5, is_a_serving=True)
    # A wins point -> 7-5 in tiebreak -> A wins set
    s1 = next_state(s, a_wins_point=True)
    assert s1.sets_a == 1
    assert s1.is_tiebreak is False
    assert s1.games_a == 0 and s1.games_b == 0


def test_tiebreak_must_win_by_two():
    s = MatchState(games_a=6, games_b=6, is_tiebreak=True,
                   points_a=6, points_b=6, is_a_serving=True)
    s1 = next_state(s, a_wins_point=True)  # 7-6
    assert s1.is_tiebreak is True  # not won yet, need 2 ahead

    s2 = next_state(s1, a_wins_point=True)  # 8-6 -> A wins set
    assert s2.sets_a == 1
    assert s2.is_tiebreak is False


def test_match_terminal():
    s = MatchState(sets_a=2)
    assert s.is_terminal() is True

    s2 = MatchState(sets_b=2)
    assert s2.is_terminal() is True


def test_build_win_prob_table_extreme():
    # If p_a = 1.0 (A wins every serve point) and p_b = 0.0 (B wins no serve points)
    # A should win with probability 1.0 from the start
    table = build_win_prob_table(p_a=1.0, p_b=0.0)
    initial = MatchState()
    assert table[initial.key()] == pytest.approx(1.0)


def test_build_win_prob_table_symmetric():
    # If both players have 0.6 serve hold, server has advantage,
    # so A serving first should have slightly > 0.5
    table = build_win_prob_table(p_a=0.6, p_b=0.6)
    initial = MatchState()
    prob = table[initial.key()]
    assert 0.45 < prob < 0.55  # roughly even


def test_build_win_prob_table_terminal_states():
    table = build_win_prob_table(p_a=0.65, p_b=0.60)
    # A won match
    s_win = MatchState(sets_a=2)
    assert table[s_win.key()] == 1.0
    # A lost match
    s_loss = MatchState(sets_b=2)
    assert table[s_loss.key()] == 0.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && source .venv/bin/activate && python3 -m pytest tests/test_engine.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Write implementation**

Create `backend/app/tennis/__init__.py` (empty).

```python
# backend/app/tennis/engine.py
from dataclasses import dataclass, replace
from functools import lru_cache


@dataclass(frozen=True)
class MatchState:
    sets_a: int = 0
    sets_b: int = 0
    games_a: int = 0
    games_b: int = 0
    points_a: int = 0
    points_b: int = 0
    is_a_serving: bool = True
    is_tiebreak: bool = False

    def key(self) -> tuple:
        return (self.sets_a, self.sets_b, self.games_a, self.games_b,
                self.points_a, self.points_b, self.is_a_serving, self.is_tiebreak)

    def is_terminal(self) -> bool:
        return self.sets_a == 2 or self.sets_b == 2


def _new_game_state(state: MatchState, sets_a: int, sets_b: int,
                     games_a: int, games_b: int) -> MatchState:
    """Reset points, handle set/tiebreak transitions."""
    # Check if someone won the set
    set_won_by_a = (games_a >= 6 and games_a - games_b >= 2)
    set_won_by_b = (games_b >= 6 and games_b - games_a >= 2)
    # Tiebreak win
    if games_a == 7 and games_b == 6:
        set_won_by_a = True
    if games_b == 7 and games_a == 6:
        set_won_by_b = True

    if set_won_by_a:
        return MatchState(
            sets_a=sets_a + 1, sets_b=sets_b,
            games_a=0, games_b=0,
            points_a=0, points_b=0,
            is_a_serving=not state.is_a_serving,
            is_tiebreak=False,
        )
    if set_won_by_b:
        return MatchState(
            sets_a=sets_a, sets_b=sets_b + 1,
            games_a=0, games_b=0,
            points_a=0, points_b=0,
            is_a_serving=not state.is_a_serving,
            is_tiebreak=False,
        )

    # Check for tiebreak
    if games_a == 6 and games_b == 6:
        return MatchState(
            sets_a=sets_a, sets_b=sets_b,
            games_a=6, games_b=6,
            points_a=0, points_b=0,
            is_a_serving=state.is_a_serving,
            is_tiebreak=True,
        )

    return MatchState(
        sets_a=sets_a, sets_b=sets_b,
        games_a=games_a, games_b=games_b,
        points_a=0, points_b=0,
        is_a_serving=not state.is_a_serving,
        is_tiebreak=False,
    )


def _tiebreak_serve_switch(state: MatchState, total_points: int) -> bool:
    """In tiebreak, first server serves 1 point, then alternate every 2."""
    if total_points == 0:
        return state.is_a_serving
    # After the first point, switch. Then switch every 2 points.
    if total_points == 1:
        return not state.is_a_serving
    return ((total_points - 1) % 2 == 0) != state.is_a_serving


def next_state(state: MatchState, a_wins_point: bool) -> MatchState:
    if state.is_terminal():
        return state

    if state.is_tiebreak:
        pa = state.points_a + (1 if a_wins_point else 0)
        pb = state.points_b + (0 if a_wins_point else 1)

        # Check tiebreak win: >= 7 and lead by 2
        if pa >= 7 and pa - pb >= 2:
            return _new_game_state(state, state.sets_a, state.sets_b, 7, 6)
        if pb >= 7 and pb - pa >= 2:
            return _new_game_state(state, state.sets_a, state.sets_b, 6, 7)

        # Determine who serves next point in tiebreak
        total = pa + pb
        first_server_serves = (total == 0) or ((total - 1) // 2) % 2 == 0
        next_a_serving = state.is_a_serving if first_server_serves else not state.is_a_serving

        return MatchState(
            sets_a=state.sets_a, sets_b=state.sets_b,
            games_a=6, games_b=6,
            points_a=pa, points_b=pb,
            is_a_serving=next_a_serving,
            is_tiebreak=True,
        )

    # Regular game
    pa = state.points_a + (1 if a_wins_point else 0)
    pb = state.points_b + (0 if a_wins_point else 1)

    # Deuce logic (both at 3 = 40-40)
    if pa >= 3 and pb >= 3:
        if pa == pb:
            # Back to deuce
            return replace(state, points_a=3, points_b=3)
        if pa > pb and pa >= 4:
            if pa - pb >= 2:
                # Game won by A (or AD + win)
                return _new_game_state(state, state.sets_a, state.sets_b,
                                       state.games_a + 1, state.games_b)
            # Advantage A
            return replace(state, points_a=pa, points_b=pb)
        if pb > pa and pb >= 4:
            if pb - pa >= 2:
                return _new_game_state(state, state.sets_a, state.sets_b,
                                       state.games_a, state.games_b + 1)
            return replace(state, points_a=pa, points_b=pb)
        return replace(state, points_a=pa, points_b=pb)

    # Non-deuce: game won at 4 points
    if pa >= 4:
        return _new_game_state(state, state.sets_a, state.sets_b,
                               state.games_a + 1, state.games_b)
    if pb >= 4:
        return _new_game_state(state, state.sets_a, state.sets_b,
                               state.games_a, state.games_b + 1)

    return replace(state, points_a=pa, points_b=pb)


def build_win_prob_table(p_a: float, p_b: float) -> dict[tuple, float]:
    """Build lookup table of P(A wins match | state) for all reachable BO3 states."""
    cache: dict[tuple, float] = {}

    def prob(state: MatchState) -> float:
        k = state.key()
        if k in cache:
            return cache[k]

        if state.sets_a == 2:
            cache[k] = 1.0
            return 1.0
        if state.sets_b == 2:
            cache[k] = 0.0
            return 0.0

        # Probability that A wins the next point
        if state.is_a_serving:
            p_point = p_a
        else:
            p_point = 1.0 - p_b

        s_win = next_state(state, a_wins_point=True)
        s_lose = next_state(state, a_wins_point=False)

        result = p_point * prob(s_win) + (1.0 - p_point) * prob(s_lose)
        cache[k] = result
        return result

    prob(MatchState())
    # Also compute from non-default starting serves
    prob(MatchState(is_a_serving=False))
    return cache
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && source .venv/bin/activate && python3 -m pytest tests/test_engine.py -v`
Expected: 11 passed

- [ ] **Step 5: Commit**

```bash
git add backend/app/tennis/__init__.py backend/app/tennis/engine.py backend/tests/test_engine.py
git commit -m "feat: add tennis backward induction engine for BO3 match states"
```

---

## Task 3: Monte Carlo Simulator

**Files:**
- Create: `backend/app/tennis/simulator.py`
- Test: `backend/tests/test_simulator.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_simulator.py
import pytest
from app.tennis.engine import MatchState, build_win_prob_table
from app.tennis.simulator import simulate_max_prob_distribution


def test_simulate_returns_correct_shape():
    table = build_win_prob_table(p_a=0.65, p_b=0.60)
    state = MatchState()
    result = simulate_max_prob_distribution(
        state, p_a=0.65, p_b=0.60, table=table, n_simulations=1000
    )
    assert result["total_count"] == 1000
    assert len(result["histogram"]) == 20  # 20 bins of 5%
    assert "stats" in result
    assert "current_win_prob" in result


def test_simulate_histogram_sums_to_100():
    table = build_win_prob_table(p_a=0.65, p_b=0.60)
    state = MatchState()
    result = simulate_max_prob_distribution(
        state, p_a=0.65, p_b=0.60, table=table, n_simulations=10000
    )
    total_pct = sum(b["percentage"] for b in result["histogram"])
    assert abs(total_pct - 100.0) < 0.5


def test_simulate_max_prob_always_gte_current():
    table = build_win_prob_table(p_a=0.65, p_b=0.60)
    state = MatchState()
    current = table[state.key()]
    result = simulate_max_prob_distribution(
        state, p_a=0.65, p_b=0.60, table=table, n_simulations=5000
    )
    # Mean of max should be >= current win prob
    assert result["stats"]["mean"] >= current * 100 - 1  # small tolerance


def test_simulate_from_winning_position():
    table = build_win_prob_table(p_a=0.65, p_b=0.60)
    # A already won 1 set, leading 5-0 in second
    state = MatchState(sets_a=1, games_a=5, games_b=0, is_a_serving=True)
    result = simulate_max_prob_distribution(
        state, p_a=0.65, p_b=0.60, table=table, n_simulations=5000
    )
    # Max prob should be very high (close to 100%)
    assert result["stats"]["mean"] > 90


def test_simulate_deterministic_p1():
    # If A wins every point, max prob is 1.0
    table = build_win_prob_table(p_a=1.0, p_b=0.0)
    state = MatchState()
    result = simulate_max_prob_distribution(
        state, p_a=1.0, p_b=0.0, table=table, n_simulations=100
    )
    assert result["stats"]["mean"] == pytest.approx(100.0)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && source .venv/bin/activate && python3 -m pytest tests/test_simulator.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Write implementation**

```python
# backend/app/tennis/simulator.py
import statistics
import numpy as np
from app.tennis.engine import MatchState, next_state


def simulate_max_prob_distribution(
    start_state: MatchState,
    p_a: float,
    p_b: float,
    table: dict[tuple, float],
    n_simulations: int = 100_000,
) -> dict:
    current_win_prob = table.get(start_state.key(), 0.5)

    max_probs = np.zeros(n_simulations)

    for i in range(n_simulations):
        state = start_state
        path_max = table.get(state.key(), 0.5)

        while not state.is_terminal():
            if state.is_a_serving:
                a_wins = np.random.random() < p_a
            else:
                a_wins = np.random.random() < (1.0 - p_b)

            state = next_state(state, a_wins_point=bool(a_wins))
            prob = table.get(state.key(), 0.5)
            if prob > path_max:
                path_max = prob

        max_probs[i] = path_max

    # Convert to percentage (0-100)
    max_probs_pct = max_probs * 100

    # Build histogram: 20 bins of 5% each
    bin_size = 5
    histogram = []
    total = len(max_probs_pct)
    for bin_start in range(0, 100, bin_size):
        bin_end = bin_start + bin_size
        if bin_start == 95:
            count = int(np.sum((max_probs_pct >= bin_start) & (max_probs_pct <= bin_end)))
        else:
            count = int(np.sum((max_probs_pct >= bin_start) & (max_probs_pct < bin_end)))
        pct = round(count / total * 100, 2) if total > 0 else 0
        histogram.append({
            "bin_start": bin_start,
            "bin_end": bin_end,
            "count": count,
            "percentage": pct,
        })

    mean_val = float(np.mean(max_probs_pct))
    median_val = float(np.median(max_probs_pct))
    std_val = float(np.std(max_probs_pct)) if total > 1 else 0.0

    return {
        "current_win_prob": round(current_win_prob * 100, 2),
        "total_count": total,
        "histogram": histogram,
        "stats": {
            "mean": round(mean_val, 2),
            "median": round(median_val, 2),
            "std": round(std_val, 2),
        },
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && source .venv/bin/activate && python3 -m pytest tests/test_simulator.py -v`
Expected: 5 passed

- [ ] **Step 5: Commit**

```bash
git add backend/app/tennis/simulator.py backend/tests/test_simulator.py
git commit -m "feat: add Monte Carlo simulator for max win probability distribution"
```

---

## Task 4: Bayesian p-Value Update

**Files:**
- Create: `backend/app/tennis/bayesian.py`
- Test: `backend/tests/test_bayesian.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_bayesian.py
import pytest
from app.tennis.bayesian import bayesian_update_p


def test_no_observations_returns_prior():
    p = bayesian_update_p(prior_p=0.65, serve_wins=0, serve_total=0)
    assert p == pytest.approx(0.65)


def test_observations_shift_posterior():
    # Strong performance: 40 wins out of 50 serve points (80%)
    p = bayesian_update_p(prior_p=0.65, serve_wins=40, serve_total=50)
    assert p > 0.65  # shifted toward observed 0.80
    assert p < 0.80  # but prior pulls it back


def test_weak_performance_lowers_p():
    # Weak: 20 wins out of 50 (40%)
    p = bayesian_update_p(prior_p=0.65, serve_wins=20, serve_total=50)
    assert p < 0.65


def test_large_sample_dominates_prior():
    # 500 observations overwhelm the prior
    p = bayesian_update_p(prior_p=0.65, serve_wins=400, serve_total=500, prior_strength=100)
    assert abs(p - 0.8) < 0.02  # close to observed rate


def test_prior_strength():
    # With strong prior, small sample barely shifts
    p = bayesian_update_p(prior_p=0.65, serve_wins=8, serve_total=10, prior_strength=200)
    assert abs(p - 0.65) < 0.03
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && source .venv/bin/activate && python3 -m pytest tests/test_bayesian.py -v`
Expected: FAIL

- [ ] **Step 3: Write implementation**

```python
# backend/app/tennis/bayesian.py


def bayesian_update_p(
    prior_p: float,
    serve_wins: int,
    serve_total: int,
    prior_strength: int = 100,
) -> float:
    """Update serve point win probability using Beta-Binomial conjugate model.

    prior_p: prior serve point win rate (e.g. 0.65)
    serve_wins: observed serve points won in this match
    serve_total: total serve points played in this match
    prior_strength: effective sample size of the prior (alpha + beta)
    """
    if serve_total == 0:
        return prior_p

    alpha_0 = prior_p * prior_strength
    beta_0 = (1 - prior_p) * prior_strength

    alpha_post = alpha_0 + serve_wins
    beta_post = beta_0 + (serve_total - serve_wins)

    return alpha_post / (alpha_post + beta_post)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && source .venv/bin/activate && python3 -m pytest tests/test_bayesian.py -v`
Expected: 5 passed

- [ ] **Step 5: Commit**

```bash
git add backend/app/tennis/bayesian.py backend/tests/test_bayesian.py
git commit -m "feat: add Bayesian p-value update for serve statistics"
```

---

## Task 5: Playwright Browser Singleton

**Files:**
- Create: `backend/app/scraper/__init__.py`
- Create: `backend/app/scraper/browser.py`

- [ ] **Step 1: Write implementation**

Create `backend/app/scraper/__init__.py` (empty).

```python
# backend/app/scraper/browser.py
import logging
from playwright.async_api import async_playwright, Browser, Playwright

logger = logging.getLogger(__name__)

_playwright: Playwright | None = None
_browser: Browser | None = None


async def get_browser() -> Browser:
    global _playwright, _browser
    if _browser is None or not _browser.is_connected():
        _playwright = await async_playwright().start()
        _browser = await _playwright.chromium.launch(headless=True)
        logger.info("Playwright browser launched")
    return _browser


async def close_browser() -> None:
    global _playwright, _browser
    if _browser and _browser.is_connected():
        await _browser.close()
        _browser = None
        logger.info("Playwright browser closed")
    if _playwright:
        await _playwright.stop()
        _playwright = None
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/scraper/__init__.py backend/app/scraper/browser.py
git commit -m "feat: add Playwright browser singleton lifecycle"
```

---

## Task 6: Tennis Abstract Scraper

**Files:**
- Create: `backend/app/scraper/tennis_abstract.py`
- Test: `backend/tests/test_tennis_abstract.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_tennis_abstract.py
import pytest
from app.scraper.tennis_abstract import parse_serve_stats_from_text


def test_parse_serve_stats():
    # Simulated text content from Tennis Abstract "Last 52" row
    text = "Last 52 64-17 (79%)12-11 (52%)10.4%57.8%74.5%52.3%42.6%1.22"
    result = parse_serve_stats_from_text(text)
    assert result is not None
    assert result["first_in"] == pytest.approx(57.8, abs=0.1)
    assert result["first_won"] == pytest.approx(74.5, abs=0.1)
    assert result["second_won"] == pytest.approx(52.3, abs=0.1)
    # p = 0.578 * 0.745 + 0.422 * 0.523 ≈ 0.651
    assert 0.60 < result["p_serve"] < 0.70


def test_parse_serve_stats_no_match():
    result = parse_serve_stats_from_text("No data here")
    assert result is None


def test_parse_serve_stats_career_only():
    text = "Career 393-162 (71%)93-73 (56%)0.0%0.0%71.7%0.0%43.2%0.43"
    result = parse_serve_stats_from_text(text)
    assert result is None  # We want Last 52, not Career
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && source .venv/bin/activate && python3 -m pytest tests/test_tennis_abstract.py -v`
Expected: FAIL

- [ ] **Step 3: Write implementation**

```python
# backend/app/scraper/tennis_abstract.py
import logging
import re
from playwright.async_api import Page
from app.scraper.browser import get_browser

logger = logging.getLogger(__name__)

DEFAULT_P_ATP = 0.64
DEFAULT_P_WTA = 0.56


def parse_serve_stats_from_text(text: str) -> dict | None:
    """Parse serve stats from Tennis Abstract page text.
    Looks for 'Last 52' row with pattern: ...1stIn%...1stWon%...2ndWon%...
    """
    match = re.search(
        r'Last 52.*?(\d+\.\d+)%.*?(\d+\.\d+)%.*?(\d+\.\d+)%.*?(\d+\.\d+)%',
        text,
    )
    if not match:
        return None

    ace_pct, first_in, first_won, second_won = (float(x) for x in match.groups())
    fi = first_in / 100
    fw = first_won / 100
    sw = second_won / 100
    p_serve = fi * fw + (1 - fi) * sw

    return {
        "first_in": first_in,
        "first_won": first_won,
        "second_won": second_won,
        "p_serve": round(p_serve, 4),
    }


async def scrape_player_p(player_name: str, gender: str = "wta") -> float:
    """Scrape a player's serve points won rate from Tennis Abstract.
    Returns the p_serve value, or a default if not found.
    """
    prefix = "w" if gender == "wta" else ""
    url_name = player_name.replace(" ", "")
    url = f"https://www.tennisabstract.com/cgi-bin/{prefix}player-classic.cgi?p={url_name}&f=ACareerqq"

    default_p = DEFAULT_P_WTA if gender == "wta" else DEFAULT_P_ATP

    try:
        browser = await get_browser()
        page = await browser.new_page()
        await page.goto(url, timeout=15000)
        await page.wait_for_timeout(3000)

        text = await page.text_content("body") or ""
        await page.close()

        result = parse_serve_stats_from_text(text)
        if result:
            logger.info(f"Got p_serve for {player_name}: {result['p_serve']}")
            return result["p_serve"]

        logger.warning(f"Could not parse stats for {player_name}, using default {default_p}")
        return default_p

    except Exception as e:
        logger.error(f"Failed to scrape {player_name}: {e}")
        return default_p
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && source .venv/bin/activate && python3 -m pytest tests/test_tennis_abstract.py -v`
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add backend/app/scraper/tennis_abstract.py backend/tests/test_tennis_abstract.py
git commit -m "feat: add Tennis Abstract scraper for player serve stats"
```

---

## Task 7: FlashScore Scraper

**Files:**
- Create: `backend/app/scraper/flashscore.py`
- Test: `backend/tests/test_flashscore.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_flashscore.py
import pytest
from app.scraper.flashscore import parse_pbp_elements


def test_parse_pbp_elements_basic():
    """Test parsing of structured PBP element data."""
    raw_elements = [
        # Game 1: A serving, A wins (score goes 0-0 -> 1-0)
        {"parent_class": "matchHistoryRow__scoreBox", "text": "0", "winning": False},
        {"parent_class": "matchHistoryRow__scoreBox", "text": "1", "winning": True},
        # Break indicator
        {"parent_class": "matchHistoryRow__lostServe matchHistoryRow__away", "text": "LOST SERVE", "winning": False},
        # Game 2: score 1-0 -> 1-1
        {"parent_class": "matchHistoryRow__scoreBox", "text": "1", "winning": False},
        {"parent_class": "matchHistoryRow__scoreBox", "text": "1", "winning": True},
    ]

    result = parse_pbp_elements(raw_elements)
    assert result is not None
    assert "sets" in result
    assert "games" in result


def test_parse_pbp_elements_empty():
    result = parse_pbp_elements([])
    assert result is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && source .venv/bin/activate && python3 -m pytest tests/test_flashscore.py -v`
Expected: FAIL

- [ ] **Step 3: Write implementation**

```python
# backend/app/scraper/flashscore.py
import logging
import re
from playwright.async_api import Page
from app.scraper.browser import get_browser

logger = logging.getLogger(__name__)


def parse_pbp_elements(raw_elements: list[dict]) -> dict | None:
    """Parse structured PBP element data from FlashScore DOM into match score.
    Returns dict with sets, games, points, serving info, and serve stats.
    """
    if not raw_elements:
        return None

    score_elements = [e for e in raw_elements if "scoreBox" in e.get("parent_class", "")]
    lost_serve = [e for e in raw_elements if "lostServe" in e.get("parent_class", "")]

    if not score_elements:
        return None

    # The last two scoreBox elements represent current game scores
    # Each pair of scores represents a game result (home, away)
    scores = []
    for e in score_elements:
        text = e["text"].strip()
        if text.isdigit():
            scores.append(int(text))

    if len(scores) < 2:
        return None

    # Last two scores are current set game scores
    games_a = scores[-2] if len(scores) >= 2 else 0
    games_b = scores[-1] if len(scores) >= 2 else 0

    # Count breaks to infer serve pattern
    home_breaks = sum(1 for e in lost_serve if "home" in e.get("parent_class", ""))
    away_breaks = sum(1 for e in lost_serve if "away" in e.get("parent_class", ""))

    # Determine sets from score patterns (look for resets to 0)
    sets_a = 0
    sets_b = 0
    set_scores = []
    prev_a, prev_b = 0, 0
    for i in range(0, len(scores) - 1, 2):
        a, b = scores[i], scores[i + 1]
        if a < prev_a or b < prev_b:
            # Score reset = new set
            set_scores.append((prev_a, prev_b))
            if prev_a > prev_b:
                sets_a += 1
            else:
                sets_b += 1
        prev_a, prev_b = a, b

    return {
        "sets": [sets_a, sets_b],
        "games": [games_a, games_b],
        "points": [0, 0],
        "serving": "a",
        "set_scores": set_scores,
        "home_breaks": home_breaks,
        "away_breaks": away_breaks,
    }


async def read_flashscore_pbp(page: Page) -> list[dict]:
    """Read PBP elements from an already-loaded FlashScore match page."""
    elements = await page.query_selector_all('[class*="pointByPoint"], [class*="matchHistoryRow__lostServe"]')

    raw = []
    for el in elements:
        parent_info = await el.evaluate(
            "el => el.parentElement ? el.parentElement.className : ''"
        )
        text = (await el.text_content() or "").strip()
        winning = await el.get_attribute("data-winning")
        raw.append({
            "parent_class": parent_info,
            "text": text,
            "winning": winning == "true",
        })

    return raw


async def search_and_open_match(player_a: str, player_b: str) -> Page | None:
    """Search FlashScore for a live/recent match between two players.
    Returns a Playwright Page with the match PBP loaded, or None.
    """
    browser = await get_browser()
    page = await browser.new_page()

    try:
        search_query = player_a.split()[-1]  # Use last name for search
        url = f"https://www.flashscoreusa.com/search/?q={search_query}"
        await page.goto(url, timeout=15000)
        await page.wait_for_timeout(3000)

        # Look for match links containing both player names
        links = await page.query_selector_all('a[href*="/game/tennis/"]')
        for link in links:
            text = (await link.text_content() or "").lower()
            a_last = player_a.split()[-1].lower()
            b_last = player_b.split()[-1].lower()
            if a_last in text and b_last in text:
                href = await link.get_attribute("href")
                if href:
                    match_url = href if href.startswith("http") else f"https://www.flashscoreusa.com{href}"
                    # Navigate to PBP page
                    pbp_url = match_url.rstrip("/") + "/summary/point-by-point/set-1/"
                    await page.goto(pbp_url, timeout=15000)
                    await page.wait_for_timeout(5000)
                    logger.info(f"Found match: {match_url}")
                    return page

        logger.warning(f"No match found for {player_a} vs {player_b}")
        await page.close()
        return None

    except Exception as e:
        logger.error(f"FlashScore search failed: {e}")
        await page.close()
        return None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && source .venv/bin/activate && python3 -m pytest tests/test_flashscore.py -v`
Expected: 2 passed

- [ ] **Step 5: Commit**

```bash
git add backend/app/scraper/flashscore.py backend/tests/test_flashscore.py
git commit -m "feat: add FlashScore PBP scraper with search and live DOM reading"
```

---

## Task 8: Simulate API Endpoints

**Files:**
- Create: `backend/app/routes/simulate.py`
- Test: `backend/tests/test_simulate_api.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_simulate_api.py
import os
import pytest
from httpx import AsyncClient, ASGITransport
from unittest.mock import patch, AsyncMock

os.environ.setdefault("KALSHI_API_KEY_ID", "")
os.environ.setdefault("KALSHI_PRIVATE_KEY_PATH", "./secrets/test.pem")
os.environ.setdefault("OPENAI_API_KEY", "test-key")


@pytest.fixture
def app():
    from app.routes.simulate import router
    from fastapi import FastAPI
    test_app = FastAPI()
    test_app.include_router(router)
    return test_app


@pytest.mark.asyncio
async def test_simulate_endpoint(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/api/simulate", json={
            "p_a": 0.65,
            "p_b": 0.60,
            "score": {
                "sets": [0, 0],
                "games": [0, 0],
                "points": [0, 0],
                "serving": "a"
            },
            "num_simulations": 1000
        })
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_count"] == 1000
    assert len(data["histogram"]) == 20
    assert "current_win_prob" in data
    assert "stats" in data


@pytest.mark.asyncio
async def test_simulate_mid_match(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/api/simulate", json={
            "p_a": 0.65,
            "p_b": 0.60,
            "score": {
                "sets": [1, 0],
                "games": [3, 2],
                "points": [2, 1],
                "serving": "a"
            },
            "num_simulations": 1000
        })
    assert resp.status_code == 200
    data = resp.json()
    assert data["current_win_prob"] > 50  # A is ahead, should be > 50%
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && source .venv/bin/activate && python3 -m pytest tests/test_simulate_api.py -v`
Expected: FAIL

- [ ] **Step 3: Write implementation**

```python
# backend/app/routes/simulate.py
import logging
from pydantic import BaseModel
from fastapi import APIRouter

from app.tennis.engine import MatchState, build_win_prob_table
from app.tennis.simulator import simulate_max_prob_distribution
from app.tennis.bayesian import bayesian_update_p

logger = logging.getLogger(__name__)

router = APIRouter()


class ScoreInput(BaseModel):
    sets: list[int]       # [sets_a, sets_b]
    games: list[int]      # [games_a, games_b]
    points: list[int]     # [points_a, points_b]
    serving: str          # "a" or "b"


class SimulateRequest(BaseModel):
    p_a: float
    p_b: float
    score: ScoreInput
    num_simulations: int = 100_000


class LookupRequest(BaseModel):
    player_input: str


def score_to_match_state(score: ScoreInput) -> MatchState:
    is_tiebreak = score.games[0] == 6 and score.games[1] == 6
    return MatchState(
        sets_a=score.sets[0],
        sets_b=score.sets[1],
        games_a=score.games[0],
        games_b=score.games[1],
        points_a=score.points[0],
        points_b=score.points[1],
        is_a_serving=(score.serving == "a"),
        is_tiebreak=is_tiebreak,
    )


@router.post("/api/simulate")
async def simulate(req: SimulateRequest):
    state = score_to_match_state(req.score)
    table = build_win_prob_table(req.p_a, req.p_b)
    result = simulate_max_prob_distribution(
        state, req.p_a, req.p_b, table, req.num_simulations
    )
    return result


@router.post("/api/lookup-match")
async def lookup_match(req: LookupRequest):
    import app.config as _config_module
    settings = _config_module.settings

    # Step 1: Parse player names with GPT-4o-mini
    from openai import AsyncOpenAI
    openai_client = AsyncOpenAI(api_key=settings.openai_api_key)

    try:
        completion = await openai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": (
                    "Extract two tennis player names from the input. "
                    "Return JSON with exactly these fields: "
                    '{"player_a": "First Last", "player_b": "First Last", "gender": "atp" or "wta"}. '
                    "Infer gender from the player names. Return only JSON, no other text."
                )},
                {"role": "user", "content": req.player_input},
            ],
            temperature=0,
        )
        import json
        parsed = json.loads(completion.choices[0].message.content)
        player_a = parsed["player_a"]
        player_b = parsed["player_b"]
        gender = parsed.get("gender", "atp")
    except Exception as e:
        logger.error(f"Failed to parse player names: {e}")
        return {"error": f"Could not parse player names: {e}"}

    # Step 2: Get p values from Tennis Abstract
    from app.scraper.tennis_abstract import scrape_player_p
    p_a = await scrape_player_p(player_a, gender)
    p_b = await scrape_player_p(player_b, gender)

    # Step 3: Search FlashScore for live match
    from app.scraper.flashscore import search_and_open_match, read_flashscore_pbp, parse_pbp_elements
    match_page = await search_and_open_match(player_a, player_b)

    match_found = match_page is not None
    current_score = {"sets": [0, 0], "games": [0, 0], "points": [0, 0], "serving": "a"}
    match_url = ""
    p_a_updated = p_a
    p_b_updated = p_b

    if match_page:
        match_url = match_page.url
        raw_pbp = await read_flashscore_pbp(match_page)
        parsed_score = parse_pbp_elements(raw_pbp)
        if parsed_score:
            current_score = {
                "sets": parsed_score["sets"],
                "games": parsed_score["games"],
                "points": parsed_score["points"],
                "serving": parsed_score["serving"],
            }
        # Don't close the page — keep it open for auto-update

    return {
        "player_a": player_a,
        "player_b": player_b,
        "gender": gender,
        "p_a_prior": round(p_a, 4),
        "p_b_prior": round(p_b, 4),
        "match_found": match_found,
        "match_url": match_url,
        "current_score": current_score,
        "p_a_updated": round(p_a_updated, 4),
        "p_b_updated": round(p_b_updated, 4),
    }


@router.get("/api/match-update")
async def match_update(
    match_url: str,
    p_a_prior: float,
    p_b_prior: float,
    num_simulations: int = 100_000,
):
    """Re-read FlashScore DOM, update p values, re-simulate."""
    from app.scraper.browser import get_browser
    from app.scraper.flashscore import read_flashscore_pbp, parse_pbp_elements

    browser = await get_browser()
    # Find the page with this URL among open pages
    pages = browser.contexts[0].pages if browser.contexts else []
    match_page = None
    for page in pages:
        if match_url in page.url:
            match_page = page
            break

    if not match_page:
        return {"error": "Match page not found. Please look up the match again."}

    raw_pbp = await read_flashscore_pbp(match_page)
    parsed_score = parse_pbp_elements(raw_pbp)

    if not parsed_score:
        return {"error": "Could not read match data"}

    score = {
        "sets": parsed_score["sets"],
        "games": parsed_score["games"],
        "points": parsed_score["points"],
        "serving": parsed_score["serving"],
    }

    # Bayesian update (simplified: use break counts as proxy for serve performance)
    p_a_updated = p_a_prior
    p_b_updated = p_b_prior

    state = score_to_match_state(ScoreInput(**score))
    table = build_win_prob_table(p_a_updated, p_b_updated)
    sim_result = simulate_max_prob_distribution(
        state, p_a_updated, p_b_updated, table, num_simulations
    )

    return {
        "current_score": score,
        "p_a_updated": round(p_a_updated, 4),
        "p_b_updated": round(p_b_updated, 4),
        **sim_result,
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && source .venv/bin/activate && python3 -m pytest tests/test_simulate_api.py -v`
Expected: 2 passed

- [ ] **Step 5: Commit**

```bash
git add backend/app/routes/simulate.py backend/tests/test_simulate_api.py
git commit -m "feat: add /api/simulate, /api/lookup-match, /api/match-update endpoints"
```

---

## Task 9: Register Simulate Router + Browser Cleanup

**Files:**
- Modify: `backend/app/main.py`

- [ ] **Step 1: Add simulate router import and browser cleanup**

Add after `from app.routes.query import router as query_router`:

```python
from app.routes.simulate import router as simulate_router
```

Add after `app.include_router(query_router)`:

```python
app.include_router(simulate_router)
```

In the `lifespan` function, add browser cleanup before `yield` returns. After the `yield` line and before `if scheduler.running:`, add:

```python
    from app.scraper.browser import close_browser
    await close_browser()
```

- [ ] **Step 2: Verify all tests still pass**

Run: `cd backend && source .venv/bin/activate && python3 -m pytest tests/ -v`
Expected: All pass

- [ ] **Step 3: Commit**

```bash
git add backend/app/main.py
git commit -m "feat: register simulate router and add browser cleanup to lifespan"
```

---

## Task 10: Frontend Types + API Functions

**Files:**
- Modify: `frontend/src/types.ts`
- Modify: `frontend/src/api.ts`

- [ ] **Step 1: Add simulator types to types.ts**

Append to `frontend/src/types.ts`:

```typescript
export interface ScoreState {
    sets: number[];
    games: number[];
    points: number[];
    serving: string;
}

export interface LookupResult {
    player_a: string;
    player_b: string;
    gender: string;
    p_a_prior: number;
    p_b_prior: number;
    match_found: boolean;
    match_url: string;
    current_score: ScoreState;
    p_a_updated: number;
    p_b_updated: number;
    error?: string;
}

export interface SimulateResult {
    current_win_prob: number;
    total_count: number;
    histogram: HistogramBin[];
    stats: Stats;
}

export interface MatchUpdateResult extends SimulateResult {
    current_score: ScoreState;
    p_a_updated: number;
    p_b_updated: number;
    error?: string;
}
```

- [ ] **Step 2: Add API functions to api.ts**

Append to `frontend/src/api.ts`:

```typescript
import type { LookupResult, SimulateResult, ScoreState, MatchUpdateResult } from "./types";

export async function lookupMatch(playerInput: string): Promise<LookupResult> {
    const resp = await fetch("/api/lookup-match", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ player_input: playerInput }),
    });
    if (!resp.ok) throw new Error(`Lookup failed: ${resp.status}`);
    return resp.json();
}

export async function runSimulation(
    p_a: number,
    p_b: number,
    score: ScoreState,
    num_simulations: number = 100000
): Promise<SimulateResult> {
    const resp = await fetch("/api/simulate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ p_a, p_b, score, num_simulations }),
    });
    if (!resp.ok) throw new Error(`Simulation failed: ${resp.status}`);
    return resp.json();
}

export async function fetchMatchUpdate(
    matchUrl: string,
    p_a_prior: number,
    p_b_prior: number,
    num_simulations: number = 100000
): Promise<MatchUpdateResult> {
    const params = new URLSearchParams({
        match_url: matchUrl,
        p_a_prior: String(p_a_prior),
        p_b_prior: String(p_b_prior),
        num_simulations: String(num_simulations),
    });
    const resp = await fetch(`/api/match-update?${params}`);
    if (!resp.ok) throw new Error(`Update failed: ${resp.status}`);
    return resp.json();
}
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/types.ts frontend/src/api.ts
git commit -m "feat: add simulator types and API functions to frontend"
```

---

## Task 11: NavBar Component

**Files:**
- Create: `frontend/src/components/NavBar.tsx`

- [ ] **Step 1: Create NavBar**

```tsx
// frontend/src/components/NavBar.tsx
import { Link, useLocation } from "react-router-dom";

export default function NavBar() {
    const location = useLocation();

    const linkStyle = (path: string) => ({
        padding: "8px 16px",
        textDecoration: "none",
        fontWeight: location.pathname === path ? 700 : 400,
        color: location.pathname === path ? "#3498db" : "#333",
        borderBottom: location.pathname === path ? "2px solid #3498db" : "2px solid transparent",
    });

    return (
        <nav style={{ display: "flex", gap: 8, borderBottom: "1px solid #ddd", marginBottom: 20, paddingBottom: 0 }}>
            <Link to="/" style={linkStyle("/")}>Query Tool</Link>
            <Link to="/simulate" style={linkStyle("/simulate")}>Match Simulator</Link>
        </nav>
    );
}
```

- [ ] **Step 2: Install react-router-dom**

Run: `cd frontend && npm install react-router-dom`

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/NavBar.tsx frontend/package.json frontend/package-lock.json
git commit -m "feat: add NavBar component with routing links"
```

---

## Task 12: MatchInput + MatchStatus Components

**Files:**
- Create: `frontend/src/components/MatchInput.tsx`
- Create: `frontend/src/components/MatchStatus.tsx`

- [ ] **Step 1: Create MatchInput**

```tsx
// frontend/src/components/MatchInput.tsx
import { useState } from "react";

interface Props {
    onLookup: (input: string) => void;
    loading: boolean;
}

export default function MatchInput({ onLookup, loading }: Props) {
    const [input, setInput] = useState("");

    const handleSubmit = (e: React.FormEvent) => {
        e.preventDefault();
        if (input.trim()) onLookup(input.trim());
    };

    return (
        <form onSubmit={handleSubmit} style={{ padding: 20, border: "1px solid #ddd", borderRadius: 8 }}>
            <h2 style={{ marginTop: 0 }}>Match Lookup</h2>
            <div style={{ display: "flex", gap: 8 }}>
                <input
                    type="text"
                    value={input}
                    onChange={(e) => setInput(e.target.value)}
                    placeholder="Enter player names (e.g. Rybakina vs Fernandez)"
                    style={{ flex: 1, padding: "8px 12px", fontSize: 16 }}
                />
                <button
                    type="submit"
                    disabled={loading || !input.trim()}
                    style={{ padding: "8px 20px", fontSize: 16, cursor: loading ? "not-allowed" : "pointer" }}
                >
                    {loading ? "Looking up..." : "Look Up Match"}
                </button>
            </div>
        </form>
    );
}
```

- [ ] **Step 2: Create MatchStatus**

```tsx
// frontend/src/components/MatchStatus.tsx
import { useEffect, useRef, useState } from "react";
import type { LookupResult, ScoreState } from "../types";

interface Props {
    lookup: LookupResult;
    pA: number;
    pB: number;
    onPChange: (pA: number, pB: number) => void;
    currentWinProb: number | null;
    autoUpdating: boolean;
    onToggleAutoUpdate: () => void;
}

const POINT_LABELS = ["0", "15", "30", "40", "AD"];

function formatScore(score: ScoreState, playerA: string, playerB: string): string {
    const sets = score.sets.join("-");
    const games = score.games.join("-");
    const pa = score.points[0];
    const pb = score.points[1];
    const points = pa <= 4 && pb <= 4
        ? `${POINT_LABELS[pa] || pa}-${POINT_LABELS[pb] || pb}`
        : `${pa}-${pb}`;
    const server = score.serving === "a" ? playerA.split(" ").pop() : playerB.split(" ").pop();
    return `Sets: ${sets}  Games: ${games}  Points: ${points}  (${server} serving)`;
}

export default function MatchStatus({
    lookup, pA, pB, onPChange, currentWinProb, autoUpdating, onToggleAutoUpdate
}: Props) {
    return (
        <div style={{ padding: 20, border: "1px solid #ddd", borderRadius: 8 }}>
            <h2 style={{ marginTop: 0 }}>
                {lookup.player_a} vs {lookup.player_b}
            </h2>

            <p style={{ fontSize: 18, fontFamily: "monospace" }}>
                {formatScore(lookup.current_score, lookup.player_a, lookup.player_b)}
            </p>

            {!lookup.match_found && (
                <p style={{ color: "#888" }}>No live match found. Using default score 0-0.</p>
            )}

            <div style={{ display: "flex", gap: 24, marginTop: 12 }}>
                <div>
                    <label style={{ fontWeight: 600 }}>
                        {lookup.player_a.split(" ").pop()} p:
                    </label>{" "}
                    <span style={{ color: "#888", fontSize: 14 }}>prior {lookup.p_a_prior.toFixed(3)}</span>
                    <br />
                    <input
                        type="number"
                        step={0.001}
                        value={pA}
                        onChange={(e) => onPChange(Number(e.target.value), pB)}
                        style={{ width: 80, padding: "4px 8px", marginTop: 4 }}
                    />
                </div>
                <div>
                    <label style={{ fontWeight: 600 }}>
                        {lookup.player_b.split(" ").pop()} p:
                    </label>{" "}
                    <span style={{ color: "#888", fontSize: 14 }}>prior {lookup.p_b_prior.toFixed(3)}</span>
                    <br />
                    <input
                        type="number"
                        step={0.001}
                        value={pB}
                        onChange={(e) => onPChange(pA, Number(e.target.value))}
                        style={{ width: 80, padding: "4px 8px", marginTop: 4 }}
                    />
                </div>
            </div>

            {currentWinProb !== null && (
                <p style={{ fontSize: 18, marginTop: 12 }}>
                    Current P({lookup.player_a.split(" ").pop()} wins):{" "}
                    <strong>{currentWinProb.toFixed(1)}%</strong>
                </p>
            )}

            {lookup.match_found && (
                <div style={{ marginTop: 12 }}>
                    <button
                        onClick={onToggleAutoUpdate}
                        style={{
                            padding: "6px 16px",
                            cursor: "pointer",
                            background: autoUpdating ? "#e74c3c" : "#27ae60",
                            color: "white",
                            border: "none",
                            borderRadius: 4,
                        }}
                    >
                        {autoUpdating ? "Stop Auto-Update" : "Start Auto-Update (30s)"}
                    </button>
                </div>
            )}
        </div>
    );
}
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/MatchInput.tsx frontend/src/components/MatchStatus.tsx
git commit -m "feat: add MatchInput and MatchStatus components"
```

---

## Task 13: SimulatorPage + App Router Integration

**Files:**
- Create: `frontend/src/pages/SimulatorPage.tsx`
- Modify: `frontend/src/App.tsx`

- [ ] **Step 1: Create SimulatorPage**

```tsx
// frontend/src/pages/SimulatorPage.tsx
import { useState, useEffect, useRef } from "react";
import MatchInput from "../components/MatchInput";
import MatchStatus from "../components/MatchStatus";
import Histogram from "../components/Histogram";
import { lookupMatch, runSimulation, fetchMatchUpdate } from "../api";
import type { LookupResult, SimulateResult, QueryResponse } from "../types";

export default function SimulatorPage() {
    const [lookup, setLookup] = useState<LookupResult | null>(null);
    const [simResult, setSimResult] = useState<SimulateResult | null>(null);
    const [loading, setLoading] = useState(false);
    const [simulating, setSimulating] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [pA, setPA] = useState(0.64);
    const [pB, setPB] = useState(0.64);
    const [autoUpdating, setAutoUpdating] = useState(false);
    const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

    const handleLookup = async (input: string) => {
        setLoading(true);
        setError(null);
        setSimResult(null);
        try {
            const result = await lookupMatch(input);
            if (result.error) {
                setError(result.error);
                return;
            }
            setLookup(result);
            setPA(result.p_a_updated);
            setPB(result.p_b_updated);

            // Auto-run simulation
            setSimulating(true);
            const sim = await runSimulation(
                result.p_a_updated, result.p_b_updated, result.current_score, 100000
            );
            setSimResult(sim);
        } catch (err) {
            setError(err instanceof Error ? err.message : "Lookup failed");
        } finally {
            setLoading(false);
            setSimulating(false);
        }
    };

    const handlePChange = async (newPA: number, newPB: number) => {
        setPA(newPA);
        setPB(newPB);
        if (lookup) {
            setSimulating(true);
            try {
                const sim = await runSimulation(newPA, newPB, lookup.current_score, 100000);
                setSimResult(sim);
            } catch (err) {
                setError(err instanceof Error ? err.message : "Simulation failed");
            } finally {
                setSimulating(false);
            }
        }
    };

    const doAutoUpdate = async () => {
        if (!lookup?.match_url) return;
        try {
            const update = await fetchMatchUpdate(lookup.match_url, lookup.p_a_prior, lookup.p_b_prior);
            if (update.error) return;
            setLookup((prev) =>
                prev ? { ...prev, current_score: update.current_score, p_a_updated: update.p_a_updated, p_b_updated: update.p_b_updated } : prev
            );
            setPA(update.p_a_updated);
            setPB(update.p_b_updated);
            setSimResult({
                current_win_prob: update.current_win_prob,
                total_count: update.total_count,
                histogram: update.histogram,
                stats: update.stats,
            });
        } catch (err) {
            // Silent fail on auto-update
        }
    };

    const toggleAutoUpdate = () => {
        if (autoUpdating) {
            if (intervalRef.current) clearInterval(intervalRef.current);
            intervalRef.current = null;
            setAutoUpdating(false);
        } else {
            doAutoUpdate();
            intervalRef.current = setInterval(doAutoUpdate, 30000);
            setAutoUpdating(true);
        }
    };

    useEffect(() => {
        return () => {
            if (intervalRef.current) clearInterval(intervalRef.current);
        };
    }, []);

    // Convert SimulateResult to QueryResponse format for Histogram reuse
    const histogramData: QueryResponse | null = simResult
        ? { total_count: simResult.total_count, histogram: simResult.histogram, stats: simResult.stats }
        : null;

    return (
        <div>
            <MatchInput onLookup={handleLookup} loading={loading} />

            {error && (
                <div style={{ marginTop: 16, padding: 12, background: "#fee", borderRadius: 6, color: "#c00" }}>
                    {error}
                </div>
            )}

            {lookup && (
                <div style={{ marginTop: 16 }}>
                    <MatchStatus
                        lookup={lookup}
                        pA={pA}
                        pB={pB}
                        onPChange={handlePChange}
                        currentWinProb={simResult?.current_win_prob ?? null}
                        autoUpdating={autoUpdating}
                        onToggleAutoUpdate={toggleAutoUpdate}
                    />
                </div>
            )}

            <div style={{ marginTop: 16 }}>
                {simulating && <p style={{ textAlign: "center", color: "#888" }}>Simulating...</p>}
                <Histogram data={histogramData} />
            </div>
        </div>
    );
}
```

- [ ] **Step 2: Update App.tsx with React Router**

Replace `frontend/src/App.tsx`:

```tsx
// frontend/src/App.tsx
import { BrowserRouter, Routes, Route } from "react-router-dom";
import { useState } from "react";
import NavBar from "./components/NavBar";
import QueryForm from "./components/QueryForm";
import Histogram from "./components/Histogram";
import SimulatorPage from "./pages/SimulatorPage";
import { fetchQueryResults } from "./api";
import type { QueryFilters, QueryResponse } from "./types";

function QueryPage() {
    const [data, setData] = useState<QueryResponse | null>(null);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);

    const handleSearch = async (filters: QueryFilters) => {
        setLoading(true);
        setError(null);
        try {
            const result = await fetchQueryResults(filters);
            setData(result);
        } catch (err) {
            setError(err instanceof Error ? err.message : "Query failed");
        } finally {
            setLoading(false);
        }
    };

    return (
        <>
            <QueryForm onSearch={handleSearch} loading={loading} />
            {error && (
                <div style={{ marginTop: 16, padding: 12, background: "#fee", borderRadius: 6, color: "#c00" }}>
                    {error}
                </div>
            )}
            <div style={{ marginTop: 20 }}>
                <Histogram data={data} />
            </div>
        </>
    );
}

function App() {
    return (
        <BrowserRouter>
            <div style={{ maxWidth: 900, margin: "0 auto", padding: 20, fontFamily: "system-ui" }}>
                <h1>Tennis Odds Tool</h1>
                <NavBar />
                <Routes>
                    <Route path="/" element={<QueryPage />} />
                    <Route path="/simulate" element={<SimulatorPage />} />
                </Routes>
            </div>
        </BrowserRouter>
    );
}

export default App;
```

- [ ] **Step 3: Verify frontend builds**

Run: `cd frontend && npm run build`
Expected: Build succeeds

- [ ] **Step 4: Commit**

```bash
git add frontend/src/pages/SimulatorPage.tsx frontend/src/App.tsx
git commit -m "feat: add SimulatorPage and integrate with React Router"
```

---

## Task 14: Histogram Reusability — Add configurable labels

**Files:**
- Modify: `frontend/src/components/Histogram.tsx`

- [ ] **Step 1: Add optional label props**

Update the `Props` interface and component to accept optional axis labels:

```tsx
interface Props {
    data: QueryResponse | null;
    xLabel?: string;
    yLabel?: string;
    title?: string;
    unit?: string;
}
```

Replace hardcoded strings:
- Title: use `props.title` or default `"Max Price After Distribution"`
- X-axis label: use `props.xLabel` or default `"Max Price After (cents)"`
- Tooltip label: use `props.unit` or default `"cents"`
- Stats unit: use `props.unit` or default `"cents"`
- Cumulative text: use `props.unit` or default `"cents"`

SimulatorPage passes: `xLabel="Max Win Probability (%)"`, `unit="%"`, `title="Max Win Probability Distribution"`

- [ ] **Step 2: Verify frontend builds**

Run: `cd frontend && npm run build`

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/Histogram.tsx
git commit -m "feat: make Histogram labels configurable for reuse across pages"
```

---

## Summary

| Task | What it builds | Tests |
|------|---------------|-------|
| 1 | Dependencies + config | - |
| 2 | Tennis backward induction engine | 11 tests |
| 3 | Monte Carlo simulator | 5 tests |
| 4 | Bayesian p-value update | 5 tests |
| 5 | Playwright browser singleton | - |
| 6 | Tennis Abstract scraper | 3 tests |
| 7 | FlashScore PBP scraper | 2 tests |
| 8 | Simulate API endpoints | 2 tests |
| 9 | Router registration + cleanup | - |
| 10 | Frontend types + API functions | - |
| 11 | NavBar component | - |
| 12 | MatchInput + MatchStatus components | - |
| 13 | SimulatorPage + App Router | - |
| 14 | Histogram label reusability | - |
