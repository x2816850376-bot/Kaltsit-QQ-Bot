"""Local, bounded opportunities to join a group conversation; no extra LLM."""
from copy import deepcopy
import hashlib
import json
import re
import time

from chat_context import GROUP

PROACTIVE_REPLY_RATE = 0.005
INTEREST_REPLY_RATE = 0.015
PROACTIVE_COOLDOWN_SECONDS = 300
PROACTIVE_WINDOW_SECONDS = 1800
PROACTIVE_WINDOW_LIMIT = 2
NAMES = r'(?:凯尔希|凯医生|凯喵|凯太后|老女人|牢猫|老猫|gpt娘|gpt|kal)'
INTEREST = re.compile(r'明日方舟|终末地|罗德岛|阿米娅|干员|肉鸽|危机合约|抽卡|十连|六星|专三|模组|卡关|漏怪|鹰角|舟圈|海猫|整活|绷不住|哈哈|离谱|逆天|笑死|舰桥', re.I)


class ChatParticipation:
    def __init__(self, path=None, clock=time.time):
        self.path, self.clock = path, clock
        self.attempts = []
        self.bindings = {}
        self.opportunities = {}
        if path and path.exists():
            try:
                data = json.loads(path.read_text('utf-8'))
                self.attempts = [float(t) for t in data.get('attempts', [])]
                self.bindings = data.get('bindings', {})
            except (ValueError, TypeError, OSError):
                self.attempts, self.bindings = [], {}

    def cooldown(self):
        now = self.clock()
        self.attempts = [t for t in self.attempts if 0 <= now - t < PROACTIVE_WINDOW_SECONDS]
        delay = max(0, self.attempts[-1] + PROACTIVE_COOLDOWN_SECONDS - now) if self.attempts else 0
        if len(self.attempts) >= PROACTIVE_WINDOW_LIMIT:
            delay = max(delay, self.attempts[0] + PROACTIVE_WINDOW_SECONDS - now)
        return round(delay, 1)

    @staticmethod
    def direct(message):
        evidence = (message.get('reply_routing') or {}).get('address_evidence')
        if evidence in ('explicit_at_bot', 'reply_to_bot', 'private_to_bot'):
            return True
        if evidence in ('explicit_at_other', 'reply_to_other', 'unresolved_reply', 'self_echo'):
            return False
        # Do not treat a display nickname or third-person game discussion as a call.
        text = ''.join(str(s.get('text', '')) for s in message.get('segments', []) if s.get('type') == 'text').strip()
        return bool(re.search(r'^' + NAMES + r'(?:[，,：:、！？!?\s]|你|在吗|帮|看看|说|怎么)', text, re.I)
                    or re.search(r'(?:在吗|你怎么看|你觉得|问你|叫你|找你)[，,\s]*' + NAMES + r'[？?！!\s]*$', text, re.I))

    @staticmethod
    def sample(sid, eid):
        # Stable across the text/structured copies and worker restarts: no rerolls.
        digest = hashlib.sha256(f'qq-participation-v1:{sid}:{eid}'.encode()).digest()
        return int.from_bytes(digest[:8], 'big') / 2**64

    def enrich(self, data, pending):
        if not isinstance(data, dict):
            return data
        out = deepcopy(data)
        session = out.get('session') or {}
        sid = out.get('session_id') or session.get('id')
        batches = []
        if isinstance(out.get('messages'), list):
            batches.append(out['messages'])
        if isinstance(out.get('context'), dict) and isinstance(out['context'].get('messages'), list):
            batches.append(out['context']['messages'])
        selected = []
        delay = self.cooldown()
        for rows in batches:
            for index, message in enumerate(rows):
                if not isinstance(message, dict):
                    continue
                eid = message.get('id')
                if (message.get('conversation_id') != GROUP or message.get('is_self')
                        or type(eid) != int or (sid, eid) not in pending):
                    continue
                addressed = self.direct(message)
                text = ''.join(str(s.get('text', '')) for s in message.get('segments', []) if s.get('type') == 'text').strip()
                has_image = any(s.get('type') == 'image' for s in message.get('segments', []))
                nearby = ' '.join(str(row.get('content', ''))[:300] for row in rows[max(0, index-3):index+1]
                                  if isinstance(row, dict) and not row.get('is_self'))
                interesting = bool(INTEREST.search(text + ' ' + nearby))
                rate = INTEREST_REPLY_RATE if interesting else PROACTIVE_REPLY_RATE
                unresolved = (message.get('reply_routing') or {}).get('address_evidence') == 'unresolved_reply'
                opportunity = bool(not addressed and not delay and not unresolved and (text or has_image)
                                   and self.sample(sid, eid) < rate)
                self.opportunities[(sid,eid)] = opportunity
                message['reply_participation'] = {
                    'priority': 'direct' if addressed else 'optional',
                    'proactive_opportunity': opportunity,
                    'interest_hint': '舟／游戏／轻松整活候选，仅作机会权重，不证明梗含义' if interesting else '普通交流',
                    'cooldown_remaining_seconds': delay,
                    'rule': 'direct优先回应；optional通常保持安静，只有机会为真才考虑主动接话，仍可以沉默。若话是对别人说的，评论事情而非冒认接收者；不把主动评论伪装direct。真实直接追问或续聊不受主动机会限制。'
                }
                if opportunity and eid not in selected:
                    selected.append(eid)
        out['group_participation'] = {
            'mode': 'quiet_observer', 'opportunity_event_ids': selected,
            'ordinary_rate': PROACTIVE_REPLY_RATE, 'interest_rate': INTEREST_REPLY_RATE,
            'cooldown_seconds': PROACTIVE_COOLDOWN_SECONDS,
            'window_seconds': PROACTIVE_WINDOW_SECONDS,
            'max_proactive_per_window': PROACTIVE_WINDOW_LIMIT,
            'rule': '日常以安静观察为主，候选机会不是发言任务，每批最多主动评论一条。兴趣关键词只选机会；不照词库硬接梗，不宣读技术元数据。'
        }
        self.opportunities=dict(list(self.opportunities.items())[-128:])
        return out

    def admit(self, arguments, mode):
        if mode not in ('direct', 'proactive'):
            raise ValueError('participation_mode必须为direct或proactive')
        key = hashlib.sha256((str(arguments.get('session_id')) + ':' + str(arguments.get('idempotency_key'))).encode()).hexdigest()
        binding = [arguments.get('respond_to_event_id'), mode]
        if key in self.bindings:
            if self.bindings[key] != binding:
                raise ValueError('同一发送编号不能改变主动/直接回复模式')
            return  # Stable retries still go through upstream receipt/idempotency checks.
        if mode == 'proactive' and self.cooldown():
            raise ValueError('主动接话正在冷却，继续等新消息；直接被叫到可正常回应')
        if mode == 'proactive' and not self.opportunities.get((arguments.get('session_id'),arguments.get('respond_to_event_id'))):
            raise ValueError('当前消息没有主动接话机会，保持观察；不要改为direct绕过')
        self.bindings[key] = binding
        self.bindings = dict(list(self.bindings.items())[-256:])
        if mode == 'proactive':
            self.attempts.append(self.clock())
        if self.path:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temporary = self.path.with_suffix('.tmp')
            temporary.write_text(json.dumps({'attempts': self.attempts, 'bindings': self.bindings}), 'utf-8')
            temporary.replace(self.path)
