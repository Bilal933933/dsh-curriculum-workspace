#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
test_normalize.py — عقد ``build_index.normalize`` ونصّ الصفحة K.

لماذا
-----
``normalize`` هي دالة المطابقة الوحيدة في طبقة البحث: لو تغيّرت قواعدها
(حرف، تشكيل، رقم) بلا انتباه، سيصير الفهرس القديم غير مطابق للعبارة الجديدة
بلا خطأ ظاهر. هذه الاختبارات تثبّت العقد الحالي وتكشف أي انحدار صامت.

ما تقرأه (قراءة فقط):
    scripts/retrieval/build_index.py
    fixtures/demo_book/output/page_*.md

ما تكتبه:
    لا شيء.

التشغيل:
    python -m unittest discover -s tests -v
"""

from __future__ import annotations

import os
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RETRIEVAL = ROOT / "scripts" / "retrieval"
FIXTURE_PAGES = ROOT / "fixtures" / "demo_book" / "output"

sys.path.insert(0, str(RETRIEVAL))
from build_index import normalize, normalize_page  # noqa: E402


class TestNormalizeLetters(unittest.TestCase):
    """توحيد الحروف: فروق إملائية لا تغيّر الكلمة عند البحث."""

    def test_hamza_forms_fold_to_alif(self):
        self.assertEqual(normalize("أحمد إبراهيم آمن ٱلله"), "احمد ابراهيم امن الله")

    def test_alif_maqsura_folds_to_ya(self):
        self.assertEqual(normalize("مصطفى"), "مصطفي")

    def test_hamza_on_ya_and_waw(self):
        self.assertEqual(normalize("يقرئ مؤمن"), "يقري مومن")

    def test_taa_marbuta_folds_to_haa(self):
        self.assertEqual(normalize("المدرسة"), "المدرسه")


class TestNormalizeDiacritics(unittest.TestCase):
    """التشكيل والتطويل والرموز القرآنية تُحذف بلا أثر."""

    def test_tashkeel_removed(self):
        self.assertEqual(normalize("العِلْمُ نُورٌ"), "العلم نور")

    def test_tatweel_removed(self):
        self.assertEqual(normalize("الـعـلـم"), "العلم")

    def test_quranic_marks_removed(self):
        self.assertEqual(normalize("بِسْمِ ٱللَّهِ ۞"), "بسم الله")


class TestNormalizeDigits(unittest.TestCase):
    """الأرقام الهندية والفارسية تُوحَّد إلى لاتينية (لأن الاستشهاد بالصفحة رقم)."""

    def test_arabic_indic_digits(self):
        self.assertEqual(normalize("٠١٢٣٤٥٦٧٨٩"), "0123456789")

    def test_persian_digits(self):
        self.assertEqual(normalize("۰۱۲۳۴۵۶۷۸۹"), "0123456789")

    def test_page_reference(self):
        self.assertEqual(normalize("ص ٣١٦"), "ص 316")


class TestNormalizePunctuationAndSpace(unittest.TestCase):
    """ما ليس حرفًا أو رقمًا يصبح مسافة، ثم تُضبط المسافات."""

    def test_arabic_punctuation_is_space(self):
        self.assertEqual(normalize("«العلمُ» — مرفوع."), "العلم مرفوع")

    def test_whitespace_collapsed_and_stripped(self):
        self.assertEqual(normalize("  نص   بمسافات   واسعة  "), "نص بمسافات واسعه")

    def test_latin_and_underscore_preserved(self):
        # \w يحفظ اللاتيني والشرطة السفلية — عقد مقصود لا سهو.
        self.assertEqual(normalize("ABC_123 عربي"), "ABC_123 عربي")

    def test_empty_input(self):
        self.assertEqual(normalize(""), "")
        self.assertEqual(normalize("   \n\t "), "")

    def test_only_diacritics_leaves_nothing(self):
        self.assertEqual(normalize("ًٌٍَُِّْ"), "")


class TestNormalizeContract(unittest.TestCase):
    """خصائص عامة يجب أن تصدق على أي مدخل."""

    SAMPLES = (
        "العِلْمُ نُورٌ",
        "أحمد إبراهيم آمن ٱلله",
        "«العلمُ» — مرفوع.",
        "ص ٣١٦ (ملف page_317)",
        "ABC_123 عربي",
        "",
    )

    def test_idempotent(self):
        for text in self.SAMPLES:
            once = normalize(text)
            self.assertEqual(normalize(once), once, f"التطبيع غير مستقر على: {text!r}")

    def test_no_tashkeel_survives(self):
        from build_index import TASHKEEL_RE

        for text in self.SAMPLES:
            self.assertIsNone(TASHKEEL_RE.search(normalize(text)), f"تشكيل نجا من: {text!r}")

    def test_no_leading_or_trailing_space(self):
        for text in self.SAMPLES:
            result = normalize(text)
            self.assertEqual(result, result.strip(), f"مسافة طرفية في: {text!r}")


class TestNormalizePageOnFixture(unittest.TestCase):
    """حالة كاملة على ``fixtures/demo_book`` — نفس البيانات التي يعمل عليها CI."""

    def setUp(self):
        self.raw = (FIXTURE_PAGES / "page_001.md").read_text(encoding="utf-8")
        self.norm, self.headings = normalize_page(self.raw)

    def test_headings_from_markdown_levels(self):
        self.assertIn((1, "الدرس الأول: الجملة الاسمية"), self.headings)
        self.assertIn((2, "تدريب"), self.headings)

    def test_bold_inline_is_not_heading(self):
        # «**المثال:** العلمُ نورٌ.» غامق جزئي لا سطر غامق كامل.
        titles = [h for _, h in self.headings]
        self.assertNotIn("المثال:", titles)

    def test_norm_text_is_line_by_line_and_stable(self):
        self.assertTrue(self.norm, "نص الصفحة المطبَّع فارغ")
        for line in self.norm.splitlines():
            self.assertEqual(normalize(line), line, f"سطر غير مطبَّع: {line!r}")

    def test_running_header_line_is_normalized(self):
        # ترويسة «26 | نص العنوان»: يُحذف الرقم والعمود ثم يُطبَّع السطر.
        raw = "26 | البَلَاغَةُ وَالْبَيَانُ\n\nنص الصفحة."
        norm, _ = normalize_page(raw)
        self.assertTrue(norm.startswith("البلاغه والبيان"), norm)
        self.assertNotIn("|", norm)

    def test_md_running_header_is_not_a_heading(self):
        # عنوان Markdown يحمل ترويسة الصفحات يُستبعد من مسوّدة العناوين.
        raw = "# كَيْفَ تُتْقِنُ البَلَاغَةَ؟ | 26\n\nنص."
        _, headings = normalize_page(raw)
        self.assertEqual(headings, [])

    def test_bold_running_header_is_not_filtered_today(self):
        # ثغرة معروفة (لم تُعدَّل الشيفرة بطلب المالك): مرشِّح الترويسات
        # (NOISE_HEADING_RE) يُطبَّق على عناوين Markdown فقط، لا على السطر الغامق.
        # هذا الاختبار يثبّت السلوك الحالي كي لا يتغيّر صامتًا.
        raw = "**كَيْفَ تُتْقِنُ البَلَاغَةَ؟**\n\nنص."
        _, headings = normalize_page(raw)
        self.assertEqual(headings, [(0, "كَيْفَ تُتْقِنُ البَلَاغَةَ؟")])

    def test_empty_page_returns_empty_text(self):
        norm, headings = normalize_page("\n\n   \n")
        self.assertEqual(norm, "")
        self.assertEqual(headings, [])

    def test_second_fixture_page_headings(self):
        raw = (FIXTURE_PAGES / "page_002.md").read_text(encoding="utf-8")
        _, headings = normalize_page(raw)
        self.assertEqual(headings, [(1, "الدرس الثاني: الجملة الفعلية")])


class TestNormalizeCli(unittest.TestCase):
    """واجهة ``scripts/retrieval/normalize.py``: الوسيط وإدخال stdin ورموز الخروج."""

    @staticmethod
    def run_cli(*args: str, stdin: str = "") -> subprocess.CompletedProcess:
        env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
        return subprocess.run(
            [sys.executable, str(RETRIEVAL / "normalize.py"), *args],
            input=stdin,
            capture_output=True,
            text=True,
            encoding="utf-8",
            env=env,
            cwd=str(ROOT),
        )

    def test_argument_is_normalized(self):
        cp = self.run_cli("العِلْمُ نُورٌ")
        self.assertEqual(cp.returncode, 0)
        self.assertEqual(cp.stdout.strip(), "العلم نور")

    def test_stdin_is_normalized(self):
        cp = self.run_cli(stdin="الاستعارة المكنية\n")
        self.assertEqual(cp.returncode, 0)
        self.assertEqual(cp.stdout.strip(), "الاستعاره المكنيه")

    def test_empty_input_fails_with_message(self):
        cp = self.run_cli(stdin="   ")
        self.assertEqual(cp.returncode, 1)
        self.assertIn("لم يتبقَّ نص بعد التطبيع", cp.stderr)


if __name__ == "__main__":
    unittest.main()
