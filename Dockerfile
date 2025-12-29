# Use official Python 3.11 slim image
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONPATH=/app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Poetry (Use latest version for PEP 621 support)
RUN pip install poetry

# Configure poetry to install dependencies globally
RUN poetry config virtualenvs.create false

# Copy dependency definition files
COPY pyproject.toml poetry.lock ./

# Install dependencies (no root project installation yet)
RUN poetry install --no-interaction --no-ansi --no-root

# Copy the rest of the application
COPY . .

# Create directories for persistence
RUN mkdir -p data logs

# Expose Streamlit port
EXPOSE 8501

# Healthcheck to ensure container is running
HEALTHCHECK CMD curl --fail http://localhost:8501/_stcore/health || exit 1

# Run the application
CMD ["streamlit", "run", "src/dashboard/app.py", "--server.port=8501", "--server.address=0.0.0.0"]
