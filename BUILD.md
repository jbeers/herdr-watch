# Local build record

## Current artifact: KubeVirt + Tailscale profiles

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
