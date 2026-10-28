import io
import importlib.util
import json
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib import request
import test_admin_console as admin_tests
from app.visitor_traffic import client_ip, traffic_report


class VisitorTests(unittest.TestCase):
    setUp = admin_tests.AdminTests.setUp
    tearDown = admin_tests.AdminTests.tearDown
    make_task = admin_tests.AdminTests.make_task
    call = admin_tests.AdminTests.call
    def test_anonymous_visit_uses_server_ip_and_admin_access(self):
        status,_=self.call('/v1/visits',{'page':'register','ip':'8.8.8.8','country':'fabricated'},user=False)
        self.assertEqual(status,201)
        event=self.app.usage.rows()[0]
        self.assertEqual(event['network']['ip'],'127.0.0.1')
        self.assertNotEqual(event['network'].get('country'),'fabricated')
        self.assertEqual(self.call('/v1/admin/traffic',user=self.owner)[0],403)
        self.assertEqual(self.call('/v1/admin/traffic',user=False)[0],401)
        status,result=self.call('/v1/admin/traffic')
        self.assertEqual(status,200)
        self.assertEqual(result['summary']['pageViews'],1)
        self.assertEqual(result['summary']['anonymousViews'],1)
        self.assertEqual(result['summary']['uniqueIps'],1)
        self.assertEqual(self.call('/v1/admin/overview')[1]['summary']['activeUsers'],1)
        self.assertEqual(self.call('/v1/visits',{'page':'../../private'},user=False)[0],400)

    def test_trusted_proxy_and_network_classification(self):
        self.assertEqual(client_ip('10.0.0.1',{'X-Real-IP':'8.8.8.8'}),'10.0.0.1')
        self.assertEqual(client_ip('127.0.0.1',{'X-Real-IP':'10.70.1.2'}),'10.70.1.2')
        self.assertEqual(client_ip('127.0.0.1',{'X-Real-IP':'8.8.8.8, 1.1.1.1'}),'127.0.0.1')
        private=self.app.ip_locator.describe('10.70.1.2')
        self.assertEqual(private['scope'],'private');self.assertFalse(private['city'])
        self.assertEqual(self.app.ip_locator.describe('invalid')['scope'],'unknown')


class ProxyTests(unittest.TestCase):
    def test_campus_proxy_overwrites_spoofed_forwarding_headers(self):
        path=Path(__file__).resolve().parents[3]/'deploy/campus/frontend_proxy.py'
        module_spec=importlib.util.spec_from_file_location('campus_proxy_test',path);module=importlib.util.module_from_spec(module_spec);module_spec.loader.exec_module(module)
        class Echo(BaseHTTPRequestHandler):
            def log_message(self,*args): pass
            def do_POST(self):
                data=json.dumps({'ip':self.headers.get('X-Real-IP'),'forwarded':self.headers.get('X-Forwarded-For'),'body':self.rfile.read(int(self.headers['Content-Length'])).decode()}).encode()
                self.send_response(200);self.send_header('Content-Length',str(len(data)));self.send_header('Content-Type','application/json');self.end_headers();self.wfile.write(data)
        backend=ThreadingHTTPServer(('127.0.0.1',0),Echo);module.BACKEND_PORT=backend.server_port
        proxy=ThreadingHTTPServer(('127.0.0.1',0),module.Handler)
        threads=[threading.Thread(target=s.serve_forever,daemon=True) for s in [backend,proxy]]
        for t in threads:t.start()
        try:
            req=request.Request('http://127.0.0.1:'+str(proxy.server_port)+'/v1/visits',data=b'{"page":"home"}',headers={'Content-Type':'application/json','X-Real-IP':'8.8.8.8','X-Forwarded-For':'1.1.1.1'})
            with request.urlopen(req,timeout=5) as response:value=json.load(response)
            self.assertEqual(value['ip'],'127.0.0.1');self.assertIsNone(value['forwarded']);self.assertEqual(json.loads(value['body']),{'page':'home'})
        finally:
            for server in [proxy,backend]:server.shutdown();server.server_close()
            for thread in threads:thread.join()


if __name__=='__main__':unittest.main()
