FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    REDRA_DATABASE_PATH=/data/settlements.db \
    REDRA_HOST=0.0.0.0 \
    PORT=8000

WORKDIR /app
COPY pyproject.toml README.md LICENSE NOTICE.md ./
COPY src ./src
RUN pip install --no-cache-dir .

RUN useradd --create-home --uid 10001 redra && mkdir -p /data && chown redra:redra /data
USER redra

EXPOSE 8000
ENTRYPOINT ["redra-mcp"]
CMD ["serve", "--transport", "streamable-http"]
