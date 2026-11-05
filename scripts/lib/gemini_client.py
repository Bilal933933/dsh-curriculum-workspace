#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
gemini_client.py — عميل Gemini المشترك (حلقة الحصة + نداء موحّد)
=================================================================
الغرض:
    توحيد منطق الاتصال بنموذج Gemini في وحدة واحدة، بدل ثلاث نسخ متباعدة
    كانت في run_vision_batch.py و review_batch.py و review_text_batch.py.

    السبب الجذري للتوحيد: كان اسم الأسلوب `mark_exhausted` يُستدعى في المُراجِعَين
    بينما الصف `QuotaRing` لا يعرّفه (يعرّف `mark_dead_pair`/`mark_key_bad` فقط)،
    فكان أي ردّ 404/403 يُسقط السكريبت بـ AttributeError بدل تجاوز الموديل المنهَك.

    الوحدة توفّر:
      - load_env(path)           : قراءة .env يدويًا (بلا مكتبات خارجية).
      - QuotaRing                : دائرة (مفتاح × موديل) آمنة مع الخيوط.
      - encode_image(path)       : تحويل صورة إلى base64 JPEG.
      - generate(ring, parts)    : نداء موحّد مع إعادة المحاولة وتصنيف الحالات.

    التاريخ: وُحّدت من run_vision_batch.py (النسخة الأحدث) في 2026-10-30.
