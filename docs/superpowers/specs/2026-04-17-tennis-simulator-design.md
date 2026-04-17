# Tennis Match Simulator — Design Spec

## 1. Overview

A real-time tennis match simulator that estimates the probability distribution of the maximum win probability a player can reach during the remainder of a match. Uses backward induction (Markov chain) for exact state-level win probabilities, Monte Carlo simulation for max-probability path sampling, and live data from FlashScore + Tennis Abstract.

**Relationship to existing tool**: This is a new page added to the existing tennis odds query tool. Shares the same backend (FastAPI) and frontend (React + Vite) infrastructure.

---

## 2. User Flow

1. User enters two player names in a text input
2. Backend calls GPT-4o-mini to parse/standardize the player names
3. Backend concurrently:
   - Scrapes Tennis Abstract (Playwright) for each player's serve points won % (prior p values)
   - Scrapes FlashScore (Playwright) for the current live match PBP data
4. If match not found or not started: use prior p values, score = 0-0
5. If match in progress: parse PBP to extract current score + Bayesian-update p values
6. Run backward induction + Monte Carlo simulation
7. Display histogram of max win probability distribution
8. **Auto-update every 30 seconds**: re-read FlashScore DOM (no page refresh) → update p → re-simulate → push new histogram to frontend

---

## 3. Tennis Scoring Model

### 3.1 State Representation

A tennis match state (BO3) is fully described by:

```
(sets_a, sets_b, games_a, games_b, points_a, points_b, is_a_serving, is_tiebreak)
```

- `sets_a/b`: 0-2 (match won when one reaches 2)
- `games_a/b`: 0-7 (tiebreak at 6-6, set won at 6 with 2-game lead or 7-6)
- `points_a/b`: 0-4 in regular game (0, 15, 30, 40, AD mapped to 0-4), 0-N in tiebreak
- `is_a_serving`: boolean (serve alternates each game, specific pattern in tiebreak)
- `is_tiebreak`: boolean

### 3.2 Backward Induction

Given `p_a` (player A serve point win rate) and `p_b` (player B serve point win rate):

1. Terminal states: `sets_a == 2` → P(A wins) = 1.0; `sets_b == 2` → P(A wins) = 0.0
2. For each non-terminal state, compute:
   - If A is serving: P(A wins next point) = `p_a`
   - If B is serving: P(A wins next point) = `1 - p_b`
   - P(A wins | state) = p_point × P(A wins | next_state_if_A_wins_point) + (1 - p_point) × P(A wins | next_state_if_A_loses_point)
3. Recurse from terminal states backward to compute a lookup table for all reachable states

The lookup table is recomputed whenever p values change.

### 3.3 Monte Carlo Simulation

From the current match state:

1. Simulate 100,000 match paths
2. Each path: at every point, draw random number, compare to p_serve of current server, advance state
3. At each state along the path, look up P(A wins) from the backward induction table
4. Record the maximum P(A wins) encountered on each path
5. Collect all 100K max values → histogram (probability distribution of max win probability)

Use NumPy vectorization: simulate all 100K paths in parallel.

---

## 4. Data Sources

### 4.1 Player p Values — Tennis Abstract (Playwright)

URL pattern: `https://www.tennisabstract.com/cgi-bin/{w}player-classic.cgi?p={PlayerName}&f=ACareerqq`

Extract from "Last 52" row:
- `1st_in`: First serve in percentage
- `1st_won`: First serve won percentage  
- `2nd_won`: Second serve won percentage
- `p_serve = 1st_in × 1st_won + (1 - 1st_in) × 2nd_won`

Gender prefix: `w` for WTA players, empty for ATP.

Fallback values if player not found: ATP average p = 0.64, WTA average p = 0.56.

### 4.2 Live PBP — FlashScore (Playwright)

**Match search**: Navigate to FlashScore, search for player names, find the matching live/recent match.

