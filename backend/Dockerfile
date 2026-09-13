FROM python:3.12-slim

# scikit-learn and xgboost link against OpenMP at import time, and the slim
# base image leaves it out.
RUN apt-get update \
    && apt-get install -y --no-install-recommends libgomp1 \
    && rm -rf /var/lib/apt/lists/*

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8080

WORKDIR /srv

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app

EXPOSE 8080

# Cloud Run and Render both inject PORT, so it is expanded at start, not at build.
CMD exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT}
