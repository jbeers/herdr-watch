# Local build record

## CI/release baseline

The release workflow separately pins **MatchBox v0.12.0**, using per-platform SHA-256 values committed in `.github/workflows/build.yml`. The official Linux x86-64 v0.12.0 compiler and its generated hwatch binary passed all nine source, bytecode, and native CLI acceptance scenarios locally. `tests/install.py` also passed all three installer scenarios using local download/platform substitutes.

The official Linux x86-64 compiler and native runner reference **GLIBC_2.39**; CI builds on Ubuntu 24.04 rather than advertising older Linux compatibility. The installer checks that the downloaded executable can run before replacing an existing installation.

The four-platform GitHub Actions matrix and tag-triggered release publishing have not yet run remotely. macOS/ARM64 support is gated by those actual-runner tests, not claimed as locally verified. The pre-existing local `dist/hwatch` described below has not been replaced by this CI configuration work.

## Artifact

- Path: `dist/hwatch`
- Target tested: `x86_64-unknown-linux-gnu`
- SHA-256: `ffa1bfc98c12f11467e32f85e59e9b3f9b54a451e41695a21af9c0286086b658`
- No external BoxLang modules or native plugins selected.

## Compiler identity

Used the existing local MatchBox executable:

```text
/home/jacob/dev/ortus-boxlang/matchbox/target/release/matchbox
matchbox version 0.13.0
commit: 2586849
built on: 2026-10-28
SHA-256: 99d182ae6d335a4aa5e0a5c60af7ffb368be5878d00665ddae8ac1ee1087b63a
```

The adjacent source checkout reports `7fc423e35564bc9ba2aaf734459e1f2655f4563c`. That is **not** asserted to be the revision that produced the pre-existing compiler or its embedded runner. The runtime was not rebuilt or modified for hwatch. No claim of certified no-JNI runner provenance is made; the application uses no Java APIs, and its native acceptance pass ran with Java/MatchBox/Cargo absent from `PATH`.

Build command, from this project directory:

```sh
/home/jacob/dev/ortus-boxlang/matchbox/target/release/matchbox \
  --target native --output dist/hwatch src/main.bxs
```

The resulting ELF depends on normal Linux system libraries. `ldd` reported `liblzma.so.5`, `libbz2.so.1.0`, `libgcc_s.so.1`, `libm.so.6`, `libc.so.6`, and the ELF loader. This is not a statically linked or universally portable Linux binary.

## Checks executed

```sh
MATCHBOX=/home/jacob/dev/ortus-boxlang/matchbox/target/release/matchbox \
  python3 tests/acceptance.py

MATCHBOX=/home/jacob/dev/ortus-boxlang/matchbox/target/release/matchbox \
  python3 tests/source_free.py
```

Nine CLI scenarios passed in each of source, source-free bytecode, and source-free native modes. The native pass used a restricted `PATH` containing only the command tools required by the test, without MatchBox, Java, Rust, or SDK tools. Kubernetes and Herdr operations used disposable command substitutes; OpenSSH parsing and proxy execution were real.

Also checked the installed Herdr CLI help and JSON listing read-only, and verified the kubectl argument forms without cluster access:

```sh
kubectl --context hwatch-no-network get vm --all-namespaces \
  --selector hwatch=enabled --output=json --request-timeout=20s --help
kubectl --context hwatch-no-network get vmi --namespace dev \
  --output=json --request-timeout=20s --help
```

Both help invocations succeeded. No live cluster query or Herdr machine registration/removal was executed. `virtctl` is not installed in the current environment, so real KubeVirt proxy connectivity remains unverified.

Make is not installed in this environment; the equivalent direct build/test commands above were executed instead of the convenience Make targets.
