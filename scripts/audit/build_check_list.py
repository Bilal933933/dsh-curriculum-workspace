# -*- coding: utf-8 -*-
"""يبني قائمة الخطط التي تحتاج تحققًا بصريًا (توزيعات بلا ذكر 2026/2027)."""
import json
import os
import sys

W = r'E:\heard\dsh-experiment\workspace'
audit = json.load(open(os.path.join(W, 'meta', 'plans_year_audit.json'), encoding='utf-8'))
tmp = r'C:\Users\blals\AppData\Local\Temp\opencode\plan_audit.json'
kinds = {x['name']: x['kind'] for x in json.load(open(tmp, encoding='utf-8'))}

rows = [r for r in audit if 'توزيع' in kinds.get(r['name'], '')]
fresh, stale = [], []
for r in rows:
    ys = set(r['years'])
    (fresh if ({'2026', '2027'} & ys) else stale).append(r)

print('توزيعات مصنّفة:', len(rows), '| حديثة (2026/2027):', len(fresh), '| تحتاج تحققًا:', len(stale))
print()
for r in stale:
    print('  {:>2}ص | {:<58} | {}'.format(r['pages'], r['name'][:58], '،'.join(r['years']) or 'بلا سنة'))

out = os.path.join(W, 'meta', 'plans_to_check.txt')
with open(out, 'w', encoding='utf-8') as fh:
    fh.write('\n'.join(r['name'] for r in stale))
print('\n[*] القائمة:', out)
