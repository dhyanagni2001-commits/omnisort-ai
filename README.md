# OmniSort AI

An AI-powered file organizer that watches multiple folders simultaneously and sorts every file into the right place — automatically. Define custom folders for your own categories (Bank, Tax, Work, ML Notes). Built privacy-first: sensitive files are detected locally and **never sent to an external API**.

---

## Privacy-first design

> Medical records, tax documents, and contracts may contain SSNs, email addresses, or phone numbers. OmniSort detects PII **before** any model or API call — including in the filename itself. If a file is sensitive, it is classified entirely on-device and the content never leaves your machine.

```
Check filename for PII
       │
       ▼
Extract text (OCR / PDF parser / plain read)
       │
       ▼
Check content for PII  (on-device regex)
       │
       ├── PII found ──► Sensitive/   ← DistilBERT and LLM never called
       │
       └── No PII ──► custom rules ──► keyword NLP ──► DistilBERT ──► LLM (last resort)
```

This is a hard guarantee, not a configuration option. The PII gate runs synchronously before any model inference or network call is attempted.

---

## What it does

Drop a file into any watched folder (`~/Downloads`, `~/Desktop`, `~/Documents`, or any custom path). Within seconds OmniSort:

1. Waits until the file is fully written (not still downloading)
2. **Checks the filename for PII** — catches `john_SSN_123456789.pdf` before it's even opened
3. Extracts text — OCR for images, PyPDF2 for PDFs, **OCR fallback for scanned PDFs** with no text layer
4. **Checks content for PII** — emails, phone numbers, SSNs detected on-device via regex
5. **Runs custom rules** — your own keyword-to-folder mappings, free, no model call
6. **Keyword NLP** — instantly matches Invoices, Resumes, Legal
7. **DistilBERT zero-shot** — catches Medical, Financial, Academic locally, no API cost
8. **GPT-4o-mini fallback** — only called when all local stages are uncertain
9. Checks for duplicates — SHA-256 hash with per-hash lock preventing concurrent misses
10. Moves the file — DB write only happens after the move succeeds
11. Generates a 384-dim embedding and stores it for semantic search
12. Logs to SQLite and pushes a live WebSocket event to the dashboard

---

## Output folder structure

```
~/Downloads/OmniSort/
├── Photos/
├── Screenshots/
├── Documents/
├── Invoices/
├── Resumes/
├── Legal/
├── Medical/
├── Financial/
├── Academic/
├── Videos/
├── Audio/
├── Archives/
├── Sensitive/        ← PII in filename OR content — classified on-device only
├── Duplicates/       ← same SHA-256 as a previously seen file
├── Other/
│
│   ── custom folders (created automatically from your rules) ──
├── Bank/             ← matches "bank statement", "HDFC", "transaction history"
├── Tax/              ← matches "form 16", "income tax", "assessment year"
├── Work/             ← matches "standup", "sprint", "quarterly review"
└── Health/           ← matches "prescription", "blood report", "diagnosis"
```

Routing priority: **Sensitive > Duplicate > Custom Rule > Keyword NLP > DistilBERT > LLM**

---

## Custom rules

Define your own folder → keyword mappings in `configs/settings.yaml`. No code change needed — edit the file and restart.

```yaml
custom_rules:
  - folder: Bank
    keywords: ["bank statement", "account number", "transaction history", "HDFC", "ICICI", "SBI"]

  - folder: Tax
    keywords: ["form 16", "itr", "income tax", "pan card", "assessment year", "tds certificate"]

  - folder: ML Notes
    keywords: ["neural network", "gradient descent", "backpropagation", "loss function", "epoch"]

  - folder: Client XYZ
    keywords: ["XYZ Corp", "project apollo", "statement of work"]
```

Rules match against **both the filename and the extracted text**. The first matching rule wins. Folders are created automatically if they don't exist.

**Priority over built-in categories** — if a rule matches, DistilBERT and the LLM are skipped entirely. Custom rules cost nothing.

**PII always wins** — a bank statement containing an SSN goes to `Sensitive/`, not `Bank/`.

---

## Architecture

