FROM python:3.11-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1

COPY . .

RUN python -m pip install --upgrade pip && \
    pip install --no-cache-dir ".[llm,test]"

ENV PORT=8000
EXPOSE 8000

CMD ["bash", "-lc", "uvicorn app.main:app --host 0.0.0.0 --port 8000"]
