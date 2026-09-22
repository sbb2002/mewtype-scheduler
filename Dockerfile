FROM python:3.12-slim
WORKDIR /app
COPY src/backend/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
COPY src ./src
COPY config ./config
ENV PORT=8080
# --timeout 300: (v3.8.5 핫픽스) 자동 /monitor 가 매월 1일 --monthly(최대 31일)·1월 1일
# --yearly(최대 366일)로 전환되며 날짜당 GitHub read_text 호출이 늘어 120s로는 빠듯해질 수
# 있어 상향(기존 120에서).
CMD ["sh", "-c", "exec gunicorn --bind :$PORT --workers 1 --threads 4 --timeout 300 src.backend.app:app"]
