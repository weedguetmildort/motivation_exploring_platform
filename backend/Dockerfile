# Use official Python image
FROM python:3.11-slim

# Set working directory inside container
WORKDIR /code

# Install system dependencies (optional, useful for MongoDB drivers, etc.)
RUN apt-get update && apt-get install -y build-essential

# Copy requirements first (better caching)
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the backend code
COPY . .

# Expose port for FastAPI
EXPOSE 8000

# Default command (can be overridden in docker-compose.yml)
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