```
~/Downloads  ──┐
~/Desktop    ──┼── watchdog FSEvents (one observer per folder)
~/Documents  ──┘
      │
      ▼
ThreadPoolExecutor (max 4 workers) ── caps concurrency, prevents thread explosion
      │
      ▼
FileWatcher._process_file()
      │
      ├── _wait_for_file_ready()          size must stabilise before processing starts
      │
      ├── SensitiveDetector (filename)    PII check on filename BEFORE file is opened
      │
      ├── ImageClassifier                 PIL resolution + filename patterns → Photos / Screenshots
      │   └── OCRExtractor                pytesseract → text from images
      │
      ├── PDFProcessor                    PyPDF2 → text + metadata
      │   └── empty text? ──────────────► OCRExtractor.extract_text_from_pdf_page()
      │                                   PyMuPDF renders page → pytesseract (scanned PDFs)
      ├── DocxProcessor                   python-docx → text
      ├── TextProcessor                   plain read → text
      │
      ├── SensitiveDetector (content)     runs before any model or network call
      │   └── PII found? ────────────────────────────────────────────────────► Sensitive/
      │   └── No PII ──► continue
      │
      ├── RulesEngine                     user-defined keyword → folder mappings
      │   └── rule matched? ─────────────────────────────────────────────────► Custom folder/
      │   └── no match ──► continue
      │
      ├── classify_document()             Stage 3: keyword NLP → Invoices / Resumes / Legal
      │   └── still "Documents"?
      │       │
      │       ├── MLClassifier            Stage 3.5: DistilBERT zero-shot (local, no API)
      │       │   └── confident result? ────────────────────────────────────► category/
      │       │   └── uncertain ──► continue
      │       │
      │       └── LLMClassifier           Stage 4: GPT-4o-mini (last resort only)
      │                                   → Medical / Financial / Academic / Other
      │
      ├── embed_text()                    fastembed 384-dim vector stored in SQLite
      │
      ├── DuplicateDetector               SHA-256 + per-hash lock (atomic check + move + DB write)
      ├── PolicyEngine                    sets is_sensitive / is_duplicate flags
      │
      ├── FileOrganizer                   shutil.move → OmniSort/<category>/
      ├── db.insert_file()                DB write AFTER confirmed move — isolated try/except
      │
      ├── Metrics                         files/min, OCR failures, LLM calls, latency
      │
      └── event_queue  ───────────────────► FastAPI WebSocket ──► Electron dashboard
```

---

## Classification logic

### Images

1. Filename contains `screenshot`, `screen_`, `capture`, `snip` → **Screenshots**
2. Resolution matches a known screen dimension (720p / 1080p / 4K / iPad) → **Screenshots**
3. Everything else → **Photos**

### Documents (PDF / DOCX / TXT / CSV / MD)

**Stage 0 — Filename PII gate (runs before file is opened)**

Filename scanned for email, phone, SSN. A file named `john_SSN_123456789.pdf` goes to `Sensitive/` immediately — the file is never read.

**Stage 1 — Content PII gate (on-device, before any model call)**

Extracted text scanned for the same patterns. Match → `Sensitive/`, `is_sensitive = 1`, no further model or network calls.

**Stage 1a — Scanned PDF OCR fallback**

If PyPDF2 returns empty text (image-only PDF), PyMuPDF renders the first page at 150 DPI and pytesseract extracts text. Scanned medical reports, tax forms, and contracts are no longer silently dropped into `Documents/`.

**Stage 2 — Custom rules (on-device, zero latency, zero cost)**

User-defined keyword mappings from `settings.yaml` checked against filename + content. First match wins → file goes to the custom folder, all remaining stages skipped.

**Stage 3 — Keyword NLP (on-device, zero latency)**

| Keywords | Category |
|---|---|
| `invoice`, `bill`, `receipt`, `total amount`, `due date` | Invoices |
| `resume`, `curriculum vitae`, `work experience`, `references` | Resumes |
| `contract`, `agreement`, `terms and conditions`, `whereas` | Legal |

**Stage 3.5 — DistilBERT zero-shot classifier (local ML, no API cost)**

Uses `typeform/distilbert-base-uncased-mnli` (~260 MB, downloads on first use). Scores seven natural-language candidate labels as NLI entailment hypotheses against the document text. Returns a category when confidence exceeds 50%, otherwise falls through to Stage 4.

Catches the categories keyword NLP misses most:

| Category | Why keywords fail | Why DistilBERT works |
|---|---|---|
| Medical | "blood report" varies widely | Understands semantic meaning |
| Financial | Bank statements rarely say "financial" | NLI scores "financial document" as entailment |
| Academic | No fixed vocabulary | Semantic similarity to "research paper" |

