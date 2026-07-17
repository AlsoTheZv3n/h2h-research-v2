#!/bin/sh
# Bring the schema up to date, then serve.
#
# Without this `docker compose up` starts an API against a database with no tables,
# and the first request 500s -- so the README's quickstart would be a lie the first
# time anyone ran it. compose waits for postgres to be *healthy* before starting us,
# so by here it is accepting connections.
#
# Safe to run every boot: alembic is a no-op when the schema is current. It would
# need a lock if several replicas booted at once; this is a single-instance app, and
# adding one now would be solving a problem we do not have.
set -e

echo "running migrations…"
alembic upgrade head

echo "starting api…"
exec uvicorn backend.main:app --host 0.0.0.0 --port 8000
