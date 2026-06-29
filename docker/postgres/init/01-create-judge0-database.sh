#!/bin/sh
set -eu

psql \
  -v ON_ERROR_STOP=1 \
  --username "$POSTGRES_USER" \
  --dbname "$POSTGRES_DB" \
  --set dbname="${JUDGE0_POSTGRES_DB:-judge0}" \
  --set owner="$POSTGRES_USER" <<-'EOSQL'
SELECT format('CREATE DATABASE %I OWNER %I', :'dbname', :'owner')
WHERE NOT EXISTS (
  SELECT FROM pg_database WHERE datname = :'dbname'
)\gexec
EOSQL
