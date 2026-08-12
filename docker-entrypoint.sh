#!/bin/sh
set -eu

# Uploaded media is private to the service account by default. The marker keeps
# large existing volumes from being recursively traversed on every restart.
umask 027

data_dir="${OSS_DATA_DIR:-/data}"
permission_marker="${data_dir}/.oss-permissions-v1"

mkdir -p "$data_dir" "$data_dir/files" "$data_dir/uploads"

if [ ! -f "$permission_marker" ]; then
    chown -R oss:oss "$data_dir"
    chmod 0750 "$data_dir" "$data_dir/files" "$data_dir/uploads"
    touch "$permission_marker"
    chown oss:oss "$permission_marker"
    chmod 0640 "$permission_marker"
else
    # Ensure directories introduced by a newer image are usable without
    # recursively touching every stored media file.
    chown oss:oss "$data_dir/files" "$data_dir/uploads"
    chmod 0750 "$data_dir/files" "$data_dir/uploads"
fi

exec gosu oss "$@"
