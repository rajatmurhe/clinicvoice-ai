"""Require every previously caught attack and zero Python/Node blocklist drift."""
import json
import sys
from pathlib import Path
baseline = json.loads((Path(__file__).parent / 'results/red-team.json').read_text())
current = json.loads(Path(sys.argv[1]).read_text())
expected = {r['id'] for r in baseline['results'] if r['verdict'] == 'caught'}
results = {r['id']: r for r in current['results']}
failures = [i for i in expected if results.get(i, {}).get('verdict') != 'caught']
failures += [r['id'] for r in current['results'] if r.get('node_blocked') is None or bool(r['py_blocked']) != bool(r['node_blocked'])]
if failures:
    raise SystemExit('Red-team regression or missing Node measurement: ' + ', '.join(sorted(set(failures))))
print('Red-team baseline preserved; Python and Node agree. Known baseline gaps remain documented.')
