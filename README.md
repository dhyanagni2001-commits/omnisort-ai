# OmniSort AI

An AI-powered file organizer that watches multiple folders simultaneously and sorts every file into the right place — automatically. Built privacy-first: sensitive files are detected locally and never sent to an external API.

---

## Privacy-first design

> Medical records, tax documents, and contracts may contain SSNs, email addresses, or phone numbers. OmniSort detects PII **before** any LLM call — including in the filename itself. If a file contains sensitive data, it is classified entirely on-device and the content never leaves your machine.

```
Check filename for PII
     │
     ▼
Extract text
     │
     ▼
Check content for PII (on-device, regex)
     │
     ├── PII found (filename OR content) ──► route to Sensitive/   ← LLM never called
     │
     └── No PII ──► keyword NLP ──► LLM fallback (only if needed)
```

This is a hard guarantee, not a configuration option. The PII gate runs synchronously before any network call is attempted.

---

## What it does

Drop a file into any watched folder (`~/Downloads`, `~/Desktop`, `~/Documents`, or any custom path). Within seconds OmniSort:

1. Waits until the file is fully written (not still downloading)
2. **Checks the filename for PII** — catches `john_SSN_123456789.pdf` before it's even opened
3. Extracts text — OCR for images, PDF parser for PDFs, **OCR fallback for scanned PDFs**
4. **Checks content for PII** — emails, phone numbers, SSNs detected on-device
5. Classifies the file — keyword NLP, then GPT-4o-mini only if no PII found
6. Checks for duplicates — SHA-256 hash with per-hash lock preventing concurrent misses
7. Moves the file — DB write only happens after the move succeeds
8. Logs to SQLite and pushes a live WebSocket event to the dashboard

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
└── Other/
```

Routing priority: **Sensitive > Duplicate > Category**

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
     ├── _wait_for_file_ready()         size must stabilise before processing starts
     │
     ├── SensitiveDetector (filename)   PII check on filename BEFORE file is opened
     │
     ├── ImageClassifier                PIL resolution + filename patterns → Photos / Screenshots
     │   └── OCRExtractor               pytesseract → text from images
     │
     ├── PDFProcessor                   PyPDF2 → text + metadata
     │   └── empty text? ─────────────► OCRExtractor.extract_text_from_pdf_page()
     │                                  PyMuPDF renders page → pytesseract (scanned PDFs)
     ├── DocxProcessor                  python-docx → text
     ├── TextProcessor                  plain read → text
     │
     ├── SensitiveDetector (content)    runs before any network call
     │   └── filename PII OR content PII? ──────────────────────────────► Sensitive/
     │   └── No PII ──► continue
     │
     ├── classify_document()            keyword NLP → Invoices / Resumes / Legal
     │   └── still "Documents"? ──────► LLMClassifier (GPT-4o-mini)
     │                                  → Medical / Financial / Academic / Other
     │
     ├── DuplicateDetector              SHA-256 + per-hash lock (atomic check + move + DB write)
     ├── PolicyEngine                   sets is_sensitive / is_duplicate flags
     │
     ├── FileOrganizer                  shutil.move → OmniSort/<category>/
     ├── db.insert_file()               DB write AFTER confirmed move — isolated try/except
     │
     ├── Metrics                        files/min, OCR failures, LLM calls, latency
     │
     └── event_queue  ──────────────────► FastAPI WebSocket ──► Electron dashboard
```

---

## Classification logic

### Images

1. Filename contains `screenshot`, `screen_`, `capture`, `snip` → **Screenshots**
2. Resolution matches a known screen dimension (720p / 1080p / 4K / iPad) → **Screenshots**
3. Everything else → **Photos**

### Documents (PDF / DOCX / TXT / CSV / MD)

**Stage 0 — Filename PII gate (runs before file is opened)**

The filename is scanned for email, phone, and SSN patterns. A file named `john_SSN_123456789.pdf` is routed to `Sensitive/` immediately — the file is never read.

**Stage 1 — Content PII gate (on-device, always runs before NLP/LLM)**

Extracted text is scanned for the same patterns. If any match:
- File is routed to `Sensitive/`
- `is_sensitive = 1` stored in DB
- No further network calls made — content stays on the machine

**Stage 1a — Scanned PDF OCR fallback**

If `PyPDF2` returns empty text (image-only PDF with no text layer), PyMuPDF renders the first page at 150 DPI and pytesseract extracts text from the rendered image. Scanned medical reports, tax forms, and contracts are no longer silently dropped into `Documents/`.

**Stage 2 — Keyword NLP (on-device, zero latency)**

| Keywords | Category |
|---|---|
| `invoice`, `bill`, `receipt`, `total amount`, `due date` | Invoices |
| `resume`, `curriculum vitae`, `work experience`, `references` | Resumes |
| `contract`, `agreement`, `terms and conditions`, `whereas` | Legal |

**Stage 3 — LLM fallback (GPT-4o-mini)**

