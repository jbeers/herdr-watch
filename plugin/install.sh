#!/bin/sh
# Herdr clones the repository; build commands run in the selected plugin subdir.
set -eu
root=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
version=$(awk -F '"' '$1 ~ /^version[[:space:]]*=[[:space:]]*$/ { print $2 }' "$root/herdr-plugin.toml")
[ -n "$version" ] || { printf '%s\n' 'Missing plugin release version' >&2; exit 1; }
# Explicit flags prevent user-level installer environment from changing the pin
# or installing the plugin binary into the standalone CLI's PATH directory.
sh "$root/../install.sh" --version "$version" --bin-dir "$root/bin" --no-path-hint
printf '%s\n' 'Plugin binary ready. Next: herdr plugin action invoke hwatch.help' \
    'Do not add this managed plugin directory to PATH.'
