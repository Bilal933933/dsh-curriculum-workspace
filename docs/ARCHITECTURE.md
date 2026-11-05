# معمارية مساحة العمل (dsh-curriculum-workspace)

> هذا الملف يصف **البنية فقط**. القواعد الملزمة في `AGENTS.md`، وهي المرجع الأعلى عند أي تعارض.

## 1. الطبقات

```
curriculum_raw/         ← المصدر الخام (PDF + صور الصفحات) — 18GB — لا يُرفع إلى git
        │  (تحويل: استخراج طبقة نصية 0 توكن، أو OCR بصري عبر Gemini)
        ▼
output/<book>/page_XXX.md   ← النص المحوَّل — مرجع القراءة والاقتباس الحرفي — مقدَّس
        │  (بناء آلي: تطبيع ثم فهرسة)
        ▼
index/<book>/norm/ + فهرس معجمي   ← مشتق قابل لإعادة البناء في أي وقت
        │
        ▼
meta/catalog.yaml + meta/books/<slug>/toc.yaml   ← سجل الكتب وبنية موضوعاتها
        │
        ▼
الاسترجاع (skill: curriculum-retrieval)  →  إجابة موثقة برقم صفحة
```

**قاعدة الفصل:** `output/` و`index/` مشتقّان من `curriculum_raw/`؛ و`index/` وحده مشتق من `output/`.
لا يُحرَّر أي منهما يدويًا. التصحيح يبدأ من المصدر أو من سكربت، لا من الملف الناتج.

## 2. طبقات المصادر (ترتيب السلطة)

1. **المنهج المدرسي**: `output/` + `index/` + `meta/catalog.yaml` — المصدر الوحيد لما يُمتحَن فيه.
2. **المراجع المحلية**: نفس البنية، كتب غير مدرسية.
3. **الشاملة MCP**: خارجي تراثي — للتوثيق والخلاف والشواهد عند نقص المحلي فقط.

`plans/` و`plans_src/` (توزيعات المناهج) **ليست مصدر استرجاع** ولا يُستشهد منها.

## 3. خريطة `scripts/`

| المجلد | الدور |
|---|---|
| `scripts/convert/` | تحويل PDF ← Markdown: `pdf_text_extract.py`، `pdf_to_images.py`، `run_vision_batch.py`، `pipeline_*.py`، سكربتات الخطط |
| `scripts/retrieval/` | بناء أدوات الاسترجاع: `normalize.py` (تطبيع عربي)، `build_index.py` (فهرسة)، `onboard_book.py` (تسجيل كتاب)، `toc_review.py`، `sarf_mizan.py`، `shamela_client.py` |
| `scripts/review/` | مراجعة نصية/بصرية للناتج |
| `scripts/audit/` | تدقيق الخطط والجودة |
| `scripts/documents/` | تجميع Markdown ← PDF/HTML: `compile.py`، `pdf_print.py`، `condense.py` |
| `scripts/lib/` | مشترك: `gemini_client.py` (QuotaRing + generate) |
| `scripts/status/` | حالة التقدّم |
| `scripts/vendor/` | كود خارجي |

### نقاط الدخول (Entry points)

| السكربت | الوظيفة |
|---|---|
| `scripts/run_book_pipeline.py` | خط كامل لكتاب واحد: طبقة نصية ← OCR للصفحات الناقصة ← إعادة محاولة ← مراجعة ← تقرير |
| `scripts/run_queue.py`، `night_run.py` | تشغيل دفعي غير مُدار على عدة كتب |
| `scripts/validate_all.py` | **حارس مساحة العمل**: 7 قواعد تفشل بصوت عالٍ (انظر §5) |
| `scripts/eval_retrieval.py` | قياس جودة الاسترجاع مقابل `meta/gold.json` |

## 4. العقود (Schemas)

- **`meta/catalog.yaml`**: لكل كتاب `id` (لاتيني)، `title`، `text_dir`، `index_dir`، `pages_converted`، `stage`.
  **المقارنة دائمًا عبر `text_dir`/`index_dir`، لا بين `id` واسم المجلد العربي** — هذا فخ أنتج سابقًا نتيجة كاذبة («111 مجلدًا بلا معرّف»).
- **`meta/books/<slug>/toc.yaml`**: شجرة الموضوعات (باب ← فصل ← درس) مع نطاقات الصفحات.
  المصدر الأولي `toc.draft.yaml` يُراجَع ثم يُعتمد.
- **`.agents/skills/<name>/SKILL.md`**: ترويسة YAML (`name` يطابق المجلد + `description` دالّ) ثم الخطوات.

## 5. حرّاس الجودة في `validate_all.py`

| # | القاعدة | السلوك |
|---|---|---|
| 1 | `env_hygiene` | `.env` غير متتبَّع ومستثنى في `.gitignore` |
| 2 | `doc_paths` | كل مسار مذكور في `AGENTS.md` والمهارات موجود فعلًا |
| 3 | `skill_frontmatter` | لكل `SKILL.md` ترويسة صحيحة |
| 4 | `no_silent_book_default` | لا `--book` بافتراضي صامت في سكربتات تكتب في `output/` |
| 5 | `pages_converted` | العدد في `catalog.yaml` يطابق الملفات الفعلية |
| 6 | `topics_baseline` | عدد موضوعات `toc.yaml` لم ينحدر عن `meta/toc_baseline.json` |
| 7 | `orphan_dirs` | (تحذير) مجلدات بلا اعتماد في السجل |

`S1` = يفشل برمز خروج · `S2` = تحذير لا يوقف.

## 6. حدود المستودع

يُرفَع إلى git: `scripts/` · `.agents/` · `meta/` · `manifest/` · `docs/` · `fixtures/` · ملفات الجذر.
**لا يُرفَع:** `curriculum_raw/` · `output/` · `index/` · `plans/` · `plans_src/` · `logs/` · `.env` · `.venv/`.

السبب: الحجم (18GB + 38MB) + حقوق المحتوى + أن المشتقات تُعاد بناؤها من المصدر.
