FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    tesseract-ocr \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV PYTHONUNBUFFERED=1
ENV OMNISORT_WATCH_FOLDER=/watch
ENV OMNISORT_OUTPUT_FOLDER=/output

EXPOSE 8000

CMD ["uvicorn", "backend.api.api:app", "--host", "0.0.0.0", "--port", "8000"]
