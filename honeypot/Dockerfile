FROM python:3.11-slim
WORKDIR /app
RUN pip install --no-cache-dir confluent-kafka
COPY producer.py .
CMD ["python", "-u", "producer.py"]
