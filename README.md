# Zepp Life Cloud for Home Assistant — experimental v0.4.0

Native custom integration for Xiaomi scales connected through Zepp Life.
Initial browser sign-in and a cloud fetch appear to work in one Home Assistant setup. Broader scale compatibility, complete metric coverage and long-term token renewal are not yet verified.

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
- Xiaomi browser sign-in is the only setup method. You paste the short-lived Zepp callback code into the local Home Assistant flow; the integration then exchanges it for and caches the Zepp app token. If authorization expires, Home Assistant asks you to sign in again in the browser.

## Install and sign in

### Add the repository in HACS

1. Open **HACS → Integrations**.
2. Open the **⋮** menu and choose **Custom repositories**.
3. Enter https://github.com/georgehanna1993/ha-zepp-life-cloud.
4. Select **Integration**, then choose **Add**.
5. Find **Zepp Life Cloud** in HACS and download it.
6. Restart Home Assistant.
7. Go to **Settings → Devices & services → Add integration** and select **Zepp Life Cloud**.

### Before setup

The scale must be paired with the **Zepp Life phone app**, and the app must have synced at least one measurement to the cloud. If it is already paired and synced, leave it as it is; you do not need to be near the scale or pair it again.

Compatibility has only been tried with the scale used for this setup. Its exact model has not been recorded, so other scale models and their available metrics are unverified. You are welcome to try it and report what works.

### Xiaomi browser sign-in

1. In the Home Assistant form, copy the **Xiaomi sign-in URL** and open it in a browser tab.
2. Sign in on Xiaomi’s website using the Xiaomi account linked to Zepp Life, and complete any verification Xiaomi requests. Do not enter your password in the Home Assistant form.
3. After sign-in, the browser redirects to a Zepp address like:
   https://api-mifit-cn.huami.com/huami.health.loginview.do?code=ALSG_CLOUDSRV_ABC123&...
   The callback page may show a routes-not-found message; use the address bar URL. Copy only the code value after **code=** and before the next **&**. In this example, copy **ALSG_CLOUDSRV_ABC123**—not code= and not the rest of the URL.
4. Return to Home Assistant, paste that value into **Code from the callback URL**, leave **Member ID** as **-1** for the main profile, and submit promptly. The code is short-lived. Never send it in chat.
5. When setup succeeds, Home Assistant creates the cloud sensors. Polling defaults to every 60 minutes; use **Sync now** for an immediate refresh.

No YAML is needed. Measurements appear only after Zepp Life has uploaded them to the cloud.

## Reliability and privacy

- This unofficial service can change without notice.
- The phone must still sync the scale with Zepp Life and upload measurements first.
  HA cannot obtain weighings the phone has not uploaded.
- Cloud login may log the phone out; SmartScaleConnect documents that behavior and this
  implementation cannot guarantee a separate phone session.
- The Zepp app token is stored in the HA config entry. Protect HA backups. No credentials or response bodies are logged by this integration.
- Diagnostics omit account identifiers, tokens, measurements and URLs.
- Only read requests are made to measurement endpoints. No weighings are written or deleted.
- Initial sign-in exchanges a short-lived Xiaomi authorization code for a Zepp app token.
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
