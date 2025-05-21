# Use an official Python runtime as a parent image
FROM python:3.9-slim

# Set the working directory in the container
WORKDIR /app

# Copy the requirements file into the container at /app
COPY requirements.txt .

# Install any needed packages specified in requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application code into the container at /app
COPY . .

# Make port 5000 available to the world outside this container
EXPOSE 5000

# Define environment variable (optional, can be overridden at runtime)
ENV FLASK_APP=app.py
ENV FLASK_RUN_HOST=0.0.0.0
# The DATABASE_URL will ideally be provided in the `docker run` command for persistence.
# Example: ENV DATABASE_URL sqlite:////app/data/reservations.db

# Run app.py when the container launches
CMD ["flask", "run"]