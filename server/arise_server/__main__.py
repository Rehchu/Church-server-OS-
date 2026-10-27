"""`python -m arise_server [--config PATH] [--demo] [--port N]` starts the web service."""
import argparse
import os

import uvicorn


def main():
    ap = argparse.ArgumentParser(prog="arise_server", description="Arise Server web service")
    ap.add_argument("--config", default=os.environ.get("ARISE_CONFIG", "/etc/arise/arise.toml"))
    ap.add_argument("--demo", action="store_true", help="serve sample data (no samba/docker/restic needed)")
    ap.add_argument("--host", default=None)
    ap.add_argument("--port", type=int, default=None)
    ap.add_argument("--reload", action="store_true")
    a = ap.parse_args()

    os.environ["ARISE_CONFIG"] = a.config
    if a.demo:
        os.environ["ARISE_DEMO"] = "1"

    from arise_server.config import load
    cfg = load()
    host = a.host or cfg.web.bind
    port = a.port or cfg.web.port
    uvicorn.run("arise_server.main:app", host=host, port=port, reload=a.reload, log_level="info")


if __name__ == "__main__":
    main()
