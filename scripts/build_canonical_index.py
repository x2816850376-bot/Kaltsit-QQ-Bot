"""Index the bundled user-supplied original texts, without any chat data."""
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import sys

ROOT = Path(__file__).resolve().parent.parent
CORPUS = ROOT / 'knowledge/kaltsit-corpus'


def tokens(text):
    result = []
    for run in re.findall(r'[\u3400-\u9fff]+|[a-zA-Z0-9]+', text.lower()):
        result.extend(run[i:i+2] for i in range(len(run)-1)) if re.search(r'[\u3400-\u9fff]', run) else result.append(run)
    return ' '.join(result)


def main():
    if (ROOT / 'runtime/owner.json').exists():
        raise ValueError('请先停止此副本的机器人，再重建语料索引')
    manifest = json.loads((CORPUS/'sources.json').read_text('utf-8'))
    entries = []
    for source in manifest['sources']:
        name = source['file']
        if Path(name).name != name or not name.endswith('.txt'):
            raise ValueError('无效的固定语料文件名')
        body = (CORPUS/'originals'/name).read_bytes()
        if hashlib.sha256(body).hexdigest() != source['sha256']:
            raise ValueError('原件哈希不一致：'+name)
        text = body.decode('utf-8-sig')
        for start in range(0, len(text), 720):
            piece = text[start:start+900]
            if not piece.strip():
                continue
            entries.append((name, source['kind'], source['stage'], 'multi-speaker_or_source-labels', '',
                            piece, start, min(start+900, len(text)), 'user_supplied_transcript'))
    voices = json.loads((CORPUS/'voice-lines.json').read_text('utf-8'))
    for row in voices['entries']:
        entries.append((row['file'], 'voice', row['stage'], '凯尔希', row['scene'], row['text'],
                        None, None, 'web_text_matched' if row.get('web_text_match') else 'user_supplied_transcript'))
    destination = CORPUS/'index.sqlite3'
    temporary = CORPUS/'index.sqlite3.new'
    if temporary.exists():
        raise ValueError('已有未完成的索引，未覆盖')
    with sqlite3.connect(temporary) as db:
        db.execute('CREATE TABLE passages(id INTEGER PRIMARY KEY, file TEXT, kind TEXT, stage TEXT, speaker TEXT, scene TEXT, text TEXT, start_char INTEGER, end_char INTEGER, verification TEXT)')
        db.execute('CREATE VIRTUAL TABLE search USING fts5(tokens,content="",tokenize="unicode61")')
        for row in entries:
            cursor = db.execute('INSERT INTO passages(file,kind,stage,speaker,scene,text,start_char,end_char,verification) VALUES(?,?,?,?,?,?,?,?,?)', row)
            db.execute('INSERT INTO search(rowid,tokens) VALUES(?,?)', (cursor.lastrowid, tokens(row[5])))
        if db.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
            raise ValueError('索引完整性检查失败')
    db.close()
    temporary.replace(destination)
    result = {'schema_version':1, 'edition':'full-user-supplied-text', 'source_files':len(manifest['sources']),
              'original_characters':sum(row['characters'] for row in manifest['sources']),
              'indexed_passages':len(entries), 'structured_voice_entries':len(voices['entries']),
              'index_sha256':hashlib.sha256(destination.read_bytes()).hexdigest(), 'group_memory_included':False,
              'verification':'原件保留完整字节与哈希。结构化语音有独立时期标记；剧情分块保留全部说话人标签，不把全部对白归给凯尔希。部分剧情场景时间未知，不凭文件名猜测。'}
    (CORPUS/'manifest.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), 'utf-8')
    print(json.dumps(result, ensure_ascii=False))


if __name__ == '__main__':
    main()
