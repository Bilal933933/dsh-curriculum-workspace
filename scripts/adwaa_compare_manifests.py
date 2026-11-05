#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
مقارنة ملفين مانيفست للعناوين "الأضواء".

الاستخدام:
  python scripts/adwaa_compare_manifests.py <old.json> <new.json>

المخرجات:
  - عدد كل ملف، الأزواج المضافة/المحذوفة، والإدخالات التي تغيّر فيها id.
"""
import json
import sys
from pathlib import Path


def main():
    old_p, new_p = Path(sys.argv[1]), Path(sys.argv[2])
    old = json.loads(old_p.read_text(encoding="utf-8"))
    new = json.loads(new_p.read_text(encoding="utf-8"))
    key = lambda x: (x["gkey"], x["subject"])  # noqa: E731
    s1, s2 = {key(x): x for x in old}, {key(x): x for x in new}

    added = [k for k in s2 if k not in s1]
    removed = [k for k in s1 if k not in s2]
    changed = [k for k in s2 if k in s1 and s2[k]["id"] != s1[k]["id"]]

    print(f"old={len(old)} new={len(new)}")
    print("ADDED:")
    for k in added:
        e = s2[k]
        print(f"  + {e['gkey']} | {e['subject']} | id={e['id']} | size={e['size']} | pdf={e['pdf'][:70]}")
    print("REMOVED:")
    for k in removed:
        print(f"  - {k[0]} | {k[1]}")
    print("CHANGED id:")
    for k in changed:
        e = s2[k]
        print(f"  * {e['gkey']} | {e['subject']} | {s1[k]['id']} -> {e['id']} | size {s1[k]['size']} -> {e['size']}")


if __name__ == "__main__":
    main()
