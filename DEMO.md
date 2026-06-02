# OmniSort AI — Demo Script

This script walks through every major feature in under 5 minutes.

---

## 0. Setup (30 s)

```bash
cd omnisort-ai
cp configs/settings.yaml.example configs/settings.yaml   # set your watch folders
export OPENAI_API_KEY=sk-...
pip install -r backend/requirements.txt
uvicorn backend.api.api:app --reload &          # start API server
python -m backend.watcher.file_watcher &        # start file watcher
```

Open the dashboard: http://localhost:8000/docs

---

## 1. Basic sorting — image goes to Photos (20 s)

```bash
cp ~/sample-files/vacation.jpg ~/Downloads/
```

Expected: file moves to `~/OmniSort/Photos/vacation.jpg`
Dashboard event: `{ "type": "file_processed", "category": "Photos" }`

---

## 2. Invoice PDF → Invoices folder (20 s)

```bash
cp ~/sample-files/invoice_march.pdf ~/Downloads/
```

Expected: file moves to `~/OmniSort/Invoices/invoice_march.pdf`
API check: `curl localhost:8000/api/files | jq '.[0]'`

---

## 3. Sensitive file — SSN in text (20 s)

```bash
echo "SSN: 123-45-6789\nName: John Doe" > ~/Downloads/personal_record.txt
```

Expected: file moves to `~/OmniSort/Sensitive/personal_record.txt`
Note: **OpenAI API was never called** — PII gate fired first.

---

## 4. Duplicate detection (20 s)

```bash
cp ~/Downloads/invoice_march.pdf ~/Downloads/invoice_copy.pdf
```

Expected: `invoice_copy.pdf` moves to `~/OmniSort/Duplicates/`
API check: `curl localhost:8000/api/stats | jq '.duplicates'`

---

## 5. Custom rule — Bank folder (20 s)

Add to `configs/settings.yaml`:
```yaml
custom_rules:
  - folder: "Bank"
    keywords: ["account number", "transaction history"]
```

```bash
echo "Account number: ACC-XYZ\nTransaction history for April 2025" > ~/Downloads/statement.pdf
```

Expected: `statement.pdf` → `~/OmniSort/Bank/`

---

## 6. Semantic search (30 s)

```bash
curl "localhost:8000/api/search?q=quarterly+revenue+report&limit=5" | jq '.[].filename'
```

Returns files ranked by semantic similarity to your query — finds relevant documents even when filenames don't match keywords.

---

## 7. Observability metrics (10 s)

```bash
curl localhost:8000/api/metrics | jq .
```

```json
{
  "files_per_min": 3.2,
  "total_processed": 12,
  "duplicates": 1,
  "sensitive": 2,
  "ocr_failures": 0,
  "llm_calls": 4,
  "avg_classification_ms": 142.5,
  "avg_llm_ms": 820.0
}
```

---

## 8. Docker run (30 s)

```bash
OPENAI_API_KEY=sk-... WATCH_FOLDER=~/Downloads docker-compose up
```

Access API at http://localhost:8000 — no Python install needed.

---

## What to highlight in a live demo

| Feature | Where to show |
|---|---|
| Privacy-first: PII never sent to OpenAI | Drop `personal_record.txt` → check API logs, no outbound call |
| Real-time WebSocket events | Open browser console on `ws://localhost:8000/ws` |
| Semantic search beats keyword search | Search "budget proposal" — finds PDF titled "Q4_planning_final.pdf" |
| Custom rules — no ML needed | Bank statement → Bank folder in < 1 ms |
| Duplicate detection | Same file, different name → Duplicates folder |
| AirDrop support | AirDrop photo from phone → auto-sorted to Photos |
