from __future__ import annotations

import sqlite3
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

USER = "labuser"
PASSWORD = "labpass"


def database() -> sqlite3.Connection:
    connection = sqlite3.connect(":memory:")
    connection.executescript(
        "CREATE TABLE items(id INTEGER PRIMARY KEY, name TEXT);"
        "INSERT INTO items(id,name) VALUES(1,'alpha'),(2,'beta'),(3,'gamma');"
    )
    return connection


class Handler(BaseHTTPRequestHandler):
    server_version = "Hex0rSynthetic/1.0"

    def _reply(self, status: int, body: str) -> None:
        data = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/health":
            self._reply(200, "healthy\n")
            return
        if parsed.path != "/item":
            self._reply(404, "not found\n")
            return
        item_id = parse_qs(parsed.query).get("id", ["1"])[0]
        # Deliberately vulnerable fixture. Input is only reachable inside the disposable CI lab.
        query = f"SELECT name FROM items WHERE id = {item_id}"
        try:
            rows = database().execute(query).fetchall()
            self._reply(200, "|".join(row[0] for row in rows) + "\n")
        except sqlite3.Error as exc:
            self._reply(500, f"sqlite error: {exc}\n")

    def do_POST(self) -> None:
        if self.path != "/login":
            self._reply(404, "not found\n")
            return
        length = int(self.headers.get("Content-Length", "0"))
        values = parse_qs(self.rfile.read(length).decode("utf-8"))
        if values.get("user", [""])[0] == USER and values.get("pass", [""])[0] == PASSWORD:
            # Keep the success control deliberately simple. Hydra uses the absence of the
            # fixed failure marker below as its positive control; redirects introduce
            # unrelated HTTP-follow behaviour into what should be a deterministic fixture.
            self._reply(200, "authenticated labuser\n")
        else:
            self._reply(200, "invalid credentials\n")

    def log_message(self, format: str, *args) -> None:
        return


if __name__ == "__main__":
    ThreadingHTTPServer(("0.0.0.0", 8080), Handler).serve_forever()