Runs entirely on CPU (~50 ms/doc). Degrades gracefully — returns `None` when torch is unavailable (Python 3.13 dev env), and Stage 4 takes over.

**Stage 4 — LLM fallback (GPT-4o-mini)**

Only reached when Stages 0–3.5 all passed without a confident match. Sends first 2,000 characters. Returns one of:

`Medical` · `Financial` · `Academic` · `Documents` · `Other`

---

## Sensitive file detection

PII is checked in two places — filename first, then content.

| Pattern | Example match |
|---|---|
| Email | `john.doe@example.com` |
| Phone | `555-867-5309` |
| SSN | `123-45-6789` |

Detection runs via `re` — no model, no network, no latency. A match in either the filename or extracted text triggers the PII gate and prevents all downstream model calls.

---

## Duplicate detection

Every file is SHA-256 hashed (4 KB streaming chunks). To prevent a race condition where two identical files processed simultaneously both pass the duplicate check before either writes to the database, the entire sequence of **check → move → DB write** runs inside a per-hash `threading.Lock`.

The DB write is isolated in its own `try/except` — if it fails, the already-sorted file is not lost.

---

## Tech stack

| Layer | Technology |
|---|---|
| File watching | `watchdog` (FSEvents on macOS) |
| Concurrency | `ThreadPoolExecutor` (max 4 workers) |
| Image classification | `Pillow` — resolution + filename heuristics |
| OCR | `pytesseract` (Tesseract 5) |
| PDF parsing | `PyPDF2` |
| Scanned PDF OCR | `PyMuPDF` — renders pages to images for pytesseract |
| DOCX parsing | `python-docx` |
| PII detection | `re` — on-device regex on filename + content, before any model call |
| Custom rules | Keyword engine — user-defined folder mappings, zero cost |
| Keyword NLP | Keyword matching — zero-dependency, zero-latency (Stage 3) |
| ML classifier | `transformers` DistilBERT zero-shot NLI — local, no API cost (Stage 3.5) |
| LLM classifier | OpenAI `gpt-4o-mini` — last resort only, never called for sensitive files (Stage 4) |
| Semantic search | `fastembed` (ONNX, BAAI/bge-small-en-v1.5) — 384-dim embeddings, cosine similarity |
| Duplicate detection | SHA-256 + per-hash threading lock |
| Observability | In-process metrics singleton — files/min, latency, LLM calls, duplicate rate |
| Database | SQLite via `sqlite3` |
| REST + WebSocket API | `FastAPI` + `uvicorn` |
| Desktop UI | Electron (Node.js) |
| Docker | `python:3.11-slim` + CPU-only torch, volume mounts for watch/output folders |

---

## Project structure

```
omnisort-ai/
├── backend/
│   ├── main.py                          entry point — starts watcher + API
│   ├── watcher/
│   │   └── file_watcher.py              core orchestrator (watchdog + thread pool)
│   ├── classifier/
│   │   ├── image_classifier.py          PIL classifier + keyword NLP (Stage 3)
│   │   ├── ml_classifier.py             DistilBERT zero-shot NLI (Stage 3.5)
│   │   └── llm_classifier.py            GPT-4o-mini fallback (Stage 4, PII-gated)
│   ├── rules/
│   │   └── rules_engine.py              user-defined keyword → folder rules
│   ├── ocr/
│   │   └── ocr_extractor.py             pytesseract + PyMuPDF scanned-PDF fallback
│   ├── processor/
│   │   ├── pdf_process.py               PyPDF2 wrapper
│   │   ├── doc_process.py               python-docx wrapper
│   │   └── text_process.py              plain text reader
│   ├── sensitive_detection/
│   │   └── sensitive.py                 on-device regex PII detector (filename + content)
│   ├── duplicate_detection/
│   │   └── duplicate_detector.py        SHA-256 + DB lookup
│   ├── policy_engine/
│   │   └── policy_engine.py             sets routing flags from metadata
│   ├── organizer/
│   │   └── file_organizer.py            shutil.move + collision handling
│   ├── metrics/
│   │   └── metrics.py                   thread-safe in-process metrics store
│   ├── embeddings/
│   │   └── embedding.py                 fastembed — 384-dim vectors, cosine similarity
│   ├── database/
│   │   └── db.py                        SQLite schema + CRUD (includes embedding column)
│   ├── api/
│   │   └── api.py                       FastAPI — /health /stats /files /metrics /search /ws
│   └── logger/
│       └── logger.py                    file + stdout logger
├── electron-app/
│   ├── main.js                          Electron main — spawns Python backend
│   ├── app.html                         dashboard UI
│   └── app.js                           WebSocket client + DOM updates
├── configs/
│   └── settings.yaml                    watch_folders, custom_rules, output_folder, ports
├── tests/
│   ├── test_classifier.py               16 unit tests — image + document classifier
│   └── test_watcher.py                  28 integration tests — full pipeline + custom rules
├── Dockerfile                           python:3.11-slim + tesseract + CPU torch
├── docker-compose.yml                   volume mounts, env var overrides
├── DEMO.md                              step-by-step walkthrough with exact commands
└── backend/requirements.txt
```

