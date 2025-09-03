FROM python:3.13-slim

# Set the working directory inside the container
WORKDIR /app

# Copy only the requirements file first
COPY requirements.txt .

# Install system dependencies for compiling Python packages
RUN apt-get update && apt-get install -y \
    build-essential \
    gcc \
    g++ \
    libffi-dev \
    libssl-dev \
    python3-dev \
    && rm -rf /var/lib/apt/lists/*

RUN python -m pip install --no-cache-dir -r requirements.txt

# Copy the rest of the backend source code
COPY . .

# Expose the port FastAPI will run on
EXPOSE 8000

# Command to start the FastAPI server
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]