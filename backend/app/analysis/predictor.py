"""Rule-based prediction system with train/test backtesting.

Flow:
1. Split data by time (train/test)
2. Generate player rules from train data
3. For each match in test, at tradeable moments, predict using rules
4. Compare prediction to outcome, compute P&L
"""
import logging
import sqlite3
import math
from collections import defaultdict
from datetime import datetime

logger = logging.getLogger(__name__)


# ─── Rule Generation ───

CLOSEOUT_THRESHOLDS = [70, 80, 90]
COMEBACK_THRESHOLDS = [30, 20, 10]


def _extract_match_features(prices):
    """Extract all features from a match's price path."""
    if not prices:
        return None

    n = len(prices)
    won = prices[-1]['won']
    ip = prices[0]['ip']
    cps = [p['cp'] for p in prices]
    min_price = min(cps)
    max_price = max(cps)
    vol = max_price - min_price
    mid_price = cps[n // 2]

    # Recent trend at 75% mark
    idx_75 = int(n * 0.75)
    price_75 = cps[idx_75] if idx_75 < n else cps[-1]

    # Max single drop and surge (over 10-min windows)
    max_drop = 0
    max_surge = 0
    for i in range(10, n):
        change = cps[i] - cps[i - 10]
        if change < max_drop:
            max_drop = change
        if change > max_surge:
            max_surge = change

    # Time from first reaching 80/90 to end
    first_80 = first_90 = None
    for i, cp in enumerate(cps):
        if cp >= 80 and first_80 is None:
            first_80 = i
        if cp >= 90 and first_90 is None:
            first_90 = i

    # Reached high then dropped back
    reached_90_dropped_80 = max_price >= 90 and any(
        cps[j] < 80 for j in range(n) if cps[j] < 80 and any(cps[k] >= 90 for k in range(j))
    )

    # Below 20 then recovered to 60+
    below_20_reached_60 = min_price <= 20 and any(
        cps[j] >= 60 for j in range(n) if cps[j] >= 60 and any(cps[k] <= 20 for k in range(j))
    )

    # Count revisits to 50-60 zone
    in_zone = False
    revisit_count = 0
    for cp in cps:
        if 50 <= cp <= 60:
            if not in_zone:
                revisit_count += 1
                in_zone = True
        else:
            in_zone = False

    return {
        'won': won, 'ip': ip, 'min_price': min_price, 'max_price': max_price,
        'vol': vol, 'mid_price': mid_price, 'price_75': price_75,
        'max_drop': max_drop, 'max_surge': max_surge,
        'first_80_idx': first_80, 'first_90_idx': first_90,
        'match_len': n,
        'reached_90_dropped_80': reached_90_dropped_80,
        'below_20_reached_60': below_20_reached_60,
        'revisit_count': revisit_count,
        'opp_rank': None,  # Will be filled by caller
        'rank_gap': None,  # Will be filled by caller
    }


def generate_rules_from_matches(player, match_features, baselines):
    """Generate rules for one player from their match features."""
    rules = []
    total = len(match_features)
    if total < 3:
        return rules

    def add(rule_type, condition, n, w, baseline_key):
        if n < 3:
            return
        wr = w / n * 100
        base = baselines.get(baseline_key, 50)
        edge = wr - base
        rules.append({
            'rule_type': rule_type, 'condition': condition,
            'win_rate': round(wr, 1), 'sample_size': n,
            'baseline': round(base, 1), 'edge': round(edge, 1),
        })

    # Closeout
    for t in CLOSEOUT_THRESHOLDS:
        n = sum(1 for f in match_features if f['max_price'] >= t)
        w = sum(1 for f in match_features if f['max_price'] >= t and f['won'])
        add('closeout', f'reached_{t}', n, w, f'closeout_{t}')

    # Comeback
    for t in COMEBACK_THRESHOLDS:
        n = sum(1 for f in match_features if f['min_price'] <= t)
        w = sum(1 for f in match_features if f['min_price'] <= t and f['won'])
        add('comeback', f'dropped_{t}', n, w, f'comeback_{t}')

    # Clutch
    n = sum(1 for f in match_features if 40 <= f['mid_price'] <= 60)
    w = sum(1 for f in match_features if 40 <= f['mid_price'] <= 60 and f['won'])
    add('clutch', 'midmatch_40_60', n, w, 'clutch')

    # As favorite / underdog
    n = sum(1 for f in match_features if f['ip'] > 55)
    w = sum(1 for f in match_features if f['ip'] > 55 and f['won'])
    add('as_favorite', 'init_gt_55', n, w, 'favorite')

    n = sum(1 for f in match_features if f['ip'] < 45)
    w = sum(1 for f in match_features if f['ip'] < 45 and f['won'])
    add('as_underdog', 'init_lt_45', n, w, 'underdog')

    # Volatility
    avg_vol = sum(f['vol'] for f in match_features) / total
    overall_wr = sum(f['won'] for f in match_features) / total * 100
    if avg_vol < 35:
        add('volatility', 'stable', total, sum(f['won'] for f in match_features), 'overall')
    elif avg_vol > 55:
        add('volatility', 'volatile', total, sum(f['won'] for f in match_features), 'overall')

    # After big lead collapse
    n = sum(1 for f in match_features if f['reached_90_dropped_80'])
    w = sum(1 for f in match_features if f['reached_90_dropped_80'] and f['won'])
    add('lead_collapse', 'reached_90_dropped_80', n, w, 'closeout_90')

    # Strong comeback
    n = sum(1 for f in match_features if f['below_20_reached_60'])
    w = sum(1 for f in match_features if f['below_20_reached_60'] and f['won'])
    add('strong_comeback', 'below_20_reached_60', n, w, 'comeback_20')

    # Big drop resilience
    for drop in [15, 20, 30]:
        n = sum(1 for f in match_features if f['max_drop'] < -drop)
        w = sum(1 for f in match_features if f['max_drop'] < -drop and f['won'])
        add('drop_resilience', f'survived_drop_{drop}', n, w, 'overall')

    # Late game strength (leading at 75%)
    for t in [60, 70, 80]:
        n = sum(1 for f in match_features if f['price_75'] >= t)
        w = sum(1 for f in match_features if f['price_75'] >= t and f['won'])
        add('late_strength', f'price_75pct_gte_{t}', n, w, f'closeout_{t}' if t >= 70 else 'overall')

    # Big surge ability
    for surge in [15, 20, 30]:
        n = sum(1 for f in match_features if f['max_surge'] > surge)
        w = sum(1 for f in match_features if f['max_surge'] > surge and f['won'])
        add('surge_ability', f'surge_gt_{surge}', n, w, 'overall')

    # Control speed: how quickly they reach 80 (as % of match length)
    fast_control = [f for f in match_features if f['first_80_idx'] is not None and f['match_len'] > 10]
    if len(fast_control) >= 3:
        speed_pcts = [f['first_80_idx'] / f['match_len'] for f in fast_control]
        avg_speed = sum(speed_pcts) / len(speed_pcts)
        if avg_speed < 0.3:
            add('control_speed', 'fast_to_80',
                sum(f['won'] for f in fast_control) / len(fast_control) * 100,
                len(fast_control), 'overall')
        elif avg_speed > 0.6:
            add('control_speed', 'slow_to_80',
                sum(f['won'] for f in fast_control) / len(fast_control) * 100,
                len(fast_control), 'overall')

    # First half vs second half performance
    first_half_leaders = [f for f in match_features if f['mid_price'] >= 60]
    second_half_closers = [f for f in match_features if f['mid_price'] >= 60 and f['price_75'] >= 70]
    if len(first_half_leaders) >= 3:
        n = len(first_half_leaders)
        w = sum(f['won'] for f in first_half_leaders)
        add('first_half_lead', 'leading_at_50pct', w/n*100, n, 'overall')
    if len(second_half_closers) >= 3:
        n = len(second_half_closers)
        w = sum(f['won'] for f in second_half_closers)
        add('second_half_close', 'leading_50pct_and_75pct', w/n*100, n, 'overall')

    # Opponent rank tiers
    for rk_lo, rk_hi, label in [(1, 20, 'vs_top20'), (20, 50, 'vs_top50'), (50, 100, 'vs_top100'), (100, 500, 'vs_rank100_500')]:
        subset = [f for f in match_features if f.get('opp_rank') and rk_lo <= f['opp_rank'] < rk_hi]
        if len(subset) >= 3:
            n = len(subset)
            w = sum(f['won'] for f in subset)
            add('vs_rank_tier', label, w/n*100, n, 'overall')

    # Rank gap performance
    close_rank = [f for f in match_features if f.get('rank_gap') and abs(f['rank_gap']) < 20]
    wide_rank = [f for f in match_features if f.get('rank_gap') and abs(f['rank_gap']) > 50]
    if len(close_rank) >= 3:
        add('rank_gap', 'close_rank_lt20',
            sum(f['won'] for f in close_rank) / len(close_rank) * 100,
            len(close_rank), 'overall')
    if len(wide_rank) >= 3:
        add('rank_gap', 'wide_rank_gt50',
            sum(f['won'] for f in wide_rank) / len(wide_rank) * 100,
            len(wide_rank), 'overall')

    # Revisit pattern: how often they revisit price zones
    revisit_matches = [f for f in match_features if f.get('revisit_count', 0) > 2]
    if len(revisit_matches) >= 3:
        n = len(revisit_matches)
        w = sum(f['won'] for f in revisit_matches)
        add('revisit_pattern', 'frequent_revisitor', w/n*100, n, 'overall')

    return rules


# ─── Prediction ───

def compute_score(triggered_rules, min_sample=3):
    """Compute total score from triggered rules.

    Each rule: score = (win_rate - 50) * sqrt(sample_size)
    Positive = player likely to win, negative = likely to lose.
    """
    total = 0
    for r in triggered_rules:
        if r['sample_size'] < min_sample:
            continue
        total += (r['win_rate'] - 50) * math.sqrt(r['sample_size'])
    return round(total, 1)


def match_rules_to_state(rules, state):
    """Given current match state, find which rules are triggered."""
    triggered = []
    cp = state.get('current_price', 50)
    ip = state.get('init_price', 50)
    rmin = state.get('running_min', cp)
    rmax = state.get('running_max', cp)
    vol = rmax - rmin
    elapsed_pct = state.get('elapsed_pct', 0.5)

    for rule in rules:
        rt = rule['rule_type']
        cond = rule['condition']
        match = False

        if rt == 'closeout':
            threshold = int(cond.split('_')[-1])
            if rmax >= threshold:
                match = True
        elif rt == 'comeback':
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
            if ('stable' in cond and vol < 35) or ('volatile' in cond and vol > 55):
                match = True
        elif rt == 'lead_collapse' and rmax >= 90 and cp < 80:
            match = True
        elif rt == 'strong_comeback' and rmin <= 20 and cp >= 60:
            match = True
        elif rt == 'drop_resilience':
            drop = int(cond.split('_')[-1])
            if (rmax - rmin) >= drop:
                match = True
        elif rt == 'late_strength' and elapsed_pct >= 0.7:
            threshold = int(cond.split('_')[-1])
            if cp >= threshold:
                match = True
        elif rt == 'surge_ability':
            surge = int(cond.split('_')[-1])
            if (rmax - rmin) >= surge:
                match = True
        elif rt == 'control_speed':
            match = True  # Profile trait, always applicable
        elif rt == 'first_half_lead' and elapsed_pct >= 0.4 and cp >= 60:
            match = True
        elif rt == 'second_half_close' and elapsed_pct >= 0.7 and cp >= 70:
            match = True
        elif rt == 'vs_rank_tier':
            match = True  # Profile trait
        elif rt == 'rank_gap':
            match = True  # Profile trait
        elif rt == 'revisit_pattern':
            match = True  # Profile trait

        if match:
            triggered.append(rule)

    return triggered


# ─── Backtesting ───

def backtest(db_path, train_cutoff_pct=0.7, trade_price_lo=None, trade_price_hi=None, min_trades=50):
    """Run full backtest: train rules on early data, test on later data."""
    db = sqlite3.connect(db_path)

    # Load all data
    all_data = db.execute('''
        SELECT match_id, player, opponent, minute, current_price, max_price_after,
               running_min, running_max, initial_price, player_ranking, opponent_ranking,
               match_date,
               COALESCE(won, CASE WHEN max_price_after >= 99 THEN 1 ELSE 0 END) as won
        FROM extracted_data
        WHERE player_ranking IS NOT NULL AND player_ranking <= 500
          AND opponent_ranking IS NOT NULL AND opponent_ranking <= 2000
        ORDER BY match_id, player, minute
    ''').fetchall()
    db.close()

    # Group by match+player
    matches = defaultdict(list)
    for row in all_data:
        mid, player, opponent = row[0], row[1], row[2]
        matches[(mid, player, opponent)].append({
            'minute': row[3], 'cp': row[4], 'mpa': row[5],
            'rmin': row[6], 'rmax': row[7], 'ip': row[8],
            'p_rank': row[9], 'o_rank': row[10], 'date': row[11], 'won': row[12],
        })

    # Sort matches by date
    sorted_keys = sorted(matches.keys(), key=lambda k: matches[k][0]['date'] if len(matches[k]) > 0 else '0')
    cutoff_idx = int(len(sorted_keys) * train_cutoff_pct)
    train_keys = sorted_keys[:cutoff_idx]
    test_keys = sorted_keys[cutoff_idx:]

    logger.info(f"Train: {len(train_keys)} match-sides, Test: {len(test_keys)} match-sides")
    if train_keys:
        logger.info(f"Train dates: {matches[train_keys[0]][0]['date']} to {matches[train_keys[-1]][0]['date']}")
    if test_keys:
        logger.info(f"Test dates: {matches[test_keys[0]][0]['date']} to {matches[test_keys[-1]][0]['date']}")

    # ─── Train: generate rules ───
    player_match_features = defaultdict(list)
    all_train_features = []

    for key in train_keys:
        mid, player, opponent = key
        prices = matches[key]
        features = _extract_match_features(prices)
        if features:
            features['opp_rank'] = prices[0].get('o_rank')
            p_rank = prices[0].get('p_rank')
            o_rank = prices[0].get('o_rank')
            features['rank_gap'] = (o_rank - p_rank) if p_rank and o_rank else None
            player_match_features[player].append(features)
            all_train_features.append(features)

    # Compute baselines from train data
    baselines = {}
    for t in CLOSEOUT_THRESHOLDS:
        n = sum(1 for f in all_train_features if f['max_price'] >= t)
        w = sum(1 for f in all_train_features if f['max_price'] >= t and f['won'])
        baselines[f'closeout_{t}'] = w / n * 100 if n > 0 else 50
    for t in COMEBACK_THRESHOLDS:
        n = sum(1 for f in all_train_features if f['min_price'] <= t)
        w = sum(1 for f in all_train_features if f['min_price'] <= t and f['won'])
        baselines[f'comeback_{t}'] = w / n * 100 if n > 0 else 50
    n = sum(1 for f in all_train_features if 40 <= f['mid_price'] <= 60)
    w = sum(1 for f in all_train_features if 40 <= f['mid_price'] <= 60 and f['won'])
    baselines['clutch'] = w / n * 100 if n > 0 else 50
    n = sum(1 for f in all_train_features if f['ip'] > 55)
    w = sum(1 for f in all_train_features if f['ip'] > 55 and f['won'])
    baselines['favorite'] = w / n * 100 if n > 0 else 50
    n = sum(1 for f in all_train_features if f['ip'] < 45)
    w = sum(1 for f in all_train_features if f['ip'] < 45 and f['won'])
    baselines['underdog'] = w / n * 100 if n > 0 else 50
    total_w = sum(f['won'] for f in all_train_features)
    baselines['overall'] = total_w / len(all_train_features) * 100 if all_train_features else 50

    # Generate rules per player
    player_rules = {}
    for player, features in player_match_features.items():
        rules = generate_rules_from_matches(player, features, baselines)
        if rules:
            player_rules[player] = rules

    logger.info(f"Generated rules for {len(player_rules)} players")

    # ─── Get trade counts per match for liquidity filter ───
    db2 = sqlite3.connect(db_path)
    trade_counts = {}
    for row in db2.execute("SELECT match_id, COUNT(*) FROM raw_prices GROUP BY match_id"):
        trade_counts[row[0]] = row[1]
    db2.close()

    # ─── Test: simulate real-time trading ───
    trades = []
    for key in test_keys:
        mid, player, opponent = key
        prices = matches[key]
        if not prices or len(prices) < 5:
            continue

        won = prices[-1]['won']
        ip = prices[0]['ip']
        p_rank = prices[0]['p_rank']
        o_rank = prices[0]['o_rank']

        # Only consider ranked-higher player
        if not (p_rank and o_rank and p_rank < o_rank):
            continue

        # Liquidity filter
        if trade_counts.get(mid, 0) < min_trades:
            continue

        a_rules = player_rules.get(player, [])
        b_rules = player_rules.get(opponent, [])

        # Walk through the match, trade based on signal strength
        last_side = None
        last_trade_minute = -10  # cooldown between trades
        for i, p in enumerate(prices):
            cp = p['cp']
            if cp < 5 or cp > 95:
                continue
            # Cooldown: at least 5 minutes between trades
            if p['minute'] - last_trade_minute < 5:
                continue

            state = {
                'current_price': cp,
                'init_price': ip,
                'running_min': p['rmin'],
                'running_max': p['rmax'],
                'elapsed_pct': i / len(prices),
            }

            a_triggered = match_rules_to_state(a_rules, state)
            opp_state = {
                'current_price': 100 - cp,
                'init_price': 100 - ip,
                'running_min': 100 - p['rmax'],
                'running_max': 100 - p['rmin'],
                'elapsed_pct': state['elapsed_pct'],
            }
            b_triggered = match_rules_to_state(b_rules, opp_state)

            a_score = compute_score(a_triggered)
            b_score = compute_score(b_triggered)
            score_diff = a_score - b_score  # positive = A stronger

            abs_diff = abs(score_diff)

            if score_diff > 0:
                side = 'A'
                buy_price = cp
                trade_won = won
            else:
                side = 'B'
                buy_price = 100 - cp
                trade_won = 1 - won

            trades.append({
                'match_id': mid, 'player': player, 'opponent': opponent,
                'side': side, 'buy_price': buy_price, 'won': trade_won,
                'a_score': a_score, 'b_score': b_score,
                'net_edge': round(abs_diff, 1), 'size': 1,
                'a_rules_count': len(a_triggered), 'b_rules_count': len(b_triggered),
                'elapsed_pct': round(i / len(prices), 2),
            })
            last_trade_minute = p['minute']
            last_side = side

    logger.info(f"Test trades: {len(trades)}")

    # ─── Evaluate ───
    results = {'thresholds': {}}
    for threshold in [3, 5, 8, 10, 15]:
        # Buy when net_edge > threshold
        buy_trades = [t for t in trades if t['net_edge'] > threshold]
        if not buy_trades:
            results['thresholds'][threshold] = {'n': 0}
            continue

        wins = sum(1 for t in buy_trades if t['won'])
        total = len(buy_trades)
        win_rate = wins / total * 100
        avg_price = sum(t['buy_price'] for t in buy_trades) / total
        # P&L: win = (100 - buy_price - 2) * size, lose = -(buy_price + 2) * size
        pnl = sum(((100 - t['buy_price'] - 2) if t['won'] else (-(t['buy_price'] + 2))) * t.get('size', 1) for t in buy_trades)
        avg_pnl = pnl / total

        results['thresholds'][threshold] = {
            'n': total, 'wins': wins, 'win_rate': round(win_rate, 1),
            'avg_price': round(avg_price, 1),
            'total_pnl': round(pnl, 1), 'avg_pnl': round(avg_pnl, 1),
        }

    # Also: no-rule baseline (buy everything in range)
    all_in_range = [t for t in trades]
    if all_in_range:
        wins = sum(1 for t in all_in_range if t['won'])
        pnl = sum((100 - t['buy_price'] - 2) if t['won'] else (-t['buy_price']) for t in all_in_range)
        results['baseline'] = {
            'n': len(all_in_range), 'wins': wins,
            'win_rate': round(wins / len(all_in_range) * 100, 1),
            'total_pnl': round(pnl, 1),
            'avg_pnl': round(pnl / len(all_in_range), 1),
        }

    results['train_matches'] = len(train_keys)
    results['test_matches'] = len(test_keys)
    results['players_with_rules'] = len(player_rules)
    results['total_test_trades'] = len(trades)
    results['trades'] = trades
    results['baselines'] = baselines

    return results


def backtest_multi_range(db_path, train_cutoff_pct=0.7):
    """Run backtest across multiple buy price ranges."""
    all_results = {}
    for lo, hi in [(60, 65), (65, 70), (70, 75), (75, 80), (80, 85), (85, 90), (87, 91)]:
        r = backtest(db_path, train_cutoff_pct, trade_price_lo=lo, trade_price_hi=hi)
        all_results[(lo, hi)] = r
    return all_results