---

## Setup

### Prerequisites

- Python 3.10+ (3.11 recommended — required for DistilBERT / Docker)
- Node.js 18+
- Tesseract OCR

```bash
# macOS
brew install tesseract

# Ubuntu/Debian
sudo apt install tesseract-ocr
```

### Install Python dependencies

```bash
cd omnisort-ai
pip install -r backend/requirements.txt
```

> **Note:** `torch` and `transformers` (for the DistilBERT stage) require Python ≤ 3.12. On Python 3.13, those packages are skipped and the DistilBERT stage degrades gracefully — all other features work normally. Use Docker or a Python 3.11 environment to run the full pipeline.

### Install Electron dependencies

```bash
cd electron-app
npm install
```

### Set your OpenAI API key

```bash
export OPENAI_API_KEY="sk-..."
```

Add to your shell profile to make it permanent:

```bash
echo 'export OPENAI_API_KEY="sk-..."' >> ~/.zshrc
source ~/.zshrc
```

> The key is only used at Stage 4 — non-sensitive, ambiguous documents that keyword NLP and DistilBERT both failed to classify confidently.

---

## Running

### Python backend only (headless)

```bash
python -m backend.main
```

```
OmniSort AI running
Watching /Users/you/Downloads
Watching /Users/you/Desktop
Watching /Users/you/Documents
API at http://127.0.0.1:8000
```

### Full desktop app (Electron + Python)

```bash
cd electron-app
npm start
```

Electron spawns the Python backend automatically and opens the dashboard.

### Docker (full pipeline including DistilBERT)

```bash
OPENAI_API_KEY=sk-... WATCH_FOLDER=~/Downloads docker-compose up
```

Docker runs Python 3.11 so the DistilBERT classifier is fully active. The DistilBERT model (~260 MB) downloads on first run and is cached inside the container.

---

## Dashboard

The Electron UI connects to `ws://127.0.0.1:8000/ws` and shows:

- **Files Sorted** — total processed count
- **Duplicates** — files with matching SHA-256
- **Sensitive** — files containing PII
- **Live Activity** — real-time feed as files are sorted
- **File History** — scrollable table with filename, category, size, timestamp

---

## REST API

All endpoints served at `http://127.0.0.1:8000`.

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/health` | Liveness check → `{"status":"ok"}` |
| `GET` | `/api/stats` | Totals + per-category counts |
| `GET` | `/api/files?limit=50&offset=0` | Paginated file history |
| `GET` | `/api/metrics` | Runtime observability snapshot |
| `GET` | `/api/search?q=...&limit=10` | Semantic search over processed files |
| `WS`  | `/ws` | Live event stream (JSON) |

### `/api/metrics` response

```json
{
  "files_per_min": 4,
  "total_files": 37,
  "ocr_failures": 1,
  "llm_calls": 3,
  "avg_classification_ms": 843.21,
  "avg_llm_ms": 712.50,
  "duplicates": 3,
  "duplicate_rate": 0.0811
}
```

### WebSocket event shape

```json
{
  "type": "file_processed",
  "filename": "hdfc_march.pdf",
  "category": "Bank",
  "is_duplicate": 0,
  "is_sensitive": 0
}
```

---

## Semantic search

Every processed text document gets a 384-dimensional embedding stored in SQLite (BAAI/bge-small-en-v1.5 via `fastembed`, ONNX runtime — no PyTorch required).

```bash
curl "localhost:8000/api/search?q=quarterly+revenue+report&limit=5"
```

Returns files ranked by cosine similarity — finds the right document even when the filename is `final_FINAL_v3.pdf`. Files without extractable text (images, video, audio) are excluded from results gracefully.

---

## Docker

No Python install needed. Mount your watch folder and set your API key:

```bash
OPENAI_API_KEY=sk-... WATCH_FOLDER=~/Downloads docker-compose up
```

The API is available at `http://localhost:8000`. Files are sorted into a named Docker volume (`omnisort_output`). To mount the output to a local path instead, edit `docker-compose.yml`:

