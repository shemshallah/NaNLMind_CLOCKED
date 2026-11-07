FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8080 \
    CLOCKED_GATEWAY_DB=/data/clocked_gateway.sqlite3

WORKDIR /app
COPY integrations/clocked/requirements.txt /app/requirements.txt
RUN python -m pip install --no-cache-dir -r /app/requirements.txt \
    && useradd --system --uid 10001 --create-home clocked \
    && mkdir -p /data \
    && chown -R clocked:clocked /app /data

COPY integrations/clocked/ /app/
COPY deploy/koyeb/start.sh /app/start.sh
RUN chmod 0755 /app/start.sh

USER 10001:10001
EXPOSE 8080
ENTRYPOINT ["/app/start.sh"]
