#!/bin/sh
set -eu

APPLICATION_USER="operations"
APPLICATION_GROUP="operations"
APPLICATION_UID="$(id -u operations)"
RUNTIME_ROOT=""

resolve_runtime_storage() {
    configured_root="${RUNTIME_STORAGE_ROOT:-}"
    [ -n "$configured_root" ] || return 0

    case "$configured_root" in
        /*) candidate="$configured_root" ;;
        *) candidate="/app/backend/$configured_root" ;;
    esac
    RUNTIME_ROOT="$(readlink -m -- "$candidate")"

    case "$RUNTIME_ROOT" in
        /data|/data/*|/app/backend/data|/app/backend/data/*) ;;
        *)
            echo "RUNTIME_STORAGE_ROOT non consentita per il bootstrap container." >&2
            exit 64
            ;;
    esac

}

prepare_runtime_storage() {
    [ -n "$RUNTIME_ROOT" ] || return 0

    umask 0027
    install -d -m 0770 -o "$APPLICATION_USER" -g "$APPLICATION_GROUP" \
        "$RUNTIME_ROOT" \
        "$RUNTIME_ROOT/journal_media" \
        "$RUNTIME_ROOT/attachments"
}

verify_runtime_storage() {
    [ -n "$RUNTIME_ROOT" ] || return 0

    for directory in \
        "$RUNTIME_ROOT" \
        "$RUNTIME_ROOT/journal_media" \
        "$RUNTIME_ROOT/attachments"
    do
        if [ ! -d "$directory" ] || [ ! -r "$directory" ] || [ ! -w "$directory" ] || [ ! -x "$directory" ]; then
            echo "Root storage non accessibile all'utente operations: $directory" >&2
            exit 70
        fi
    done
}

resolve_runtime_storage

if [ "$(id -u)" -eq 0 ]; then
    prepare_runtime_storage
    exec gosu "$APPLICATION_USER:$APPLICATION_GROUP" "$@"
fi

if [ "$(id -u)" -ne "$APPLICATION_UID" ]; then
    echo "L'entrypoint deve terminare come utente operations." >&2
    exit 70
fi

verify_runtime_storage
exec "$@"
