FROM python:3.12-slim

WORKDIR /app

COPY pyproject.toml .
COPY notificator/ notificator/

RUN pip install --no-cache-dir .

CMD ["python", "-m", "notificator.main"]
