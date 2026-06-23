# san_sw 컨테이너 이미지
# 빌드 컨텍스트는 저장소 루트(.) 기준입니다.
#   docker build -f deploy/Dockerfile -t san_sw:latest .
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    SANSW_DATA_DIR=/app/data

WORKDIR /app

# 의존성 먼저(레이어 캐시)
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# 앱 소스
COPY . .

# 데이터 디렉터리(볼륨으로 마운트 권장)
RUN mkdir -p /app/data
VOLUME ["/app/data"]

EXPOSE 8000

# httpx는 런타임 의존성이라 헬스체크에 재사용
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import httpx,sys; sys.exit(0 if httpx.get('http://127.0.0.1:8000/healthz',timeout=3).status_code==200 else 1)"

CMD ["python", "-m", "uvicorn", "backend.app.main:app", \
     "--host", "0.0.0.0", "--port", "8000"]
