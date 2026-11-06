# فهرس السكريبتات

**القاعدة:** لا تخمّن أي سكريبت. ابحث عن مهمتك في §1، واستخدم السكريبت المعتمد فيها. كل ما ليس في §1 فهو أداة داخلية أو أرشيفية — لا تستدعيه إلا بطلب صريح من المالك.

الحالة: `معتمد` = مستخدم في المسار الحالي · `موسمي` = يُستدعى عند الحاجة إليه فقط · `داخلي` = أداة مساعدة بلا عقد استخدام · `أرشيفي` = انتهت مهمته، يبقى للسجل.

---

## 1. المهمة ← السكريبت

| المهمة | السكريبت المعتمد | الأوامر |
|---|---|---|
| تحويل كتاب واحد كاملًا (نص ← OCR ← مراجعة) | `run_book_pipeline.py` | `--book "..." --workers 2` |
| تحويل عدة كتب في طابور ثم تسجيلها آليًا | `run_queue.py` | `--dry-run` ثم بلا علم |
| تفريغ كتاب ممسوح كبير على دفعات | `convert/pipeline_external_book.py` | `--pdf ... --start 1 --end 120` |
| تفريغ توزيعات المناظرة (PDF مصوّر) | `convert/pipeline_official_plans.py` | `--limit 1` / `--only <id>` / `--dry-run` |
| تسجيل كتاب بعد التحويل (سجل + فهرس + مسوّدة خريطة) | `retrieval/onboard_book.py` | `--book "..." --id ... --title "..."` |
| بناء الفهرس المعجمي فقط | `retrieval/build_index.py` | `--book "..."` |
| تطبيع عبارة عربية قبل البحث | `retrieval/normalize.py` | `normalize.py "العبارة"` أو عبر stdin |
| قياس جودة الاسترجاع | `eval_retrieval.py` | `--k 5 --verbose` / `--json` |
| فحص سلامة المساحة | `validate_all.py` | بلا علم / `--json` / `--quiet` |
| البصمة (المصادر المقدّسة) | `validate_all.py` | `--write-hash` / `--check-hash` / `--hash-only` |
| متابعة تقدّم التحويل الآن | `status/queue_status.py` | `--minutes 15` |
| تجميع Markdown إلى PDF/HTML | `documents/cli.py` | انظر `documents/README.md` |
| بناء سجل التوزيعات | `convert/plans_inventory.py` | بلا علم |
| فصل التوزيعات الحقيقية عن صفحات الكتب | `plans_curate.py` | `--dry-run` ثم بلا علم |
| تدقيق سنة التوزيعات | `audit/plans_year_audit.py` | `--only-distributions` / `--json` |

## 2. السكريبتات في الجذر

| السكريبت | الوظيفة | يقرأ | يكتب | الحالة |
|---|---|---|---|---|
| `validate_all.py` | حارس المساحة: 8 قواعد | `meta/catalog.yaml` · `toc.yaml` · `output/` · `index/` | `meta/output.hash` · `meta/toc_baseline.json` | معتمد |
| `eval_retrieval.py` | hit@1 · hit@k · MRR مقابل `meta/gold.json` | `index/` · `meta/gold.json` | لا شيء (طباعة/JSON) | معتمد |
| `run_book_pipeline.py` | خط كامل لكتاب واحد بلا تدخل | `curriculum_raw/<book>.pdf` · `.env` | `output/` · `_images/` · `logs/` | معتمد |
| `run_queue.py` | طابور كتب + تسجيل آلي عند الاكتمال | PDF في Downloads · `catalog.yaml` | `output/` · `index/` · `catalog.yaml` · `toc.draft.yaml` · `logs/` | معتمد |
| `night_run.py` | مراقب ليلي ثم **إغلاق الجهاز** | `output/` · `catalog.yaml` | `output/` · `index/` · `catalog.yaml` · `logs/external/` | موسمي ⚠ |
| `plans_curate.py` | وسم `role: plan / not_plan` في `meta/plans.yaml` | `plans/` · `meta/plans.yaml` | `meta/plans.yaml` | موسمي |
| `download_books.py` | تنزيل كتب الوزارة (الترم الأول) | `ellibrary.moe.gov.eg` | مجلد التنزيلات | أرشيفي |
| `library_add_all_subjects.py` | نقل كتب إلى `D:\المكتبة-التعليمية` ثم **حذف المصدر** | مجلد التنزيلات | `D:\المكتبة-التعليمية` | أرشيفي ⚠ |
| `library_add_downloads.py` | نسخ كتب العربية إلى المكتبة | مجلد التنزيلات | `D:\المكتبة-التعليمية` | أرشيفي |
| `library_purge_downloads.py` | حذف نسخ التنزيلات بعد التحقق بالبصمة | المكتبة + التنزيلات | سلة المحذوفات | أرشيفي ⚠ |
| `adwaa_tawzee3.py` | 4 مراحل: manifest · download · extract · report | archive.org | `manifest/` · `logs/` · `_source/` | أرشيفي |
| `adwaa_coverage.py` | جدول تغطية (مرحلة × مادة) | `manifest/` | `logs/adwaa_coverage.md` | أرشيفي |
| `adwaa_gap_analysis.py` | لماذا فجوة (مرحلة، مادة)؟ | archive.org | `logs/adwaa_gap_analysis.md` | أرشيفي |
| `adwaa_compare_manifests.py` | مقارنة مانيفستين | ملفان JSON | لا شيء | أرشيفي |
| `verify_adwaa_downloads.py` | فحص تنزيلات archive بالحجم والترويسة | `manifest/` · `_source/` | `logs/adwaa_verify_report.json` | أرشيفي |

