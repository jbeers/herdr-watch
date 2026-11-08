#!/bin/sh
# Install a checksum-verified hwatch release. No sudo or shell-profile edits.
set -eu

usage() {
    printf '%s\n' 'Usage: install.sh [--version <version>] [--bin-dir <directory>]' \
        'Defaults: latest release, ${HWATCH_INSTALL_DIR:-$HOME/.local/bin}' \
        'HWATCH_VERSION may select a release such as v0.1.0.'
}
fail() { printf 'hwatch installer: %s\n' "$*" >&2; exit 1; }
fetch() { curl --fail --silent --show-error --location --proto '=https' --tlsv1.2 "$@"; }

main() {
    version=${HWATCH_VERSION:-latest}
    bin_dir=${HWATCH_INSTALL_DIR:-${HOME:?HOME is required}/.local/bin}
    while [ "$#" -gt 0 ]; do
        case "$1" in
            --version) [ "$#" -ge 2 ] || fail '--version requires a value'; version=$2; shift 2 ;;
            --bin-dir) [ "$#" -ge 2 ] || fail '--bin-dir requires a value'; bin_dir=$2; shift 2 ;;
            --help|-h) usage; return ;;
            *) fail "Unknown argument: $1" ;;
        esac
    done
    case "$bin_dir" in /*) ;; *) fail '--bin-dir must be an absolute path' ;; esac
    command -v curl >/dev/null 2>&1 || fail 'curl is required'
    case "$(uname -s)" in
        Linux) os=linux ;;
        Darwin) os=macos ;;
        *) fail 'Supported operating systems: Linux (glibc) and macOS' ;;
    esac
    case "$(uname -m)" in
        x86_64|amd64) arch=x64 ;;
        aarch64|arm64) arch=arm64 ;;
        *) fail 'Supported architectures: x86-64 and ARM64' ;;
    esac
    if command -v sha256sum >/dev/null 2>&1; then
        hash_tool=sha256sum
    elif command -v shasum >/dev/null 2>&1; then
        hash_tool=shasum
    else
        fail 'sha256sum or shasum is required to verify the download'
    fi
    repo=https://github.com/jbeers/herdr-watch
    if [ "$version" = latest ]; then
        # Resolve once so the binary and checksum always come from the same tag.
        url=$(fetch --output /dev/null --write-out '%{url_effective}' "$repo/releases/latest") || fail 'No release could be resolved. Check GitHub releases or use --version.'
        version=${url##*/}
    fi
    case "$version" in v*) ;; *) version=v$version ;; esac
    case "$version" in v[0-9]*) ;; *) fail 'Version must begin with a number (optionally prefixed with v)' ;; esac
    case "$version" in *[!a-zA-Z0-9._-]*) fail 'Invalid release version' ;; esac
    asset=hwatch-$os-$arch
    work=$(mktemp -d "${TMPDIR:-/tmp}/hwatch-install.XXXXXXXX") || fail 'Cannot create temporary directory'
    trap 'rm -rf "$work"' 0
    trap 'exit 129' HUP
    trap 'exit 130' INT
    trap 'exit 143' TERM
    base=$repo/releases/download/$version
    printf 'Downloading %s (%s)…\n' "$asset" "$version"
    fetch "$base/$asset" --output "$work/$asset" || fail "Download failed: $base/$asset"
    fetch "$base/SHA256SUMS" --output "$work/SHA256SUMS" || fail 'Could not download SHA256SUMS'
    expected=$(awk -v asset="$asset" '$2 == asset { print $1 }' "$work/SHA256SUMS")
    [ "${#expected}" -eq 64 ] || fail 'Missing or invalid checksum for the selected binary'
    case "$expected" in *[!0-9a-f]*) fail 'Invalid SHA-256 checksum' ;; esac
    if [ "$hash_tool" = sha256sum ]; then
        actual=$(sha256sum "$work/$asset" | awk '{print $1}')
    else
        actual=$(shasum -a 256 "$work/$asset" | awk '{print $1}')
    fi
    [ "$actual" = "$expected" ] || fail 'Checksum mismatch; existing installation was not changed'
    chmod 755 "$work/$asset"
    "$work/$asset" --help >/dev/null || fail 'The downloaded binary cannot run on this system; existing installation was not changed'
    mkdir -p "$bin_dir" || fail "Cannot create $bin_dir"
    # Stage on the destination filesystem, then replace without exposing a partial binary.
    staged=$(mktemp "$bin_dir/.hwatch.XXXXXXXX") || fail "Cannot write to $bin_dir"
    trap 'rm -rf "$work"; rm -f "$staged"' 0
    cp "$work/$asset" "$staged"
    chmod 755 "$staged"
    mv -f "$staged" "$bin_dir/hwatch"
    printf 'Installed hwatch %s to %s/hwatch\n' "$version" "$bin_dir"
    case ":${PATH:-}:" in
        *":$bin_dir:"*) ;;
        *) printf 'Add this directory to PATH in your shell configuration: %s\n' "$bin_dir" ;;
    esac
    printf '%s\n' 'Next: hwatch profile new <name>, then hwatch doctor.' \
        'Runtime tools required: kubectl, virtctl, herdr, ssh, sh, mkdir.'
}

main "$@"
