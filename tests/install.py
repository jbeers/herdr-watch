#!/usr/bin/env python3
"""Exercise the real installer with local substitutes for GitHub downloads/uname."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
PAYLOAD=b'#!/bin/sh\nprintf "hwatch fixture help\\n"\n'
CURL='''#!/usr/bin/env python3
import json, os, pathlib, sys
args=sys.argv[1:]
url=next(a for a in args if a.startswith('https://'))
with open(os.environ['REQUESTS'],'a') as f: f.write(url+'\\n')
if url.endswith('/latest'):
 print('https://github.com/jbeers/herdr-watch/releases/tag/v1.2.3',end=''); sys.exit()
name=url.rsplit('/',1)[1]
source=pathlib.Path(os.environ['FIXTURES'])/name
if not source.exists(): sys.exit(22)
out=args[args.index('--output')+1]
pathlib.Path(out).write_bytes(source.read_bytes())
'''


class Installer(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='hwatch-installer-')
        self.addCleanup(self.temp.cleanup)
        self.home=Path(self.temp.name)
        self.bin=self.home/'installed bin'
        tools=self.home/'tools'
        tools.mkdir()
        self.fixtures=self.home/'fixtures'
        self.fixtures.mkdir()
        self.env=dict(os.environ, HOME=str(self.home), PATH=str(tools)+os.pathsep+os.environ['PATH'], FIXTURES=str(self.fixtures), REQUESTS=str(self.home/'requests'), HWATCH_INSTALL_DIR=str(self.bin))
        self.env.pop('HWATCH_VERSION',None)
        for name,source in [('curl',CURL),('uname','#!/bin/sh\ncase "$1" in -s) echo "$TEST_OS";; -m) echo "$TEST_ARCH";; esac\n')]:
            path=tools/name
            path.write_text(source)
            path.chmod(0o755)

    def release(self,platform):
        asset='hwatch-'+platform
        (self.fixtures/asset).write_bytes(PAYLOAD)
        (self.fixtures/'SHA256SUMS').write_text(hashlib.sha256(PAYLOAD).hexdigest()+'  '+asset+'\n')

    def call(self,*args,ok=True):
        p=subprocess.run(['sh',str(ROOT/'install.sh'),*args],env=self.env,text=True,capture_output=True,timeout=10)
        if ok: self.assertEqual(p.returncode,0,p.stdout+p.stderr)
        else: self.assertNotEqual(p.returncode,0,p.stdout+p.stderr)
        return p

    def test_latest_install_and_platform_selection(self):
        for system,arch,platform in [('Linux','x86_64','linux-x64'),('Linux','aarch64','linux-arm64'),('Darwin','x86_64','macos-x64'),('Darwin','arm64','macos-arm64')]:
            with self.subTest(platform=platform):
                self.env.update(TEST_OS=system,TEST_ARCH=arch)
                self.release(platform)
                result=self.call()
                self.assertEqual((self.bin/'hwatch').read_bytes(),PAYLOAD)
                self.assertTrue(os.access(self.bin/'hwatch',os.X_OK))
                self.assertIn('PATH',result.stdout)
                requests=(self.home/'requests').read_text()
                self.assertIn('/releases/download/v1.2.3/hwatch-'+platform,requests)
                self.assertIn('/releases/download/v1.2.3/SHA256SUMS',requests)
                self.assertFalse((self.home/'.ssh/config').exists())

    def test_explicit_version_checksum_failure_preserves_install(self):
        self.env.update(TEST_OS='Linux',TEST_ARCH='x86_64')
        self.release('linux-x64')
        self.bin.mkdir()
        (self.bin/'hwatch').write_text('previous binary')
        (self.fixtures/'hwatch-linux-x64').write_bytes(PAYLOAD+b'tampered')
        result=self.call('--version','0.2.0',ok=False)
        self.assertIn('Checksum mismatch',result.stderr)
        self.assertEqual((self.bin/'hwatch').read_text(),'previous binary')
        requests=(self.home/'requests').read_text()
        self.assertNotIn('/latest',requests)
        self.assertIn('/download/v0.2.0/',requests)

    def test_missing_release_and_unsupported_system_do_not_install(self):
        self.env.update(TEST_OS='Linux',TEST_ARCH='x86_64')
        self.call('--version','v9.9.9',ok=False)
        self.assertFalse(self.bin.exists())
        self.env['TEST_OS']='Windows'
        self.assertIn('Supported operating systems',self.call(ok=False).stderr)
        self.assertFalse(self.bin.exists())


if __name__=='__main__': unittest.main()
