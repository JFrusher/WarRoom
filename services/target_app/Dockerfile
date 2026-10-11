FROM python:3.12-slim

# iputils-ping gives us a real `ping` binary so the diagnostics endpoint
# (and its injection bug) behaves like a genuine network tool.
RUN apt-get update \
    && apt-get install -y --no-install-recommends iputils-ping \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY config ./config
COPY src ./src
COPY templates ./templates
COPY scripts ./scripts
COPY scenarios ./scenarios

EXPOSE 5000

CMD ["python", "-m", "src.app"]