**PBP extraction**: Query DOM elements with `[class*="pointByPoint"]`:
- `matchHistoryRow__scoreBox`: game-by-game scores with `data-winning` attribute
- `matchHistoryRow__lostServe`: break indicators (home/away)
- `matchHistoryRow__fifteen`: break point (BP) / set point (SP) markers
- Tiebreak scores indicated by `data-reverse` attribute

**Live updates**: Keep Playwright browser open. Every 30 seconds, re-read DOM elements (FlashScore auto-updates via WebSocket). No page refresh needed.

**Score parsing**: From PBP elements, reconstruct:
- Current set scores
- Current game score within the active set
- Current point score within the active game
- Who is serving (inferred from `lostServe` home/away pattern)
- Per-player serve point wins/losses for Bayesian update

### 4.3 Player Name Parsing — GPT-4o-mini

User input: free-form text like "Rybakina vs Fernandez" or "elena rybakina leylah fernandez"

GPT-4o-mini prompt extracts:
- `player_a`: standardized full name
- `player_b`: standardized full name  
- `gender`: "atp" or "wta" (inferred from player names)

---

## 5. Bayesian p Value Update

Prior: Beta distribution from Tennis Abstract data.
- Convert prior p to Beta(α₀, β₀) using the number of serve points from recent matches as effective sample size. Use a moderate prior strength (e.g., α₀ + β₀ = 100).

Update with observed PBP data:
- Count serve points won/lost for each player from the PBP
- Posterior: Beta(α₀ + serve_wins, β₀ + serve_losses)
- Updated p = posterior mean = (α₀ + serve_wins) / (α₀ + β₀ + serve_total)

---

## 6. API Endpoints

### `POST /api/lookup-match`

Request:
```json
{
    "player_input": "Rybakina vs Fernandez"
}
```

Response:
```json
{
    "player_a": "Elena Rybakina",
    "player_b": "Leylah Fernandez",
    "gender": "wta",
    "p_a_prior": 0.651,
    "p_b_prior": 0.599,
    "match_found": true,
    "match_url": "https://flashscoreusa.com/...",
    "current_score": {
        "sets": [1, 0],
        "games": [3, 2],
        "points": [30, 15],
        "serving": "a"
    },
    "p_a_updated": 0.668,
    "p_b_updated": 0.583
}
```

### `POST /api/simulate`

Request:
```json
{
    "p_a": 0.668,
    "p_b": 0.583,
    "score": {
        "sets": [1, 0],
        "games": [3, 2],
        "points": [30, 15],
        "serving": "a"
    },
    "num_simulations": 100000
}
```

Response:
```json
{
    "current_win_prob": 0.72,
    "total_count": 100000,
    "histogram": [
        {"bin_start": 0, "bin_end": 5, "count": 0, "percentage": 0},
        {"bin_start": 70, "bin_end": 75, "count": 12340, "percentage": 12.34},
        ...
    ],
    "stats": {
        "mean": 85.3,
        "median": 87.0,
        "std": 8.2
    }
}
```

Histogram: 20 bins of 5% each (0-100%), showing distribution of max P(A wins) across all simulated paths.

### `GET /api/match-update?match_url=...`

Lightweight endpoint for periodic updates. Re-reads FlashScore DOM, returns updated score + p values + new simulation results. Frontend polls this every 30 seconds.

---

## 7. Frontend

### New Page: `/simulate`

