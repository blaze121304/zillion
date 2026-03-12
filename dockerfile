
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
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 백엔드 코드 복사
COPY backend/ ./backend/

# 기존 zillion 프로젝트 복사 (백테스트 엔진)
COPY zillion/ ./zillion/ 2>/dev/null || echo "zillion 디렉터리가 없습니다. 나중에 마운트하세요."

# 환경 변수 설정
ENV PYTHONPATH=/app
ENV ENVIRONMENT=production

# 포트 노출
EXPOSE 8000

# 헬스체크
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
  CMD curl -f http://localhost:8000/health || exit 1

# 서버 실행
CMD ["python", "-m", "uvicorn", "backend.app:app", "--host", "0.0.0.0", "--port", "8000"]