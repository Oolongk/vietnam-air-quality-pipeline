FROM python:3.11-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PIP_NO_CACHE_DIR=1
ENV PYTHONPATH=/app
ENV PATH="/usr/local/bin:${PATH}"

WORKDIR /app

COPY dashboard/requirements.txt /app/requirements-dashboard.txt

RUN python -m pip install --upgrade pip setuptools wheel \
    && python -m pip install \
        --no-cache-dir \
        -r /app/requirements-dashboard.txt \
    && python -c "import streamlit; print('Installed Streamlit:', streamlit.__version__)"

COPY .streamlit /app/.streamlit
COPY dashboard /app/dashboard
COPY docker/dashboard/entrypoint.sh /usr/local/bin/dashboard-entrypoint

RUN chmod 0755 /usr/local/bin/dashboard-entrypoint \
    && test -f /app/dashboard/app.py \
    && test -f /app/dashboard/snapshot_client.py \
    && python -m py_compile \
        /app/dashboard/app.py \
        /app/dashboard/snapshot_client.py

EXPOSE 8501

ENTRYPOINT ["/usr/local/bin/dashboard-entrypoint"]
