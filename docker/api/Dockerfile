FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PIP_NO_CACHE_DIR=1
ENV PYTHONPATH=/app

WORKDIR /app

COPY requirements-api.txt /app/requirements-api.txt

RUN python -m pip install --upgrade pip \
    && python -m pip install \
        --no-cache-dir \
        -r /app/requirements-api.txt

COPY api /app/api

EXPOSE 8000

CMD ["python", "-m", "uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]