FROM python:3.12-slim

WORKDIR /app

COPY agents/blue_team/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY agent_core ./agent_core
COPY agents/blue_team/config ./config
COPY agents/blue_team/src ./src

CMD ["python", "-m", "src.monitor"]
