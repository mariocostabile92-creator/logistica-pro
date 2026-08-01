#!/bin/sh
set -eu

APPLICATION_USER="operations"
APPLICATION_GROUP="operations"
APPLICATION_UID="$(id -u operations)"

prepare_runtime_storage() {
    configured_root="${RUNTIME_STORAGE_ROOT:-}"
    [ -n "$configured_root" ] || return 0

    case "$configured_root" in
        /*) candidate="$configured_root" ;;
        *) candidate="/app/backend/$configured_root" ;;
    esac
    runtime_root="$(readlink -m -- "$candidate")"

    case "$runtime_root" in
        /data|/data/*|/app/backend/data|/app/backend/data/*) ;;
        *)
            echo "RUNTIME_STORAGE_ROOT non consentita per il bootstrap container." >&2
            exit 64
            ;;
    esac

    if [ "$(id -u)" -ne 0 ]; then
        echo "Il bootstrap della root storage richiede i privilegi iniziali del container." >&2
        exit 70
    fi

    umask 0027
    install -d -m 0770 -o "$APPLICATION_USER" -g "$APPLICATION_GROUP" \
        "$runtime_root" \
        "$runtime_root/journal_media" \
        "$runtime_root/attachments"
}

prepare_runtime_storage

if [ "$(id -u)" -eq 0 ]; then
    exec gosu "$APPLICATION_USER:$APPLICATION_GROUP" "$@"
fi

if [ "$(id -u)" -ne "$APPLICATION_UID" ]; then
    echo "L'entrypoint deve terminare come utente operations." >&2
    exit 70
fi

exec "$@"