## 3. الأدوات الداخلية (`_`)

بلا عقد استخدام، ولا تُستدعى من خارج سكريبت آخر. ستة منها بلا توثيق في رأسها (معلَّمة ⚠).

| السكريبت | الوظيفة |
|---|---|
| `_onboard_resume.py` | استئناف التسجيل إذا انهار بعد كتابة السجل وقبل بناء الفهرس |
| `_plans_status.py` | عرض حالة وحدات `meta/plans.yaml` (قراءة فقط) |
| `_plans_fidelity.py` | هل صفحات الوحدة توزيع حقيقي أم صفحة كتاب؟ (قراءة فقط) |
| `_plans_scan.py` ⚠ | فحص وحدات الخطط |
| `_check_queue.py` ⚠ | فحص حالة الطابور |
| `_count_pages.py` ⚠ | عدّ الصفحات |
| `_progress.py` ⚠ | تقدّم التشغيل |
| `_resume_queue.py` ⚠ | استئناف الطابور |

## 4. المجلدات الفرعية

| المجلد | الغرض | نقاط الدخول |
|---|---|---|
| `convert/` | PDF/صور ← Markdown | `pdf_text_extract.py` · `pdf_to_images.py` · `run_vision_batch.py` · `render_book_images.py` · `pipeline_*` |
| `retrieval/` | طبقة البحث | `normalize.py` · `build_index.py` · `onboard_book.py` · `toc_review.py` · `sarf_mizan.py` · `shamela_client.py` |
| `review/` | مراجعة الناتج نصيًا وبصريًا | `review_batch.py` · `review_text_batch.py` |
| `documents/` | Markdown ← PDF/HTML | `cli.py` (انظر `README.md` داخله) |
| `audit/` | تدقيق التوزيعات والخطط | `plans_year_audit.py` · `plans_year_table.py` · `plans_year_visual.py` · `build_check_list.py` |
| `status/` | لوحة الحالة | `queue_status.py` |
| `lib/` | مشترك | `gemini_client.py` (`QuotaRing` + `generate`) |
| `vendor/` | كود خارجي | `vendor/arabiyya/` — **لا يُعدَّل** (له اختباره) |

### خطوط المعالجة الخمسة — لا تخلط بينها

| السكريبت | متى | من يستدعيه |
|---|---|---|
| `run_book_pipeline.py` | كتاب واحد، طبقة نصية غالبًا | `run_queue.py` |
| `convert/pipeline_external_book.py` | كتاب ممسوح كبير، على دفعات | `night_run.py` |
| `convert/pipeline_all.py` | 3 كتب متزامنة + تسجيل فوري | `_check_queue.py` |
| `convert/pipeline_plans.py` | توزيعات: رسمية ثم مستخرجة | **لا يستدعيه أحد** — تحقّق قبل الاستخدام |
| `convert/pipeline_official_plans.py` | توزيعات رسمية مصوّرة فقط | **لا يستدعيه أحد** — تحقّق قبل الاستخدام |

## 5. أوامر مقيّدة

| الأمر | القيد |
|---|---|
| `night_run.py` | يُغلق الجهاز بعد 60 ثانية. للاختبار: `--no-shutdown --once` |
| `library_add_all_subjects.py` | يحذف الملف الأصلي بعد نسخه بنجاح |
| `library_purge_downloads.py --apply` | ينقل إلى سلة المحذوفات؛ بلا `--apply` فحصٌ فقط |
| `run_vision_batch.py` · `pipeline_*` | تستهلك حصة مفاتيح `.env` وتكتب في `output/` — لا تعمل بلا `--book` |
| `adwaa_tawzee3.py download` | ينزّل 63 كتابًا من الشبكة |
| `download_books.py` | يكتب في مجلد التنزيلات خارج المساحة |

## 6. قبل وبعد أي تشغيل يكتب في `output/`

```bash
python scripts/validate_all.py --check-hash     # قبل: هل المصادر كما تركتها؟
# ... التشغيل المعتمد ...
python scripts/validate_all.py --write-hash     # بعد: اعتماد التغيير
```

الخطاف `.githooks/pre-commit` يمنع أي التزام يُغيّر البصمة دون اعتماد صريح.

## 7. الاختبارات

```bash
python -m unittest discover -s tests -v
```

`tests/test_normalize.py` يثبّت عقد `build_index.normalize` و`normalize_page` على `fixtures/demo_book` ويعمل في CI.
تعديل قواعد التطبيع يستلزم تعديل الاختبار **عن قصد** لا بانحدار صامت.
