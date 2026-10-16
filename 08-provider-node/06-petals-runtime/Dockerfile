FROM python:3.10-slim
RUN apt-get update && apt-get install -y --no-install-recommends git build-essential libgomp1 ca-certificates && rm -rf /var/lib/apt/lists/*
WORKDIR /app
RUN pip install --no-cache-dir torch==2.2.2 --index-url https://download.pytorch.org/whl/cpu
RUN pip install --no-cache-dir 'numpy<2' 'petals @ git+https://github.com/bigscience-workshop/petals.git@22afba627a7eb4fcfe9418c49472c6a51334b8ac'
ENV HF_HOME=/cache/huggingface PETALS_CACHE=/cache/petals PYTHONUNBUFFERED=1
COPY gateway.py generate_job.py worker.py ./
EXPOSE 8002 31330 31331
CMD ["python", "/app/gateway.py"]
