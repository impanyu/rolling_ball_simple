"""Generate player-specific rules from historical Kalshi price data.

Each rule: (player, condition) → (win_rate, sample_size, baseline, edge)
"""
import logging
import sqlite3
from collections import defaultdict

logger = logging.getLogger(__name__)


def generate_all_rules(db_path: str, min_matches: int = 5, max_rank: int = 200) -> list[dict]:
    """Generate rules for all players with enough data."""
    db = sqlite3.connect(db_path, timeout=60)

    # Load all match data
    all_data = db.execute('''
        SELECT match_id, player, minute, current_price, max_price_after,
               running_min, running_max, initial_price, player_ranking,
               COALESCE(won, CASE WHEN max_price_after >= 99 THEN 1 ELSE 0 END) as won
        FROM extracted_data
        WHERE player_ranking IS NOT NULL AND player_ranking <= ?
          AND opponent_ranking IS NOT NULL AND opponent_ranking <= 2000
        ORDER BY match_id, player, minute
    ''', (max_rank,)).fetchall()
    db.close()

    # Group by player -> matches
    players = defaultdict(lambda: defaultdict(list))
    for mid, player, minute, cp, mpa, rmin, rmax, ip, rank, won in all_data:
        players[player][(mid,)].append({
            'minute': minute, 'cp': cp, 'mpa': mpa,
            'rmin': rmin, 'rmax': rmax, 'ip': ip, 'rank': rank, 'won': won,
        })

    # Compute global baselines first
    baselines = _compute_baselines(players)

    # Generate rules per player
    all_rules = []
    for player, match_dict in players.items():
        if len(match_dict) < min_matches:
            continue
        rank = list(match_dict.values())[0][0]['rank']
        rules = _generate_player_rules(player, rank, match_dict, baselines)
        all_rules.extend(rules)

    logger.info(f"Generated {len(all_rules)} rules for {len(set(r['player'] for r in all_rules))} players")
    return all_rules


