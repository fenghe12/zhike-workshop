"""Serve the campus frontend and preserve the TCP peer address for the backend."""
import argparse
import http.client
import os
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = str(Path(__file__).resolve().parents[2]/'software/frontend-web')
BACKEND_PORT = 18774
ADAPTER_PORT = 18772


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=ROOT, **kwargs)

    def proxy(self):
        path = self.path.split('?', 1)[0]
        connection = http.client.HTTPConnection('127.0.0.1', ADAPTER_PORT if path.startswith('/api') else BACKEND_PORT, timeout=900)
        omit = {'host','connection','proxy-connection','transfer-encoding','keep-alive','upgrade','x-real-ip','x-forwarded-for','forwarded'}
        try:
            connection.putrequest(self.command, self.path, skip_accept_encoding=True)
            for key, value in self.headers.items():
                if key.lower() not in omit: connection.putheader(key, value)
            connection.putheader('X-Real-IP', self.client_address[0])
            connection.putheader('Connection', 'close')
            connection.endheaders()
            remaining = int(self.headers.get('Content-Length', '0'))
            while remaining:
                part = self.rfile.read(min(65536, remaining))
                if not part: break
                connection.send(part);remaining -= len(part)
            response = connection.getresponse();self.send_response(response.status)
            for key, value in response.getheaders():
                if key.lower() not in omit and key.lower() not in {'server','date'}: self.send_header(key, value)
            if response.getheader('Content-Length') is None:
                self.send_header('Connection', 'close');self.close_connection = True
            self.end_headers()
            if self.command != 'HEAD':
                while True:
                    data = response.read(65536)
                    if not data: break
                    self.wfile.write(data)
        except (BrokenPipeError, ConnectionResetError): pass
        except Exception:
            try: self.send_error(502, 'Service unavailable')
            except (BrokenPipeError, ConnectionResetError): pass
        finally: connection.close()

    def do_GET(self):
        if self.path.startswith(('/v1/','/api/','/artifacts/')): self.proxy()
        else: super().do_GET()

    def do_HEAD(self):
        if self.path.startswith(('/v1/','/api/','/artifacts/')): self.proxy()
        else: super().do_HEAD()

    def do_POST(self): self.proxy()
    def do_PUT(self): self.proxy()
    def do_DELETE(self): self.proxy()
    def do_PATCH(self): self.proxy()


def main():
    global ROOT, BACKEND_PORT, ADAPTER_PORT
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', required=True)
    parser.add_argument('--host', default='127.0.0.1')
    parser.add_argument('--port', type=int, default=18770)
    parser.add_argument('--backend-port', type=int, default=18774)
    parser.add_argument('--adapter-port', type=int, default=18772)
    args = parser.parse_args()
    root = Path(args.root).resolve()
    if not root.is_dir(): raise SystemExit('Frontend directory does not exist')
    ROOT, BACKEND_PORT, ADAPTER_PORT = str(root), args.backend_port, args.adapter_port
    ThreadingHTTPServer((args.host,args.port),Handler).serve_forever()


if __name__ == '__main__': main()
