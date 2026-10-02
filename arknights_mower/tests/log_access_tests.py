"""Local log reads stay available without a configured Web UI token."""

import json
import unittest
from threading import Thread
from unittest.mock import patch

from simple_websocket import Client
from werkzeug.serving import make_server
from werkzeug.test import EnvironBuilder

import server
from arknights_mower.utils.log_stream import LogStream


class FakeSocket:
    def __init__(self):
        self.closed = False
        self.received = False

    def receive(self, timeout=None):
        self.received = True
        return None

    def close(self, reason=None, message=None):
        self.closed = True


class TrustedProxyOriginTests(unittest.TestCase):
    """X-Forwarded-* only affects origin comparison when the operator opts in."""

    HOST = "xxx.work:55007"
    BROWSER_ORIGIN = "https://xxx.work:55007"

    def _context(self, headers):
        return server.app.test_request_context(
            "/log", headers={"Host": self.HOST, **headers}
        )

    def test_same_origin_allowed_compares_scheme_and_netloc(self):
        with self._context({}):
            self.assertTrue(server.same_origin_allowed("http://xxx.work:55007"))
            self.assertTrue(server.same_origin_allowed(None))
            self.assertFalse(server.same_origin_allowed(self.BROWSER_ORIGIN))
            self.assertFalse(server.same_origin_allowed("https://attacker.example"))

    def test_tls_terminating_proxy_origin_is_rejected_until_opted_in(self):
        # 未声明可信代理：TLS 在代理终止时后端 scheme 仍是 http，来源不匹配。
        with self._context({"X-Forwarded-Proto": "https"}):
            self.assertFalse(server.same_origin_allowed(self.BROWSER_ORIGIN))

    def test_apply_trusted_proxy_reconstructs_forwarded_scheme(self):
        # 声明 MOWER_TRUSTED_PROXY=1 后，来源比较看到的 scheme 与浏览器一致。
        for declared, expected_origin_allowed in (("1", True), ("", False), ("0", False)):
            with self.subTest(declared=declared):
                declared_app = server.app
                original_wsgi_app = declared_app.wsgi_app
                try:
                    server.apply_trusted_proxy(
                        declared_app, environ={"MOWER_TRUSTED_PROXY": declared}
                    )
                    environ = EnvironBuilder(
                        path="/log",
                        base_url=f"http://{self.HOST}",
                        headers={
                            "Host": self.HOST,
                            "Origin": self.BROWSER_ORIGIN,
                            "X-Forwarded-Proto": "https",
                        },
                    ).get_environ()
                    declared_app.wsgi_app(environ, lambda *_: None)
                    with server.app.test_request_context(
                        "/log", environ_overrides=environ
                    ):
                        self.assertIs(
                            server.same_origin_allowed(self.BROWSER_ORIGIN),
                            expected_origin_allowed,
                        )
                finally:
                    declared_app.wsgi_app = original_wsgi_app

    def test_untrusted_forwarded_headers_cannot_spoof_origin(self):
        # 未声明可信代理时，伪造 X-Forwarded-Host/Proto 不得放宽来源边界。
        headers = {
            "X-Forwarded-Host": "attacker.example",
            "X-Forwarded-Proto": "https",
        }
        with self._context(headers):
            self.assertTrue(server.same_origin_allowed("http://xxx.work:55007"))
            self.assertFalse(server.same_origin_allowed("https://attacker.example"))


