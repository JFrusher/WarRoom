FROM python:3.12-slim

WORKDIR /app

COPY agents/red_team/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY agent_core ./agent_core
COPY agents/red_team/config ./config
COPY agents/red_team/src ./src

ENTRYPOINT ["python", "-m", "src.cli"]
CMD ["--help"]
