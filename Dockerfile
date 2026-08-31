FROM python:3.12-slim
WORKDIR /app
COPY src/backend/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
COPY src ./src
COPY config ./config
ENV PORT=8080
CMD ["sh", "-c", "exec gunicorn --bind :$PORT --workers 1 --threads 4 --timeout 120 src.backend.app:app"]
