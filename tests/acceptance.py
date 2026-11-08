#!/usr/bin/env python3
"""CLI-boundary checks; all files and external commands use a disposable home."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]
MATCHBOX = os.environ.get('MATCHBOX', 'matchbox')
COMMAND = [os.environ['HWATCH_BIN']] if 'HWATCH_BIN' in os.environ else [MATCHBOX, os.environ.get('HWATCH_BYTECODE', str(ROOT / 'src/main.bxs'))]

FAKE = '''#!/usr/bin/env python3
import json, os, pathlib, sys
home = pathlib.Path(os.environ['HOME'])
name = pathlib.Path(sys.argv[0]).name
a = sys.argv[1:]
with (home/'calls').open('a') as f: f.write(json.dumps([name]+a)+'\\n')
if name == 'kubectl':
 if 'config' in a:
  print('lab'); sys.exit()
 if '--all-namespaces' in a and a.index('--all-namespaces') < a.index('get'):
  print('unknown flag: --all-namespaces',file=sys.stderr); sys.exit(1)
 data = json.loads((home/'cluster.json').read_text())
 if data.get('fail') or 'unavailable' in a: print('cluster unavailable', file=sys.stderr); sys.exit(1)
 print(json.dumps(data['vmi' if 'vmi' in a else 'vm']))
elif name == 'herdr':
 if '--help' in a: print('machine list --json; add --remote-session --label; remove'); sys.exit()
 p=home/'machines.json'
 data=json.loads(p.read_text())
 if a[:2]==['machine','list']: print(json.dumps(data))
 elif a[:2]==['machine','add']:
  if (home/'add-fails').exists(): print('setup needed',file=sys.stderr); sys.exit(1)
  data.append(dict(id='id-'+a[2],target=a[2],label=a[2],session='default'))
  p.write_text(json.dumps(data))
 elif a[:2]==['machine','remove']:
  p.write_text(json.dumps([m for m in data if m['id']!=a[2]]))
 else: print('machine list --json; add --remote-session; remove')
else: print('test tool')
'''


class Acceptance(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='hwatch-test-')
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name)
        self.env = dict(os.environ, HOME=str(self.home), XDG_CONFIG_HOME=str(self.home/'config'), XDG_STATE_HOME=str(self.home/'state'))
        bin_dir = self.home/'bin'
        bin_dir.mkdir()
        self.env['PATH'] = str(bin_dir)+os.pathsep+os.environ['PATH']
        for tool in ['kubectl', 'virtctl', 'herdr']:
            p=bin_dir/tool
            p.write_text(FAKE)
            p.chmod(0o755)
        (self.home/'machines.json').write_text(json.dumps([dict(id='unrelated', target='nas', label='nas')]))
        self.cluster()

    def call(self, *args, input=None, ok=True):
        p=subprocess.run(COMMAND+list(args), env=self.env, input=input, text=True, capture_output=True, timeout=20)
        if ok: self.assertEqual(p.returncode, 0, p.stdout+p.stderr)
        return p

    def profile(self, name='lab', stopped=True):
        folder=self.home/'config/hwatch/profiles'
        folder.mkdir(parents=True, exist_ok=True)
        (folder/(name+'.json')).write_text(json.dumps(dict(context='lab', namespace='dev', selector='hwatch=enabled', user='jacob', port=22, identityFile='', includeStopped=stopped)))

    def cluster(self, running=True, empty=False, fail=False):
        metadata=dict(name='devbox', namespace='dev', uid='vm-1')
        vm=[] if empty else [dict(metadata=metadata)]
        vmi=[] if empty or not running else [dict(metadata=dict(metadata, ownerReferences=[dict(kind='VirtualMachine', uid='vm-1', name='devbox')]), status=dict(phase='Running'))]
        (self.home/'cluster.json').write_text(json.dumps(dict(vm=dict(items=vm), vmi=dict(items=vmi), fail=fail)))

    def machines(self):
        return json.loads((self.home/'machines.json').read_text())

    def test_profile_wizard_and_read_only_doctor(self):
        self.assertIn('hwatch', self.call('--help').stdout)
        self.call('profile','new','lab',input='lab\ndev\nhwatch=enabled\njacob\n\n\n\n\ny\n')
        p=self.home/'config/hwatch/profiles/lab.json'
        self.assertTrue(json.loads(p.read_text())['includeStopped'])
        self.assertEqual(self.call('profile','where','lab').stdout.strip(), str(p))
        self.assertIn('lab', self.call('profile','list').stdout)
        self.assertIn('includeStopped', self.call('profile','show','lab').stdout)
        result=self.call('doctor',ok=False)
        self.assertIn('Include',result.stdout)
        self.assertFalse((self.home/'.ssh/config').exists())
        self.assertFalse((self.home/'.ssh/hwatch.conf').exists())

    def test_reconcile_is_idempotent_and_preserves_failed_cluster(self):
        self.profile()
        self.call('run','--once')
        ssh=self.home/'.ssh/hwatch.conf'
        text=ssh.read_text()
        self.assertIn('virtctl',text)
        self.assertIn('devbox',text)
        self.assertEqual(len(self.machines()),2)
        before=ssh.stat().st_mtime_ns
        self.call('run','--once')
        self.assertEqual(ssh.stat().st_mtime_ns,before)
        self.assertEqual(len(self.machines()),2)
        self.cluster(fail=True)
        self.assertNotEqual(self.call('run','--once',ok=False).returncode,0)
        self.assertEqual(ssh.read_text(),text)
        self.assertEqual(len(self.machines()),2)
        self.cluster(empty=True)
        self.call('run','--once')
        self.assertNotIn('devbox',ssh.read_text())
        self.assertEqual([m['id'] for m in self.machines()],['unrelated'])

    def test_stopped_vm_pending_then_retained_or_excluded(self):
        self.profile()
        self.cluster(running=False)
        self.call('run','--poll-seconds=1','--once')
        self.assertIn('devbox',(self.home/'.ssh/hwatch.conf').read_text())
        self.assertEqual(len(self.machines()),1)
        self.cluster()
        self.call('run','--once')
        self.cluster(running=False)
        self.call('run','--once')
        self.assertEqual(len(self.machines()),2)
        self.profile(stopped=False)
        self.call('run','--once')
        self.assertEqual(len(self.machines()),1)
        self.assertNotIn('devbox',(self.home/'.ssh/hwatch.conf').read_text())

    def test_setup_failure_retries_and_profile_removal_cleans_up(self):
        self.profile()
        (self.home/'add-fails').touch()
        self.assertNotEqual(self.call('run','--once',ok=False).returncode,0)
        self.assertIn('devbox',(self.home/'.ssh/hwatch.conf').read_text())
        (self.home/'add-fails').unlink()
        self.call('run','--once')
        self.call('profile','remove','lab',input='y\n')
        self.assertEqual(len(self.machines()),1)
        self.assertNotIn('devbox',(self.home/'.ssh/hwatch.conf').read_text())
        self.assertFalse((self.home/'config/hwatch/profiles/lab.json').exists())

    def test_profiles_reconcile_independently_and_openssh_reads_include(self):
        self.profile('first')
        self.profile('second')
        second=self.home/'config/hwatch/profiles/second.json'
        config=json.loads(second.read_text())
        config['namespace']='*'
        second.write_text(json.dumps(config))
        self.call('run','--poll-seconds','2','--once')
        self.assertEqual(len(self.machines()),3)
        # A failure for one context must not keep deleted VMs from the other.
        config=self.home/'config/hwatch/profiles/first.json'
        data=json.loads(config.read_text())
        data['context']='unavailable'
        config.write_text(json.dumps(data))
        self.cluster(empty=True)
        self.assertNotEqual(self.call('run','--once',ok=False).returncode,0)
        self.assertEqual(len(self.machines()),2)
        self.assertIn('hw-first.dev.devbox',(self.home/'.ssh/hwatch.conf').read_text())
        self.assertNotIn('hw-second.dev.devbox',(self.home/'.ssh/hwatch.conf').read_text())
        # Use the real SSH parser, not an approximation of Include semantics.
        ssh_config=self.home/'.ssh/config'
        ssh_config.write_text('Include "'+str(self.home/'.ssh/hwatch.conf')+'"\nHost *\n')
        before=ssh_config.read_bytes()
        result=self.call('doctor',ok=False)  # first context remains unavailable
        self.assertIn('OK: SSH reads',result.stdout)
        self.assertIn('OK: managed SSH host settings are effective',result.stdout)
        self.assertEqual(ssh_config.read_bytes(),before)
        ssh_config.write_text('Host *\n    User wrong-user\n'+before.decode())
        result=self.call('doctor',ok=False)
        self.assertIn('overridden',result.stdout)
        self.assertNotEqual(result.returncode,0)

    def test_proxycommand_passes_context_as_one_literal_argument(self):
        self.profile()
        path=self.home/'config/hwatch/profiles/lab.json'
        data=json.loads(path.read_text())
        context='lab with spaces; $HOME '+chr(39)+'quoted'+chr(39)+' "double" %value #comment'
        data['context']=context
        path.write_text(json.dumps(data))
        self.call('run','--once')
        p=subprocess.run(['ssh','-F',str(self.home/'.ssh/hwatch.conf'),'-o','BatchMode=yes','-o','ConnectTimeout=2','hw-lab.dev.devbox'],env=self.env,text=True,capture_output=True,timeout=10)
        self.assertNotEqual(p.returncode,0)  # fake virtctl is not an SSH server
        calls=[json.loads(line) for line in (self.home/'calls').read_text().splitlines()]
        virtctl=[call for call in calls if call[0]=='virtctl']
        self.assertEqual(len(virtctl),1,p.stderr)
        self.assertEqual(virtctl[0],['virtctl','--context',context,'--namespace','dev','port-forward','--stdio=true','vm/devbox','22'])

    def test_unrelated_ssh_file_and_colliding_herdr_target_are_not_owned(self):
        self.profile()
        path=self.home/'.ssh/hwatch.conf'
        path.parent.mkdir()
        path.write_text('# personal SSH config\n')
        machines=self.machines()+[dict(id='user-owned',target='hw-lab.dev.devbox',label='mine',session='default')]
        (self.home/'machines.json').write_text(json.dumps(machines))
        self.assertNotEqual(self.call('run','--once',ok=False).returncode,0)
        self.assertEqual(path.read_text(),'# personal SSH config\n')
        self.assertEqual(self.machines(),machines)
        path.unlink()
        result=self.call('run','--once',ok=False)
        self.assertNotEqual(result.returncode,0)
        self.assertIn('not owned by hwatch',result.stdout)
        self.cluster(empty=True)
        self.call('run','--once')
        self.assertEqual(self.machines(),machines)

    def test_loop_polls_and_reloads_profile_settings(self):
        self.profile()
        log=(self.home/'loop.log').open('w')
        self.addCleanup(log.close)
        process=subprocess.Popen(COMMAND+['run','--poll-seconds','1'],env=self.env,stdin=subprocess.DEVNULL,stdout=log,stderr=log)
        self.addCleanup(lambda: process.kill() if process.poll() is None else None)
        def wait_for(predicate):
            deadline=time.monotonic()+10
            while time.monotonic()<deadline:
                self.assertIsNone(process.poll(),(self.home/'loop.log').read_text())
                try:
                    if predicate(): return
                except (FileNotFoundError,json.JSONDecodeError): pass
                time.sleep(0.05)
            self.fail('Polling did not produce the expected change: '+(self.home/'loop.log').read_text())
        wait_for(lambda: len(self.machines())==2)
        # Changes to includeStopped take effect without restarting the watcher.
        self.profile(stopped=False)
        self.cluster(running=False)
        wait_for(lambda: len(self.machines())==1)
        process.terminate()
        process.wait(timeout=5)

    def test_single_runner_and_poll_validation(self):
        self.profile()
        self.assertNotEqual(self.call('run','--poll-seconds','0','--once',ok=False).returncode,0)
        lock=self.home/'state/hwatch/run.lock'
        lock.mkdir(parents=True)
        (lock/'owner').write_text('test owner')
        self.assertNotEqual(self.call('run','--once',ok=False).returncode,0)
        self.assertFalse((self.home/'.ssh/hwatch.conf').exists())


if __name__ == '__main__':
    unittest.main()
