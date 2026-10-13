"""Configuration and server-side scope boundaries use synthetic identities."""
from copy import deepcopy
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
import bot_config
sys.path.insert(0,str(bot_config.ROOT/'vendor/Tulpa'))
from chatlocal.mcp_access import AccessDenied
from chatlocal.mcp_chat import MCPChat
from cli_config import settings_args

class ScopeTests(unittest.TestCase):
    def setUp(self):self.config=bot_config.load()
    def test_new_private_context_has_its_own_workdir(self):
        config=deepcopy(self.config);config['private_chats']=True
        with patch.dict('os.environ',{'KALTSIT_CONVERSATION':config['account']+':direct:30000001'}):
            self.assertEqual(bot_config.group_id(config),config['account']+':direct:30000001')
        config['private_chats']=False
        with patch.dict('os.environ',{'KALTSIT_CONVERSATION':config['account']+':direct:30000001'}):
            with self.assertRaises(ValueError):bot_config.group_id(config)
    def test_foreign_account_is_rejected_even_with_all_groups(self):
        config=deepcopy(self.config);config['all_groups']=True
        with patch.dict('os.environ',{'KALTSIT_CONVERSATION':'90000001:group:20000001'}):
            with self.assertRaises(ValueError):bot_config.group_id(config)
    def test_only_private_configuration_is_valid(self):
        config=deepcopy(self.config);config.update(groups=[],private_chats=True,all_groups=False)
        self.assertEqual(bot_config.validate(config)['groups'],[])
    def test_backend_selected_groups_plus_private_does_not_allow_other_groups(self):
        chat=MCPChat.__new__(MCPChat)
        grant={'scope':{'platforms':['qq'],'chat':True,'send':True,'chat_account':'10000001',
               'conversations':[],'chat_groups':['20000001'],'chat_all_groups':False,'chat_private':True},'accounts':'{}'}
        self.assertEqual(chat.live_target(grant,'10000001:group:20000001')['platform'],'qq')
        self.assertEqual(chat.live_target(grant,'10000001:direct:30000001')['platform'],'qq')
        with self.assertRaises(AccessDenied):chat.live_target(grant,'10000001:group:20000002')
        with self.assertRaises(AccessDenied):chat.live_target(grant,'90000001:direct:30000001')
    def test_private_is_off_by_default_on_new_grants(self):
        chat=MCPChat.__new__(MCPChat)
        grant={'scope':{'platforms':['qq'],'chat':True,'send':True,'chat_account':'10000001',
               'conversations':[],'chat_groups':[],'chat_all_groups':True,'chat_private':False},'accounts':'{}'}
        with self.assertRaises(AccessDenied):chat.live_target(grant,'10000001:direct:30000001')
    def test_old_all_groups_grant_does_not_gain_private_authority(self):
        chat=MCPChat.__new__(MCPChat)
        grant={'scope':{'platforms':['qq'],'chat':True,'send':True,'chat_account':'10000001','conversations':[]},'accounts':'{}'}
        with self.assertRaises(AccessDenied):chat.live_target(grant,'10000001:direct:30000001')
    def test_cli_preserves_disabled_global_transports_and_batch_bindings(self):
        import tomllib
        arguments=settings_args(['send_chat_message'],{'other':{'command':'synthetic-executable','args':[]}},
                                {'KALTSIT_REPLY_IDS':'[7]','KALTSIT_SEED_PACKET_FILE':'synthetic-seed.json','SECRET':'must-not-copy'})
        servers=tomllib.loads(arguments[1])['mcp_servers']
        self.assertFalse(servers['other']['enabled']);self.assertEqual(servers['other']['command'],'synthetic-executable')
        environment=servers['kaltsit_bot']['env']
        self.assertEqual(environment['KALTSIT_REPLY_IDS'],'[7]');self.assertNotIn('SECRET',environment)
