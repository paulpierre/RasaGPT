FROM python:3.8-slim

WORKDIR /app/rasa-credentials
COPY . .

# Add CURL
RUN apt-get -y update
RUN apt-get -y install curl

# Install python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Expose the port
EXPOSE 8889

ENTRYPOINT ["uvicorn", "main:app", "--host", "rasa-credentials", "--port", "8889", "--reload"]