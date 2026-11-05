"""إعدادات طبقة توليد المستندات — القيم كلها هنا، ولا تُكتب داخل الكود.

أي تعديل في المسارات أو مقاس الصفحة أو المتصفح يتم من هذا الملف وحده.
"""

from __future__ import annotations

from pathlib import Path

# ---------------------------------------------------------------------------
# المسارات
# ---------------------------------------------------------------------------
# جذر الورك سبيس: هذا الملف في scripts/documents/config.py
ROOT = Path(__file__).resolve().parents[2]

# باب المخرجات البحثية (PDF)
DOCS_DIR = ROOT / "البحوث"

# أصول العرض: القوالب وأوراق الأنماط
ASSETS_DIR = Path(__file__).resolve().parent / "assets"

# المستند الرئيسي داخل كل مجلد بحث
SOURCE_NAME = "report.md"
HTML_NAME = "report.html"
PDF_NAME = "report.pdf"

# النسخة الموجزة (condense.py) — نفس المجلد، أسماء مختلفة
BRIEF_SOURCE_NAME = "report_brief.md"

# نسخ المستند: مفاتيح تُمرَّر إلى cli.py عبر --variant
VARIANTS = {
    "full": {"source": SOURCE_NAME, "html": HTML_NAME, "pdf": PDF_NAME},
    "brief": {"source": BRIEF_SOURCE_NAME,
              "html": "report_brief.html",
              "pdf": "report_brief.pdf"},
}
DEFAULT_VARIANT = "full"

# ---------------------------------------------------------------------------
# العرض
# ---------------------------------------------------------------------------
PAGE_SIZE = "A4"
DEFAULT_KICKER = "ملفّ بحثيّ مُعدّ للطبع"

# ملفات الأنماط تُدمج بهذا الترتيب داخل <style>
STYLE_FILES = ("base.css", "report.css")

# ترويسة المستند
DEFAULT_LANG = "ar"
DEFAULT_DIR = "rtl"

# المعاينة البصرية (preview.py)
PREVIEW_DIR_NAME = "_معاينة"
PREVIEW_DPI = 110

# خدمة المعاينة على الشبكة (cli.py serve) — للقراءة من الهاتف
# 8910 خارج نطاقات المشاريع المحجوزة (3000-3999 / 8000-8099 / 4100-4199 / 8100-8199 / 5000-5099)
SERVE_PORT = 8910

# ---------------------------------------------------------------------------
# الطبع
# ---------------------------------------------------------------------------
BROWSER_CANDIDATES = (
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
)

HEADLESS_FLAGS = ("--headless=new", "--headless")

# إجبارية في هذه البيئة: بدونها يخرج المتصفح فورًا بالرمز 0x80000003
# (لا يملك صلاحية إنشاء ملف تعريف ولا مجلد الأعطال في المسار الافتراضي).
REQUIRED_FLAGS = (
    "--no-sandbox",
    "--disable-crash-reporter",
    "--disable-breakpad",
)

# ملف التعريف يوضع داخل الورك سبيس (لا نكتب في مسارات النظام)
PROFILE_DIR = Path(__file__).resolve().parent / ".cache" / "chrome"

PRINT_TIMEOUT_SECONDS = 180
VIRTUAL_TIME_BUDGET_MS = 15000
MIN_PDF_BYTES = 2000
