FROM python:3.12-alpine

LABEL org.opencontainers.image.title="fnos-nfo-bridge" \
      org.opencontainers.image.description="Sync NFO metadata into fnOS (Feiniu) Trim Media database" \
      org.opencontainers.image.licenses="MIT"

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    TZ=Asia/Shanghai

RUN apk add --no-cache tzdata \
    && cp /usr/share/zoneinfo/Asia/Shanghai /etc/localtime \
    && echo "Asia/Shanghai" > /etc/timezone

WORKDIR /app

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY app/ /app/app/

VOLUME ["/media"]
ENTRYPOINT ["python", "-u", "/app/app/main.py"]
