"""V2 predictor with richer features and better aggregation."""
import logging
import sqlite3
import math
from collections import defaultdict

logger = logging.getLogger(__name__)


def _extract_features_at(prices, up_to):
    """Extract features from prices[0:up_to] — only data observable at that moment.

    Each call represents a snapshot: "given what we've seen up to minute `up_to`,
    what features can we observe?" The label (won) is always the final outcome.
    """
    partial = prices[:up_to]
    if len(partial) < 3:
        return None

    cps = [p['cp'] for p in partial]
    n = len(cps)
    won = prices[-1]['won']
    ip = partial[0]['ip']
    cp = cps[-1]
    min_p = min(cps)
    max_p = max(cps)
    vol = max_p - min_p
    minutes = n

    # Recent changes at multiple windows
    lookback = max(0, n - 10)
    recent_change = cp - cps[lookback]
    change_5 = cp - cps[max(0, n - 5)]
    change_20 = cp - cps[max(0, n - 20)]

    # Max drop/surge in any 10-min window so far
    max_drop = max_surge = 0
    for i in range(10, n):
        change = cps[i] - cps[i - 10]
        max_drop = min(max_drop, change)
        max_surge = max(max_surge, change)

    # Break response: after drops > 15, how quickly does price recover 10 pts?
    break_recoveries = []
    i = 10
    while i < n:
        if cps[i] - cps[i - 10] < -15:
            low = cps[i]
            for j in range(i + 1, min(i + 30, n)):
                if cps[j] >= low + 10:
                    break_recoveries.append(j - i)
                    break
            i += 10
        else:
            i += 1
    avg_break_recovery = sum(break_recoveries) / len(break_recoveries) if break_recoveries else None

    # Tiebreak proxy: price stayed in 40-60 for 20+ consecutive minutes
    tiebreak_count = 0
    consecutive_close = 0
    for c in cps:
        if 40 <= c <= 60:
            consecutive_close += 1
            if consecutive_close == 20:
                tiebreak_count += 1
        else:
            consecutive_close = 0

    # Shape (outcome-independent, based on path so far)
    if vol < 30 and max_p >= 70:
        shape = 'dominant'
    elif min_p <= 30 and cp >= 50:
        shape = 'comeback'
    elif max_p >= 70 and cp < max_p - 20:
        shape = 'collapse'
    elif vol < 40:
        shape = 'close'
    else:
        shape = 'volatile'

    # Momentum streaks so far
    up_streaks = down_streaks = 0
    streak = 0
    for i in range(1, n):
        d = cps[i] - cps[i - 1]
        if d > 1:
            streak = streak + 1 if streak > 0 else 1
            up_streaks = max(up_streaks, streak)
        elif d < -1:
            streak = streak - 1 if streak < 0 else -1
            down_streaks = max(down_streaks, -streak)
        else:
            streak = 0

    # Change from start
    change_from_start = cp - cps[0]

    # Multi-window trend confirmation
    trend_up = change_5 > 2 and recent_change > 3 and change_20 > 5
    trend_down = change_5 < -2 and recent_change < -3 and change_20 < -5

    # Lead changes: how many times price crossed 50
    lead_changes = 0
    for i in range(1, n):
        if (cps[i-1] < 50 and cps[i] >= 50) or (cps[i-1] >= 50 and cps[i] < 50):
            lead_changes += 1

    # Current trend duration: how many consecutive minutes in same direction
    current_trend_len = 0
    if n >= 2:
        direction = 1 if cps[-1] >= cps[-2] else -1
        for i in range(n - 2, -1, -1):
            d = 1 if cps[i + 1] >= cps[i] else -1
            if d == direction:
                current_trend_len += 1
            else:
                break

    # Recent stability: std of last 10 minutes
    recent_cps = cps[max(0, n - 10):]
    recent_mean = sum(recent_cps) / len(recent_cps)
    recent_std = (sum((c - recent_mean) ** 2 for c in recent_cps) / len(recent_cps)) ** 0.5

    # ── Statistical features ──
    mean_p = sum(cps) / n
    std_p = (sum((c - mean_p) ** 2 for c in cps) / n) ** 0.5 if n > 1 else 0
    cp_vs_mean = cp - mean_p

    # Fraction of time leading (price > 50)
    pct_leading = sum(1 for c in cps if c > 50) / n

    # Price acceleration (recent change vs prior change)
    if n >= 20:
        prev_change = cps[n - 10] - cps[n - 20]
        acceleration = recent_change - prev_change
    else:
        acceleration = 0

    # Comeback ratio: how much of the drop has been recovered
    if max_p > ip and min_p < ip:
        comeback_ratio = (cp - min_p) / (max_p - min_p) if max_p > min_p else 0.5
    else:
        comeback_ratio = 0.5

    # Time bin
    if minutes <= 30:
        time_bin = 'early'
    elif minutes <= 60:
        time_bin = 'mid'
    else:
        time_bin = 'late'

    return {
        'won': won, 'ip': ip, 'current_price': cp,
        'min_price': min_p, 'max_price': max_p, 'vol': vol,
        'minutes': minutes, 'time_bin': time_bin,
        'recent_change': recent_change, 'change_from_start': change_from_start,
        'max_drop': max_drop, 'max_surge': max_surge,
        'shape': shape,
        'avg_break_recovery': avg_break_recovery,
        'tiebreak_count': tiebreak_count,
        'up_streaks': up_streaks, 'down_streaks': down_streaks,
        'mean_price': mean_p, 'std_price': std_p,
        'cp_vs_mean': cp_vs_mean, 'pct_leading': pct_leading,
        'acceleration': acceleration, 'comeback_ratio': comeback_ratio,
        'change_5': change_5, 'change_20': change_20,
        'trend_up': trend_up, 'trend_down': trend_down,
        'lead_changes': lead_changes, 'current_trend_len': current_trend_len,
        'recent_std': recent_std,
        'opp_rank': None, 'rank_gap': None,
    }


