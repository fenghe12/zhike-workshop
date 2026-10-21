import importlib.util
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.request import Request, urlopen


class MediaProxyTests(unittest.TestCase):
    def test_byte_range_and_partial_payload_are_preserved(self):
        module_path = Path(__file__).resolve().parents[3] / "web" / "serve.py"
        spec = importlib.util.spec_from_file_location("acceptance_media_proxy", module_path)
        proxy = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(proxy)
        payload = b"0123456789abcdef"
        received = []
        class Upstream(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass
            def do_GET(self):
                received.append(self.headers.get("Range"))
                self.send_response(206)
                self.send_header("Content-Type", "video/mp4")
                self.send_header("Content-Range", "bytes 5-11/16")
                self.send_header("Content-Length", "7")
                self.send_header("Accept-Ranges", "bytes")
                self.end_headers()
                self.wfile.write(payload[5:12])
        upstream = ThreadingHTTPServer(("127.0.0.1", 0), Upstream)
        proxy.config = lambda: {"base_url": f"http://127.0.0.1:{upstream.server_port}"}
        downstream = ThreadingHTTPServer(("127.0.0.1", 0), proxy.Handler)
        threads = [threading.Thread(target=server.serve_forever, daemon=True) for server in [upstream, downstream]]
        for thread in threads:
            thread.start()
        try:
            request = Request(f"http://127.0.0.1:{downstream.server_port}/artifacts/video.mp4", headers={"Range": "bytes=5-11"})
            with urlopen(request, timeout=5) as response:
                self.assertEqual(response.status, 206)
                self.assertEqual(response.headers["Content-Range"], "bytes 5-11/16")
                self.assertEqual(response.read(), payload[5:12])
            self.assertEqual(received, ["bytes=5-11"])
        finally:
            for server in [downstream, upstream]:
                server.shutdown()
                server.server_close()
            for thread in threads:
                thread.join(timeout=2)
