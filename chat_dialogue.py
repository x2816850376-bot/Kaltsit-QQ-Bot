"""Load trusted dialogue guidance into the existing single Luna invocation."""
import hashlib
from pathlib import Path

SKILL_PATH = Path(__file__).resolve().parent/'skills/kaltsit-dialogue-output/SKILL.md'
COHERENCE_PATH = Path(__file__).resolve().parent/'skills/kaltsit-bubble-coherence/SKILL.md'
ACTION_PATH = Path(__file__).resolve().parent/'skills/kaltsit-conversation-action/SKILL.md'

def read_action_skill(path=None):
    source=Path(path) if path is not None else ACTION_PATH
    text=source.read_text('utf-8-sig').replace('\r\n','\n')
    pieces=text.split('\n---\n',1)
    if not text.startswith('---\n') or len(pieces)!=2 or 'name: kaltsit-conversation-action' not in pieces[0]:raise ValueError('Unexpected action skill')
    body=pieces[1].strip()
    if not body or len(body)>2400 or '[TODO' in body:raise ValueError('Invalid action skill')
    return body

def action_sha256(path=None):
    return hashlib.sha256(read_action_skill(path).encode('utf-8')).hexdigest()


def read_dialogue_skill(path=None):
    source = Path(path) if path is not None else SKILL_PATH
    text = source.read_text('utf-8-sig').replace('\r\n', '\n')
    if not text.startswith('---\n'):
        raise ValueError('Dialogue skill frontmatter missing')
    pieces = text.split('\n---\n', 1)
    if len(pieces) != 2 or 'name: kaltsit-dialogue-output' not in pieces[0]:
        raise ValueError('Unexpected dialogue skill')
    body = pieces[1].strip()
    if not body or len(body) > 4000 or '[TODO' in body:
        raise ValueError('Dialogue skill body is empty, unfinished or oversized')
    return body


def read_coherence_skill(path=None):
    source=Path(path) if path is not None else COHERENCE_PATH
    text=source.read_text('utf-8-sig').replace('\r\n','\n')
    pieces=text.split('\n---\n',1)
    if not text.startswith('---\n') or len(pieces)!=2 or 'name: kaltsit-bubble-coherence' not in pieces[0]:
        raise ValueError('Unexpected coherence skill')
    body=pieces[1].strip()
    if not body or len(body)>2000 or '[TODO' in body:raise ValueError('Invalid coherence skill')
    return body


def build_developer_instructions(persona, path=None, coherence_path=None):
    if not isinstance(persona, str) or not persona.strip():
        raise ValueError('Current persona is required')
    body = read_dialogue_skill(path)
    return (persona + '\n\n【交流选择：先承接当下，再组织表达，服从角色卡】\n'+read_action_skill()
            + '\n\n【发送前表达辅助：服从上面的当前角色卡，不另设人格】\n' + body
            + '\n\n【表达重组后：检查整组气泡承接，仍服从角色卡】\n'+read_coherence_skill(coherence_path))


def dialogue_sha256(path=None):
    return hashlib.sha256(read_dialogue_skill(path).encode('utf-8')).hexdigest()


def coherence_sha256(path=None):
    return hashlib.sha256(read_coherence_skill(path).encode('utf-8')).hexdigest()
