# كتاب عيّنة (Demo Book)

بيانات **مصطنعة** فقط، لغرض اختبار السكربتات بلا أي محتوى منهجي حقيقي.
لا تُستشهد بها، ولا تُضاف إلى `meta/catalog.yaml` الحقيقي.

## البنية

```
fixtures/demo_book/
├── output/
│   ├── page_001.md
│   └── page_002.md
└── meta/
    ├── catalog.entry.yaml   ← مدخل جاهز للدمج في catalog.yaml
    └── toc.yaml             ← شجرة موضوعات مبسطة
```

## الاستخدام

```bash
# تطبيع نص صفحة
python scripts/retrieval/normalize.py "$(cat fixtures/demo_book/output/page_001.md)"

# فهرسة (يتوقع مساراً في catalog.yaml — استخدم نسخة مؤقتة لا الأصل)
python scripts/retrieval/build_index.py --help
```

## ما تختبره العيّنة

- تطبيع الهمزات والتشكيل والألف المقصورة.
- مطابقة عبارة عربية داخل نص مُشكَّل.
- بنية `toc.yaml` (باب ← فصل ← درس) مع نطاقات صفحات.
- حقول السجل: `id`, `text_dir`, `index_dir`, `pages_converted`, `stage`.
