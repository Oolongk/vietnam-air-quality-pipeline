FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY requirements.txt /app/requirements.txt

RUN python -m pip install --upgrade pip \
    && python -m pip install \
        --no-cache-dir \
        -r /app/requirements.txt

COPY api /app/api
COPY src /app/src
COPY configs /app/configs

CMD ["python", "-m", "uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]