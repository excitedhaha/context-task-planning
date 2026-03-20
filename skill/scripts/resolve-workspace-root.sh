#!/bin/sh

set -eu

START_DIR="${1:-$PWD}"
START_DIR=$(cd "$START_DIR" 2>/dev/null && pwd)

candidate="$START_DIR"
git_root=""

while :; do
    if [ -d "$candidate/.planning" ]; then
        printf '%s\n' "$candidate"
        exit 0
    fi

    if [ -e "$candidate/.git" ] && [ -z "$git_root" ]; then
        git_root="$candidate"
    fi

    parent=$(dirname "$candidate")
    if [ "$parent" = "$candidate" ]; then
        break
    fi

    candidate="$parent"
done

if [ -n "$git_root" ]; then
    printf '%s\n' "$git_root"
else
    printf '%s\n' "$START_DIR"
fi
