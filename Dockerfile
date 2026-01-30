# Use an official Python runtime as a parent image
FROM python:3.11-slim

# Set the working directory in the container
WORKDIR /app

# Copy the dependencies file to the working directory
COPY requirements.txt .

# Install any needed packages specified in requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application's code to the working directory
COPY . .

# Get the port from the environment variable (Cloud Run provides this)
ENV PORT 8080

# Expose the port the app runs on
EXPOSE $PORT

# Define the command to run the application
# Uvicorn will be started by the python script
CMD ["python", "main.py"]
