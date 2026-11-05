# طبقة المستندات (scripts/documents)

مهمتها الواحدة: **تحويل ملف Markdown إلى مستند PDF عربي منظّم**.

## قاعدة الهيكلة
- مجلد واحد لكل **مهمة** (`documents`).
- ملف واحد لكل **وظيفة** داخل المهمة.
- لا يعرف ملفٌ عملَ ملفٍ آخر؛ الربط في `report_task.py` وحده.

## الملفات والوظائف

| الملف | الوظيفة (وفقط) |
|---|---|
| `config.py` | الإعدادات: المسارات، مقاس الصفحة، أسماء الملفات، المتصفح، المهل |
| `markdown_io.py` | قراءة/كتابة النصوص، واستخراج العنوان من الترويسة |
| `markdown_html.py` | Markdown ← HTML + فهرس آلي |
| `page_render.py` | تركيب القالب + الأنماط + الغلاف + الفهرس → مستند واحد |
| `pdf_print.py` | HTML ← PDF عبر Chrome/Edge، وعدّ الصفحات |
| `report_task.py` | خط سير مهمة «التقرير» (ربط الخطوات فقط) |
| `compile.py` | دمج `sections/*.md` في `report.md` (يحذف كتل `overflow`) |
| `condense.py` | توليد نسخة موجزة `report_brief.md`: عنوان + فقرة + جدول + صندوق + مصادر |
| `preview.py` | معاينة صفحات PDF كصور PNG |
| `cli.py` | واجهة الأوامر (`--variant full\|brief`) |
| `assets/base.css` | الأنماط المشتركة (نصوص، جداول، اقتباسات) |
| `assets/report.css` | أنماط التقرير (غلاف، فهرس، فواصل الأقسام) |
| `assets/report.html` | قالب الصفحة بعلامات `{{…}}` |

## الاستخدام

```powershell
# 1) أنشئ مجلد البحث وضع فيه report.md
#    البحوث/<الاسم>/report.md

# 2) افحص الجاهزية
.\scripts\.venv\Scripts\python.exe scripts\documents\cli.py check --slug <الاسم>

# 3) بناء وطبع
.\scripts\.venv\Scripts\python.exe scripts\documents\cli.py make --slug <الاسم> --author "فلان"

# أو خطوة خطوة
... cli.py build --slug <الاسم>
... cli.py print --slug <الاسم>
```

## قواعد لا تُخترق
1. الملف يُقرأ من `البحوث/<slug>/report.md` فقط، ويكتب في المجلد نفسه.
2. لا يُقرأ أي مسار خارج الورك سبيس (الخطوط تُطلب بالاسم من النظام عبر CSS).
3. لا تثبيت مكتبات PDF؛ الطبع عبر متصفح النظام.
4. تغيير المسارات أو المقاسات يكون في `config.py` لا في بقية الملفات.
