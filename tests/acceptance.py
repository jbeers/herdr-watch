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
elif name == 'tailscale':
 if a != ['status','--json']: print('unexpected tailscale arguments',file=sys.stderr); sys.exit(1)
 if (home/'tailscale-fails').exists(): print('daemon unavailable',file=sys.stderr); sys.exit(1)
 print((home/'tailscale.json').read_text())
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
        for tool in ['kubectl', 'virtctl', 'herdr', 'tailscale']:
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
        self.call('profile','new','lab',input='1\nlab\ndev\nhwatch=enabled\njacob\n\n\n\n\ny\n')
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

    def tailscale_profile(self, offline=None):
        folder=self.home/'config/hwatch/profiles'
        folder.mkdir(parents=True,exist_ok=True)
        config=dict(type='tailscale',tag='tag:devbox',user='jacob',port=22,identityFile='')
        if offline is not None: config['includeOffline']=offline
        (folder/'tailnet.json').write_text(json.dumps(config))

    def tailnet(self, online=True, tagged=True):
        peer=dict(ID='nStable123',HostName='buildbox',DNSName='buildbox.example.ts.net.',Tags=['tag:devbox'] if tagged else [],Online=online,TailscaleIPs=['100.64.0.20','fd7a:115c:a1e0::20'])
        data=dict(BackendState='Running',Self=dict(ID='nSelf'),Peer={
            'nodekey:rotating':peer,
            'nodekey:untagged':dict(peer,ID='nOther',Tags=['tag:devbox-other']),
            'nodekey:wrong-case':dict(peer,ID='nCase',Tags=['tag:Devbox']),
            'nodekey:self':dict(peer,ID='nSelf'),
        })
        (self.home/'tailscale.json').write_text(json.dumps(data))
        return data

    def test_tailscale_wizard_doctor_and_profile_display(self):
        self.tailnet()
        self.call('profile','new','tailnet',input='2\ntag:devbox\njacob\n\n\n\n\ny\n')
        config=json.loads((self.home/'config/hwatch/profiles/tailnet.json').read_text())
        self.assertEqual(config['type'],'tailscale')
        self.assertTrue(config['includeOffline'])
        self.assertNotIn('context',config)
        self.assertIn('tag:devbox',self.call('profile','list').stdout)
        self.assertIn('includeOffline',self.call('profile','show','tailnet').stdout)
        self.call('run','--once')
        ssh_config=self.home/'.ssh/config'
        ssh_config.write_text('Include "'+str(self.home/'.ssh/hwatch.conf')+'"\nHost *\n')
        before=ssh_config.read_bytes()
        result=self.call('doctor')
        self.assertIn('OK: tailscale',result.stdout)
        self.assertNotIn('kubectl',result.stdout)
        self.assertNotIn('virtctl',result.stdout)
        self.assertEqual(ssh_config.read_bytes(),before)
        calls=[json.loads(line) for line in (self.home/'calls').read_text().splitlines()]
        self.assertFalse(any(call[0] in ['kubectl','virtctl'] for call in calls))

    def test_tailscale_tag_identity_offline_and_removal_lifecycle(self):
        self.tailscale_profile()  # omitted includeOffline defaults to true
        self.tailnet(online=False)
        self.call('run','--once')
        ssh=self.home/'.ssh/hwatch.conf'
        self.assertIn('100.64.0.20',ssh.read_text())
        self.assertNotIn('ProxyCommand',ssh.read_text())
        self.assertEqual(len(self.machines()),1)  # offline first add is pending
        data=self.tailnet()
        self.call('run','--once')
        self.assertEqual(len(self.machines()),2)  # excludes self and nonmatching tag
        alias=next(m['target'] for m in self.machines() if m['id']!='unrelated')
        old_id=next(m['id'] for m in self.machines() if m['target']==alias)
        before=ssh.stat().st_mtime_ns
        self.call('run','--once')
        self.assertEqual(ssh.stat().st_mtime_ns,before)
        # A new public key, hostname, and address must not replace the Herdr identity.
        peer=data['Peer'].pop('nodekey:rotating')
        peer.update(HostName='renamed',TailscaleIPs=['100.64.0.25'])
        data['Peer']['nodekey:new-key']=peer
        # Duplicate display names must still produce distinct aliases; IPv6-only is usable.
        data['Peer']['nodekey:another']=dict(peer,ID='nStable456',TailscaleIPs=['fd7a:115c:a1e0::26'])
        (self.home/'tailscale.json').write_text(json.dumps(data))
        self.call('run','--once')
        self.assertEqual(len(self.machines()),3)
        self.assertIn('Host '+alias+'\n',ssh.read_text())
        self.assertIn('100.64.0.25',ssh.read_text())
        self.assertIn('fd7a:115c:a1e0::26',ssh.read_text())
        ipv6_alias=next(m['target'] for m in self.machines() if m['id']!='unrelated' and m['target']!=alias)
        parsed=subprocess.run(['ssh','-G','-F',str(ssh),ipv6_alias],env=self.env,text=True,capture_output=True,check=True)
        self.assertIn('hostname fd7a:115c:a1e0::26',parsed.stdout)
        self.assertNotIn('proxycommand ',parsed.stdout)
        self.assertEqual(next(m['id'] for m in self.machines() if m['target']==alias),old_id)
        for peer in data['Peer'].values(): peer['Online']=False
        (self.home/'tailscale.json').write_text(json.dumps(data))
        self.call('run','--once')
        self.assertEqual(len(self.machines()),3)
        self.tailscale_profile(offline=False)
        self.call('run','--once')
        self.assertEqual(len(self.machines()),1)
        self.assertNotIn('Host '+alias+'\n',ssh.read_text())
        self.tailscale_profile()
        self.tailnet()
        self.call('run','--once')
        self.tailnet(tagged=False)
        self.call('run','--once')
        self.assertEqual(len(self.machines()),1)
        self.tailnet()
        self.call('run','--once')
        (self.home/'tailscale.json').write_text(json.dumps(dict(BackendState='Running',Peer={})))
        self.call('run','--once')
        self.assertEqual(len(self.machines()),1)
        self.tailnet()
        self.call('run','--once')
        self.call('profile','remove','tailnet',input='y\n')
        self.assertEqual(len(self.machines()),1)
        self.assertNotIn('100.64.0.20',ssh.read_text())

    def test_tailscale_failure_preserves_entries_while_kubevirt_continues(self):
        self.profile()
        self.tailscale_profile()
        self.tailnet()
        self.call('run','--once')
        self.assertEqual(len(self.machines()),3)
        self.cluster(empty=True)
        (self.home/'tailscale-fails').touch()
        self.assertNotEqual(self.call('run','--once',ok=False).returncode,0)
        self.assertEqual(len(self.machines()),2)
        ssh=self.home/'.ssh/hwatch.conf'
        before=ssh.read_bytes()
        (self.home/'tailscale-fails').unlink()
        missing_id=self.tailnet()
        del missing_id['Peer']['nodekey:rotating']['ID']
        invalid_ip=self.tailnet()
        invalid_ip['Peer']['nodekey:rotating']['TailscaleIPs']=['100.64.0.20\nProxyCommand bad']
        for bad in ['not JSON',json.dumps(dict(BackendState='Stopped',Peer={})),json.dumps(dict(BackendState='Running')),json.dumps(missing_id),json.dumps(invalid_ip)]:
            (self.home/'tailscale.json').write_text(bad)
            self.assertNotEqual(self.call('run','--once',ok=False).returncode,0)
            self.assertEqual(ssh.read_bytes(),before)
            self.assertEqual(len(self.machines()),2)
        self.tailnet()
        self.call('run','--once')
        self.assertEqual(len(self.machines()),2)

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
