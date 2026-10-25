FROM python:3.12-slim
WORKDIR /app
COPY . .

RUN pip install --no-cache-dir -r requirements.txt
RUN mkdir -p /app/db/
VOLUME /app/db/

EXPOSE 5000

CMD ["gunicorn", "--preload", "--workers", "2", "--threads", "2", "--bind", "0.0.0.0:5000", "--access-logfile", "-", "app:app"]