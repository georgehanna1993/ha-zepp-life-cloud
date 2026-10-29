"""Read-only cloud client. Never logs credentials, URLs, cookies or bodies.

Endpoint behavior is based on SmartScaleConnect v0.4.2 (MIT), but this
implementation validates every login stage and can reuse a Xiaomi session.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
import time
import uuid
from urllib.parse import parse_qs, urlencode, urljoin, urlsplit

AUTH_URL = "https://account.xiaomi.com/oauth2/authorize"
CALLBACK = "https://api-mifit-cn.huami.com/huami.health.loginview.do"
API = "https://api-mifit.zepp.com"
AUTH_PARAMS = {
    "_json": "true", "client_id": "428135909242707968", "pt": "1",
    "redirect_uri": CALLBACK, "response_type": "code",
}


class CloudError(Exception):
    """A sanitized error safe to display in HA."""


class AuthError(CloudError):
    def __init__(self, stage, payload=None):
        self.stage = stage
        payload = payload if isinstance(payload, dict) else {}
        code = str(payload.get("code", payload.get("error_code", "missing_redirect")))
        self.code = code if re.fullmatch(r"[A-Za-z0-9_-]{1,48}", code) else "unknown"
        self.verification = bool(payload.get("notificationUrl") or payload.get("captchaUrl"))
        message = f"Authentication failed at {stage} (code {self.code})."
        if stage == "zepp_token_exchange" and self.code == "0106":
            message += " Zepp rejected third-party verification after Xiaomi sign-in."
        if self.verification:
            message += " Xiaomi requires verification/captcha; use Xiaomi session setup."
        super().__init__(message)


def trusted_url(url):
    """Restrict redirects and credential-bearing requests to known HTTPS hosts."""
    p = urlsplit(url)
    if p.scheme != "https" or p.username or p.password or p.port not in (None, 443):
        raise CloudError("Cloud returned an unsafe redirect; request stopped.")
    host = p.hostname or ""
    if host not in {"account.xiaomi.com", "api-mifit-cn.huami.com", "account.zepp.com", "api-mifit.zepp.com"} and not host.endswith(".account.xiaomi.com"):
        raise CloudError("Cloud returned an unrecognized redirect host; request stopped.")
    return url


def decode_json(text, stage):
    if text.startswith("&&&START&&&"):
        text = text[11:]
    try:
        value = json.loads(text)
    except (ValueError, TypeError):
        raise CloudError(f"{stage}: cloud returned non-JSON content.") from None
    if not isinstance(value, dict):
        raise CloudError(f"{stage}: unexpected response format.")
    return value


def latest_record(items):
    """Keep the last real measurement, not a change/deletion record."""
    valid = []
    for item in items:
        if not isinstance(item, dict) or item.get("weightType", 0) != 0:
            continue
        summary = item.get("summary")
        if isinstance(summary, str):
            try:
                summary = json.loads(summary)
            except ValueError:
                continue
        if not isinstance(summary, dict):
            continue
        try:
            weight = float(summary.get("weight", 0))
            timestamp = float(item.get("generatedTime", 0))
        except (ValueError, TypeError):
            continue
        if not math.isfinite(weight) or weight <= 0 or not math.isfinite(timestamp) or timestamp <= 0:
            continue
        valid.append({"generatedTime": timestamp, "summary": summary})
    return max(valid, key=lambda x: x["generatedTime"], default=None)


class ZeppClient:
    def __init__(self, session, credentials):
        self.session = session
        self.credentials = dict(credentials)
        self.user_id = str(credentials.get("zepp_user_id", ""))
        self.app_token = credentials.get("app_token", "")
        # Match the canonical UUID format sent by the upstream Zepp client.
        self.device_id = credentials.get("device_id") or str(uuid.uuid4())
        self._last_response = {}

    async def _http(self, method, url, stage, **kwargs):
        trusted_url(url)
        request_headers = dict(kwargs.pop("headers", {}))
        host = urlsplit(url).hostname or ""
        if host == "account.xiaomi.com" or host.endswith(".account.xiaomi.com"):
            request_headers.update(self._xiaomi_headers())
        else:
            request_headers.pop("Cookie", None)
        if request_headers:
            kwargs["headers"] = request_headers
        async with self.session.request(method, url, allow_redirects=False, **kwargs) as response:
            text = await response.text()
            self._last_response = {
                "status": response.status,
                "content_type": response.headers.get("Content-Type", "").split(";", 1)[0],
                "host": host,
                "has_location": bool(response.headers.get("Location")),
            }
            if response.status in (401, 403):
                raise AuthError(stage, {"code": response.status})
            if response.status == 429:
                raise CloudError("Cloud rate limit reached. Wait before retrying.")
            if response.status >= 400:
                raise CloudError(f"{stage}: HTTP {response.status}.")
            return text, response.headers.get("Location", "")

    def _xiaomi_headers(self):
        cookies = [f"deviceId={self.device_id}"]
        for key in ("userId", "passToken"):
            value = self.credentials.get(key, "")
            if value:
                if any(c in str(value) for c in "\r\n;"):
                    raise AuthError("xiaomi_session", {"code": "invalid_cookie"})
                cookies.append(f"{key}={value}")
        return {"Cookie": "; ".join(cookies)}

    async def authorization_url(self):
        """Build Xiaomi's HTML authorization URL for an interactive browser login."""
        params = {**AUTH_PARAMS, "_json": "false"}
        return trusted_url(AUTH_URL + "?" + urlencode(params))

    async def _follow_code(self, url):
        for _ in range(12):
            trusted_url(url)
            p = urlsplit(url)
            if p.hostname == "api-mifit-cn.huami.com" and p.path == urlsplit(CALLBACK).path:
                code = parse_qs(p.query).get("code", [""])[0]
                if code:
                    return code
            text, redirect = await self._http("GET", url, "oauth_redirect")
            if redirect:
                url = urljoin(url, redirect)
                continue
            try:
                payload = decode_json(text, "oauth_redirect")
            except CloudError:
                meta = self._last_response
                content_type = meta.get("content_type") or "unspecified content type"
                if "html" in content_type.lower() or text.lstrip().lower().startswith(("<!doctype html", "<html")):
                    lowered = text[:8192].lower()
                    if any(marker in lowered for marker in ("captcha", "verification", "verify", "security check", "risk control")):
                        kind = "HTML that appears to request security verification"
                    else:
                        kind = "HTML; its purpose is not confirmed"
                    detail = f"{kind}"
                else:
                    detail = "non-JSON response"
                raise CloudError(
                    f"oauth_redirect: {detail} from {meta.get('host', 'cloud')} "
                    f"(HTTP {meta.get('status', 'unknown')}, {content_type}, "
                    f"Location header: {'yes' if meta.get('has_location') else 'no'}). "
                    "Response content was withheld."
                ) from None
            url = payload.get("location", "")
            if not url:
                raise AuthError("oauth_redirect", payload)
        raise CloudError("Too many OAuth redirects.")

    async def login(self):
        try:
            await self._login_once()
        except AuthError:
            if (self.credentials.get("method") != "session" and self.credentials.get("passToken")
                    and self.credentials.get("username") and self.credentials.get("password")):
                self.credentials.pop("passToken", None)
                self.credentials.pop("userId", None)
                await self._login_once()
            else:
                raise

    async def _login_once(self):
        headers = self._xiaomi_headers()
        text, redirect = await self._http("GET", AUTH_URL + "?" + urlencode(AUTH_PARAMS), "oauth_authorize", headers=headers)
        code = None
        if redirect:
            code = await self._follow_code(urljoin(AUTH_URL, redirect))
        else:
            payload = decode_json(text, "oauth_authorize")
            location = payload.get("location")
            if location:
                code = await self._follow_code(location)
            else:
                login_url = payload.get("data", {}).get("oauthLoginUrl", "") if isinstance(payload.get("data"), dict) else ""
                if not login_url:
                    raise AuthError("oauth_authorize", payload)
                text, redirect = await self._http("GET", urljoin(AUTH_URL, login_url), "oauth_login_page", headers=headers)
                if redirect:
                    code = await self._follow_code(urljoin(AUTH_URL, redirect))
                else:
                    page = decode_json(text, "oauth_login_page")
                    if page.get("location"):
                        code = await self._follow_code(page["location"])
                    else:
                        if self.credentials.get("method") == "session":
                            raise AuthError("xiaomi_session", page)
                        form = {key: str(page.get(key, "")) for key in ("sid", "callback", "_sign", "qs")}
                        if not form["_sign"]:
                            raise AuthError("oauth_login_page", page)
                        form.update({"_json": "true", "user": self.credentials["username"], "hash": hashlib.md5(self.credentials["password"].encode()).hexdigest().upper()})
                        text, _ = await self._http("POST", "https://account.xiaomi.com/pass/serviceLoginAuth2", "xiaomi_password", data=form, headers=headers)
                        result = decode_json(text, "xiaomi_password")
                        if not result.get("location"):
                            raise AuthError("xiaomi_password", result)
                        if result.get("passToken") and result.get("userId"):
                            self.credentials.update({"passToken": result["passToken"], "userId": str(result["userId"])})
                        code = await self._follow_code(result["location"])
        await self.exchange_code(code)

    async def exchange_code(self, code):
        form = {"app_name": "com.xiaomi.hm.health", "app_version": "6.14.0", "code": code,
                "country_code": "CN", "device_id": self.device_id, "device_model": "phone",
                "dn": "api-mifit.zepp.com", "grant_type": "request_token", "third_name": "xiaomi-hm-mifit"}
        text, _ = await self._http("POST", "https://account.zepp.com/v2/client/login", "zepp_token_exchange", data=form)
        payload = decode_json(text, "zepp_token_exchange")
        token = payload.get("token_info", {})
        if not isinstance(token, dict) or not token.get("app_token") or not token.get("user_id"):
            raise AuthError("zepp_token_exchange", payload)
        uid = str(token["user_id"])
        if not uid.isdigit():
            raise AuthError("zepp_token_exchange", {"code": "invalid_user_id"})
        if self.user_id and self.user_id != uid:
            raise AuthError("account_changed", {"code": "wrong_account"})
        self.user_id, self.app_token = uid, token["app_token"]

    def export_credentials(self):
        return {**self.credentials, "device_id": self.device_id, "zepp_user_id": self.user_id, "app_token": self.app_token}

    async def _records(self):
        if not self.user_id.isdigit():
            raise AuthError("zepp_user_id")
        member = str(self.credentials.get("member_id", "-1"))
        if not re.fullmatch(r"-?\d+", member):
            raise CloudError("Member ID must be numeric; use -1 for the main profile.")
        # Paginate only when a whole page has no valid measurement. Daily polls
        # normally need one request, rather than downloading the full history.
        cursor = int(time.time())
        for _ in range(10):
            url = f"{API}/users/{self.user_id}/members/{member}/weightRecords?limit=200&toTime={cursor}"
            text, _ = await self._http("GET", url, "weight_records", headers={"apptoken": self.app_token})
            payload = decode_json(text, "weight_records")
            if payload.get("code") not in (None, 0, "0"):
                raise AuthError("weight_records", payload)
            items = payload.get("items")
            if not isinstance(items, list):
                raise CloudError("weight_records: missing items list; cloud response changed.")
            latest = latest_record(items)
            if latest:
                return latest
            next_cursor = payload.get("next", 0)
            try:
                next_cursor = int(next_cursor)
            except (ValueError, TypeError):
                raise CloudError("weight_records: invalid pagination cursor.") from None
            if not 0 < next_cursor < cursor:
                return None
            cursor = next_cursor
        raise CloudError("No valid measurement in the first 2000 cloud records.")

    async def latest(self):
        if not self.app_token:
            await self.login()
        try:
            return await self._records()
        except AuthError:
            if self.credentials.get("method") == "browser":
                # Browser grants cannot be renewed silently; HA will start reauth.
                raise
            await self.login()
            return await self._records()
