# hwatch

A small [MatchBox](https://github.com/ortus-boxlang/matchbox) CLI that keeps selected **KubeVirt VirtualMachines** available in OpenSSH and [Herdr](https://herdr.dev). It shells out to your existing tools; no Kubernetes or cloud SDK is bundled.

## Install a release

Once a release is published, install the latest binary without sudo:

```sh
curl -fsSL https://raw.githubusercontent.com/jbeers/herdr-watch/main/install.sh | sh
```

The installer supports Linux (glibc 2.39+, e.g. Ubuntu 24.04) and macOS on x86-64 and ARM64. The Linux baseline comes from the upstream MatchBox binaries; musl/Alpine and older glibc systems are not supported by these release artifacts. It resolves the latest release once, downloads that tag's binary and `SHA256SUMS`, verifies SHA-256, checks that the binary runs, and installs to `~/.local/bin`. Existing installations are not replaced if download, verification, or the startup check fails. It does not install dependencies, edit your shell profile, or modify SSH configuration.

Choose a version or installation directory:

```sh
curl -fsSL https://raw.githubusercontent.com/jbeers/herdr-watch/main/install.sh \
  | sh -s -- --version v0.1.0 --bin-dir "$HOME/.local/bin"
```

`HWATCH_VERSION` and `HWATCH_INSTALL_DIR` are also supported. For example, pass them to `sh` on the right side of the pipe. If the destination is not on your `PATH`, the installer tells you to add it. Checksums protect against corruption; the script, binary, and checksum trust GitHub and this repository's release access. You can download and inspect `install.sh` before executing it instead of piping it to a shell.

**The curl command requires this repository's `main` branch and at least one published release.** Before the first release, build from source below.

## Build and run

Requires MatchBox during development/building only. CI pins MatchBox **v0.12.0**, whose Linux x86-64 source, bytecode, and native acceptance checks have also passed locally:

```sh
mkdir -p dist
matchbox --target native --output dist/hwatch src/main.bxs
./dist/hwatch --help
```

**Put MatchBox build flags before the source filename.** Arguments after the source filename belong to the application.

For development, replace `hwatch` below with `matchbox src/main.bxs`, or run the compiled `./dist/hwatch` directly. To install, copy the executable to a user-owned directory on your `PATH`.

The executable needs `kubectl`, `virtctl`, `herdr`, OpenSSH (`ssh`), and standard Unix `sh`/`mkdir` on `PATH`. It also needs your kubeconfig, cluster access, and normal SSH credentials. No MatchBox, Java, Python, Rust, or SDK is needed to run the native application. The currently tested artifact is **Linux x86-64 GNU**, with normal system shared-library requirements; other platforms have not been validated.

## Quick start

```sh
hwatch profile new lab
hwatch doctor
```

The wizard lists contexts and asks for:

- Kubernetes context;
- namespace (`*` for all namespaces);
- standard Kubernetes VM label selector (default `hwatch=enabled`);
- SSH user;
- optional identity file (blank uses normal SSH defaults/agent);
- SSH port (default `22`);
- whether to include stopped VMs (default **yes**).

It validates discovery access before saving. Your account needs permission to list both `virtualmachines` and `virtualmachineinstances` in the configured scope. Labels are selected on the **VirtualMachine** resource; they do not need to be copied to the VMI.

Doctor prints the SSH snippet to copy/paste near the top of `~/.ssh/config`, **before other `Host` or `Match` blocks**:

```sshconfig
Include ~/.ssh/hwatch.conf
Host *
```

Neither doctor nor the wizard edits your main SSH configuration. The generated include file is created on the first reconciliation:

```sh
hwatch run --once
hwatch doctor
hwatch run
```

Doctor may initially report the generated file missing. After the first reconciliation, it uses real OpenSSH parsing to check that the include is read and that existing managed hosts' hostname, user, port, and proxy command have not been overridden by earlier settings. `Host *` resets matching scope, not already assigned SSH values or syntax errors.

Before unattended registration can succeed, the VM must offer SSH and have a compatible Herdr installation. Unknown host keys, unloaded/passphrase-protected keys, authentication failures, missing Herdr installations, or incompatible remote servers may require manual setup. hwatch reports the manual `herdr machine add ...` command and retries; it does not approve prompts or automatically replace remote software.

## Commands

```text
hwatch --help
hwatch profile list
hwatch profile new <name>
hwatch profile show <name>
hwatch profile where <name>
hwatch profile remove <name>
hwatch run [--once] [--poll-seconds 120]
hwatch doctor
```

Profile names use 1–40 lowercase letters, digits, or hyphens, starting with a letter or digit. Use different profiles for different clusters, namespace scopes, or selectors.

- `profile where` prints only the existing profile's path.
- `profile show` displays readable JSON. Edit the file directly to change settings; the watcher reloads profiles on every poll.
- `profile remove` asks for confirmation, removes only that profile's owned connections, then deletes its configuration. It refuses to race with a running reconciler. Remote sessions are not stopped.
- `run` polls immediately, then sleeps between passes. The default delay is 120 seconds **after each pass**, not a fixed-rate schedule.
- `run --once` exits 0 when reconciliation succeeds and nonzero for discovery, setup, or reconciliation failures. A stopped VM awaiting its first registration is not an error.
- `doctor` performs diagnostics without writing hwatch configuration, SSH files, or machine entries. It exits nonzero when setup needs attention.

## Configuration and storage

| Content | Location |
| --- | --- |
| Profiles | `$XDG_CONFIG_HOME/hwatch/profiles/<name>.json` (default `~/.config/hwatch/profiles/`) |
| Ownership/reconciliation journal | `$XDG_STATE_HOME/hwatch/state.json` (default `~/.local/state/hwatch/`) |
| Run lock | Same state directory, `run.lock/` |
| Generated SSH include | `~/.ssh/hwatch.conf` |

Unset, empty, or relative XDG paths use the defaults. Keep the state journal: it records actual Herdr profile IDs and pending add attempts. hwatch does not infer IDs from labels, edit Herdr's catalog directly, or adopt an unrelated entry merely because its SSH target matches.

Example profile:

```json
{
  "context": "my-k3s",
  "namespace": "dev",
  "selector": "hwatch=enabled",
  "user": "jacob",
  "identityFile": "~/.ssh/id_ed25519",
  "port": 22,
  "includeStopped": true
}
```

The SSH alias for `devbox` in namespace `dev` and profile `lab` is:

```text
hw-lab.dev.devbox
```

Dot separators disambiguate the profile and namespace, neither of which allows dots. Different profiles intentionally produce different aliases, even if they select the same VM.

A generated entry uses `virtctl` as a byte-stream proxy to the VM's SSH server:

```sshconfig
Host hw-lab.dev.devbox
    HostName hw-lab.dev.devbox
    User jacob
    Port 22
    ProxyCommand virtctl --context 'my-k3s' --namespace 'dev' port-forward --stdio=true 'vm/devbox' %p
```

## Reconciliation behavior

| VM condition | `includeStopped: true` (default) | `includeStopped: false` |
| --- | --- | --- |
| Running VMI owned by the matching VM | Generate SSH; add to Herdr if necessary | Same |
| Stopped, previously registered | Keep SSH and Herdr entries | Remove owned SSH/Herdr entries |
| Stopped, never registered | Generate SSH; defer Herdr registration until running | No entries |
| Deleted or no longer selected | Remove owned entries | Same |
| Cluster query fails or returns malformed data | Preserve that profile's previous entries; continue other profiles | Same |

A VMI in phase `Running` is eligible for an add attempt, not proof SSH or Herdr is ready. Those failures are retried on subsequent polls.

The include and journal are published with same-directory atomic renames and are not rewritten when unchanged. A pre-existing `hwatch.conf` without hwatch's generated marker is not overwritten. Subprocess arguments are passed as arrays, and generated proxy arguments are shell-quoted with OpenSSH percent expansion accounted for.

Herdr add runs with closed stdin, an explicit `default` remote session, and a timeout. Before calling add, hwatch records an ownership intent; after add, it reads `herdr machine list --json` to obtain the actual ID. Failed adds are retried. A manually completed setup for a recorded pending add can be picked up on the next poll. Removals verify that the stored ID still points to the expected SSH alias.

If you delete a profile file manually, the next successful reconciliation also retires its owned entries. Prefer `profile remove` for explicit confirmation and immediate feedback.

### Interrupted runs and lock recovery

Only one reconciler/profile-removal operation may run at once. The current lock is an atomic directory lock. Normal returns and handled errors release it, but **Ctrl+C, termination, or a crash can leave a stale lock** because this MatchBox implementation does not install signal cleanup handlers.

Run `hwatch doctor` to see the lock path and owner PID. Confirm that no hwatch process is running before removing the lock using the command doctor prints. Never delete a live runner's lock. Automatic stale-lock recovery is deliberately not attempted, to avoid races between competing reconcilers.

## Verification

Python 3 is needed for development tests only. No third-party Python packages are required:

```sh
MATCHBOX=/path/to/matchbox python3 tests/acceptance.py
MATCHBOX=/path/to/matchbox python3 tests/source_free.py
python3 tests/install.py
```

Optional Make targets provide `build`, `test`, and `check` if Make is installed.

The acceptance suite exercises the public CLI in disposable home directories. Kubernetes and Herdr are controlled command substitutes; OpenSSH is real, including an actual proxy-command invocation that verifies quoting. The scenarios cover polling/reloaded settings, independent profiles, discovery-failure preservation, stopped VM transitions, registration retry, ownership boundaries, cleanup, and read-only doctor diagnostics.

The source-free check stages a copy of the source, builds bytecode and a native executable, removes the staged source, and runs the acceptance suite in both modes. The native pass uses a tool-only `PATH` without MatchBox, Java, Rust, or SDK tools.

**Not yet verified:** end-to-end registration against a live KubeVirt VM and real Herdr remote setup; macOS/Windows; signal-clean lock cleanup. No live machines are added or removed by the tests.

## CI and releases

`.github/workflows/build.yml` runs on pushes to `main`, pull requests, manual dispatches, and version tags. It downloads checksum-pinned MatchBox v0.12.0, runs CLI/installer tests, verifies source-free bytecode/native execution, then builds and tests each distributable on its actual runner:

| Asset | Runner |
| --- | --- |
| `hwatch-linux-x64` | Ubuntu 24.04 x86-64 |
| `hwatch-linux-arm64` | Ubuntu 24.04 ARM64 |
| `hwatch-macos-x64` | macOS 15 Intel |
| `hwatch-macos-arm64` | macOS 15 ARM64 |

Every build uploads workflow artifacts. A pushed `v` version tag publishes a GitHub release **only after all four platforms pass**, attaching the binaries, per-platform compiler/source information, and `SHA256SUMS`. Tags containing a hyphen are marked prereleases and are not selected by the installer's `latest` default. There is no Windows release because the current application relies on Unix tools.

To publish after committing and pushing the code:

```sh
git tag v0.1.0
git push origin v0.1.0
```

Tagged releases require GitHub Actions to be enabled and the workflow's release job to receive `contents: write` permission. An immutable version tag should point to the intended reviewed commit. No release has been published as part of local setup, and remote CI/macOS/ARM64 execution is still pending until the workflow runs.

See [BUILD.md](BUILD.md) for the local build identity.
