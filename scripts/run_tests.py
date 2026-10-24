"""Source tests: synthetic config, no installed Codex required, no QQ network."""
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT))


def main():
    with tempfile.TemporaryDirectory(prefix='kaltsit-tests-') as temp:
        config=Path(temp)/'synthetic-config.json'
        config.write_text(json.dumps({'account':'10000001','groups':['20000001','20000002'],
            'onebot_http_url':'http://127.0.0.1:3000','onebot_ws_url':'ws://127.0.0.1:3001',
            'onebot_token':'synthetic-test-only','codex_path':'synthetic-codex.exe','node_path':'node'}),'utf-8')
        os.environ['KALTSIT_SEMANTIC_DISABLED']='1'
        os.environ['KALTSIT_CONFIG']=str(config);os.environ['KALTSIT_GROUP']='20000001'
        # Patches cover only CLI discovery/help. subprocess generation tests still
        # verify their own argument/stdin isolation and mock their model result.
        with patch('cli_config.capabilities',return_value={'--ephemeral','--skip-git-repo-check','--json','--no-daemon','--strict-config','--ignore-rules'}):
            suite=unittest.defaultTestLoader.discover(str(ROOT/'tests'),pattern='test_*.py')
            result=unittest.TextTestRunner(verbosity=1).run(suite)
        return result.wasSuccessful()


if __name__=='__main__':sys.exit(not main())
