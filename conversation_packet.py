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

def enrich_snapshot(root,directory,packet):
    root=Path(root);directory=Path(directory)
    quotes=ReplyContextCache(directory/'qq-reply-context.json')
    addresses=DoctorAddress(directory/'doctor-address-state.json')
    expressions=ExpressionHistory(directory/'qq-expression-history.json',
                                  hashlib.sha256((root/'prompts/persona_runtime.txt').read_bytes()).hexdigest())
    out=addresses.enrich(quotes.enrich(packet),quotes.pending)
    out=expressions.enrich(out)
    for provider in (OperatorKnowledge(root/'knowledge/arknights/operators.json'),
                     ChatParticipation(directory/'group-participation-state.json'),
                     CommunityKnowledge(root/'knowledge/bilibili-arknights'),TerraKnowledge(),CanonicalKnowledge()):
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