"""

import base64
import io
import threading
import time

import requests
from PIL import Image

API_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

# ------------------------------------------------------------------ تصنيف الحالات
RETRYABLE = {429, 500, 502, 503, 504}   # عابر: تهدئة وإعادة محاولة
FATAL = {400}                            # طلب غير صالح ⇒ فشل نهائي للصفحة
MODEL_GONE = {404, 403}                  # الموديل غير متاح لهذا الحساب ⇒ وسم الزوج
KEY_BAD = {401}                          # مفتاح باطل ⇒ إقصاء المفتاح كله


# ------------------------------------------------------------------ الإعدادات
def load_env(path) -> dict:
    """قراءة ملف .env يدويًا (بلا مكتبات خارجية)."""
    data = {}
    if not path.exists():
        return data
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        data[key.strip()] = value.strip().strip('"').strip("'")
    return data


# ------------------------------------------------------------------ حلقة التدوير
class QuotaRing:
    """دائرة (مفتاح × موديل) آمنة مع الخيوط، تفرّق بين نفاد الحصة الحقيقي
    وحدّ المعدل المؤقت.

    سابقًا: أي استجابة 429/5xx كانت تُعدم الزوج إعدامًا دائمًا، فتنتهي الدفعة
    كلها على «نفدت كل المفاتيح» بعد ٧٩ صفحة مع أن المفاتيح سليمة. الآن:
      - 429 (حدّ دقيقة) ⇒ تهدئة الزوج عشرات الثواني ثم يصلح.
      - 5xx/انقطاع ⇒ تهدئة قصيرة.
      - 429 (حدّ يوم) أو 401/403/404 ⇒ إعدام حقيقي.
    مع فاصل أدنى بين طلبات الزوج نفسه (تقليل 429 من الأصل).
    """

    def __init__(self, keys, models, min_interval: float = 5.0):
        self.keys = keys
        self.models = models
        self.pairs = [(k, m) for k in keys for m in models]
        self.cursor = 0
        self.dead_pairs = set()
        self.dead_keys = set()
        self.cooldown = {}      # pair -> time until
        self.last_use = {}      # pair -> last request time
        self.min_interval = min_interval
        self.lock = threading.Lock()

    def next_pair(self):
        """يعيد زوجًا جاهزًا، أو ينتظر قليلًا حتى يخرج زوج من التهدئة."""
        while True:
            with self.lock:
                if len(self.dead_pairs) >= len(self.pairs):
                    return None
                now = time.time()
                earliest = None
                for _ in range(len(self.pairs)):
                    pair = self.pairs[self.cursor % len(self.pairs)]
                    self.cursor += 1
                    key, _model = pair
                    if pair in self.dead_pairs or key in self.dead_keys:
                        continue
                    ready = max(self.cooldown.get(pair, 0.0),
                                self.last_use.get(pair, 0.0) + self.min_interval)
                    if ready <= now:
                        self.last_use[pair] = now
                        return pair
                    earliest = ready if earliest is None else min(earliest, ready)
                wait = 2.0 if earliest is None else min(max(earliest - now, 0.5), 5.0)
            time.sleep(wait)

    def cooldown_pair(self, pair, seconds: float):
        with self.lock:
            self.cooldown[pair] = max(self.cooldown.get(pair, 0.0), time.time() + seconds)

    def mark_dead_pair(self, pair):
        """يُعدم زوج (مفتاح×موديل) — موديل غير متاح أو نفدت حصته اليومية."""
        with self.lock:
            self.dead_pairs.add(pair)

    def mark_key_bad(self, key):
        """يُقصي مفتاحًا كاملًا (مفتاح باطل)."""
        with self.lock:
            self.dead_keys.add(key)
            for m in self.models:
                self.dead_pairs.add((key, m))

    def alive_pairs(self):
        with self.lock:
            return len(self.pairs) - len(self.dead_pairs)


# ------------------------------------------------------------------ الصورة
def encode_image(path, max_side: int = 2000, quality: int = 85) -> str:
    """تحويل صورة إلى base64 JPEG (مُصغّرة لخفض حجم الطلب)."""
    with Image.open(path) as im:
        im = im.convert("RGB")
        im.thumbnail((max_side, max_side), Image.LANCZOS)
        buf = io.BytesIO()
        im.save(buf, "JPEG", quality=quality, optimize=True)
    return base64.b64encode(buf.getvalue()).decode("ascii")


# ------------------------------------------------------------------ النداء الموحّد
def _post(model, key, payload, timeout):
    return requests.post(
        API_URL.format(model=model),
        headers={"x-goog-api-key": key, "Content-Type": "application/json"},
        json=payload,
        timeout=timeout,
    )


def _parse_text(resp):
    data = resp.json()
    parts = data["candidates"][0]["content"]["parts"]
    text = "".join(p.get("text", "") for p in parts).strip()
    usage = data.get("usageMetadata", {})
    return text, usage


def generate(ring: QuotaRing, parts: list, timeout: int = 90,
             temperature: float = 0.1, max_output_tokens: int = 8192):
    """نداء موحّد عبر الحلقة. يعيد (text, model, usage, err).

    `parts` قائمة أجزاء المحتوى (نص/صورة). القيم المرجعة:
      - (text, model, usage, None) عند النجاح — بأي طول، والمستدعي يقرّر صلاحيته
        (صفحات الفواصل والعناوين نصّها قصير مشروع).
      - (None, model, {}, err) عند الفشل (400 / نفاد الكل / تجاوز المحاولات).
    """
    payload = {
        "contents": [{"parts": parts}],
        "generationConfig": {"temperature": temperature,
                             "maxOutputTokens": max_output_tokens},
    }

    attempts = 0
    max_attempts = 60          # محاولات كافية بعد أن صار الانتظار تهدئةً لا إعدامًا

    while attempts < max_attempts:
        pair = ring.next_pair()
        if pair is None:
            return None, "—", {}, "نفدت كل المفاتيح والموديلات (الحصة اليومية)"

        key, model = pair
        attempts += 1

        try:
            resp = _post(model, key, payload, timeout)
        except requests.RequestException:
            ring.cooldown_pair(pair, 15)
            continue

        if resp.status_code == 200:
            try:
                text, usage = _parse_text(resp)
            except Exception:
                ring.cooldown_pair(pair, 5)
                continue
            return text, model, usage, None

        if resp.status_code in FATAL:          # 400: طلب غير صالح ⇒ فشل نهائي
            return None, model, {}, f"HTTP {resp.status_code}: {resp.text[:200]}"

        if resp.status_code in MODEL_GONE:     # 403/404: الموديل غير متاح
            ring.mark_dead_pair(pair)
            continue

        if resp.status_code in KEY_BAD:        # 401: مفتاح باطل
            ring.mark_key_bad(key)
            continue

        if resp.status_code == 429:
            body = (resp.text or "").lower()
            # ٤٢٩ نوعان: نفاد حصة اليوم (لا يفيد الانتظار) وحدّ المعدل (يفيد).
            if "per day" in body or "perday" in body:
                ring.mark_dead_pair(pair)
            else:
                ring.cooldown_pair(pair, 60)
            continue

        if resp.status_code in RETRYABLE:      # 5xx: ازدحام مؤقت
            ring.cooldown_pair(pair, 25)
            continue

        ring.cooldown_pair(pair, 10)

    return None, "—", {}, "تجاوز الحد الأقصى للمحاولات"
