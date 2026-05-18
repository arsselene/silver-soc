# Use a lightweight Python image
FROM python:3.11-slim

# Set the working directory inside the container
WORKDIR /app

# Copy the requirements file and install them
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy your Python script into the container
COPY enricher.py .

# Run the script with unbuffered output (-u) so logs appear instantly
CMD ["python", "-u", "enricher.py"]