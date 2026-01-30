# Use an official Python runtime as a parent image
FROM python:3.11-slim

# Set the working directory in the container
WORKDIR /app

# Install Node.js and npm
RUN apt-get update && apt-get install -y nodejs npm

# Copy application files
COPY . .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Install Node.js dependencies and build CSS
RUN npm install
RUN npm run build

# Get the port from the environment variable (Cloud Run provides this)
ENV PORT 8080

# Expose the port the app runs on
EXPOSE $PORT

# Define the command to run the application
# Uvicorn will be started by the python script
CMD gunicorn -k uvicorn.workers.UvicornWorker -w 1 -b 0.0.0.0:$PORT main:app
