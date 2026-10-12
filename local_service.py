"""Own data directory and explicit OneBot grants; no native QQ reader or LLM."""
import os
from pathlib import Path
import sys
import time
from bot_config import ROOT, load

VENDOR=ROOT/'vendor/Tulpa'
sys.path.insert(0,str(VENDOR))


def environment(config):
    os.environ.update(REPLY_ONEBOT_URL=config['onebot_http_url'],
                      REPLY_ONEBOT_TOKEN=config['onebot_token'],
                      REPLY_ONEBOT_WS_URL=config['onebot_ws_url'],
                      REPLY_ONEBOT_WS_TOKEN=config['onebot_token'])


def create_access(config):
    environment(config)
    from chatlocal.store import Store
    from chatlocal.mcp_access import MCPAccess
    access=MCPAccess(Store())
    access.configure(True,config['mcp_port'])
    return access


def main():
    config=load()
    access=create_access(config)
    from chatlocal.mcp_server import MCPService
    service=MCPService(access);service.start()
    if not service.status()['running']:raise RuntimeError(service.status()['error'])
    try:
        while not (ROOT/'runtime/SERVICE_STOP').exists():time.sleep(.5)
    finally:service.stop()


if __name__=='__main__':main()