class LocalLogAccessTests(unittest.TestCase):
    def setUp(self):
        self.old_token = getattr(server.app, "token", None)
        self.old_local_mode = server.app.config["WEBVIEW_LOCAL_ONLY_NO_TOKEN"]
        server.app.token = "runtime-secret"
        server.app.config["WEBVIEW_LOCAL_ONLY_NO_TOKEN"] = True

    def tearDown(self):
        if self.old_token is None:
            del server.app.token
        else:
            server.app.token = self.old_token
        server.app.config["WEBVIEW_LOCAL_ONLY_NO_TOKEN"] = self.old_local_mode

    def context(
        self,
        *,
        origin="http://127.0.0.1:58000",
        host="127.0.0.1:58000",
        remote="127.0.0.1",
        fetch_site="same-origin",
    ):
        headers = {"Host": host, "Sec-Fetch-Site": fetch_site}
        if origin is not None:
            headers["Origin"] = origin
        return server.app.test_request_context(
            "/log", headers=headers, environ_base={"REMOTE_ADDR": remote}
        )

    def test_local_log_socket_without_token_does_not_open_ai_socket(self):
        with self.context():
            log_socket = FakeSocket()
            self.assertTrue(
                server._authorize_websocket(log_socket, allow_local_log=True)
            )
            self.assertFalse(log_socket.received)
            ai_socket = FakeSocket()
            self.assertFalse(server._authorize_websocket(ai_socket))
            self.assertTrue(ai_socket.closed)

    def test_local_log_socket_rejects_cross_origin_and_nonlocal_requests(self):
        cases = (
            {"origin": "https://attacker.example"},
            {"origin": None},
            {"host": "attacker.example"},
            {"remote": "192.0.2.1"},
            {"fetch_site": "cross-site"},
        )
        for kwargs in cases:
            with self.subTest(kwargs=kwargs), self.context(**kwargs):
                socket = FakeSocket()
                self.assertFalse(
                    server._authorize_websocket(socket, allow_local_log=True)
                )
                self.assertTrue(socket.closed)

    def test_configured_token_disables_local_exemption(self):
        server.app.config["WEBVIEW_LOCAL_ONLY_NO_TOKEN"] = False
        with self.context():
            socket = FakeSocket()
            self.assertFalse(server._authorize_websocket(socket, allow_local_log=True))
            self.assertTrue(socket.closed)

    def test_local_log_socket_streams_without_token_frame(self):
        stream = LogStream()
        stream.publish("local-log-fixture")
        # 仅绑定请求的日志流，后台日志消费者继续使用原流。
        with patch.object(server.log_stream, "serve", stream.serve):
            service = make_server("127.0.0.1", 0, server.app, threaded=True)
            thread = Thread(target=service.serve_forever, daemon=True)
            thread.start()
            try:
                connection = Client.connect(
                    f"ws://127.0.0.1:{service.server_port}/log",
                    headers={"Origin": "http://127.0.0.1"},
                    # 按字节接收，避免客户端把同批首帧留在握手解析器中。
                    receive_bytes=1,
                )
                try:
                    payload = json.loads(connection.receive(timeout=2))
                    self.assertEqual(
                        payload, {"type": "log", "data": "local-log-fixture"}
                    )
                finally:
                    connection.close()
            finally:
                service.shutdown()
                service.server_close()
                thread.join(3)
                self.assertFalse(thread.is_alive())

    def test_log_read_routes_allow_local_window_and_reject_cross_site(self):
        with patch.object(server, "error_events", return_value=[]):
            client = server.app.test_client()
            for origin, remote, fetch_site, expected_status in (
                ("http://127.0.0.1:58000", "127.0.0.1", "same-origin", 200),
                (None, "127.0.0.1", "same-origin", 200),
                ("https://attacker.example", "127.0.0.1", "cross-site", 403),
                ("http://127.0.0.1:58000", "192.0.2.1", "same-origin", 403),
            ):
                with self.subTest(origin=origin, remote=remote):
                    headers = {
                        "Host": "127.0.0.1:58000",
                        "Sec-Fetch-Site": fetch_site,
                    }
                    if origin is not None:
                        headers["Origin"] = origin
                    response = client.get(
                        "/diagnostics/errors",
                        headers=headers,
                        environ_base={"REMOTE_ADDR": remote},
                    )
                    self.assertEqual(response.status_code, expected_status)
                    if expected_status == 200:
                        self.assertEqual(json.loads(response.data), {"events": []})

            self.assertEqual(client.get("/conf").status_code, 403)
            self.assertEqual(client.delete("/diagnostics/errors/123").status_code, 403)

            server.app.config["WEBVIEW_LOCAL_ONLY_NO_TOKEN"] = False
            response = client.get(
                "/diagnostics/errors", headers={"Host": "127.0.0.1:58000"}
            )
            self.assertEqual(response.status_code, 403)
            response = client.get(
                "/diagnostics/errors",
                headers={"Host": "127.0.0.1:58000", "token": "runtime-secret"},
            )
            self.assertEqual(response.status_code, 200)


if __name__ == "__main__":
    unittest.main()
