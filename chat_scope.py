"""Each worker can only read or act on its own immutable group session."""
import json
from chat_context import GROUP

CHAT_TOOLS={'get_chat_session','wait_chat_messages','send_chat_message','read_chat_image',
            'list_chat_stickers','read_chat_sticker','note_chat_sticker','send_chat_sticker',
            'get_operator_knowledge','get_community_knowledge','get_world_knowledge','get_canonical_knowledge'}

def content(result):
    if isinstance(result.structuredContent,dict):return result.structuredContent
    for part in result.content:
        if part.type=='text':
            try:return json.loads(part.text)
            except ValueError:pass
    return {}

class GroupScope:
    def __init__(self):self.confirmed=set()

    async def check(self,name,arguments,upstream):
        if name not in CHAT_TOOLS or not isinstance(arguments,dict):return False
        sid=arguments.get('session_id')
        if not isinstance(sid,str) or not sid:return False
        if sid in self.confirmed:return True
        result=await upstream.call_tool('get_chat_session',{'session_id':sid})
        if result.isError:return False
        if content(result).get('session',{}).get('conversation_id')!=GROUP:return False
        self.confirmed.add(sid)
        return True
