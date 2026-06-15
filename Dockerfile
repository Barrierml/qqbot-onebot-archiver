FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1
WORKDIR /app

COPY pyproject.toml README.md ./
COPY src ./src

RUN pip install --no-cache-dir .

VOLUME ["/data"]
ENV QQBOT_DATA_DIR=/data
CMD ["qqbot"]

