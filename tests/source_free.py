#!/usr/bin/env python3
"""Build staged copies and verify the public CLI without its source files."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
MATCHBOX = str(Path(shutil.which(os.environ.get('MATCHBOX', 'matchbox')) or os.environ.get('MATCHBOX', 'matchbox')).resolve())


def run(args, **kwargs):
    subprocess.run(args, check=True, **kwargs)


with tempfile.TemporaryDirectory(prefix='hwatch-source-free-') as directory:
    stage=Path(directory)
    app=stage/'app'
    app.mkdir()
    entry=app/'main.bxs'
    shutil.copyfile(ROOT/'src/main.bxs',entry)
    bytecode=stage/'hwatch.bxb'
    native=stage/'hwatch'
    env=dict(os.environ, BOXLANG_HOME=str(stage/'empty-boxlang-home'))
    run([MATCHBOX,str(entry),'--help'],env=env,cwd=stage)
    # A fixed build timestamp proves identity is embedded, not read at runtime.
    env['SOURCE_DATE_EPOCH']='1700000000'
    env['MATCHBOX']=MATCHBOX
    info=dict(version=subprocess.check_output(['git','describe','--tags','--always','--dirty'],cwd=ROOT,text=True).strip(),
              commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
              date='2023-11-14T22:13:20Z')
    env['HWATCH_EXPECT_BUILD_INFO']=json.dumps(info)
    for target,output in [('bytecode',bytecode),('native',native)]:
        run(['python3',str(ROOT/'tools/build.py'),'--target',target,'--output',str(output),
             '--source',str(entry)],env=env,cwd=stage)
    entry.unlink()
    app.rmdir()
    for index,command in enumerate([[MATCHBOX,str(bytecode)],[str(native)]]):
        env['MATCHBOX_NATIVE_CACHE']=str(stage/('cache-'+str(index)))
        result=subprocess.run(command+['profile','where','does-not-exist'],env=env,cwd=stage,text=True,capture_output=True)
        assert result.returncode != 0 and 'Profile not found' in result.stdout, result
        result=subprocess.run(command+['--help'],env=env,cwd=stage,text=True,capture_output=True,check=True)
        assert 'profile new <name>' in result.stdout, result.stdout
        if index == 0:
            env.pop('HWATCH_BIN',None)
            env['HWATCH_BYTECODE']=str(bytecode)
            env['MATCHBOX']=MATCHBOX
        else:
            env['HWATCH_BIN']=str(native)
            # Exercise distribution with no Java, Cargo, SDK, or MatchBox on PATH.
            tools=stage/'tools'
            tools.mkdir()
            for tool in ['sh','mkdir','rmdir','rm','ps','ssh','python3']:
                (tools/tool).symlink_to(shutil.which(tool))
            env['PATH']=str(tools)
        run(['python3',str(ROOT/'tests/acceptance.py')],env=env,cwd=stage)
    print('Source-free bytecode and native acceptance checks passed.')
