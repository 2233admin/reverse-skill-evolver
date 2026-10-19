#!/bin/sh
set -e
CDPATH= cd "$(dirname "$0")"
exec ./gradlew jar "$@"
