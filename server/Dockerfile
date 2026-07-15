FROM python:3.9-slim
WORKDIR /app
COPY server.py .
RUN pip install flask
ENV SERVER_ID=default
CMD ["python", "server.py"]