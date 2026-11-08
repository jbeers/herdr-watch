#!/usr/bin/env python3
"""Stamp immutable Git/build identity into a temporary source copy and compile it."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
FALLBACK = 'function buildInfo() { return {version: "dev", commit: "unknown", date: "unbuilt"}; }'


def git(*args):
    return subprocess.check_output(['git', '-C', str(ROOT), *args], text=True).strip()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, default=ROOT/'src/main.bxs')
    parser.add_argument('--output', type=Path, default=ROOT/'dist/hwatch')
    parser.add_argument('--target', choices=['native', 'bytecode'], default='native')
    args = parser.parse_args()
    date = (datetime.fromtimestamp(int(os.environ['SOURCE_DATE_EPOCH']), timezone.utc)
            if 'SOURCE_DATE_EPOCH' in os.environ else datetime.now(timezone.utc))
    info = dict(version=git('describe', '--tags', '--always', '--dirty'),
                commit=git('rev-parse', 'HEAD'), date=date.strftime('%Y-%m-%dT%H:%M:%SZ'))
    source = args.source.read_text()
    if source.count(FALLBACK) != 1:
        parser.error('Source must contain exactly one buildInfo fallback')
    source = source.replace(FALLBACK, 'function buildInfo() { return '+json.dumps(info)+'; }')
    output = args.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    compiler = os.environ.get('MATCHBOX', 'matchbox')
    flags = ['--target', 'native'] if args.target == 'native' else ['--build']
    with tempfile.TemporaryDirectory(prefix='hwatch-build-') as directory:
        entry = Path(directory)/'main.bxs'
        entry.write_text(source)
        subprocess.run([compiler, *flags, '--output', str(output), str(entry)], check=True)
    print(f"hwatch {info['version']}\nCommit: {info['commit']}\nBuilt: {info['date']}")


if __name__ == '__main__':
    main()
