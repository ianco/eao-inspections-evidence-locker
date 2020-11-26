#!/bin/bash
set -e

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
    CREATE USER mara_db with password 'mara_db_pwd';
    CREATE DATABASE mara_db;
    GRANT ALL PRIVILEGES ON DATABASE mara_db TO mara_db;
EOSQL

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
    CREATE USER eao_locker_db with password 'eao_locker_db_pwd';
    CREATE DATABASE eao_locker_db;
    GRANT ALL PRIVILEGES ON DATABASE eao_locker_db TO eao_locker_db;
EOSQL

