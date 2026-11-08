# Local build record

## Current artifact: build identity and interrupted-run lock recovery

- Path/target: `dist/hwatch`, `x86_64-unknown-linux-gnu`
- SHA-256: `88ce65fe0d2c7b03af1ee628a65784f58c713d3112c695d566c245658013546f`
- Version: `v0.2.1-dirty`
- Commit: `3028631e3f5f6712dd7c4c27cd5fbd5bd6141c21` (working tree modifications included, as indicated by `-dirty`)
- Built: `2026-11-08T07:50:42Z`
- Build: `MATCHBOX=/tmp/hwatch-matchbox-v012 python3 tools/build.py --output dist/hwatch`
- Compiler/target and absence of modules/plugins are unchanged from the records below.

All 14 acceptance scenarios passed in source, source-free bytecode/native, and the final native artifact; all 3 installer scenarios passed. Commands were the same as below, except the build now uses `tools/build.py`. `git diff --check` passed. The source-free check fixes `SOURCE_DATE_EPOCH`, asserts exact embedded version/commit/date, removes staged source, and runs the native tests with Git and build tools absent from `PATH`. Direct source runs correctly report unbuilt provenance. Updated CI builds use the stamping script and fetch tags/history; the actual GitHub Actions workflow and non-Linux platforms were not executed locally.

## Previous artifact: interrupted-run lock recovery

- Path: `dist/hwatch` (local build output, not committed)
- Target: `x86_64-unknown-linux-gnu`
- SHA-256: `831ebfa015702f08c8526206f91fba6b37b5f5d20fddec5fe1bd9a1f99d329bf`
- Compiler: the same pinned `/tmp/hwatch-matchbox-v012` described below; no modules/plugins.

Executed successfully:

```sh
MATCHBOX=/tmp/hwatch-matchbox-v012 python3 tests/acceptance.py
MATCHBOX=/tmp/hwatch-matchbox-v012 python3 tests/source_free.py
/tmp/hwatch-matchbox-v012 --target native --output dist/hwatch src/main.bxs
HWATCH_BIN="$PWD/dist/hwatch" python3 tests/acceptance.py
python3 tests/install.py
git diff --check
```

All 13 acceptance scenarios passed in source, source-free bytecode/native, and the final native artifact; all 3 installer scenarios passed. The new regression sends SIGINT to a real runner process group in a disposable home and verifies restart without manual lock removal, plus refusal while that runner is still alive. It failed against the previous code with the reported lock error. External inventory/Herdr commands remain controlled substitutes; no live services were queried or changed.

Recovery occurs on the next lock acquisition, not at signal time. A dead owner is reclaimed under a serialized acquisition guard; live/unknown owners fail closed. Unix `ps`, `rm`, and `rmdir` are now also needed for this transaction. macOS and forced interruption of the acquisition helper itself remain unverified locally. `make` was unavailable, so the direct build command above was used.

## Previous build record: KubeVirt + Tailscale profiles

- Path: `dist/hwatch` (local build output, not committed)
- Target tested: `x86_64-unknown-linux-gnu`
- SHA-256: `a4544995055578c9a950b821b9e7e7b126a8ee799829aa6bec6f4ddbd3dc2cbb`
- No external BoxLang modules or native plugins selected.

Used the official Linux x86-64 MatchBox asset from release `v0.12.0`, matching the compiler checksum pinned by CI:

```text
/tmp/hwatch-matchbox-v012
matchbox version 0.12.0+48
commit: 9799967
built on: 2026-10-22
SHA-256: a74a263b450421b007ba59fe640a8d3b2378a82b071aa49291984a093b486279
```

Build command, from the project directory:

```sh
/tmp/hwatch-matchbox-v012 --target native --output dist/hwatch src/main.bxs
```

The runtime was not rebuilt or modified for hwatch. It references **GLIBC_2.39**; CI uses Ubuntu 24.04 rather than advertising older Linux compatibility. `ldd dist/hwatch` reported `libgcc_s.so.1`, `libm.so.6`, `libc.so.6`, and the ELF loader. This is not a statically linked or universally portable Linux binary.

No claim of certified no-JNI runner provenance is made. The application uses no Java APIs, and the source-free native acceptance pass ran with Java, MatchBox, Cargo, and SDK tools absent from `PATH`.

## Checks executed for this change

```sh
MATCHBOX=/tmp/hwatch-matchbox-v012 python3 tests/acceptance.py
MATCHBOX=/tmp/hwatch-matchbox-v012 python3 tests/source_free.py
HWATCH_BIN="$PWD/dist/hwatch" python3 tests/acceptance.py
python3 tests/install.py
sh -n install.sh
git diff --check
```

All twelve CLI scenarios passed in source, source-free bytecode, source-free native, and the final local native artifact. All three installer scenarios also passed.

The new scenarios exercise Tailscale profile creation/display, profile-aware doctor dependencies, exact tag selection and local-machine exclusion, offline retention/exclusion, stable aliases/Herdr IDs across hostname/public-key/IP changes, duplicate display names, IPv6 fallback, disappearance/tag removal, profile cleanup, and preservation of failed/invalid Tailscale discovery while KubeVirt reconciliation continues. Existing untyped KubeVirt profiles continue to pass unchanged reconciliation scenarios.

Kubernetes, Tailscale, and Herdr operations used isolated command substitutes in disposable homes. OpenSSH syntax/effective-settings checks and the KubeVirt proxy-quoting invocation used real `ssh`. The source-free script staged copies of the source, compiled bytecode and native artifacts, deleted staged source, and ran the suite with fresh private native-cache paths.

No live cluster query, Tailscale status query, or Herdr registration/removal was executed for this change. Live Tailscale/KubeVirt connectivity and real Herdr remote setup remain unverified. Local macOS/ARM64 tests were not possible; the existing actual-runner CI matrix gates release publication. Signal-clean lock cleanup remains a documented limitation, unchanged by this feature.
