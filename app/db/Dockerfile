FROM ankane/pgvector:latest

# Copy in the load-extensions script
COPY ./create_db.sh /docker-entrypoint-initdb.d/
RUN chmod +x /docker-entrypoint-initdb.d/create_db.sh