"""Concurrent same-grant MCP requests use distinct client IDs, never real QQ."""
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent
text=(ROOT/'scripts/smoke_private_bridge.py').read_text('utf-8')
old="                assert len(clients)==1"
new='''                assert len(clients)==1
                async def parallel_wait(index):
                    async with httpx.AsyncClient(headers={'Authorization':'Bearer '+connection['token'],'X-Tulpa-Client-ID':'parallel-test-'+str(index)},timeout=10,trust_env=False) as peer_http:
                        async with streamable_http_client(connection['url'],http_client=peer_http) as (r2,w2,_):
                            async with ClientSession(r2,w2) as peer:
                                await peer.initialize()
                                return data(await peer.call_tool('wait_chat_messages',{'session_id':sids[index],'timeout_seconds':1,'quiet_seconds':0}))
                waits=await asyncio.gather(parallel_wait(0),parallel_wait(1))
                assert all(w['event']=='idle' for w in waits)
                print('Concurrent same-grant long polls passed without 409')'''
assert text.count(old)==1
text=text.replace(old,new)
exec(compile(text,str(ROOT/'scripts/smoke_private_bridge.py'),'exec'),dict(__name__='__main__',__file__=str(ROOT/'scripts/smoke_private_bridge.py')))
