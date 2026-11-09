#!/bin/sh
# Herdr runs manifest commands in this directory; also support direct local use.
set -u
root=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd) || exit 1
binary=$root/bin/hwatch
herdr=${HERDR_BIN_PATH:-herdr}

open_pane() {
    entry=$1
    set -- plugin pane open --plugin "${HERDR_PLUGIN_ID:-hwatch}" --entrypoint "$entry"
    # Herdr overlays target the active pane and reject an explicit workspace.
    # Tabs can (and should) target the action's workspace context.
    if [ "$entry" = watcher ] && [ -n "${HERDR_WORKSPACE_ID:-}" ]; then
        set -- "$@" --workspace "$HERDR_WORKSPACE_ID"
    fi
    exec "$herdr" "$@"
}

profile_menu() {
    while :; do
        printf '\n%s\n' 'hwatch profiles' \
            '1. List profiles' '2. Create a profile' '3. Show a profile' \
            '4. Show configuration file location' '5. Remove a profile' \
            '6. Check setup' '7. Setup and configuration guide' 'q. Exit'
        printf 'Choice: '
        IFS= read -r choice || return 0
        case "$choice" in
            1) "$binary" profile list ;;
            2|3|4|5)
                printf 'Profile name: '
                IFS= read -r name || return 0
                case "$choice" in
                    2) operation=new ;;
                    3) operation=show ;;
                    4) operation=where ;;
                    5) operation=remove ;;
                esac
                "$binary" profile "$operation" "$name"
                ;;
            6) "$binary" doctor ;;
            7) "$binary" guide ;;
            q|Q) return 0 ;;
            *) printf '%s\n' 'Choose 1-7 or q.' ;;
        esac
    done
}

case "${1:-help}" in
    profile) open_pane profiles ;;
    watch) open_pane watcher ;;
esac
if [ ! -x "$binary" ]; then
    printf '%s\n' 'hwatch plugin binary is missing. Run sh plugin/install.sh, or build tools/build.py --output plugin/bin/hwatch before linking.' >&2
    exit 1
fi
case "${1:-help}" in
    help) exec "$binary" guide ;;
    doctor) exec "$binary" doctor ;;
    version) exec "$binary" --version ;;
    run) exec "$binary" run --once ;;
    profile-menu) profile_menu ;;
    watch-pane) exec "$binary" run ;;
    *) printf '%s\n' 'Usage: launch.sh {help|doctor|profile|version|run|watch}' >&2; exit 2 ;;
esac
