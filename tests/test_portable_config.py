import asyncio
from copy import deepcopy
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import bot_config
from chat_scope import GroupScope
from cli_config import settings_args

class PortableTests(unittest.TestCase):
    def setUp(self):self.cfg=bot_config.load()

    def test_no_foreign_group_or_remote_endpoint(self):
        with patch.dict('os.environ',{'KALTSIT_GROUP':'99999999'}):
            with self.assertRaises(ValueError):bot_config.group_id(self.cfg)
        for field,value in [('account','1;whoami'),('groups',['all']),
                            ('onebot_http_url','https://example.com:3000'),
                            ('onebot_ws_url','ws://user:password@127.0.0.1:3001'),
                            ('model','gpt-6.1-sol'),('max_parallel_groups',True)]:
            data=deepcopy(self.cfg);data[field]=value
            with self.assertRaises(ValueError):bot_config.validate(data)

    def test_group_workdirs_are_distinct(self):
        with patch.dict('os.environ',{'KALTSIT_GROUP':self.cfg['groups'][0]}):a=bot_config.runtime_dir()
        with patch.dict('os.environ',{'KALTSIT_GROUP':self.cfg['groups'][1]}):b=bot_config.runtime_dir()
        self.assertNotEqual(a,b)

    def test_mcp_stdin_transport_has_no_tokens(self):
        import tomllib
        stanza=tomllib.loads(settings_args(['get_chat_session'])[1])['mcp_servers']['kaltsit_bot']
        self.assertNotIn('url',stanza);self.assertNotIn('http_headers',stanza)
        self.assertNotIn(self.cfg['onebot_token'],str(stanza))
        self.assertTrue(stanza['args'][0].endswith('mcp-stdio-proxy.py'))

class GroupScopeTests(unittest.IsolatedAsyncioTestCase):
    async def test_read_and_send_cannot_cross_group(self):
        class Remote:
            async def call_tool(self,name,args):
                return SimpleNamespace(isError=False,structuredContent={'session':{'conversation_id':'foreign'}},content=[])
        scope=GroupScope()
        for name in ('get_chat_session','send_chat_message','read_chat_image','get_world_knowledge'):
            self.assertFalse(await scope.check(name,{'session_id':'s'},Remote()))

    async def test_session_metadata_is_cached_without_mutating_permissions(self):
        class Remote:
            count=0
            async def call_tool(self,name,args):
                self.count+=1
                return SimpleNamespace(isError=False,structuredContent={'session':{'conversation_id':bot_config.group_id()}},content=[])
        scope=GroupScope();remote=Remote()
        for name in ('get_chat_session','send_chat_message'):
            self.assertTrue(await scope.check(name,{'session_id':'s'},remote))
        self.assertEqual(remote.count,1)
        self.assertFalse(await scope.check('exec_command',{'session_id':'s'},remote))
