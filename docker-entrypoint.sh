#!/bin/sh
set -e

# Ensure the data volume exists and is writable by the unprivileged `oss`
# user (uid 1000), regardless of who owns the bind mount on the host.
mkdir -p "$OSS_DATA_DIR"
chown -R oss:oss "$OSS_DATA_DIR"

# Drop privileges and run the actual command.
exec gosu oss "$@"
