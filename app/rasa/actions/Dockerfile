FROM khalosa/rasa-aarch64:3.5.2

COPY . /app

WORKDIR /app
RUN pip install python-dotenv rasa-sdk requests
EXPOSE 5055

CMD ["run", "actions", "--debug"]