# Use an official Python runtime as a parent image
FROM python:3.12

# Set the working directory in the container
WORKDIR /app

# Copy the local directory contents into the container at /app
COPY ./transcriber_service /app/transcriber_service

# Install any needed packages specified in requirements.txt
# For now, installing directly
RUN pip install fastapi uvicorn[standard] celery redis boto3
RUN pip install git+https://github.com/geraldthewes/multistep-transcriber.git

# Make port 8000 available to the world outside this container
EXPOSE 8000

# Define environment variable
ENV MODULE_NAME="transcriber_service.app.main"
ENV VARIABLE_NAME="app"

# Run app.py when the container launches
CMD ["uvicorn", "transcriber_service.app.main:app", "--host", "0.0.0.0", "--port", "8000"]
