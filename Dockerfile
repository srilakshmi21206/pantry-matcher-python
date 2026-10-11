FROM python:3.12.15-slim

WORKDIR /app

# Install dependencies first so this layer is cached
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Create a non-root user
RUN useradd --create-home --shell /usr/sbin/nologin appuser

# Copy source after dependencies
COPY app ./app
COPY migrations ./migrations

USER appuser

EXPOSE 8080

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]