def _compute_baselines(players):
    """Compute global average win rates for each condition type."""
    baselines = {}

    # Closeout baselines
    for threshold in [70, 80, 90]:
        total = wins = 0
        for player, match_dict in players.items():
            for match_key, prices in match_dict.items():
                max_price = max(p['cp'] for p in prices)
                won = prices[-1]['won']
                if max_price >= threshold:
                    total += 1
                    if won: wins += 1
        baselines[f'closeout_{threshold}'] = wins / total * 100 if total > 0 else 0

    # Comeback baselines
    for threshold in [30, 20, 10]:
        total = wins = 0
        for player, match_dict in players.items():
            for match_key, prices in match_dict.items():
                min_price = min(p['cp'] for p in prices)
                won = prices[-1]['won']
                if min_price <= threshold:
                    total += 1
                    if won: wins += 1
        baselines[f'comeback_{threshold}'] = wins / total * 100 if total > 0 else 0

    # Clutch baseline (close match at 50%)
    total = wins = 0
    for player, match_dict in players.items():
        for match_key, prices in match_dict.items():
            n = len(prices)
            mid_price = prices[n // 2]['cp']
            won = prices[-1]['won']
            if 40 <= mid_price <= 60:
                total += 1
                if won: wins += 1
    baselines['clutch'] = wins / total * 100 if total > 0 else 0

    # Favorite/underdog baselines
    for label, lo, hi in [('favorite', 55, 100), ('underdog', 0, 45)]:
        total = wins = 0
        for player, match_dict in players.items():
            for match_key, prices in match_dict.items():
                ip = prices[0]['ip']
                won = prices[-1]['won']
                if lo <= ip <= hi:
                    total += 1
                    if won: wins += 1
        baselines[label] = wins / total * 100 if total > 0 else 0

    return baselines


def _generate_player_rules(player, rank, match_dict, baselines):
    """Generate all rules for a single player."""
    rules = []
    matches = list(match_dict.values())
    total_matches = len(matches)
    total_wins = sum(1 for m in matches if m[-1]['won'] == 1)
    overall_wr = total_wins / total_matches * 100

    def add_rule(rule_type, condition, win_rate, sample_size, baseline_key):
        baseline = baselines.get(baseline_key, 50)
        edge = win_rate - baseline
        signal = 'strong_buy' if edge > 15 else 'buy' if edge > 5 else 'neutral' if edge > -5 else 'avoid' if edge > -15 else 'strong_avoid'
        rules.append({
            'player': player,
            'rank': rank,
            'rule_type': rule_type,
            'condition': condition,
            'win_rate': round(win_rate, 1),
            'sample_size': sample_size,
            'baseline': round(baseline, 1),
            'edge': round(edge, 1),
            'signal': signal,
        })

    # 1. Closeout rules
    for threshold in [70, 80, 90]:
        n = w = 0
        for m in matches:
            if max(p['cp'] for p in m) >= threshold:
                n += 1
                if m[-1]['won']: w += 1
        if n >= 3:
            add_rule('closeout', f'price_reached_{threshold}', w/n*100, n, f'closeout_{threshold}')

    # 2. Comeback rules
    for threshold in [30, 20, 10]:
        n = w = 0
        for m in matches:
            if min(p['cp'] for p in m) <= threshold:
                n += 1
                if m[-1]['won']: w += 1
        if n >= 3:
            add_rule('comeback', f'price_dropped_{threshold}', w/n*100, n, f'comeback_{threshold}')

    # 3. Clutch (close match at 50%)
    n = w = 0
    for m in matches:
        mid_price = m[len(m) // 2]['cp']
        if 40 <= mid_price <= 60:
            n += 1
            if m[-1]['won']: w += 1
    if n >= 3:
        add_rule('clutch', 'midmatch_40_60', w/n*100, n, 'clutch')

    # 4. Favorite performance
    n = w = 0
    for m in matches:
        if m[0]['ip'] > 55:
            n += 1
            if m[-1]['won']: w += 1
    if n >= 3:
        add_rule('as_favorite', 'init_above_55', w/n*100, n, 'favorite')

    # 5. Underdog performance
    n = w = 0
    for m in matches:
        if m[0]['ip'] < 45:
            n += 1
            if m[-1]['won']: w += 1
    if n >= 3:
        add_rule('as_underdog', 'init_below_45', w/n*100, n, 'underdog')

    # 6. Volatility profile
    vols = [max(p['cp'] for p in m) - min(p['cp'] for p in m) for m in matches]
    avg_vol = sum(vols) / len(vols)
    if avg_vol < 35:
        add_rule('volatility', 'stable_player', overall_wr, total_matches, 'favorite')
    elif avg_vol > 55:
        add_rule('volatility', 'volatile_player', overall_wr, total_matches, 'favorite')

    # 7. After big lead (reached 90+ then dropped back)
    n = w = 0
    for m in matches:
        reached_90 = False
        dropped_back = False
        for p in m:
            if p['cp'] >= 90:
                reached_90 = True
            if reached_90 and p['cp'] < 80:
                dropped_back = True
        if reached_90 and dropped_back:
            n += 1
            if m[-1]['won']: w += 1
    if n >= 3:
        add_rule('after_big_lead', 'reached_90_dropped_80', w/n*100, n, f'closeout_90')

    # 8. Comeback from big deficit (below 20 then reached 60+)
    n = w = 0
    for m in matches:
        was_low = False
        recovered = False
        for p in m:
            if p['cp'] <= 20:
                was_low = True
            if was_low and p['cp'] >= 60:
                recovered = True
        if was_low and recovered:
            n += 1
            if m[-1]['won']: w += 1
    if n >= 3:
        add_rule('strong_comeback', 'below_20_reached_60', w/n*100, n, f'comeback_20')

    # 9. Momentum after break (price drops > 15 in 10 min)
    n_drop = w_drop = 0
    n_surge = w_surge = 0
    for m in matches:
        for i in range(10, len(m)):
            change = m[i]['cp'] - m[i-10]['cp']
            if change < -15:
                n_drop += 1
                if m[-1]['won']: w_drop += 1
                break
            if change > 15:
                n_surge += 1
                if m[-1]['won']: w_surge += 1
                break
    if n_drop >= 3:
        add_rule('after_price_drop', 'drop_15_in_10min', w_drop/n_drop*100, n_drop, 'favorite')
    if n_surge >= 3:
        add_rule('after_price_surge', 'surge_15_in_10min', w_surge/n_surge*100, n_surge, 'favorite')

    return rules


def store_rules(db_path: str, rules: list[dict]):
    """Store rules in database."""
    db = sqlite3.connect(db_path, timeout=60)
    db.execute("""CREATE TABLE IF NOT EXISTS player_rules (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        player TEXT NOT NULL,
        rank INTEGER,
        rule_type TEXT NOT NULL,
        condition TEXT NOT NULL,
        win_rate REAL,
        sample_size INTEGER,
        baseline REAL,
        edge REAL,
        signal TEXT,
        updated_at TEXT,
        UNIQUE(player, rule_type, condition)
    )""")
    db.execute("DELETE FROM player_rules")

    from datetime import datetime
    now = datetime.utcnow().isoformat() + "Z"

    for r in rules:
        db.execute(
            """INSERT OR REPLACE INTO player_rules
               (player, rank, rule_type, condition, win_rate, sample_size, baseline, edge, signal, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (r['player'], r['rank'], r['rule_type'], r['condition'],
             r['win_rate'], r['sample_size'], r['baseline'], r['edge'], r['signal'], now),
        )
    db.commit()
    db.close()
    logger.info(f"Stored {len(rules)} rules")


def get_player_rules(db_path: str, player: str) -> list[dict]:
    """Get all rules for a player."""
    db = sqlite3.connect(db_path, timeout=60)
    rows = db.execute(
        "SELECT * FROM player_rules WHERE player = ? ORDER BY abs(edge) DESC",
        (player,)
    ).fetchall()
    db.close()
    cols = ['id', 'player', 'rank', 'rule_type', 'condition', 'win_rate', 'sample_size', 'baseline', 'edge', 'signal', 'updated_at']
    return [dict(zip(cols, r)) for r in rows]


def match_rules_to_state(db_path: str, player: str, state: dict) -> list[dict]:
    """Given current match state, find which rules are triggered."""
    rules = get_player_rules(db_path, player)
    triggered = []

    cp = state.get('current_price', 0)
    ip = state.get('init_price', 0)
    rmin = state.get('running_min', 0)
    rmax = state.get('running_max', 0)

    for rule in rules:
        rt = rule['rule_type']
        cond = rule['condition']

        match = False
        if rt == 'closeout' and 'price_reached_' in cond:
            threshold = int(cond.split('_')[-1])
            if rmax >= threshold:
                match = True
        elif rt == 'comeback' and 'price_dropped_' in cond:
            threshold = int(cond.split('_')[-1])
            if rmin <= threshold:
                match = True
        elif rt == 'clutch' and 40 <= cp <= 60:
            match = True
        elif rt == 'as_favorite' and ip > 55:
            match = True
        elif rt == 'as_underdog' and ip < 45:
            match = True
        elif rt == 'volatility':
            match = True  # Always applicable
        elif rt == 'after_big_lead' and rmax >= 90 and cp < 80:
            match = True
        elif rt == 'strong_comeback' and rmin <= 20 and cp >= 60:
            match = True
        elif rt == 'after_price_drop':
            match = True  # Would need recent price history to check properly
        elif rt == 'after_price_surge':
            match = True

        if match:
            triggered.append(rule)

    return triggered
