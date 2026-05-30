FROM python:3.11-slim

WORKDIR /app

COPY pyproject.toml README.md ./
COPY blog_agent ./blog_agent

RUN pip install --no-cache-dir -e .

CMD ["python", "-m", "blog_agent.cli", "run", "--count", "5"]
