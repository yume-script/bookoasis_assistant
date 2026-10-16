FROM python:3.12-slim

# rclone (VFS 새로고침·토큰 갱신에 rclone 실행 파일을 쓴다)
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates curl unzip tzdata \
    && curl -fsSL https://rclone.org/install.sh | bash \
    && apt-get purge -y curl unzip && apt-get autoremove -y && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .

ENV DATA_DIR=/data WEB_HOST=0.0.0.0 WEB_PORT=5931 PYTHONUNBUFFERED=1
VOLUME ["/data"]
EXPOSE 5931
STOPSIGNAL SIGTERM
CMD ["python", "app.py"]
