#!/usr/bin/env python3
"""Generate player rules from historical data.
Usage: cd backend && source .venv/bin/activate && python3 -m scripts.generate_rules
"""
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import settings
from app.analysis.player_rules import generate_all_rules, store_rules

logging.basicConfig(level=logging.INFO)

rules = generate_all_rules(settings.db_path, min_matches=5, max_rank=500)
store_rules(settings.db_path, rules)

# Summary
from collections import Counter
signals = Counter(r['signal'] for r in rules)
types = Counter(r['rule_type'] for r in rules)
print(f"\nTotal rules: {len(rules)}")
print(f"Players: {len(set(r['player'] for r in rules))}")
print(f"By signal: {dict(signals)}")
print(f"By type: {dict(types)}")

# Show strongest edges
print("\nStrongest positive edges:")
rules.sort(key=lambda x: -x['edge'])
for r in rules[:10]:
    print(f"  {r['player']:>25s} {r['rule_type']:>18s} {r['condition']:>25s} wr={r['win_rate']}% base={r['baseline']}% edge={r['edge']:+.1f}% N={r['sample_size']}")

print("\nStrongest negative edges:")
rules.sort(key=lambda x: x['edge'])
for r in rules[:10]:
    print(f"  {r['player']:>25s} {r['rule_type']:>18s} {r['condition']:>25s} wr={r['win_rate']}% base={r['baseline']}% edge={r['edge']:+.1f}% N={r['sample_size']}")