```
┌─ NavBar ─────────────────────────────────────┐
│  [Query Tool]  [Match Simulator]             │
├──────────────────────────────────────────────┤
│  Match Input                                 │
│  ┌────────────────────────────────────────┐  │
│  │ Enter player names (e.g. Rybakina vs   │  │
│  │ Fernandez)                             │  │
│  └────────────────────────────────────────┘  │
│                         [Look Up Match]      │
├──────────────────────────────────────────────┤
│  Match Status (after lookup)                 │
│                                              │
│  Elena Rybakina vs Leylah Fernandez          │
│  Score: 6-4  3-2  30-15  (Rybakina serving)  │
│                                              │
│  p values:                                   │
│  Rybakina: prior 0.651 → updated 0.668      │
│  Fernandez: prior 0.599 → updated 0.583     │
│                                              │
│  [p_a: [0.668]]  [p_b: [0.583]]  (editable) │
│                                              │
│  Current P(Rybakina wins): 72.0%             │
│  ○ Auto-update every 30s  [▶ Start] [⏸ Stop]│
├──────────────────────────────────────────────┤
│  Max Win Probability Distribution            │
│  (Rybakina)                                  │
│                                              │
│  %│          ██                              │
│   │        ████                              │
│   │      ████████                            │
│   │    ████████████                          │
│   └───────────────────── max P(win) %        │
│   0  10  20  ... 90  100                     │
│                                              │
│  Click bin for cumulative probability        │
│  Mean: 85.3%  Median: 87.0%  Std: 8.2%      │
└──────────────────────────────────────────────┘
```

### Components

- **NavBar**: top navigation between "Query Tool" (existing `/`) and "Match Simulator" (`/simulate`)
- **MatchInput**: text input + "Look Up Match" button
- **MatchStatus**: displays parsed score, p values (editable), current win prob, auto-update toggle
- **Histogram**: reuse existing component (same structure, different axis label: "Max Win Probability (%)")

### Auto-Update Flow

1. User clicks "Start" auto-update
2. Frontend polls `GET /api/match-update?match_url=...` every 30 seconds
3. On response: update score display, p values, re-render histogram
4. User can click "Stop" to pause

---

## 8. New Files

### Backend

| File | Responsibility |
|---|---|
| `app/tennis/__init__.py` | Package marker |
| `app/tennis/engine.py` | Backward induction: build win probability lookup table for all BO3 states |
| `app/tennis/simulator.py` | Monte Carlo: simulate N paths, collect max win prob distribution |
| `app/tennis/bayesian.py` | Bayesian update of p values from observed PBP serve data |
| `app/scraper/__init__.py` | Package marker |
| `app/scraper/tennis_abstract.py` | Playwright: scrape player p values from Tennis Abstract |
| `app/scraper/flashscore.py` | Playwright: search match + extract PBP from FlashScore |
| `app/routes/simulate.py` | API endpoints: /api/lookup-match, /api/simulate, /api/match-update |

### Frontend

| File | Responsibility |
|---|---|
| `src/components/NavBar.tsx` | Navigation between Query Tool and Simulator |
| `src/components/MatchInput.tsx` | Player name input + lookup button |
| `src/components/MatchStatus.tsx` | Score display, p values, current win prob, auto-update controls |
| `src/pages/SimulatorPage.tsx` | Simulator page layout, wires components together |

---

## 9. Dependencies

### New Backend Dependencies

```
playwright==1.58.0
openai>=1.0.0
numpy>=1.26.0
```

Playwright browser (Chromium) must be installed: `python3 -m playwright install chromium`

### OpenAI API Key

Add to `.env`:
```
OPENAI_API_KEY=your_key_here
```

---

## 10. Browser Lifecycle

Playwright browser instances are expensive to start. Design:

1. **On first `/api/lookup-match` call**: launch Chromium, keep it alive as a module-level singleton
2. **Tennis Abstract scraping**: open tab, scrape, close tab (quick, ~2-3 seconds per player)
3. **FlashScore monitoring**: open tab, keep it open for the duration of auto-update polling
4. **Cleanup**: close browser on app shutdown (FastAPI lifespan)

---

## 11. Scope Boundaries

**In scope:**
- BO3 match simulation only
- Backward induction + Monte Carlo engine
- Tennis Abstract p value scraping
- FlashScore PBP scraping + live monitoring
- GPT-4o-mini player name parsing
- Bayesian p value update from PBP
- Auto-update polling (30s interval)
- Histogram of max win probability distribution

**Out of scope:**
- BO5 support (future)
- Multiple simultaneous match monitoring
- Historical simulation playback
- Automated betting/trading signals
- Mobile-optimized layout