def extract_match_samples(prices, interval=5, match_id=None):
    """Extract multiple feature snapshots from one match, every `interval` minutes.

    Each snapshot captures the state at that point. The `minutes` field
    carries exact time info so rules are time-aware without explicit gates.
    """
    samples = []
    n = len(prices)
    if n < 5:
        return samples
    for t in range(interval, n + 1, interval):
        feat = _extract_features_at(prices, t)
        if feat:
            if match_id:
                feat['match_id'] = match_id
            samples.append(feat)
    if not samples and n >= 5:
        feat = _extract_features_at(prices, n)
        if feat:
            if match_id:
                feat['match_id'] = match_id
            samples.append(feat)
    return samples


def _time_bucket(minutes):
    """Round minutes to nearest 5-min bucket for rule conditions."""
    return (minutes // 5) * 5


def _generate_rules(player, features, baselines):
    """Generate rules from multi-snapshot features.

    Rules carry time info via 5-min buckets in conditions (e.g., 'at_70_85_m30').
    Matching finds the closest time bucket to current minutes_played.
    """
    rules = []
    if len(features) < 5:
        return rules

    def add(category, condition, n, w, description=""):
        if n < 3:
            return
        rules.append({
            'category': category, 'condition': condition,
            'win_rate': round(w / n * 100, 1), 'sample_size': n,
            'description': description,
        })

    # ── Time-independent rules (same across all snapshots of a match) ──
    # Use only one snapshot per match to avoid inflating sample size.
    # Each feature carries a match_id if available; otherwise deduplicate
    # by taking only the first snapshot per unique (ip, opp_rank, won) combo.
    seen = set()
    unique_matches = []
    for f in features:
        key = f.get('match_id') or (f['ip'], f.get('opp_rank'), f['won'])
        if key not in seen:
            seen.add(key)
            unique_matches.append(f)

    for cond, filt in [('favorite', lambda f: f['ip'] > 55), ('underdog', lambda f: f['ip'] < 45)]:
        sub = [f for f in unique_matches if filt(f)]
        add('role', cond, len(sub), sum(f['won'] for f in sub), f'Win rate as {cond}')

    for rk_lo, rk_hi, label in [(1, 30, 'vs_top30'), (30, 100, 'vs_rank30_100'), (100, 500, 'vs_rank100_500')]:
        sub = [f for f in unique_matches if f.get('opp_rank') and rk_lo <= f['opp_rank'] < rk_hi]
        add('opponent', label, len(sub), sum(f['won'] for f in sub),
            f'Win rate vs rank {rk_lo}-{rk_hi}')

    for gap_lo, gap_hi, gap_label in [(-500, -100, 'big_underdog'), (-100, 0, 'slight_underdog'),
                                       (0, 100, 'slight_fav'), (100, 500, 'big_fav')]:
        sub = [f for f in unique_matches if f.get('rank_gap') is not None and gap_lo <= f['rank_gap'] < gap_hi]
        add('rank_gap', gap_label, len(sub), sum(f['won'] for f in sub),
            f'Rank gap {gap_label}')

    # ── Time-independent aggregate rules ──
    # "Did this ever happen in the match?" — each match counted once (first snapshot that matches)
    def add_ever(category, condition, filter_fn, description):
        seen_mid = set()
        n = w = 0
        for f in features:
            mid = f.get('match_id') or id(f)
            if mid in seen_mid:
                continue
            if filter_fn(f):
                seen_mid.add(mid)
                n += 1
                if f['won']: w += 1
        add(category, condition, n, w, description)

    for t in [70, 80, 90]:
        add_ever('closeout', f'reached_{t}', lambda f, t=t: f['max_price'] >= t,
                 f'Ever reached {t}')

    for t in [30, 20, 10]:
        add_ever('comeback', f'dropped_{t}', lambda f, t=t: f['min_price'] <= t,
                 f'Ever dropped to {t}')

    for drop in [15, 25]:
        add_ever('resilience', f'drop_{drop}', lambda f, d=drop: f['max_drop'] < -d,
                 f'Ever had {drop}+ drop')

    for rmax_t in [70, 80, 90]:
        for drop in [10, 20]:
            add_ever('pullback', f'from_{rmax_t}_drop_{drop}',
                     lambda f, r=rmax_t, d=drop: f['max_price'] >= r and f['current_price'] < r - d,
                     f'Reached {rmax_t}, dropped {drop}+')

    for ip_label, ip_lo, ip_hi in [('fav', 55, 100), ('even', 45, 55), ('dog', 0, 45)]:
        for cp_lo, cp_hi in [(5, 25), (25, 40), (40, 55), (55, 70), (70, 85), (85, 100)]:
            add_ever('init_current', f'{ip_label}_cp{cp_lo}_{cp_hi}',
                     lambda f, ilo=ip_lo, ihi=ip_hi, clo=cp_lo, chi=cp_hi: ilo <= f['ip'] < ihi and clo <= f['current_price'] < chi,
                     f'Init {ip_label}, ever at price {cp_lo}-{cp_hi}')

    for ip_label, ip_lo, ip_hi in [('fav', 55, 100), ('even', 45, 55), ('dog', 0, 45)]:
        for min_lo, min_hi in [(0, 15), (15, 30), (30, 45)]:
            add_ever('comeback_from', f'{ip_label}_min{min_lo}_{min_hi}',
                     lambda f, ilo=ip_lo, ihi=ip_hi, mlo=min_lo, mhi=min_hi: ilo <= f['ip'] < ihi and mlo <= f['min_price'] < mhi,
                     f'Init {ip_label}, ever dropped to {min_lo}-{min_hi}')

    # ── Time-aware rules (use all snapshots, bucketed by 5-min) ──
    # Group features by time bucket
    by_time = defaultdict(list)
    for f in features:
        tb = _time_bucket(f['minutes'])
        by_time[tb].append(f)

    for tb, tf in by_time.items():
        suffix = f'm{tb}'

        # Price level at this time
        for plo, phi in [(5, 25), (25, 40), (40, 55), (55, 70), (70, 85), (85, 100)]:
            sub = [f for f in tf if plo <= f['current_price'] < phi]
            add('price_level', f'at_{plo}_{phi}_{suffix}', len(sub),
                sum(f['won'] for f in sub),
                f'Win rate at price {plo}-{phi} at minute {tb}')

        # Closeout at this time
        for t in [70, 80, 90]:
            sub = [f for f in tf if f['max_price'] >= t]
            add('closeout', f'reached_{t}_{suffix}', len(sub),
                sum(f['won'] for f in sub), f'Win rate when reached {t} by minute {tb}')

        # Comeback at this time
        for t in [30, 20, 10]:
            sub = [f for f in tf if f['min_price'] <= t]
            add('comeback', f'dropped_{t}_{suffix}', len(sub),
                sum(f['won'] for f in sub), f'Win rate when dropped to {t} by minute {tb}')

        # Shape at this time
        for shape in ['dominant', 'comeback', 'collapse', 'close', 'volatile']:
            sub = [f for f in tf if f['shape'] == shape]
            add('shape', f'{shape}_{suffix}', len(sub),
                sum(f['won'] for f in sub), f'{shape} pattern at minute {tb}')

        # Momentum at this time
        sub = [f for f in tf if f['recent_change'] > 10]
        add('momentum', f'surging_{suffix}', len(sub),
            sum(f['won'] for f in sub), f'Price surging at minute {tb}')
        sub = [f for f in tf if f['recent_change'] < -10]
        add('momentum', f'dropping_{suffix}', len(sub),
            sum(f['won'] for f in sub), f'Price dropping at minute {tb}')

        # Trend from start
        sub_up = [f for f in tf if f['change_from_start'] > 10]
        sub_dn = [f for f in tf if f['change_from_start'] < -10]
        add('trend', f'up_{suffix}', len(sub_up),
            sum(f['won'] for f in sub_up), f'Up 10+ from start at minute {tb}')
        add('trend', f'down_{suffix}', len(sub_dn),
            sum(f['won'] for f in sub_dn), f'Down 10+ from start at minute {tb}')

        # Resilience at this time
        for drop in [15, 25]:
            sub = [f for f in tf if f['max_drop'] < -drop]
            add('resilience', f'drop_{drop}_{suffix}', len(sub),
                sum(f['won'] for f in sub), f'Survived {drop}+ drop by minute {tb}')

    # ── Tiebreak and break response (time-bucketed) ──
    for tb, tf in by_time.items():
        suffix = f'm{tb}'
        sub = [f for f in tf if f['tiebreak_count'] > 0]
        add('tiebreak', f'in_tiebreak_{suffix}', len(sub),
            sum(f['won'] for f in sub), f'Tiebreak observed by minute {tb}')

        fast = [f for f in tf if f['avg_break_recovery'] is not None and f['avg_break_recovery'] <= 5]
        slow = [f for f in tf if f['avg_break_recovery'] is not None and f['avg_break_recovery'] > 10]
        add('break_response', f'fast_recovery_{suffix}', len(fast),
            sum(f['won'] for f in fast), f'Fast break recovery by minute {tb}')
        add('break_response', f'slow_recovery_{suffix}', len(slow),
            sum(f['won'] for f in slow), f'Slow break recovery by minute {tb}')

        # ── Init × Current price cross (time-bucketed) ──
        for ip_label, ip_lo, ip_hi in [('fav', 55, 100), ('even', 45, 55), ('dog', 0, 45)]:
            for cp_lo, cp_hi in [(5, 25), (25, 40), (40, 55), (55, 70), (70, 85), (85, 100)]:
                sub = [f for f in tf if ip_lo <= f['ip'] < ip_hi and cp_lo <= f['current_price'] < cp_hi]
                add('init_current', f'{ip_label}_cp{cp_lo}_{cp_hi}_{suffix}', len(sub),
                    sum(f['won'] for f in sub),
                    f'Init {ip_label}, price {cp_lo}-{cp_hi} at minute {tb}')

        # ── Pullback: reached high but dropped back (time-bucketed) ──
        for rmax_t in [70, 80, 90]:
            for drop in [10, 20]:
                sub = [f for f in tf if f['max_price'] >= rmax_t and f['current_price'] < rmax_t - drop]
                add('pullback', f'from_{rmax_t}_drop_{drop}_{suffix}', len(sub),
                    sum(f['won'] for f in sub),
                    f'Reached {rmax_t}, dropped {drop}+ at minute {tb}')

        # ── Init × Min price (comeback from low as fav/dog, time-bucketed) ──
        for ip_label, ip_lo, ip_hi in [('fav', 55, 100), ('even', 45, 55), ('dog', 0, 45)]:
            for min_lo, min_hi in [(0, 15), (15, 30), (30, 45)]:
                sub = [f for f in tf if ip_lo <= f['ip'] < ip_hi and min_lo <= f['min_price'] < min_hi]
                add('comeback_from', f'{ip_label}_min{min_lo}_{min_hi}_{suffix}', len(sub),
                    sum(f['won'] for f in sub),
                    f'Init {ip_label}, dropped to {min_lo}-{min_hi} by minute {tb}')

        # ── Lead changes (time-bucketed) ──
        for lc_lo, lc_hi, lc_label in [(0, 1, 'no_lead_change'), (1, 3, 'few_lead_changes'), (3, 20, 'many_lead_changes')]:
            sub = [f for f in tf if lc_lo <= f['lead_changes'] < lc_hi]
            add('lead_changes', f'{lc_label}_{suffix}', len(sub),
                sum(f['won'] for f in sub), f'{lc_label} by minute {tb}')

        # ── Current trend duration (time-bucketed) ──
        sub = [f for f in tf if f['current_trend_len'] >= 10]
        add('trend_duration', f'long_run_{suffix}', len(sub),
            sum(f['won'] for f in sub), f'10+ min same direction at minute {tb}')
        sub = [f for f in tf if f['current_trend_len'] <= 2 and f['vol'] > 10]
        add('trend_duration', f'choppy_{suffix}', len(sub),
            sum(f['won'] for f in sub), f'Choppy (no sustained direction) at minute {tb}')

        # ── Recent stability (time-bucketed) ──
        for rs_lo, rs_hi, rs_label in [(0, 3, 'very_stable'), (3, 8, 'stable'), (8, 20, 'unstable')]:
            sub = [f for f in tf if rs_lo <= f['recent_std'] < rs_hi]
            add('recent_stability', f'{rs_label}_{suffix}', len(sub),
                sum(f['won'] for f in sub), f'Recent std {rs_label} at minute {tb}')

        # ── Trend features (time-bucketed) ──
        # Multi-window confirmed trend
        sub = [f for f in tf if f['trend_up']]
        add('confirmed_trend', f'up_{suffix}', len(sub),
            sum(f['won'] for f in sub), f'Confirmed uptrend at minute {tb}')
        sub = [f for f in tf if f['trend_down']]
        add('confirmed_trend', f'down_{suffix}', len(sub),
            sum(f['won'] for f in sub), f'Confirmed downtrend at minute {tb}')

        # Streak length
        sub = [f for f in tf if f['up_streaks'] >= 8]
        add('streak', f'up8_{suffix}', len(sub),
            sum(f['won'] for f in sub), f'8+ min up streak by minute {tb}')
        sub = [f for f in tf if f['down_streaks'] >= 8]
        add('streak', f'down8_{suffix}', len(sub),
            sum(f['won'] for f in sub), f'8+ min down streak by minute {tb}')

        # 20-min change buckets
        for c_lo, c_hi, c_label in [(-50, -15, 'big_drop_20'), (-15, -5, 'drop_20'),
                                      (5, 15, 'rise_20'), (15, 50, 'big_rise_20')]:
            sub = [f for f in tf if c_lo <= f['change_20'] < c_hi]
            add('change_20', f'{c_label}_{suffix}', len(sub),
                sum(f['won'] for f in sub), f'20-min change {c_label} at minute {tb}')

        # ── Statistical features (time-bucketed) ──
        # Volatility by std
        for s_lo, s_hi, s_label in [(0, 5, 'stable'), (5, 12, 'normal'), (12, 25, 'choppy'), (25, 100, 'wild')]:
            sub = [f for f in tf if s_lo <= f['std_price'] < s_hi]
            add('std_vol', f'{s_label}_{suffix}', len(sub),
                sum(f['won'] for f in sub), f'Std {s_label} ({s_lo}-{s_hi}) at minute {tb}')

        # Current price vs mean (above/below average)
        sub_above = [f for f in tf if f['cp_vs_mean'] > 5]
        sub_below = [f for f in tf if f['cp_vs_mean'] < -5]
        add('vs_mean', f'above_{suffix}', len(sub_above),
            sum(f['won'] for f in sub_above), f'Price above mean at minute {tb}')
        add('vs_mean', f'below_{suffix}', len(sub_below),
            sum(f['won'] for f in sub_below), f'Price below mean at minute {tb}')

        # Dominance: fraction of time leading
        for d_lo, d_hi, d_label in [(0, 0.2, 'trailing'), (0.2, 0.4, 'mostly_behind'),
                                     (0.6, 0.8, 'mostly_ahead'), (0.8, 1.01, 'dominating')]:
            sub = [f for f in tf if d_lo <= f['pct_leading'] < d_hi]
            add('dominance', f'{d_label}_{suffix}', len(sub),
                sum(f['won'] for f in sub), f'{d_label} at minute {tb}')

        # Acceleration (momentum shift)
        sub_accel = [f for f in tf if f['acceleration'] > 8]
        sub_decel = [f for f in tf if f['acceleration'] < -8]
        add('acceleration', f'positive_{suffix}', len(sub_accel),
            sum(f['won'] for f in sub_accel), f'Accelerating at minute {tb}')
        add('acceleration', f'negative_{suffix}', len(sub_decel),
            sum(f['won'] for f in sub_decel), f'Decelerating at minute {tb}')

        # Comeback ratio (where in the range is current price)
        sub_low = [f for f in tf if f['comeback_ratio'] < 0.3 and f['vol'] > 15]
        sub_high = [f for f in tf if f['comeback_ratio'] > 0.7 and f['vol'] > 15]
        add('position', f'near_low_{suffix}', len(sub_low),
            sum(f['won'] for f in sub_low), f'Near session low at minute {tb}')
        add('position', f'near_high_{suffix}', len(sub_high),
            sum(f['won'] for f in sub_high), f'Near session high at minute {tb}')

    return rules


def generate_global_rules(all_features):
    """Generate universal rules from all players' features combined.

    These capture patterns that hold across tennis in general,
    not specific to any player.
    """
    return _generate_rules("__GLOBAL__", all_features, {})


# ── Aggregation ──

def compute_score_v2(triggered_rules, min_sample=3):
    """Category-based aggregation.

    1. Group by category
    2. Prefer time-sliced rules over time-independent when both exist
    3. Score per category = (win_rate - 50) * min(sqrt(sample_size), 5)
    4. Total = sum of category scores
    """
    if not triggered_rules:
        return 0

    by_cat = defaultdict(list)
    for r in triggered_rules:
        if r['sample_size'] < min_sample:
            continue
        by_cat[r['category']].append(r)

    total = 0
    for cat, rules in by_cat.items():
        has_time = '_m' in rules[0]['condition'] and rules[0]['condition'].split('_m')[-1].isdigit()
        timed = [r for r in rules if '_m' in r['condition'] and r['condition'].split('_m')[-1].isdigit()]
        untimed = [r for r in rules if r not in timed]

        # Use time-sliced rules if available, otherwise fall back to time-independent
        pool = timed if timed else untimed

        best = max(pool, key=lambda r: abs(r['win_rate'] - 50) * math.sqrt(r['sample_size']))
        weight = min(math.sqrt(best['sample_size']), 5)
        score = (best['win_rate'] - 50) * weight
        total += score

    return round(total, 1)


# ── Rule matching ──

def match_rules(rules, state):
    """Match rules to current match state.

    state keys:
        current_price, init_price, running_min, running_max,
        minutes_played, recent_change (last 10 min price diff)
    """
    triggered = []
    cp = state.get('current_price', 50)
    ip = state.get('init_price', 50)
    rmin = state.get('running_min', cp)
    rmax = state.get('running_max', cp)
    vol = rmax - rmin
    minutes = state.get('minutes_played', 60)
    recent_change = state.get('recent_change', 0)

    cur_tb = _time_bucket(minutes)

    def _cond_has_time(c):
        return '_m' in c and c.split('_m')[-1].isdigit()

    def _cond_time_matches(c):
        if not _cond_has_time(c):
            return True
        rule_t = int(c.split('_m')[-1])
        return abs(rule_t - cur_tb) <= 5

    for r in rules:
        cat = r['category']
        cond = r['condition']
        match = False

        # --- Time-independent rules ---
        if cat == 'role':
            if cond == 'favorite' and ip > 55:
                match = True
            elif cond == 'underdog' and ip < 45:
                match = True
        elif cat == 'opponent':
            opp_rank = state.get('opponent_rank')
            if opp_rank:
                if cond == 'vs_top30' and 1 <= opp_rank < 30:
                    match = True
                elif cond == 'vs_rank30_100' and 30 <= opp_rank < 100:
                    match = True
                elif cond == 'vs_rank100_500' and 100 <= opp_rank < 500:
                    match = True
        elif cat == 'tiebreak' and _cond_time_matches(cond) and 40 <= cp <= 60:
            match = True
        elif cat == 'break_response' and _cond_time_matches(cond):
            base = cond.split('_m')[0] if _cond_has_time(cond) else cond
            if base == 'fast_recovery' and recent_change > 10:
                match = True
            elif base == 'slow_recovery' and recent_change < -5:
                match = True

        # --- Time-aware rules: only match if time bucket is close ---
        elif cat == 'closeout' and _cond_time_matches(cond):
            # reached_{t} or reached_{t}_m{N}
            try:
                t = int(cond.split('_')[1])
                if rmax >= t:
                    match = True
            except (ValueError, IndexError):
                pass
        elif cat == 'comeback' and _cond_time_matches(cond):
            try:
                t = int(cond.split('_')[1])
                if rmin <= t:
                    match = True
            except (ValueError, IndexError):
                pass
        elif cat == 'price_level' and _cond_time_matches(cond):
            # Format: at_{lo}_{hi}_m{N}
            parts = cond.split('_')
            try:
                plo, phi = int(parts[1]), int(parts[2])
                if plo <= cp < phi:
                    match = True
            except (ValueError, IndexError):
                pass
        elif cat == 'shape' and _cond_time_matches(cond):
            shape = cond.split('_m')[0] if _cond_has_time(cond) else cond
            if shape == 'dominant' and cp > 70 and vol < 30:
                match = True
            elif shape == 'comeback' and rmin <= 30 and cp > 50:
                match = True
            elif shape == 'collapse' and rmax >= 70 and cp < rmax - 20:
                match = True
            elif shape == 'close' and vol < 40 and 35 <= cp <= 65:
                match = True
            elif shape == 'volatile' and vol > 40:
                match = True
        elif cat == 'momentum' and _cond_time_matches(cond):
            base = cond.split('_m')[0] if _cond_has_time(cond) else cond
            if base == 'surging' and recent_change > 10:
                match = True
            elif base == 'dropping' and recent_change < -10:
                match = True
        elif cat == 'trend' and _cond_time_matches(cond):
            change_from_start = cp - ip
            base = cond.split('_m')[0] if _cond_has_time(cond) else cond
            if base == 'up' and change_from_start > 10:
                match = True
            elif base == 'down' and change_from_start < -10:
                match = True
        elif cat == 'resilience' and _cond_time_matches(cond):
            base = cond.split('_m')[0] if _cond_has_time(cond) else cond
            if base == 'drop_15' and vol >= 15:
                match = True
            elif base == 'drop_25' and vol >= 25:
                match = True
        elif cat == 'init_current' and _cond_time_matches(cond):
            # Format: {fav|even|dog}_cp{lo}_{hi}_m{N}
            parts = cond.split('_')
            try:
                ip_label = parts[0]
                cp_lo, cp_hi = int(parts[1][2:]), int(parts[2])
                ip_match = (ip_label == 'fav' and ip > 55) or (ip_label == 'even' and 45 <= ip <= 55) or (ip_label == 'dog' and ip < 45)
                if ip_match and cp_lo <= cp < cp_hi:
                    match = True
            except (ValueError, IndexError):
                pass
        elif cat == 'pullback' and _cond_time_matches(cond):
            # Format: from_{rmax_t}_drop_{drop}_m{N}
            parts = cond.split('_')
            try:
                rmax_t = int(parts[1])
                drop = int(parts[3])
                if rmax >= rmax_t and cp < rmax_t - drop:
                    match = True
            except (ValueError, IndexError):
                pass
        elif cat == 'comeback_from' and _cond_time_matches(cond):
            # Format: {fav|even|dog}_min{lo}_{hi}_m{N}
            parts = cond.split('_')
            try:
                ip_label = parts[0]
                min_lo, min_hi = int(parts[1][3:]), int(parts[2])
                ip_match = (ip_label == 'fav' and ip > 55) or (ip_label == 'even' and 45 <= ip <= 55) or (ip_label == 'dog' and ip < 45)
                if ip_match and min_lo <= rmin < min_hi:
                    match = True
            except (ValueError, IndexError):
                pass
        elif cat == 'rank_gap':
            opp_rank = state.get('opponent_rank')
            p_rank = state.get('player_rank')
            if opp_rank and p_rank:
                gap = opp_rank - p_rank
                gap_ranges = {'big_underdog': (-500, -100), 'slight_underdog': (-100, 0),
                              'slight_fav': (0, 100), 'big_fav': (100, 500)}
                if cond in gap_ranges:
                    g_lo, g_hi = gap_ranges[cond]
                    if g_lo <= gap < g_hi:
                        match = True
        elif cat == 'lead_changes' and _cond_time_matches(cond):
            base = cond.split('_m')[0] if _cond_has_time(cond) else cond
            # Approximate from vol and cp: high vol near 50 = many lead changes
            lc_approx = 0 if vol < 10 else (3 if vol > 20 and 35 <= cp <= 65 else 1)
            ranges = {'no_lead_change': (0, 1), 'few_lead_changes': (1, 3), 'many_lead_changes': (3, 20)}
            if base in ranges:
                lo, hi = ranges[base]
                if lo <= lc_approx < hi:
                    match = True
        elif cat == 'trend_duration' and _cond_time_matches(cond):
            base = cond.split('_m')[0] if _cond_has_time(cond) else cond
            if base == 'long_run' and abs(recent_change) > 5:
                match = True
            elif base == 'choppy' and abs(recent_change) < 3 and vol > 10:
                match = True
        elif cat == 'recent_stability' and _cond_time_matches(cond):
            base = cond.split('_m')[0] if _cond_has_time(cond) else cond
            rs_approx = abs(recent_change) / 3.0
            ranges = {'very_stable': (0, 3), 'stable': (3, 8), 'unstable': (8, 20)}
            if base in ranges:
                lo, hi = ranges[base]
                if lo <= rs_approx < hi:
                    match = True
        elif cat == 'change_20' and _cond_time_matches(cond):
            base = cond.split('_m')[0] if _cond_has_time(cond) else cond
            chg20 = (cp - ip) if minutes < 20 else recent_change * 2
            ranges = {'big_drop_20': (-50, -15), 'drop_20': (-15, -5),
                      'rise_20': (5, 15), 'big_rise_20': (15, 50)}
            if base in ranges:
                c_lo, c_hi = ranges[base]
                if c_lo <= chg20 < c_hi:
                    match = True
        elif cat == 'confirmed_trend' and _cond_time_matches(cond):
            base = cond.split('_m')[0] if _cond_has_time(cond) else cond
            change_5_approx = recent_change * 0.5
            change_20_approx = (cp - ip) if minutes < 20 else recent_change * 2
            if base == 'up' and change_5_approx > 2 and recent_change > 3 and change_20_approx > 5:
                match = True
            elif base == 'down' and change_5_approx < -2 and recent_change < -3 and change_20_approx < -5:
                match = True
        elif cat == 'streak' and _cond_time_matches(cond):
            base = cond.split('_m')[0] if _cond_has_time(cond) else cond
            if base == 'up8' and recent_change > 5:
                match = True
            elif base == 'down8' and recent_change < -5:
                match = True
        elif cat == 'std_vol' and _cond_time_matches(cond):
            # Needs std_price in state — approximate from vol
            std_approx = vol / 3.5 if vol > 0 else 0
            base = cond.split('_m')[0] if _cond_has_time(cond) else cond
            ranges = {'stable': (0, 5), 'normal': (5, 12), 'choppy': (12, 25), 'wild': (25, 100)}
            if base in ranges:
                s_lo, s_hi = ranges[base]
                if s_lo <= std_approx < s_hi:
                    match = True
        elif cat == 'vs_mean' and _cond_time_matches(cond):
            mean_approx = (rmin + rmax + cp) / 3
            diff_from_mean = cp - mean_approx
            base = cond.split('_m')[0] if _cond_has_time(cond) else cond
            if base == 'above' and diff_from_mean > 5:
                match = True
            elif base == 'below' and diff_from_mean < -5:
                match = True
        elif cat == 'dominance' and _cond_time_matches(cond):
            # Can't compute pct_leading without full history; use cp as proxy
            pct_proxy = 0.8 if cp > 65 else 0.65 if cp > 55 else 0.35 if cp < 45 else 0.2 if cp < 35 else 0.5
            base = cond.split('_m')[0] if _cond_has_time(cond) else cond
            ranges = {'trailing': (0, 0.2), 'mostly_behind': (0.2, 0.4),
                      'mostly_ahead': (0.6, 0.8), 'dominating': (0.8, 1.01)}
            if base in ranges:
                d_lo, d_hi = ranges[base]
                if d_lo <= pct_proxy < d_hi:
                    match = True
        elif cat == 'acceleration' and _cond_time_matches(cond):
            base = cond.split('_m')[0] if _cond_has_time(cond) else cond
            if base == 'positive' and recent_change > 8:
                match = True
            elif base == 'negative' and recent_change < -8:
                match = True
        elif cat == 'position' and _cond_time_matches(cond):
            if vol > 15:
                ratio = (cp - rmin) / vol
                base = cond.split('_m')[0] if _cond_has_time(cond) else cond
                if base == 'near_low' and ratio < 0.3:
                    match = True
                elif base == 'near_high' and ratio > 0.7:
                    match = True

        if match:
            triggered.append(r)

    return triggered


# ── Backtest ──

def backtest_v2(db_path, train_pct=0.7, min_trades=50, cooldown=10, threshold=200):
    """V2 backtest with time-sliced rules."""
    db = sqlite3.connect(db_path)
    all_data = db.execute('''
        SELECT match_id, player, opponent, minute, current_price, max_price_after,
               running_min, running_max, initial_price, player_ranking, opponent_ranking,
               match_date,
               COALESCE(won, CASE WHEN max_price_after >= 99 THEN 1 ELSE 0 END) as won
        FROM extracted_data
        WHERE player_ranking IS NOT NULL AND player_ranking <= 2000
          AND opponent_ranking IS NOT NULL AND opponent_ranking <= 2000
        ORDER BY match_id, player, minute
    ''').fetchall()

    trade_counts = {}
    for row in db.execute("SELECT match_id, COUNT(*) FROM raw_prices GROUP BY match_id"):
        trade_counts[row[0]] = row[1]
    db.close()

    matches = defaultdict(list)
    for row in all_data:
        matches[(row[0], row[1], row[2])].append({
            'minute': row[3], 'cp': row[4], 'mpa': row[5],
            'rmin': row[6], 'rmax': row[7], 'ip': row[8],
            'p_rank': row[9], 'o_rank': row[10], 'date': row[11], 'won': row[12],
        })

    sorted_keys = sorted(matches.keys(), key=lambda k: matches[k][0]['date'])
    cutoff = int(len(sorted_keys) * train_pct)
    train_keys = sorted_keys[:cutoff]
    test_keys = sorted_keys[cutoff:]

    logger.info(f"Train: {len(train_keys)}, Test: {len(test_keys)}")

    # ── Train with multi-snapshot features ──
    player_features = defaultdict(list)
    for key in train_keys:
        mid, player, opponent = key
        prices = matches[key]
        samples = extract_match_samples(prices, interval=5, match_id=mid)
        for s in samples:
            s['opp_rank'] = prices[0]['o_rank']
            s['rank_gap'] = (prices[0]['o_rank'] - prices[0]['p_rank']) if prices[0]['p_rank'] and prices[0]['o_rank'] else None
        player_features[player].extend(samples)

    player_rules = {}
    for player, feats in player_features.items():
        rules = _generate_rules(player, feats, {})
        if rules:
            player_rules[player] = rules

    logger.info(f"Rules for {len(player_rules)} players")

    # ── Test ──
    trades = []
    for key in test_keys:
        mid, player, opponent = key
        prices = matches[key]
        if len(prices) < 10:
            continue
        if trade_counts.get(mid, 0) < min_trades:
            continue

        won = prices[-1]['won']
        ip = prices[0]['ip']
        p_rank = prices[0]['p_rank']
        o_rank = prices[0]['o_rank']
        if not (p_rank and o_rank and p_rank < o_rank):
            continue

        a_rules = player_rules.get(player, [])
        b_rules = player_rules.get(opponent, [])

        last_trade_min = -cooldown
        for i, p in enumerate(prices):
            cp = p['cp']
            if cp < 5 or cp > 95:
                continue
            if p['minute'] - last_trade_min < cooldown:
                continue

            lookback = max(0, i - 10)
            recent_change = cp - prices[lookback]['cp']
            minutes_played = p['minute'] - prices[0]['minute']

            state = {
                'current_price': cp, 'init_price': ip,
                'running_min': p['rmin'], 'running_max': p['rmax'],
                'minutes_played': minutes_played,
                'recent_change': recent_change,
                'opponent_rank': o_rank, 'player_rank': p_rank,
            }

            a_triggered = match_rules(a_rules, state)
            opp_state = {
                'current_price': 100 - cp, 'init_price': 100 - ip,
                'running_min': 100 - p['rmax'], 'running_max': 100 - p['rmin'],
                'minutes_played': minutes_played,
                'recent_change': -recent_change,
                'opponent_rank': p_rank, 'player_rank': o_rank,
            }
            b_triggered = match_rules(b_rules, opp_state)

            a_score = compute_score_v2(a_triggered)
            b_score = compute_score_v2(b_triggered)
            score_diff = a_score - b_score

            if abs(score_diff) < threshold:
                continue

            side = 'A' if score_diff > 0 else 'B'
            buy_price = cp if side == 'A' else 100 - cp
            trade_won = won if side == 'A' else 1 - won

            trades.append({
                'match_id': mid, 'player': player, 'opponent': opponent,
                'side': side, 'buy_price': buy_price, 'won': trade_won,
                'score_diff': round(score_diff, 1),
                'a_score': a_score, 'b_score': b_score,
                'a_rules': len(a_triggered), 'b_rules': len(b_triggered),
                'minutes': minutes_played,
            })
            last_trade_min = p['minute']

    # ── Results ──
    wins = sum(1 for t in trades if t['won'])
    pnl = sum((100 - t['buy_price'] - 2) if t['won'] else -(t['buy_price'] + 2) for t in trades)
    n_matches = len(set(t['match_id'] for t in trades))

    return {
        'trades': trades,
        'total_trades': len(trades),
        'matches_traded': n_matches,
        'wins': wins,
        'win_rate': round(wins / len(trades) * 100, 1) if trades else 0,
        'total_pnl': round(pnl, 1),
        'avg_pnl': round(pnl / len(trades), 1) if trades else 0,
        'players_with_rules': len(player_rules),
        'train_size': len(train_keys),
        'test_size': len(test_keys),
    }
