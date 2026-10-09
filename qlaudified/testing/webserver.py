"""A local web server for saved pages, so web tests and the eval never need the internet.

    py -3 -m qlaudified.testing.webserver tests/fixtures/web [--port 8765]

Serves the folder's files, plus ``/paywall`` (403), ``/slow`` (sleeps past the re-fetch timeout)
and ``/notes.txt``-style plain text as is.
"""

import argparse
import http.server
import threading
import time
from functools import partial
from pathlib import Path


class _Handler(http.server.SimpleHTTPRequestHandler):
    slow_s = 12.0

    def do_GET(self) -> None:
        if self.path.startswith("/paywall"):
            self.send_error(403, "Subscribe to continue reading")
            return
        if self.path.startswith("/slow"):
            time.sleep(self.slow_s)
        super().do_GET()

    def log_message(self, format: str, *args) -> None:
        pass


def serve(folder: Path, port: int = 0) -> tuple[http.server.ThreadingHTTPServer, str]:
    """Start serving in a background thread; returns the server and its base URL."""
    handler = partial(_Handler, directory=str(folder))
    server = http.server.ThreadingHTTPServer(("127.0.0.1", port), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, f"http://127.0.0.1:{server.server_address[1]}"


def main() -> None:
    parser = argparse.ArgumentParser(prog="qlaudified-webserver")
    parser.add_argument("folder")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    server, url = serve(Path(args.folder), args.port)
    print(f"serving {args.folder} at {url} (Ctrl+C to stop)")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        server.shutdown()


if __name__ == "__main__":
    main()
