#!/bin/bash

# This is run one-time during the first time Postgres is initialized

echo "Creating database ${DB_NAME} and user..."

# Create the user and database "api"

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" <<-EOSQL
    CREATE USER ${DB_USER} WITH ENCRYPTED PASSWORD '${DB_PASSWORD}';
    CREATE DATABASE ${DB_NAME} OWNER ${DB_USER};
    GRANT ALL PRIVILEGES ON DATABASE ${DB_NAME} TO ${DB_USER};
EOSQL