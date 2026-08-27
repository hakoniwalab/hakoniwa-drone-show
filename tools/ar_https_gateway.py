#!/usr/bin/env python3
"""Serve the AR UI over HTTPS and tunnel WSS to the existing WebBridge."""

from __future__ import annotations

import argparse
import select
import socket
import ssl
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer


def relay_streams(client: ssl.SSLSocket, backend: socket.socket) -> None:
    client.settimeout(None)
    backend.settimeout(None)
    sockets = [client, backend]
    try:
        while True:
            readable, _, _ = select.select(sockets, [], [], 1.0)
            if client.pending() and client not in readable:
                readable.append(client)
            for source in readable:
                try:
                    chunk = source.recv(65536)
                except (ConnectionError, ssl.SSLError, OSError):
                    return
                if not chunk:
                    return
                destination = backend if source is client else client
                destination.sendall(chunk)
    finally:
        for stream in sockets:
            try:
                stream.close()
            except OSError:
                pass


class NoCacheRequestHandler(SimpleHTTPRequestHandler):
    websocket_backend_host = "127.0.0.1"
    websocket_backend_port = 8765

    def end_headers(self) -> None:
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate")
        self.send_header("Pragma", "no-cache")
        self.send_header("Expires", "0")
        super().end_headers()

    def do_GET(self) -> None:
        if self.headers.get("Upgrade", "").lower() == "websocket":
            self._proxy_websocket()
            return
        super().do_GET()

    def _proxy_websocket(self) -> None:
        try:
            backend = socket.create_connection(
                (self.websocket_backend_host, self.websocket_backend_port),
                timeout=10,
            )
        except OSError:
            self.send_error(502, "WebBridge is not available")
            return
        # The browser uses /pdu on the public same-origin gateway, while the
        # existing WebBridge accepts its WebSocket handshake at the root path.
        request = [f"{self.command} / {self.request_version}\r\n"]
        request.extend(f"{name}: {value}\r\n" for name, value in self.headers.raw_items())
        request.append("\r\n")
        backend.sendall("".join(request).encode("iso-8859-1"))
        self.close_connection = True
        relay_streams(self.connection, backend)


def relay(client: ssl.SSLSocket, backend_host: str, backend_port: int) -> None:
    backend = socket.create_connection((backend_host, backend_port), timeout=10)
    relay_streams(client, backend)


def run_wss_proxy(
    context: ssl.SSLContext,
    listen_port: int,
    backend_host: str,
    backend_port: int,
) -> None:
    with socket.create_server(("", listen_port), reuse_port=False) as listener:
        while True:
            connection, _address = listener.accept()
            try:
                client = context.wrap_socket(connection, server_side=True)
            except (ssl.SSLError, OSError):
                connection.close()
                continue
            threading.Thread(
                target=relay,
                args=(client, backend_host, backend_port),
                daemon=True,
            ).start()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cert", required=True)
    parser.add_argument("--key", required=True)
    parser.add_argument("--https-port", type=int, default=8443)
    parser.add_argument("--wss-port", type=int, default=8766)
    parser.add_argument("--backend-host", default="127.0.0.1")
    parser.add_argument("--backend-port", type=int, default=8765)
    args = parser.parse_args()

    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    context.load_cert_chain(args.cert, args.key)
    NoCacheRequestHandler.websocket_backend_host = args.backend_host
    NoCacheRequestHandler.websocket_backend_port = args.backend_port
    threading.Thread(
        target=run_wss_proxy,
        args=(
            context,
            args.wss_port,
            args.backend_host,
            args.backend_port,
        ),
        daemon=True,
    ).start()

    server = ThreadingHTTPServer(("", args.https_port), NoCacheRequestHandler)
    server.socket = context.wrap_socket(server.socket, server_side=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