```yaml
volumes:
  - /Users/you/OmniSort:/output
```

Build the image manually:

```bash
docker build -t omnisort-ai .
```

---

## Demo

See [DEMO.md](DEMO.md) for a step-by-step walkthrough of every feature with exact commands.

---

## AirDrop support

AirDrop writes a `.part` temp file then renames it to the final name. OmniSort catches the rename via `on_moved` (not `on_created`), skips `.part` files entirely, and processes the destination path — so AirDropped files sort correctly.

---

## Safety mechanisms

| Mechanism | What it prevents |
|---|---|
| `fcntl` PID lock (`/tmp/omnisort.lock`) | Multiple OmniSort instances running simultaneously |
| `ThreadPoolExecutor(max_workers=4)` | Thread explosion when hundreds of files land at once |
| `_processing` set + `threading.Lock` | Same file processed twice from concurrent watchdog events |
| Per-hash `threading.Lock` | Two identical files both passing duplicate check before either writes to DB |
| `_wait_for_file_ready()` | Processing a file still being written (checks size stability) |
| DB write after confirmed move | Move fails → DB never written; DB failure → file already sorted, error logged |
| `SKIP_SUFFIXES` (`.crdownload`, `.part`, `.tmp`, `.download`) | Browser temp files that never stabilise |
| Dot-file filter (`.DS_Store`, `.com.brave.*`) | macOS metadata and browser internal files |
| Output folder filter | OmniSort's own `shutil.move` re-triggering the watcher |
| PII gate on filename before file is opened | Sensitive filenames caught before content is read |
| PII gate on content before any model call | Sensitive content never sent to DistilBERT or OpenAI |

---

## Configuration

`configs/settings.yaml`:

```yaml
watch_folders:            # folders to monitor — add as many as you need
  - ~/Downloads
  - ~/Desktop
  - ~/Documents

output_folder: ~/Downloads/OmniSort

custom_rules:             # keyword → folder mappings, checked before NLP/ML/LLM
  - folder: Bank
    keywords: ["bank statement", "account number", "HDFC", "ICICI", "SBI"]
  - folder: Tax
    keywords: ["form 16", "itr", "income tax", "assessment year"]
  - folder: Work
    keywords: ["standup", "sprint", "jira", "quarterly review"]
  - folder: Health
    keywords: ["prescription", "blood report", "diagnosis", "pathology"]

tesseract_path: /usr/local/bin/tesseract
api_host: 127.0.0.1
api_port: 8000
log_file: omnisort.log
file_ready_timeout: 30
```

---

## Tests

```bash
python -m pytest tests/ -v
```

```
tests/test_classifier.py   — 16 tests   (ImageClassifier + classify_document)
tests/test_watcher.py      — 28 tests   (full pipeline + custom rules)
─────────────────────────────────────────
44 tests, 0 failures
```

Integration tests cover: image sorting, screenshot detection by filename and resolution, PDF → Invoices / Resumes / Documents, TXT, unsupported extension → Other, PII detection → Sensitive, PII overrides custom rule, custom rule → custom folder, duplicate detection, concurrent deduplication race condition, DB record creation, SHA-256 storage, output-folder re-processing guard.

---

## Supported file types

| Type | Extensions | Processing |
|---|---|---|
| Images | `.jpg` `.jpeg` `.png` `.gif` `.webp` `.heic` | PIL classification + optional OCR |
| PDF | `.pdf` | PyPDF2 text extraction; PyMuPDF + OCR fallback for scanned PDFs |
| Word | `.docx` `.doc` | python-docx text extraction |
| Text | `.txt` `.csv` `.md` | plain read |
| Video | `.mp4` `.mov` `.avi` `.mkv` `.m4v` | routed to `Videos/` |
| Audio | `.mp3` `.wav` `.aac` `.flac` `.m4a` | routed to `Audio/` |
| Archive | `.zip` `.rar` `.tar` `.gz` `.7z` | routed to `Archives/` |
| Other | anything else | routed to `Other/` |
