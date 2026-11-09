FROM python:3.13-slim

# 日本時間で記録するため、タイムゾーンを埋め込む
ENV TZ=Asia/Tokyo
ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src/ ./src/

# 鍵ファイルを読むだけなので、root で動かす必要がない
RUN useradd --create-home --uid 1000 runner
USER runner

CMD ["python", "-m", "src.main"]
