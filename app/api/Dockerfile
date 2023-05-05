FROM python:3.9

# Set the path to the API directory
WORKDIR /app/api

# Copy the codebase into the container
COPY . .

# Install the requirements
RUN pip install --no-cache-dir -r requirements.txt

# Expose the port
EXPOSE 8888

ENTRYPOINT ["uvicorn", "main:app", "--host", "api", "--port", "8888", "--reload"]