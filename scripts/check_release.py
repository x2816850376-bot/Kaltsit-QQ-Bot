"""Positive release boundaries and credential/path scanning, offline."""
import json
from pathlib import Path
import re
import sys
ROOT=Path(__file__).resolve().parent.parent
FORBIDDEN={'runtime','.venv','private-knowledge','__pycache__','.cache','.tmp','imports','data'}


def findings():
    issues=[]
    for path in ROOT.rglob('*'):
        if not path.is_file():continue
        relative=path.relative_to(ROOT)
        if path.is_symlink():
            issues.append(str(relative)+': 链接文件不可发布');continue
        if any(part in FORBIDDEN for part in relative.parts):
            issues.append(str(relative)+': 运行或私有文件不可发布');continue
        if path.name in ('config.json','auth.json','.env') or path.suffix in ('.log','.jsonl','.pyc','.exe','.dll','.pdf','.jpg','.png'):
            issues.append(str(relative)+': 登录/运行/二进制/扫描素材不可发布');continue
        if path.suffix=='.sqlite3' and relative.as_posix()!='knowledge/terra-journey/index.sqlite3':
            issues.append(str(relative)+': 未列入公开摘要的数据库');continue
        if path.suffix not in ('.py','.md','.txt','.json','.cjs','.ps1','.cmd','.yml','.yaml','.toml'):continue
        text=path.read_text('utf-8-sig',errors='replace')
        for expression,label in [(r'[A-Z]:[/\\]Users[/\\][^\s"\n]+','个人绝对路径'),
                                 (r'(?:sk-[A-Za-z0-9_-]{24,}|eyJ[A-Za-z0-9_-]{30,}\.[A-Za-z0-9_-]+\.)','疑似密钥'),
                                 (r'(?i)(?:bearer|token|password)["\s:=]+[A-Za-z0-9_-]{32,}','疑似固定凭据')]:
            if re.search(expression,text):issues.append(str(relative)+': '+label)
    return issues


if __name__=='__main__':
    issues=findings()
    print(json.dumps({'ok':not issues,'issues':issues},ensure_ascii=False,indent=2))
    sys.exit(bool(issues))
