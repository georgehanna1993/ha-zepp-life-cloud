"""UI setup, reauthentication and polling interval."""
from __future__ import annotations
import asyncio
import aiohttp
import re
from urllib.parse import parse_qs, urlsplit
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers import selector
from homeassistant.helpers.aiohttp_client import async_create_clientsession
from .api import ZeppClient, AuthError, CloudError
from .const import DOMAIN, DEFAULT_INTERVAL

SECRET = selector.TextSelector(selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD))
TEXT = selector.TextSelector()


def _authorization_code(value):
    """Accept the short-lived code or the Zepp callback URL, never other URLs."""
    value = value.strip()
    if value.startswith("https://"):
        parsed = urlsplit(value)
        if parsed.hostname != "api-mifit-cn.huami.com" or parsed.path != "/huami.health.loginview.do":
            raise ValueError("Paste the final Zepp callback URL, or just its code value.")
        code = parse_qs(parsed.query).get("code", [""])[0]
    elif "code=" in value:
        code = parse_qs(value.lstrip("?" )).get("code", [""])[0]
    else:
        code = value
    if not re.fullmatch(r"[A-Za-z0-9._~+/=-]{1,2048}", code):
        raise ValueError("No valid authorization code was found. Complete Xiaomi sign-in first.")
    return code


class ZeppLifeConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input=None):
        return self.async_show_menu(step_id="user", menu_options=["browser", "password", "session"])

    async def async_step_browser(self, user_input=None):
        """Authenticate in Xiaomi's browser UI and exchange its callback code."""
        errors = {}
        placeholders = {"login_url": getattr(self, "_browser_login_url", ""), "error_detail": ""}
        if user_input is not None:
            try:
                code = _authorization_code(user_input["authorization"])
                member_id = user_input.get("member_id", "-1")
                data = {"method": "browser", "member_id": member_id}
                client = ZeppClient(
                    async_create_clientsession(self.hass, cookie_jar=aiohttp.CookieJar()), data
                )
                async with asyncio.timeout(60):
                    await client.exchange_code(code)
                    await client.latest()
                data = client.export_credentials()
                unique_id = client.user_id + ":" + str(member_id)
                if self.context.get("source") == config_entries.SOURCE_REAUTH:
                    entry = self._get_reauth_entry()
                    if entry.unique_id != unique_id:
                        errors["base"] = "wrong_account"
                    else:
                        self.hass.config_entries.async_update_entry(entry, data=data)
                        await self.hass.config_entries.async_reload(entry.entry_id)
                        return self.async_abort(reason="reauth_successful")
                else:
                    await self.async_set_unique_id(unique_id)
                    self._abort_if_unique_id_configured()
                    return self.async_create_entry(title="Zepp Life", data=data)
            except ValueError as err:
                errors["base"] = "invalid_callback"
                placeholders["error_detail"] = str(err)
            except AuthError as err:
                errors["base"] = "invalid_auth"
                placeholders["error_detail"] = str(err)
            except CloudError as err:
                errors["base"] = "cloud_error"
                placeholders["error_detail"] = str(err)
            except (aiohttp.ClientError, TimeoutError):
                errors["base"] = "cannot_connect"

        if not getattr(self, "_browser_login_url", None):
            try:
                client = ZeppClient(
                    async_create_clientsession(self.hass, cookie_jar=aiohttp.CookieJar()),
                    {"method": "browser"},
                )
                async with asyncio.timeout(30):
                    self._browser_login_url = await client.authorization_url()
                placeholders["login_url"] = self._browser_login_url
            except (AuthError, CloudError) as err:
                errors["base"] = "cloud_error"
                placeholders["error_detail"] = str(err)
            except (aiohttp.ClientError, TimeoutError):
                errors["base"] = "cannot_connect"

        fields = {
            vol.Required("login_url", default=self._browser_login_url): TEXT,
            vol.Required("authorization"): TEXT,
            vol.Optional("member_id", default="-1"): TEXT,
        }
        return self.async_show_form(
            step_id="browser", data_schema=vol.Schema(fields), errors=errors,
            description_placeholders=placeholders,
        )

    async def async_step_password(self, user_input=None):
        return await self._credentials("password", user_input)

    async def async_step_session(self, user_input=None):
        return await self._credentials("session", user_input)

    async def _credentials(self, method, user_input):
        errors = {}
        placeholders = {"error_detail": ""}
        if user_input is not None:
            data = {**user_input, "method": method}
            client = ZeppClient(async_create_clientsession(self.hass, cookie_jar=aiohttp.CookieJar()), data)
            try:
                async with asyncio.timeout(60):
                    await client.latest()
                data = client.export_credentials()
                unique_id = client.user_id + ":" + str(data.get("member_id", "-1"))
                if self.context.get("source") == config_entries.SOURCE_REAUTH:
                    entry = self._get_reauth_entry()
                    if entry.unique_id != unique_id:
                        errors["base"] = "wrong_account"
                    else:
                        self.hass.config_entries.async_update_entry(entry, data=data)
                        await self.hass.config_entries.async_reload(entry.entry_id)
                        return self.async_abort(reason="reauth_successful")
                else:
                    await self.async_set_unique_id(unique_id)
                    self._abort_if_unique_id_configured()
                    return self.async_create_entry(title=user_input.get("name", "Zepp Life"), data=data)
            except AuthError as err:
                errors["base"] = "invalid_auth"
                placeholders["error_detail"] = str(err)
            except CloudError as err:
                errors["base"] = "cloud_error"
                placeholders["error_detail"] = str(err)
            except (aiohttp.ClientError, TimeoutError):
                errors["base"] = "cannot_connect"
        fields = {vol.Required("name", default="Zepp Life"): TEXT}
        if method == "password":
            fields.update({vol.Required("username"): TEXT, vol.Required("password"): SECRET})
        else:
            fields.update({vol.Required("userId"): TEXT, vol.Required("passToken"): SECRET})
        fields[vol.Optional("member_id", default="-1")] = TEXT
        return self.async_show_form(step_id=method, data_schema=vol.Schema(fields),
            errors=errors, description_placeholders=placeholders)

    async def async_step_reauth(self, entry_data):
        return await self.async_step_user()

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return ZeppOptionsFlow()

class ZeppOptionsFlow(config_entries.OptionsFlow):
    async def async_step_init(self, user_input=None):
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)
        return self.async_show_form(step_id="init", data_schema=vol.Schema({
            vol.Required("interval", default=self.config_entry.options.get("interval", DEFAULT_INTERVAL)):
                vol.All(vol.Coerce(int), vol.Range(min=15, max=1440))
        }))
