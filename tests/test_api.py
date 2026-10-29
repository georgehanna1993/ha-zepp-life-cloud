"""Offline protocol regression tests; no live credentials or network."""
import asyncio
import importlib.util
import json
from pathlib import Path
from urllib.parse import parse_qs, urlsplit
import unittest

FILE = Path(__file__).resolve().parents[1] / "custom_components/zepp_life_cloud/api.py"
spec = importlib.util.spec_from_file_location("zepp_api", FILE)
api = importlib.util.module_from_spec(spec)
spec.loader.exec_module(api)

class Response:
    def __init__(self, body=None, status=200, redirect=""):
        self.body = json.dumps(body) if not isinstance(body, str) else body
        self.status = status
        self.headers = {"Location": redirect}
    async def __aenter__(self):
        return self
    async def __aexit__(self, *args):
        pass
    async def text(self):
        return self.body

class Session:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls = []
    def request(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        if not self.responses:
            raise AssertionError("Unexpected request: " + url)
        return self.responses.pop(0)

def record(ts=100, weight=86.5, **fields):
    return {"generatedTime": ts, "weightType": 0,
            "summary": {"weight": weight, "fatRate": 21, **fields}}

def token(uid="123"):
    return Response({"token_info": {"app_token": "secret", "user_id": uid}})
def callback():
    return api.CALLBACK + "?extra=ignored&code=auth%2Bcode"
def password_session(*last):
    return Session(
        Response({"data": {"oauthLoginUrl": "https://account.xiaomi.com/login"}}),
        Response({"_sign": "sign", "sid": "sid", "callback": "callback", "qs": "qs"}),
        Response({"location": "https://account.xiaomi.com/sts", "passToken": "V1:new", "userId": "456"}),
        Response({}, redirect=callback()), token(), *last)

class ParsingTests(unittest.TestCase):
    def test_xiaomi_prefix(self):
        self.assertEqual(api.decode_json('&&&START&&&{"code":0}', "test"), {"code":0})
    def test_bad_json_sanitized(self):
        with self.assertRaises(api.CloudError) as ctx:
            api.decode_json("<html>SECRET</html>", "test")
        self.assertNotIn("SECRET", str(ctx.exception))
    def test_bad_shape(self):
        with self.assertRaises(api.CloudError):
            api.decode_json("[]", "test")
    def test_latest_filters_deleted_bad_weight_and_order(self):
        deleted = record(900); deleted["weightType"] = 1
        self.assertEqual(api.latest_record([record(100), record(200), deleted, record(300, 0), record(400, float("nan")), {}])["generatedTime"], 200)
    def test_string_summary(self):
        item = record(); item["summary"] = json.dumps(item["summary"])
        self.assertEqual(api.latest_record([item])["summary"]["weight"], 86.5)
    def test_no_data(self):
        self.assertIsNone(api.latest_record([]))
    def test_urls_reject_credentials_http_and_external(self):
        for url in ("http://account.xiaomi.com/", "https://evil.example/", "https://user:secret@account.xiaomi.com/", "https://account.xiaomi.com:444/"):
            with self.subTest(url=url), self.assertRaises(api.CloudError):
                api.trusted_url(url)
    def test_auth_error_does_not_echo_server_message(self):
        err = api.AuthError("password", {"code":70016, "description":"secret", "notificationUrl":"https://account.xiaomi.com/verify?token=secret"})
        self.assertNotIn("secret", str(err))
        self.assertTrue(err.verification)

class ProtocolTests(unittest.IsolatedAsyncioTestCase):
    async def test_browser_authorization_url_uses_xiaomi_login_page(self):
        session = Session()
        client = api.ZeppClient(session, {"method": "browser"})
        url = await client.authorization_url()
        parsed = urlsplit(url)
        self.assertEqual(parsed.hostname, "account.xiaomi.com")
        self.assertEqual(parse_qs(parsed.query)["_json"], ["false"])
        self.assertEqual(parse_qs(parsed.query)["redirect_uri"], [api.CALLBACK])
        self.assertEqual(session.calls, [])

    async def test_password_oauth_success_and_fields(self):
        session = password_session(Response({"items":[record()], "next":0}))
        client = api.ZeppClient(session, {"method":"password","username":"test","password":"pw"})
        result = await client.latest()
        self.assertEqual(result["summary"]["fatRate"], 21)
        self.assertEqual(client.user_id,"123")
        self.assertEqual(client.export_credentials()["passToken"],"V1:new")
        self.assertEqual(session.calls[4][2]["data"]["code"],"auth+code")
        self.assertNotIn("pw", session.calls[2][2]["data"]["hash"])
    async def test_password_verification_not_empty_url(self):
        session = Session(Response({"data":{"oauthLoginUrl":"https://account.xiaomi.com/login"}}),
                          Response({"_sign":"s"}),
                          Response({"code":70016,"notificationUrl":"https://account.xiaomi.com/verify"}))
        client = api.ZeppClient(session, {"username":"u","password":"p"})
        with self.assertRaises(api.AuthError) as ctx:
            await client.login()
        self.assertEqual(ctx.exception.stage,"xiaomi_password")
        self.assertTrue(ctx.exception.verification)
        self.assertTrue(all(call[1] for call in session.calls))
    async def test_missing_oauth_url_reports_exact_stage(self):
        client = api.ZeppClient(Session(Response({"code":123})), {"username":"u","password":"p"})
        with self.assertRaises(api.AuthError) as ctx:
            await client.login()
        self.assertEqual(ctx.exception.stage,"oauth_authorize")
    async def test_session_route_without_password(self):
        session = Session(Response({"location":"https://account.xiaomi.com/sts"}),
                          Response({},redirect=callback()), token(),
                          Response({"items":[record()]}))
        client = api.ZeppClient(session, {"method":"session","userId":"456","passToken":"V1:existing"})
        await client.latest()
        self.assertIn("passToken=V1:existing", session.calls[0][2]["headers"]["Cookie"])
        self.assertFalse(any("serviceLoginAuth2" in call[1] for call in session.calls))
    async def test_expired_session_is_clear(self):
        session = Session(Response({"data":{"oauthLoginUrl":"https://account.xiaomi.com/login"}}),Response({"_sign":"s"}))
        with self.assertRaises(api.AuthError) as ctx:
            await api.ZeppClient(session, {"method":"session","userId":"456","passToken":"expired"}).login()
        self.assertEqual(ctx.exception.stage,"xiaomi_session")
    async def test_cached_zepp_token_avoids_login(self):
        session = Session(Response({"items":[record()]}))
        await api.ZeppClient(session, {"zepp_user_id":"123","app_token":"cached"}).latest()
        self.assertEqual(len(session.calls),1)
        self.assertEqual(session.calls[0][2]["headers"]["apptoken"],"cached")
    async def test_auth_retry_once(self):
        session = password_session(Response({"items":[record()]}))
        session.responses.insert(0,Response({},status=401))
        client = api.ZeppClient(session, {"zepp_user_id":"123","app_token":"expired","username":"u","password":"p"})
        self.assertIsNotNone(await client.latest())
        self.assertEqual(len(session.calls),7)
    async def test_wrong_account_cannot_replace_existing_account(self):
        client = api.ZeppClient(Session(token("999")), {"zepp_user_id":"123"})
        with self.assertRaises(api.AuthError) as ctx:
            await client.exchange_code("code")
        self.assertEqual(ctx.exception.stage,"account_changed")
    async def test_rate_limit_no_retry(self):
        session = Session(Response({}, status=429))
        with self.assertRaises(api.CloudError):
            await api.ZeppClient(session, {"zepp_user_id":"123","app_token":"cached"}).latest()
        self.assertEqual(len(session.calls),1)
    async def test_missing_items_is_not_success(self):
        session = Session(Response({"unexpected":[]}))
        with self.assertRaises(api.CloudError):
            await api.ZeppClient(session, {"zepp_user_id":"123","app_token":"cached"}).latest()
    async def test_pagination_and_loop_guard(self):
        session = Session(Response({"items":[],"next":100}), Response({"items":[record(90)],"next":0}))
        result = await api.ZeppClient(session, {"zepp_user_id":"123","app_token":"cached"}).latest()
        self.assertEqual(result["generatedTime"],90)
        self.assertIn("toTime=100",session.calls[1][1])
    async def test_unsafe_redirect_stops_before_request(self):
        session = Session(Response({},redirect="https://evil.example/?code=secret"))
        with self.assertRaises(api.CloudError):
            await api.ZeppClient(session, {}).login()
        self.assertEqual(len(session.calls),1)
    async def test_cookie_injection_rejected(self):
        client=api.ZeppClient(Session(),{"userId":"456","passToken":"bad;other=secret"})
        with self.assertRaises(api.AuthError):
            await client.login()
    async def test_empty_cloud_is_success_without_fake_values(self):
        client=api.ZeppClient(Session(Response({"items":[],"next":0})),{"zepp_user_id":"123","app_token":"cached"})
        self.assertIsNone(await client.latest())

if __name__ == "__main__":
    unittest.main()
