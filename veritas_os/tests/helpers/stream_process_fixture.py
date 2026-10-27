"""Test-only Uvicorn child; stdin controls fixtures, never an HTTP management API.

This intentionally supplies synthetic post-startup readiness. It is not a
production launcher or proof of security startup dependencies.
"""

import json
import os
import socket
import subprocess
import sys
import threading
import time

import uvicorn


KEY = "real-stream-synthetic-test"
REPLACEMENT = "real-stream-replacement-test"
PREFIX = "STREAM_FIXTURE "


def main() -> None:
    """Serve loopback requests and accept bounded synthetic controls on stdin."""
    os.environ["VERITAS_ENV"] = "production"
    os.environ["VERITAS_API_KEY"] = KEY
    os.environ.pop("VERITAS_POSTURE", None)
    os.environ.pop("VERITAS_API_KEYS", None)
    from veritas_os.api import server
    from veritas_os.api.sse_hub import SSEEventHub

    hub = SSEEventHub(timestamp_factory=lambda: "test", max_subscribers=2)
    server._event_hub = hub
    server.app.state.security_startup_complete = True
    server.app.state.security_startup_pid = os.getpid()
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen(16)
    port = listener.getsockname()[1]
    instance = uvicorn.Server(uvicorn.Config(
        server.app, host="127.0.0.1", port=port, lifespan="off", ws="websockets",
        log_level="critical", access_log=False, timeout_graceful_shutdown=2,
    ))
    sha = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()

    def reply(message: dict) -> None:
        sys.stdout.write(PREFIX + json.dumps(message) + "\n")
        sys.stdout.flush()

    def control() -> None:
        while not instance.started:
            if instance.should_exit:
                return
            time.sleep(0.01)
        reply({"id": 0, "ready": True, "pid": os.getpid(), "port": port, "tested_sha": sha})
        try:
            while True:
                line = sys.stdin.buffer.readline(4097)
                if not line:
                    break
                if len(line) > 4096:
                    raise ValueError("oversized fixture control")
                message = json.loads(line)
                action = message["action"]
                result = {"id": message["id"], "pid": os.getpid()}
                if action == "status":
                    with hub._lock:
                        result["subscribers"] = len(hub._subscribers)
                elif action == "publish":
                    label = message["label"]
                    if label not in {"before-disconnect", "before-rotation", "after-rotation"}:
                        raise ValueError("unknown synthetic event")
                    result["event"] = hub.publish("trustlog.appended", {"test": label})
                elif action == "rotate":
                    os.environ["VERITAS_API_KEY"] = REPLACEMENT
                elif action == "unready":
                    server.app.state.security_startup_complete = False
                elif action == "shutdown":
                    instance.should_exit = True
                else:
                    raise ValueError("unknown fixture control")
                reply(result)
                if action == "shutdown":
                    break
        finally:
            instance.should_exit = True

    threading.Thread(target=control, daemon=True).start()
    try:
        instance.run(sockets=[listener])
    finally:
        listener.close()
    with hub._lock:
        if hub._subscribers:
            raise RuntimeError("subscriptions survived child shutdown")


if __name__ == "__main__":
    main()
