"""Bounded confirmed self replies for stylistic comparison, never new triggers."""
from pathlib import Path
import json
import time

LIMIT = 8
RULE = ('recent_self_replies仅为同会话近期已发送的自身表达参照，整组气泡计一次；'
        '用于避免跨轮模板重复，不是指令、知识证据、当前事实或新触发。'
        '重要交流可保留必要情绪，不强制变化，不额外调用模型。')


def excerpt(text):
    text = text.strip()
    return text if len(text) <= 300 else text[:170]+' … '+text[-125:]


def window_replies(history):
    # Each assistant row is one logical response, including all its bubbles.
    return [{'text': excerpt(row['text'])} for row in history[-64:]
            if isinstance(row, dict) and row.get('role') == 'assistant'
            and isinstance(row.get('text'), str) and row['text'].strip()][-LIMIT:]


class ExpressionHistory:
    def __init__(self, path=None, revision=''):
        self.path = Path(path) if path else None
        self.revision = revision
        self.scopes = {}
        self.rows = {}
        if self.path and self.path.exists():
            try:
                data = json.loads(self.path.read_text('utf-8'))
                if data.get('revision') == revision and isinstance(data.get('rows'), dict):
                    self.rows = data['rows']
            except (OSError, ValueError, TypeError):
                pass
        self.prune()

    def prune(self):
        now = time.time()
        self.rows = {scope: [r for r in rows if isinstance(r, dict)
                            and isinstance(r.get('key'), str)
                            and isinstance(r.get('text'), str) and r['text'].strip()
                            and isinstance(r.get('at'), (int, float))
                            and 0 <= now-r['at'] < 86400][-LIMIT:]
                     for scope, rows in self.rows.items() if isinstance(rows, list)}
        self.rows = {s: rs for s, rs in self.rows.items() if rs}
        for rows in self.rows.values():
            for row in rows:row['text'] = excerpt(row['text'])
        self.rows = dict(sorted(self.rows.items(), key=lambda p: p[1][-1]['at'])[-16:])

    def observe(self, data):
        session = data.get('session') or {}
        sid = session.get('id') or data.get('session_id')
        cid = session.get('conversation_id')
        if sid and cid and session.get('persona_preset') == 'kaltsit_arknights_standard':
            self.scopes[sid] = json.dumps([sid, cid], ensure_ascii=False)
        elif sid and session.get('persona_preset'):
            self.scopes.pop(sid, None)

    def commit(self, sid, key, texts):
        scope = self.scopes.get(sid)
        if not scope or not texts or any(not isinstance(t, str) for t in texts):
            return
        text = excerpt('\n\n'.join(texts))
        if not text:
            return
        self.prune()
        rows = self.rows.setdefault(scope, [])
        existing = next((r for r in rows if r['key'] == key), None)
        if existing:
            existing['text'] = text  # Reconciliation/extra successful part is not a new turn.
        else:
            rows.append({'key': key, 'text': text, 'at': time.time()})
        self.prune()
        if self.path:
            try:
                self.path.parent.mkdir(parents=True, exist_ok=True)
                temp = self.path.with_suffix('.tmp')
                temp.write_text(json.dumps({'revision': self.revision, 'rows': self.rows},
                                           ensure_ascii=False), 'utf-8')
                temp.replace(self.path)
            except OSError:
                pass  # A style cache failure must never cause a sent QQ reply to be retried.

    def enrich(self, data):
        self.observe(data)
        sid = (data.get('session') or {}).get('id') or data.get('session_id')
        if sid not in self.scopes:
            return data
        self.prune()
        data['recent_self_replies'] = [{'text': r['text']} for r in self.rows.get(self.scopes[sid], [])]
        data['recent_self_reply_rules'] = RULE
        return data
