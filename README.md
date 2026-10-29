# Zepp Life Cloud for Home Assistant — experimental v0.3.0

Native custom integration for Xiaomi scales connected through Zepp Life.
This is a first implementation, NOT a confirmed working replacement against a live account.
Offline tests pass; live Xiaomi login and a real Home Assistant installation have not been tested.
It deliberately makes no claim of permanent unattended authentication.

## What it does

- Polls Zepp Life cloud every 60 minutes (configurable 15–1440).
- Runs as an HA integration; no SmartScaleConnect add-on, MQTT or Bluetooth needed.
- Reads the main scale profile (-1) or a numeric family member ID.
- Creates weight, BMI, body fat, body water, muscle mass, bone mass, protein percentage,
  visceral fat index, BMR, body age, body score, body type, standard weight, impedance, height, balance score, last measurement and last sync sensors.
- Groups sensor names by measurement, composition, metabolism, reference values and sync status, with a distinct icon for every known metric. The seconds-based one-foot balance sensor is omitted.
- Automatically creates separate sensors for extra numeric body metrics returned by the cloud.
  Technical fields such as source and device type are excluded. Raw numeric summaries are also
  available as weight-sensor attributes.
- Only uses values supplied by the cloud. Missing/zero placeholder composition values
  show unknown; it does not invent estimates.
- Includes a Sync now button, safe diagnostics, reauthentication flow, cached Zepp app token,
  and automatic login retry when cloud access is rejected.
- Reads the latest valid record. It does NOT import old records into HA's historical statistics.
  HA records future sensor states normally once installed.
- Browser login lets Xiaomi handle its own sign-in and verification page. You paste the short-lived
  Zepp callback URL (or code) into the local Home Assistant flow; the integration then exchanges it
  for and caches the Zepp app token. Browser grants require Home Assistant reauthentication if revoked.
- Password and existing-session methods remain available as experimental alternatives.

## Install through HACS

1. HACS > three-dot menu > Custom repositories.
2. Repository: https://github.com/georgehanna1993/ha-zepp-life-cloud
3. Type: Integration. Add, then download Zepp Life Cloud.
4. Restart Home Assistant.
5. Settings > Devices & services > Add integration > Zepp Life Cloud.

## Manual installation

1. Extract the ZIP on your computer.
2. Copy the whole custom_components/zepp_life_cloud folder into
   /config/custom_components/zepp_life_cloud on Home Assistant.
   manifest.json must sit directly inside that final folder.
3. Restart Home Assistant.
4. Settings > Devices & services > Add integration > Zepp Life Cloud.
   If it is missing, refresh the browser after the restart.
5. Choose **Sign in through Xiaomi in your browser**. Complete sign-in and any verification in the
   Xiaomi page opened by the flow. When it redirects to the Zepp callback, copy that final address
   (or just the `code` value) into the Home Assistant form. The short-lived code is entered only in HA.
   The integration checks cloud access before creating an entry.
6. If you prefer, the Xiaomi email/ID and password or existing-session methods remain available.
   Password-based verification errors show the failed stage and sanitized details.
7. Once connected, use Configure to choose the polling interval. The default is one hour.
   Sync now triggers a read on demand.

No YAML is added to configuration.yaml. Disable the SmartScaleConnect add-on while testing
to avoid competing sessions. Do not delete existing HA or add-on config files.

## Existing Xiaomi session: verification fallback

This is an experimental alternate authentication route, not a guaranteed workaround.
It reuses a real Xiaomi login rather than trying to evade verification.

Option A — your own desktop browser:
1. Sign in normally at https://account.xiaomi.com/ and finish any verification.
2. Open developer tools > Application (Chrome/Edge) > Cookies for account.xiaomi.com.
3. If the cookies userId and passToken are present, enter their values in the HA integration's
   Existing Xiaomi session form. Do not paste the entire Cookie header.
4. If these cookies are absent, try option B. Do not use serviceToken, ssecurity, a device's
   32-character token, or your Google token.

Option B — the maintainer's documented go2rtc Xiaomi login:
1. go2rtc v1.9.13+ has WebUI > Add > Xiaomi.
2. Log in to Xiaomi there and complete email/SMS/captcha verification.
3. Its YAML contains xiaomi: followed by your numeric account ID and a V1:... value.
4. Enter the numeric key as userId and the entire V1:... value as passToken in this integration.
   Do not include the account ID in the passToken field.
