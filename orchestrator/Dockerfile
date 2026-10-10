FROM python:3.10-slim

WORKDIR /app

COPY orchestrator/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir --timeout 180 --retries 10 -r requirements.txt

COPY orchestrator/app/ ./app/
COPY 04-task-slicer-scheduler/src/task_slicer.py ./04-task-slicer-scheduler/src/task_slicer.py
COPY 06-verification-engine/src/verification.py ./06-verification-engine/src/verification.py
ENV COMPUTETORRENT_MODULE_ROOT=/app

EXPOSE 8001

CMD ["python", "app/main_production.py"]
