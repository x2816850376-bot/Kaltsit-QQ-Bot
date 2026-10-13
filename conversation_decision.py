"""Reuse the real quote and participation rules before spending a model call."""
from chat_context import ReplyContextCache
from chat_participation import ChatParticipation
import json
import time

def needs_generation(packet, root):
    quotes=ReplyContextCache(root/'qq-reply-context.json')
    scoped=quotes.enrich(packet)
    participation=ChatParticipation(root/'group-participation-state.json')
    enriched=participation.enrich(scoped,quotes.pending)
    rows=[r for r in enriched.get('messages',[]) if isinstance(r,dict) and not r.get('is_self')]
    if any(participation.direct(r) or (r.get('reply_participation') or {}).get('proactive_opportunity') for r in rows):return True
    # A recent actual outgoing turn establishes continuity with this one peer;
    # explicit messages directed to someone else are never counted as continuity.
    path=root/'doctor-address-state.json'
    try:last=json.loads(path.read_text('utf-8')).get('last',{}).get(packet.get('session_id'),{})
    except (OSError,ValueError,TypeError):last={}
    if time.time()-last.get('at',0)<180:
        for row in rows:
            if str(row.get('sender_id'))==last.get('recipient') and (row.get('reply_routing') or {}).get('address_evidence')=='not_explicit':return True
    return False
