#!/bin/sh
set -e

# El volumen de Coolify puede montarse como root; nos aseguramos de que
# el usuario sin privilegios pueda escribir la base de datos y los logs.
mkdir -p /data /app/instance
chown -R app:app /data /app/instance

exec gosu app "$@"
