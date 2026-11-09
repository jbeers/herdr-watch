#!/usr/bin/env python3
"""Plugin entrypoints using a real native hwatch and disposable CLI fixtures."""
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import tempfile
import time
import tomllib
import unittest

import acceptance

ROOT=Path(__file__).resolve().parents[1]


class Plugin(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.build=tempfile.TemporaryDirectory(prefix='hwatch-plugin-build-')
        cls.addClassCleanup(cls.build.cleanup)
        cls.binary=Path(os.environ.get('HWATCH_BIN', str(Path(cls.build.name)/'hwatch'))).resolve()
        if 'HWATCH_BIN' not in os.environ:
            subprocess.run(['python3',str(ROOT/'tools/build.py'),'--output',str(cls.binary)],check=True)

    def setUp(self):
        self.fixture=acceptance.Acceptance(methodName='runTest')
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.home=self.fixture.home
        self.env=self.fixture.env
        self.plugin=self.home/'plugin checkout'
        shutil.copytree(ROOT/'plugin',self.plugin,ignore=shutil.ignore_patterns('bin'))
        (self.plugin/'bin').mkdir()
        shutil.copy2(self.binary,self.plugin/'bin/hwatch')
        self.env.update(HERDR_PLUGIN_ROOT=str(self.plugin),HERDR_PLUGIN_ID='hwatch',
                        HERDR_PLUGIN_CONFIG_DIR=str(self.home/'unused plugin config'),
                        HERDR_PLUGIN_STATE_DIR=str(self.home/'unused plugin state'),
                        HERDR_BIN_PATH=str(self.home/'bin/herdr'))
        self.manifest=tomllib.loads((self.plugin/'herdr-plugin.toml').read_text())

    def call(self,entry,input=None,ok=True):
        command=next(a['command'] for a in self.manifest['actions'] if a['id']==entry)
        result=subprocess.run(command,cwd=self.plugin,env=self.env,input=input,text=True,
                              capture_output=True,timeout=20)
        if ok: self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        return result

    def pane(self,entry,input):
        command=next(a['command'] for a in self.manifest['panes'] if a['id']==entry)
        result=subprocess.run(command,cwd=self.plugin,env=self.env,input=input,text=True,
                              capture_output=True,timeout=20)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        return result

    def test_help_version_and_diagnostics_share_real_configuration_paths(self):
        result=self.call('help')
        for path in [self.home/'config/hwatch/profiles', self.home/'state/hwatch',self.home/'.ssh/hwatch.conf']:
            self.assertIn(str(path),result.stdout)
        for action in ['profile','doctor','run','watch']:
            self.assertIn(action,result.stdout)
        self.assertIn('hwatch ',self.call('version').stdout)
        self.assertFalse((self.home/'state').exists())
        self.assertFalse((self.home/'config').exists())
        result=self.call('doctor',ok=False)
        self.assertNotEqual(result.returncode,0)
        self.assertIn('Include',result.stdout)
        self.assertFalse((self.home/'unused plugin config').exists())
        self.assertFalse((self.home/'.ssh/config').exists())

    def test_profile_menu_creates_inspects_and_removes_shared_profiles(self):
        result=self.pane('profiles','2\nlab\n1\nlab\ndev\nhwatch=enabled\njacob\n\n\n\n\ny\n1\n3\nlab\n4\nlab\nq\n')
        profile=self.home/'config/hwatch/profiles/lab.json'
        self.assertEqual(json.loads(profile.read_text())['context'],'lab')
        self.assertIn(str(profile),result.stdout)
        self.assertIn('includeStopped',result.stdout)
        self.call('run')
        self.assertEqual(len(self.fixture.machines()),2)
        # The same journal is usable by the ordinary CLI (not a plugin-private copy).
        result=subprocess.run([str(self.binary),'run','--once'],env=self.env,text=True,capture_output=True)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        self.assertEqual(len(self.fixture.machines()),2)
        self.pane('profiles','5\nlab\ny\n6\nq\n')
        self.assertFalse(profile.exists())
        self.assertEqual(len(self.fixture.machines()),1)
        self.assertFalse((self.home/'unused plugin state').exists())

    def test_interactive_actions_route_to_declared_host_panes(self):
        host=self.home/'host tools/herdr'
        host.parent.mkdir()
        (self.home/'bin/herdr').rename(host)
        self.env.update(HERDR_BIN_PATH=str(host),HERDR_WORKSPACE_ID='w-test')
        for action,entry in [('profile','profiles'),('watch','watcher')]:
            self.call(action)
            calls=[json.loads(line) for line in (self.home/'calls').read_text().splitlines()]
            expected=['herdr','plugin','pane','open','--plugin','hwatch','--entrypoint',entry]
            if action=='watch': expected+=['--workspace','w-test']
            self.assertEqual(calls[-1],expected)
            self.assertTrue(any(p['id']==entry for p in self.manifest['panes']))

    @unittest.skipUnless(os.environ.get('HERDR_TEST_BIN'), 'Set HERDR_TEST_BIN to opt into an isolated real Herdr server')
    def test_real_host_links_invokes_and_logs_plugin_actions(self):
        host=str(Path(os.environ['HERDR_TEST_BIN']).resolve())
        env={k:v for k,v in self.env.items() if not k.startswith('HERDR_')}
        env.update(HERDR_CONFIG_PATH=str(self.home/'config/herdr/config.toml'),
                   XDG_DATA_HOME=str(self.home/'data'),XDG_RUNTIME_DIR=str(self.home/'runtime'))
        (self.home/'runtime').mkdir(mode=0o700)
        prefix=[host,'--session','hwatch-plugin-test']
        def host_call(*args,ok=True):
            result=subprocess.run(prefix+list(args),env=env,cwd=self.home,text=True,
                                  capture_output=True,timeout=15)
            if ok: self.assertEqual(result.returncode,0,result.stdout+result.stderr)
            return result
        host_call('plugin','link',str(self.plugin))
        with (self.home/'server.log').open('w') as log:
            server=subprocess.Popen(prefix+['server'],env=env,cwd=self.home,stdout=log,stderr=log)
            try:
                deadline=time.monotonic()+10
                while time.monotonic()<deadline:
                    self.assertIsNone(server.poll(),(self.home/'server.log').read_text())
                    result=host_call('plugin','action','list','--plugin','hwatch',ok=False)
                    if result.returncode==0: break
                    time.sleep(0.05)
                else: self.fail('Isolated Herdr server did not become ready')
                actions=json.loads(result.stdout)['result']['actions']
                self.assertEqual({a['action_id'] for a in actions},{'help','doctor','profile','version','run','watch'})
                workspace=json.loads(host_call('workspace','create','--cwd',str(self.home),
                                               '--label','hwatch-plugin-test','--focus').stdout)['result']
                root_pane=workspace['root_pane']['pane_id']
                for action in ['help','version','profile']:
                    host_call('plugin','action','invoke','hwatch.'+action)
                deadline=time.monotonic()+10
                while time.monotonic()<deadline:
                    logs=json.loads(host_call('plugin','log','list','--plugin','hwatch').stdout)['result']['logs']
                    if len(logs)==3 and all(item['status']!='running' for item in logs): break
                    time.sleep(0.05)
                else: self.fail('Plugin actions did not complete')
                self.assertTrue(all(item['status']=='succeeded' for item in logs),logs)
                output={item['action_id']:item['stdout'] for item in logs}
                self.assertIn(str(self.home/'config/hwatch/profiles'),output['help'])
                self.assertIn('Commit:',output['version'])
                panes=json.loads(host_call('pane','list').stdout)['result']['panes']
                menu=next(p['pane_id'] for p in panes if p['pane_id']!=root_pane)
                deadline=time.monotonic()+5
                while time.monotonic()<deadline:
                    screen=host_call('pane','read',menu,'--raw').stdout
                    if 'hwatch profiles' in screen: break
                    time.sleep(0.05)
                else: self.fail('Profile menu was not rendered in its real terminal pane')
                host_call('pane','send-keys',menu,'q','enter')
                self.assertFalse((self.home/'state/hwatch').exists())
            finally:
                if server.poll() is None:
                    host_call('server','stop',ok=False)
                try: server.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    server.kill()
                    server.wait(timeout=5)

    def test_watcher_runs_in_foreground_and_can_be_interrupted_then_restarted(self):
        self.fixture.profile()
        command=next(p['command'] for p in self.manifest['panes'] if p['id']=='watcher')
        with (self.home/'watch.log').open('w') as log:
            process=subprocess.Popen(command,cwd=self.plugin,env=self.env,stdin=subprocess.DEVNULL,
                                     stdout=log,stderr=log,start_new_session=True)
            try:
                deadline=time.monotonic()+10
                while time.monotonic()<deadline:
                    self.assertIsNone(process.poll(),(self.home/'watch.log').read_text())
                    if len(self.fixture.machines())==2: break
                    time.sleep(0.05)
                else: self.fail('Watcher did not reconcile')
                self.assertNotEqual(self.call('run',ok=False).returncode,0)
                os.killpg(process.pid,signal.SIGINT)
                process.wait(timeout=5)
                self.call('run')
                self.assertEqual(len(self.fixture.machines()),2)
            finally:
                if process.poll() is None:
                    os.killpg(process.pid,signal.SIGKILL)
                    process.wait(timeout=5)


if __name__=='__main__': unittest.main()