5. You do not need a camera for this integration; the session comes from Xiaomi account login.
   Availability of go2rtc's account login without linked cameras still needs verification.

The integration attempts the Zepp Life OAuth authorization using this Xiaomi session and caches
the resulting Zepp app token. Its session path is new and has only been tested against simulated
cloud responses. If Xiaomi responds differently, the form reports the stage without leaking secrets.

Reference: https://github.com/AlexxIT/go2rtc/blob/master/internal/xiaomi/README.md

## What we found in SmartScaleConnect v0.4.2

The add-on runs scaleconnect -i -r with a default sleep of 24h. /config is its working directory.
The sync configuration can arrive through hassio.addon_stdin.
Its options schema only contains sleep; credentials do not belong in HA configuration.yaml.

For zepp/xiaomi the flow is:
Xiaomi OAuth authorize -> oauthLoginUrl -> Xiaomi password request -> redirect/code ->
Zepp token exchange -> Zepp weightRecords endpoint.

There are TWO unchecked empty URL sites in that Xiaomi OAuth implementation:
data.oauthLoginUrl and the password response location. Either can cause Get "":
unsupported protocol scheme "". Password error codes, captchaUrl and notificationUrl
are not handled before the redirect is requested. Your log cannot distinguish the two.

The maintainer confirms verification can cause this symptom. The XiaomiGateway3/go2rtc
xiaomi: token workaround in issue #4 concerns Xiaomi cloud clients. The zepp/xiaomi client
does not load that Xiaomi token in the same path; it uses its own zepp/xiaomi: cached
user-id:app-token. Simply putting a Xiaomi token into that key is incorrect.

The custom client validates each stage, uses a cookie jar and persistent device identifier,
parses OAuth codes by name, restricts redirects to known HTTPS hosts, and adds session reuse.
The actual upstream response for the affected account has not been observed.

## Reliability and privacy

- This unofficial service can change without notice.
- The phone must still sync the scale with Zepp Life and upload measurements first.
  HA cannot obtain weighings the phone has not uploaded.
- Cloud login may log the phone out; SmartScaleConnect documents that behavior and this
  implementation cannot guarantee a separate phone session.
- Passwords / session tokens are stored in HA config entries like other integrations.
  Protect HA backups. No credentials or response bodies are logged by this integration.
- Diagnostics omit account identifiers, tokens, measurements and URLs.
- Only read requests are made to measurement endpoints. No weighings are written or deleted.
- Initial login makes a POST to the account service; password mode retains the Xiaomi password
  so it can retry authentication. Session mode does not require the password.
- HTTP 429 is reported as a rate limit; there are no rapid retry loops.
- No requests go to third-party telemetry services.
- The session can expire or require renewed verification; a new integration cannot remove
  Xiaomi's authentication requirements.

## Testing

Run from the extracted project directory:
python -m unittest discover -s tests -v
python -m compileall -q custom_components

Tests use simulated HTTP and real client code. They cover OAuth password/session flows,
verification rejection, empty redirects, token retry, account isolation, record filtering,
pagination and unsafe redirect rejection. No live credentials were used. Sensor extraction and dynamic discovery are also tested
against small HA interface stubs; these do not replace a full HA runtime test.
HA platform code was syntax-checked; full HA runtime/hassfest validation was not available here.

## Sources and attribution

- SmartScaleConnect v0.4.2:
  https://github.com/AlexxIT/SmartScaleConnect/tree/v0.4.2
- Authentication implementation:
  https://github.com/AlexxIT/SmartScaleConnect/blob/v0.4.2/pkg/xiaomi/auth.go
  https://github.com/AlexxIT/SmartScaleConnect/blob/v0.4.2/pkg/zepp/auth.go
- Cloud fields and endpoints:
  https://github.com/AlexxIT/SmartScaleConnect/blob/v0.4.2/pkg/zepp/client.go
- Maintainer discussion: https://github.com/AlexxIT/SmartScaleConnect/issues/4
- HA config flow / coordinator documentation:
  https://developers.home-assistant.io/docs/config_entries_config_flow_handler/
  https://developers.home-assistant.io/docs/integration_fetching_data/

Endpoint and field mapping research was derived from AlexxIT's MIT-licensed
SmartScaleConnect. Original license notice is included in THIRD_PARTY_LICENSES.txt.
