
# 백엔드 전용 Dockerfile
FROM python:3.11-slim

# 시스템 의존성 설치
RUN apt-get update && apt-get install -y \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# 작업 디렉터리 설정
WORKDIR /app

# Python 의존성 설치
COPY require.txt .
RUN pip install --no-cache-dir -r require.txt

# 소스 코드 복사
COPY src/ ./src/
COPY data/ ./data/ 2>/dev/null || echo "data 디렉터리가 없습니다."
COPY test/ ./test/ 2>/dev/null || echo "test 디렉터리가 없습니다."
COPY report/ ./report/ 2>/dev/null || echo "report 디렉터리가 없습니다."
COPY .env .env 2>/dev/null || echo ".env 파일이 없습니다."

# 환경 변수 설정
ENV PYTHONPATH=/app
ENV ENVIRONMENT=production

# 포트 노출 (10002번 포트로 통일)
EXPOSE 10002

# 헬스체크 (포트 번호 수정)
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
  CMD curl -f http://localhost:10002/health || exit 1

# 서버 실행 (10002 포트로 수정)
CMD ["python", "-m", "uvicorn", "src.app:app", "--host", "0.0.0.0", "--port", "10002"]