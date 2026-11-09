# hwatch for Herdr

A terminal-based Herdr plugin for KubeVirt and Tailscale inventory reconciliation.
It bundles the same native hwatch CLI, not a second implementation. Herdr **0.9.2+**,
Linux (glibc 2.39+) or macOS, and x86-64 or ARM64 are supported packaging targets.
The plugin has been exercised locally on Linux x86-64 with Herdr 0.9.2; release
binaries and launcher tests for the other targets are gated by CI.

## Install

**This plugin is prepared for v0.3.0. GitHub installation requires that tag and its
native release assets to be published first.** Until then, use local linking below.

```sh
herdr plugin install jbeers/herdr-watch/plugin --ref v0.3.0
```

Review the install preview before confirming. Herdr clones this repository and
runs `plugin/install.sh`. It reuses the repository installer to download the
**exact release pinned by the manifest's version**, verify SHA-256, and install
into `plugin/bin/hwatch` inside the managed checkout. It does not install MatchBox,
change your standalone binary, edit your SSH config, or register any machines.
Install-time tools are Git (for Herdr's clone), curl, a SHA-256 utility, and the
standard Unix installer tools; no compiler, Python, Java, or Rust is needed.

Runtime tools: Herdr, OpenSSH, `sh`, `mkdir`, `rmdir`, `rm`, `ps`, and the standard
shell tools used by the launcher. KubeVirt profiles additionally require `kubectl`
and `virtctl`; Tailscale profiles require `tailscale` and a logged-in daemon.
All existing network, SSH authentication, and remote Herdr prerequisites still apply.

## Actions

```sh
herdr plugin action invoke hwatch.help
herdr plugin action invoke hwatch.profile
herdr plugin action invoke hwatch.doctor
herdr plugin action invoke hwatch.version
herdr plugin action invoke hwatch.run
herdr plugin action invoke hwatch.watch
```

| Action | Effect |
| --- | --- |
| `help` | Setup steps, dependencies, actual configuration/state/SSH paths, CLI and update guidance |
| `profile` | Opens an interactive overlay menu: list, create, show, locate, remove, doctor, and help |
| `doctor` | Read-only dependency, discovery, SSH configuration, and lock diagnostics |
| `version` | Bundled binary's embedded version, commit, and UTC build date |
| `run` | Reconcile once; never waits for interactive SSH/setup approval |
| `watch` | Opens a tab running the watcher in the foreground; Ctrl+C stops it |

Actions launch asynchronously. Successful `action invoke` means launch was
accepted, not that reconciliation succeeded. Inspect completion, stdout, stderr,
and exit status with:

```sh
herdr plugin log list --plugin hwatch
```

Profile and watch output appears in their terminal panes. You can open them directly:

```sh
herdr plugin pane open --plugin hwatch --entrypoint profiles
herdr plugin pane open --plugin hwatch --entrypoint watcher
```

No startup hook or detached daemon is installed. Start the watcher explicitly.
Only one watcher/reconciliation/profile-removal operation may hold the shared lock.

## First-time setup

1. Run `hwatch.profile`, choose **Create a profile**, and complete the existing wizard.
2. Run `hwatch.doctor` and review its output in the plugin logs (or choose **Check
   setup** inside the profile menu).
3. Add the recommended `Include` near the top of your SSH config, before other
   `Host` or `Match` blocks. hwatch does not edit this file for you.
4. Run `hwatch.run`. If remote setup or authentication is needed, complete the
   manual command reported in its logs; hwatch never approves it automatically.
5. Run `hwatch.watch` for continued polling. Stop it with Ctrl+C when finished.

## Configuration and shared ownership

Plugin and standalone execution deliberately use the **same** existing paths:

| Content | Default |
| --- | --- |
| Editable JSON profiles | `${XDG_CONFIG_HOME:-$HOME/.config}/hwatch/profiles/` |
| Ownership journal and lock | `${XDG_STATE_HOME:-$HOME/.local/state}/hwatch/` |
| Generated SSH include | `$HOME/.ssh/hwatch.conf` |
| Your SSH configuration | `$HOME/.ssh/config` |

Empty or relative XDG directory values fall back to the normal HOME defaults.
`hwatch.help` prints the resolved paths for the running plugin. Existing profiles
need no migration. The profile menu's **Show configuration file location** option
prints a file path you can edit in your own editor; configuration is reloaded on
the next poll. See the [main README](../README.md) for profile fields and discovery
semantics. Use **Remove a profile** for confirmed cleanup of its owned entries.

Herdr creates `HERDR_PLUGIN_CONFIG_DIR` and `HERDR_PLUGIN_STATE_DIR`, but hwatch
does **not** redirect its existing profiles/journal there. This avoids separate
ownership journals managing the same SSH aliases. Run plugin and standalone tools
with the same HOME and XDG settings; do not point separate journals at the same
SSH include. No credentials or durable inventory state are written to the managed
plugin checkout. Unlink/uninstall does not remove profiles or owned machines;
remove profiles through the menu first if that cleanup is desired.

All Herdr CLI calls use `HERDR_BIN_PATH` when supplied, preserving the invocation's
socket/session environment. Standalone usage falls back to `herdr` on PATH.

## Direct binary use

For a stable `hwatch` command on PATH, install the standalone CLI using the
[repository installer](../README.md#install-a-release). Do **not** add the managed
plugin checkout to PATH: its path may change or disappear during plugin updates.
The standalone command shares the profiles and journal described above.

## Updates and uninstall

Stop the watch pane before updating, reinstalling, unlinking, or uninstalling.
Plugin updates do not upgrade an already-running watcher; reopen it afterward.
On Herdr 0.9.2, reinstall with `plugin install ... --ref <new-tag>` to update.
Newer Herdr versions also provide `plugin update`; an installation pinned with
`--ref` continues to track that ref, so select a new tag explicitly for upgrades.
The manifest version and downloaded binary release advance together.

```sh
herdr plugin uninstall hwatch
# For a locally linked checkout instead:
herdr plugin unlink hwatch
```

## Local development

`plugin link` does not run build commands. Build the current code into the private
binary location before linking:

```sh
MATCHBOX=/path/to/matchbox python3 tools/build.py --output plugin/bin/hwatch
herdr plugin link "$PWD/plugin"
herdr plugin action invoke hwatch.help
```

`make build-plugin` runs the same build. Generated `plugin/bin/` is ignored by Git.
To download the manifest-pinned release instead of building, use `sh plugin/install.sh`
(after that release exists).

Run the launcher checks with disposable state and external command substitutes:

```sh
MATCHBOX=/path/to/matchbox python3 tests/plugin.py
# Or use an already-built native executable:
HWATCH_BIN="$PWD/plugin/bin/hwatch" python3 tests/plugin.py
```

The optional real-host smoke test links a staged plugin, invokes help/version,
and opens, reads, and exits the real profile-menu terminal pane in its own temporary
HOME/config and named headless server. It does not link into
your actual installation, query live inventory, or control your current session:

```sh
MATCHBOX=/path/to/matchbox HERDR_TEST_BIN="$(command -v herdr)" python3 tests/plugin.py
```
