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

# 소스 코드 및 데이터 복사 (이미 생성된 폴더들을 단순 복사)
COPY src/ ./src/
COPY data/ ./data/
COPY test/ ./test/
COPY report/ ./report/

# .env 파일은 빌드 환경에 따라 없을 수도 있으므로 와일드카드(*)를 쓰면 안전합니다.
# 파일이 있으면 복사하고, 없어도 에러 없이 넘어갑니다.
COPY .env* ./

# 환경 변수 설정
ENV PYTHONPATH=/app
ENV ENVIRONMENT=production

# 포트 노출
EXPOSE 10002

# 헬스체크
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
  CMD curl -f http://localhost:10002/health || exit 1

# 서버 실행
CMD ["python", "-m", "uvicorn", "src.app:app", "--host", "0.0.0.0", "--port", "10002"]