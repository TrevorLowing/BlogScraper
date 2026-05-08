FROM python:3.11-slim

WORKDIR /app

COPY requirements-smoke.txt .
RUN pip install --no-cache-dir -r requirements-smoke.txt

COPY smoke_fetch.py .

ENV TARGET_URL=https://www.yidaiyilu.gov.cn/list/w/xmzb
ENV HTTP_TIMEOUT_SECONDS=120
ENV HTTP_RETRIES=3

CMD ["python", "/app/smoke_fetch.py"]
