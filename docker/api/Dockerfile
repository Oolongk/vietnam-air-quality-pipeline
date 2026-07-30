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
        -r /app/requirements-api.txt \
    && python -m pip check

# The API reuses the canonical database configuration from src.utils.db.
RUN mkdir -p /app/src/utils
COPY src/__init__.py /app/src/__init__.py
COPY src/utils/__init__.py /app/src/utils/__init__.py
COPY src/utils/db.py /app/src/utils/db.py
COPY api /app/api

RUN python -m py_compile \
        /app/api/main.py \
        /app/api/database.py \
        /app/src/utils/db.py

EXPOSE 8000

CMD ["python", "-m", "uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
