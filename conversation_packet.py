"""Same enrichment for host prefetch and model proxy; all chat remains inert data."""
from copy import deepcopy
import hashlib
from pathlib import Path
from chat_context import ReplyContextCache
from chat_address import DoctorAddress
from chat_expression_history import ExpressionHistory
from chat_knowledge import OperatorKnowledge
from chat_participation import ChatParticipation
from chat_community import CommunityKnowledge
from chat_world import TerraKnowledge
from chat_corpus import CanonicalKnowledge
from chat_social import ConversationSocial
from chat_continuity import ConversationContinuity
from chat_time import ExchangeClock
from chat_semantic import SemanticClient

def merge_wait_packets(first, second):
    """Merge two successive wait results without losing the first speaker.

    Tulpa can return the first quiet-window batch and then a second fragment
    batch.  The second result is newer, but it is not a replacement: both
    batches belong to the same model turn.  De-duplicate by the stable event
    id (falling back to the OneBot id) and keep chronological order.
    """
    if not isinstance(first,dict):
        return deepcopy(second) if isinstance(second,dict) else {}
    if not isinstance(second,dict):
        return deepcopy(first)
    out=deepcopy(first)
    rows=[];seen=set()
    for source in (first.get('messages',[]),second.get('messages',[])):
        if not isinstance(source,list):
            continue
        for row in source:
            if not isinstance(row,dict):
                continue
            key=('event',row.get('id')) if type(row.get('id')) is int else ('onebot',str(row.get('onebot_message_id','')))
            if key in seen:
                continue
            seen.add(key);rows.append(deepcopy(row))
    rows.sort(key=lambda row: (row.get('id') if type(row.get('id')) is int else 10**18,
                               row.get('received_at',0)))
    if rows:
        out['messages']=rows
    for key in ('read_through_id','has_more'):
        if key not in second:
            continue
        if key=='read_through_id' and type(second.get(key)) is int and type(first.get(key)) is int:
            out[key]=max(first[key],second[key])
        else:
            out[key]=deepcopy(second[key])
    if second.get('event') not in (None,'idle'):
        out['event']=second.get('event')
    return out

def _batch_routing(packet):
    """Build a compact, model-facing map of current speakers and targets."""
    rows=[row for row in packet.get('messages',[]) if isinstance(row,dict) and not row.get('is_self')]
    events=[];threads={}
    for row in rows:
        routing=row.get('reply_routing') or {}
        speaker=str(row.get('sender_id',''))
        event={'event_id':row.get('id'),'speaker_id':speaker,
               'speaker_name':str(row.get('sender',''))[:120],
               'content':str(row.get('content',''))[:1500],
               'address_evidence':routing.get('address_evidence','not_explicit'),
               'explicit_at_ids':list(routing.get('explicit_at_ids') or []),
               'quoted_speaker_id':routing.get('quoted_speaker_id'),
               'quoted_event_id':routing.get('quoted_event_id'),
               'mentioned_people_candidates':list(routing.get('mentioned_people_candidates') or [])}
        events.append(event)
        threads.setdefault(speaker,{'speaker_id':speaker,'speaker_name':event['speaker_name'],'event_ids':[],'messages':[]})
        threads[speaker]['event_ids'].append(row.get('id'))
        threads[speaker]['messages'].append(str(row.get('content',''))[:500])
    direct=[event['event_id'] for event in events if event['address_evidence'] in ('explicit_at_bot','reply_to_bot','private_to_bot')]
    other=[event['event_id'] for event in events if event['address_evidence'] in ('explicit_at_other','reply_to_other','unresolved_reply')]
    return {'speaker_count':len(threads),'interleaved':len(threads)>1,
            'events':events,'speaker_threads':list(threads.values()),
            'direct_target_event_ids':direct,'non_bot_target_event_ids':other,
            'rules':'每个event_id的speaker_id是实际发言者。引用和@别人只改变接收对象，不改变speaker_id。交错消息不得把前后两人的内容拼成一人的经历。若多个独立事件都明确叫到机器人，可分别用对应event_id调用send_chat_message；若只有一个事件需要回应，只回应它。不能用一个event_id绑定另一位发言者。'}

def enrich_snapshot(root,directory,packet):
    root=Path(root);directory=Path(directory)
    quotes=ReplyContextCache(directory/'qq-reply-context.json')
    addresses=DoctorAddress(directory/'doctor-address-state.json')
    expressions=ExpressionHistory(directory/'qq-expression-history.json',
                                  hashlib.sha256((root/'prompts/persona_runtime.txt').read_bytes()).hexdigest())
    out=addresses.enrich(quotes.enrich(packet),quotes.pending)
    out=expressions.enrich(out)
    providers=(OperatorKnowledge(root/'knowledge/arknights/operators.json'),
               ChatParticipation(directory/'group-participation-state.json'),
               CommunityKnowledge(root/'knowledge/bilibili-arknights'),TerraKnowledge(),CanonicalKnowledge())
    for provider in providers:
        out=provider.enrich(out,quotes.pending)
    cid=(packet.get('session') or {}).get('conversation_id')
    if cid:
        social=ConversationSocial(directory/'conversation-social.private.json',cid,
                                  hashlib.sha256((root/'prompts/persona_runtime.txt').read_bytes()).hexdigest())
        out=social.enrich(out)
        continuity=ConversationContinuity(directory/'conversation-continuity.private.json',cid,
                                         hashlib.sha256((root/'prompts/persona_runtime.txt').read_bytes()).hexdigest())
        continuity.reconcile(directory/'qq-response-batches.json')
        out=continuity.enrich(out)
        clock=ExchangeClock(directory/'exchange-time.private.json',cid)
        clock.reconcile(directory/'qq-response-batches.json')
        out=clock.enrich(out)
    out=SemanticClient(root).enrich(out)
    out['current_batch_routing']=_batch_routing(out)
    return out

def combine(snapshot,incoming):
    packet=deepcopy(snapshot)
    for key in ('messages','session_id','read_through_id','has_more','receiver','event'):
        if key in incoming:packet[key]=deepcopy(incoming[key])
    return packet

def model_packet(enriched):
    packet=deepcopy(enriched)
    # Current role and protocol already appear in trusted developer/system text.
    # Remove repeated transport instructions, never the role card or its Skills.
    packet.pop('instructions',None)
    for key in ('chat_prompt','chat_guidance'):
        value=packet.get(key)
        if isinstance(value,dict):
            for duplicate in ('persona','behavior','continue_with','resume'):value.pop(duplicate,None)
    session=packet.get('session')
    if isinstance(session,dict):session.pop('persona',None)
    context=packet.get('context')
    if isinstance(context,dict) and isinstance(context.get('messages'),list):
        context['messages']=context['messages'][-15:]
    return packet