Only reached when Stage 0 + Stage 1 found no PII **and** Stage 2 returned the generic `"Documents"` label. Sends the first 2 000 characters of extracted text and returns one of:

`Medical` · `Financial` · `Academic` · `Documents` · `Other`

---

## Sensitive file detection

PII is checked in two places — filename first, then content.

| Pattern | Example match |
|---|---|
| Email | `john.doe@example.com` |
| Phone | `555-867-5309` |
| SSN | `123-45-6789` |

Detection runs via `re` — no model, no network, no latency. A match in either the filename or the extracted text triggers the PII gate and prevents any LLM call.

---

## Duplicate detection

Every file is SHA-256 hashed (4 KB streaming chunks). To prevent a race condition where two identical files processed simultaneously both pass the duplicate check before either writes to the database, the entire sequence of **check → move → DB write** runs inside a per-hash `threading.Lock`. Only one thread can hold the lock for a given hash at a time.

The DB write is isolated in its own `try/except` — if it fails, the already-sorted file is not lost, and the error is logged.

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
| PII detection | `re` — on-device regex on filename + content, before any network call |
| NLP classification | Keyword matching — zero-dependency, zero-latency |
| LLM classification | OpenAI `gpt-4o-mini` — only for non-sensitive, ambiguous files |
| Duplicate detection | SHA-256 + per-hash threading lock |
| Observability | In-process metrics singleton (`metrics.py`) |
| Database | SQLite via `sqlite3` |
| REST + WebSocket API | `FastAPI` + `uvicorn` |
| Desktop UI | Electron (Node.js) |

---

## Project structure

```
omnisort-ai/
├── backend/
│   ├── main.py                          entry point — starts watcher + API
│   ├── watcher/
│   │   └── file_watcher.py              core orchestrator (watchdog + thread pool)
│   ├── classifier/
│   │   ├── image_classifier.py          PIL classifier + keyword NLP
│   │   └── llm_classifier.py            GPT-4o-mini fallback (PII-gated)
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
│   ├── database/
│   │   └── db.py                        SQLite schema + CRUD
│   ├── api/
│   │   └── api.py                       FastAPI — /health /stats /files /metrics /ws
│   └── logger/
│       └── logger.py                    file logger
├── electron-app/
│   ├── main.js                          Electron main — spawns Python backend
│   ├── app.html                         dashboard UI
│   └── app.js                           WebSocket client + DOM updates
├── configs/
│   └── settings.yaml                    watch_folders (list), output_folder, ports
├── tests/
│   ├── test_classifier.py               16 unit tests — image + document classifier
│   └── test_watcher.py                  26 integration tests — full pipeline
└── backend/requirements.txt
```

---

## Setup

### Prerequisites

- Python 3.10+
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

> The key is only used when a file reaches Stage 3 — non-sensitive, ambiguous documents only.

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
| `WS` | `/ws` | Live event stream (JSON) |

### `/api/metrics` response

```json
{
  "files_per_min": 4,
  "total_files": 37,
  "ocr_failures": 1,
  "llm_calls": 12,
  "avg_classification_ms": 843.21,
  "avg_llm_ms": 712.50,
  "duplicates": 3,
  "duplicate_rate": 0.0811
}
```

`files_per_min` is a live sliding 60-second window. `avg_classification_ms` covers the full NLP + optional LLM block per file. `avg_llm_ms` measures only the GPT-4o-mini call itself.

### WebSocket event shape

```json
{
  "type": "file_processed",
  "filename": "invoice_march.pdf",
  "category": "Invoices",
  "is_duplicate": 0,
  "is_sensitive": 0
}
```

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
| PII gate on content before LLM call | Sensitive content never sent to an external API |

---

## Configuration

`configs/settings.yaml`:

```yaml
watch_folders:            # all folders OmniSort monitors — add as many as you need
  - ~/Downloads
  - ~/Desktop
  - ~/Documents
output_folder: ~/Downloads/OmniSort
tesseract_path: /usr/local/bin/tesseract
api_host: 127.0.0.1
api_port: 8000
log_file: omnisort.log
file_ready_timeout: 30
```

OmniSort spins up one watchdog observer per folder. Folders that don't exist are skipped with a log warning — no crash. Add any folder you download files to; each is watched independently with the same pipeline.

---

## Tests

```bash
python -m pytest tests/ -v
```

```
tests/test_classifier.py   — 16 tests   (ImageClassifier + classify_document)
tests/test_watcher.py      — 26 tests   (full pipeline integration)
─────────────────────────────────────────
42 tests, 0 failures
```

Integration tests cover: image sorting, screenshot detection (filename + resolution), PDF → Invoices / Resumes / Documents, TXT, unsupported extensions → Other, PII detection → Sensitive, duplicate detection → Duplicates, concurrent processing deduplication, DB record creation, SHA-256 storage, output-folder re-processing guard.

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
