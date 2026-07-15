FROM python:3.9-slim
RUN apt-get update && apt-get install -y docker.io && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY lb.py consistent_hash.py .
RUN pip install flask requests
CMD ["python", "lb.py"]