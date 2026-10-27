"""Start only this installation's local persona test and open its browser page."""
import ctypes
import json
import msvcrt
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
from urllib.request import ProxyHandler, build_opener

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

def record(message):
    directory = ROOT / 'runtime'
    directory.mkdir(exist_ok=True)
    with (directory / 'test-window-launch.log').open('a', encoding='utf-8') as log:
        log.write(time.strftime('%Y-%m-%d %H:%M:%S ') + message + '\n')


def main():
    record('Launcher entered')
    from bot_config import load
    port = load()['test_port']
    url = f'http://127.0.0.1:{port}/'
    runtime = ROOT / 'runtime'
    runtime.mkdir(exist_ok=True)
    opener = build_opener(ProxyHandler({}))

    def healthy():
        try:
            with opener.open(url + 'health', timeout=4) as response:
                return json.load(response).get('name') == 'kaltsit-dialogue-test'
        except Exception:
            return False

    with (runtime / 'test-window-launch.lock').open('a+b') as lock:
        lock.seek(0)
        if not lock.read(1):
            lock.write(b'0')
            lock.flush()
        deadline = time.monotonic() + 20
        while True:
            lock.seek(0)
            try:
                msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
                break
            except OSError:
                if time.monotonic() >= deadline:
                    raise RuntimeError('测试窗口正在启动，请稍后再次打开')
                time.sleep(.2)
        try:
            if not healthy():
                record('Starting test service')
                with socket.socket() as sock:
                    if sock.connect_ex(('127.0.0.1', port)) == 0:
                        raise RuntimeError(f'端口{port}已被其他服务占用，未停止其他程序')
                env = dict(os.environ, PYTHONUTF8='1', PYTHONIOENCODING='utf-8')
                with (runtime / 'test-window.stdout.log').open('ab') as out, (runtime / 'test-window.stderr.log').open('ab') as err:
                    child = subprocess.Popen(
                        [sys.executable, str(ROOT / 'dialogue-test-window/server.py')],
                        cwd=str(ROOT), env=env, stdout=out, stderr=err,
                        shell=False, creationflags=subprocess.CREATE_NO_WINDOW)
                deadline = time.monotonic() + 20
                while not healthy():
                    if child.poll() is not None:
                        raise RuntimeError('测试服务启动失败，请查看 runtime/test-window.stderr.log')
                    if time.monotonic() >= deadline:
                        raise RuntimeError('测试服务启动超时，请查看 runtime/test-window.stderr.log')
                    time.sleep(.2)
                (runtime / 'test-window.pid').write_text(str(child.pid), encoding='utf-8')
            record('Test service healthy on port ' + str(port))
        finally:
            lock.seek(0)
            msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)
    edge = Path(os.environ.get('ProgramFiles(x86)', r'C:\Program Files (x86)')) / 'Microsoft/Edge/Application/msedge.exe'
    if edge.is_file():
        child = subprocess.Popen([str(edge), '--new-window', url], shell=False,
                                 creationflags=subprocess.CREATE_NO_WINDOW)
        record('Browser launch requested, pid ' + str(child.pid))
    else:
        import webbrowser
        webbrowser.open(url)


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        record(type(exc).__name__ + ': ' + str(exc))
        ctypes.windll.user32.MessageBoxW(None, str(exc), '凯尔希对话测试', 0x10)
