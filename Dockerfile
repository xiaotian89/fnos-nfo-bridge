FROM python:3.11-slim

LABEL org.opencontainers.image.title="fnos-nfo-bridge" \
      org.opencontainers.image.description="Sync NFO metadata into fnOS (Feiniu) Trim Media database" \
      org.opencontainers.image.licenses="MIT"

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    TZ=Asia/Shanghai

RUN apt-get update \
    && apt-get install -y --no-install-recommends tzdata \
    && ln -snf /usr/share/zoneinfo/$TZ /etc/localtime \
    && echo $TZ > /etc/timezone \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY app/ /app/app/

VOLUME ["/media"]
ENTRYPOINT ["python", "-u", "/app/app/main.py"]
