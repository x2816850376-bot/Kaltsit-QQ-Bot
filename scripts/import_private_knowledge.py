"""Import a user-owned compatible text index, without shipping it in source."""
import argparse
import json
from pathlib import Path
import shutil
import sqlite3
import sys
import tempfile
ROOT=Path(__file__).resolve().parent.parent


def main():
    parser=argparse.ArgumentParser();parser.add_argument('source',type=Path);args=parser.parse_args()
    if (ROOT/'runtime/owner.json').exists():raise ValueError('请先停止机器人，再导入知识库')
    required=['index.sqlite3','topic-catalog.json','verified-anchors.json','story-events.json']
    for name in required:
        if not (args.source/name).is_file():raise ValueError('缺少 '+name)
    with sqlite3.connect((args.source/'index.sqlite3').resolve().as_uri()+'?mode=ro',uri=True) as db:
        if db.execute('PRAGMA quick_check').fetchone()[0]!='ok':raise ValueError('索引完整性检查失败')
        tables={r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if not {'pages','search'}<=tables:raise ValueError('不是兼容的全文索引')
        if not {'page','text','verification','scope','speaker'}<={r[1] for r in db.execute('PRAGMA table_info(pages)')}:raise ValueError('索引缺少时期/核验等必要字段')
    for name in required[1:]:json.loads((args.source/name).read_text('utf-8'))
    parent=ROOT/'private-knowledge';parent.mkdir(exist_ok=True)
    target=parent/'terra-journey'
    if target.exists():raise ValueError('已有本地扩展，未覆盖；请先自行备份并移出旧目录')
    with tempfile.TemporaryDirectory(dir=parent,prefix='import-') as temp:
        stage=Path(temp)/'terra-journey';stage.mkdir()
        # SQLite backup includes a source WAL consistently; never copy a live DB alone.
        with sqlite3.connect((args.source/'index.sqlite3').resolve().as_uri()+'?mode=ro',uri=True) as src,sqlite3.connect(stage/'index.sqlite3') as dst:src.backup(dst)
        for name in required[1:]+['manifest.json']:
            if (args.source/name).exists():shutil.copy2(args.source/name,stage/name)
        stage.replace(target)
    print('已导入使用者自己的本地知识库；下次启动QQ和测试窗口会优先使用，不进入GitHub发布包')


if __name__=='__main__':
    try:main()
    except Exception as exc:print('导入未完成：'+str(exc));sys.exit(1)
