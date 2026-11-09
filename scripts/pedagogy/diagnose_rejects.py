#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""تشخيص صفحات «في رحاب» التي يرفضها المحوّل: يطبع سبب الرفض الحقيقي."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "scripts" / "convert"))

import run_vision_batch as rvb  # noqa: E402
from lib.gemini_client import QuotaRing, encode_image, generate  # noqa: E402

BOOK = "في_رحاب_لغتنا_العربية_جامعة_دمشق"
PAGES = [32, 36, 37, 38, 39, 40, 42, 43]

rvb.set_book(BOOK)
settings = rvb.load_settings()
ring = QuotaRing(settings["keys"], settings["models"])

for p in PAGES:
    img = rvb.IMAGE_DIR / f"page_{p:03d}.png"
    if not img.exists():
        print(p, "NO IMAGE")
        continue
    parts = [
        {"text": rvb.PROMPT},
        {"inline_data": {"mime_type": "image/jpeg", "data": encode_image(img)}},
    ]
    text, model, usage, err = generate(ring, parts, timeout=150)
    if err:
        print(p, "ERR", err)
        continue
    cleaned, dropped, runaway = rvb.repair_repetition(text)
    print(
        p,
        "model=", model,
        "raw=", len(text),
        "clean=", len(cleaned),
        "dropped=", dropped,
        "runaway=", runaway,
        "usable_raw=", rvb._usable(text),
        "usable_clean=", rvb._usable(cleaned),
    )
    if runaway:
        (ROOT / "logs" / "pedagogy" / f"raw_{p}.txt").write_text(text, encoding="utf-8")
