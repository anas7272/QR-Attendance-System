FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Create folder for SQLite DB persistence
RUN mkdir -p /data
ENV DB_PATH=/data/attendance.db

EXPOSE 5000

CMD ["gunicorn", "--workers", "2", "--bind", "0.0.0.0:5000", "--timeout", "60", "app:app"]
