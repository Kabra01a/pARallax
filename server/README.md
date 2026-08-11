# pARallax — local server

Flask service bridging the mobile app, the segmentation service and your image
editor.

## Setup

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
```

Edit `.env` — at minimum set `SEGMENTATION_SERVICE_URL` to a reachable
background-removal endpoint.

## Run

```bash
python src/main.py
```

CLI flags override the environment:

```bash
python src/main.py \
    --segmentation_service_url http://localhost:8081 \
    --port 8080 \
    --debug
```

## Verify

```bash
curl http://localhost:8080/ping     # shows the segmentation service and paste target
python tools/check_target.py        # detects the editor and pastes a test layer
python tools/check_target.py gimp   # or check a specific target
```

## Endpoints

| Method | Route | Body | Returns |
|---|---|---|---|
| `GET` | `/ping` | — | JSON status |
| `POST` | `/cut` | multipart `data` | `image/png` with alpha |
| `POST` | `/paste` | multipart `data` | `{ status, x, y }` |

`/paste` reuses the most recent `/cut` result, cached at `server/tmp/cut_current.png`.
Calling `/paste` first returns HTTP 409.

## Paste targets

Selected with `PASTE_TARGET`. Implementations live in `src/targets/`.

| Target | Platforms | Transport | Status |
|---|---|---|---|
| `gimp` | macOS, Linux, Windows | TCP to the Script-Fu server | **Default.** Free. Needs the server started in GIMP. |
| `photoshop` | macOS only | AppleScript `do javascript` | Supported, currently unverified — see note below. Requires a licensed desktop Photoshop; the web and Express tiers have no scripting interface. |

The Photoshop target works but has not been re-tested since the refactor into
the `PasteTarget` interface, for want of a licence. The AppleScript and
ExtendScript are unchanged from the version that worked. Confirm with
`python tools/check_target.py photoshop`.

Adding one: subclass `PasteTarget` in `src/targets/`, register it in
`src/targets/__init__.py`.

Note on coordinates: `screenpoint` returns an absolute *screen* pixel, but an
editor positions layers within its *document*. The mapping depends on window
position and zoom, which neither editor reports, so targets approximate —
Photoshop offsets from the document centre, GIMP places at the same fraction of
the canvas as the pointed fraction of the screen. See `src/targets/base.py`.

## Troubleshooting

**"segmentation service unreachable"** — `SEGMENTATION_SERVICE_URL` is wrong or
the service is down. Check with `curl`.

**"GIMP did not respond within 30s"** — a modal dialog is open in GIMP, holding
its main thread. Close every GIMP dialog, including the Script-Fu Server Options
window, and retry.

**"screen not found" on macOS, with everything apparently correct** — the
terminal is missing Screen Recording permission, so the screenshot contains only
wallpaper. Grant it in System Settings > Privacy & Security > Screen & System
Audio Recording, then fully quit and reopen the terminal. With
`SAVE_DEBUG_IMAGES=true`, check `server/tmp/paste_screenshot.png`: if it shows no
windows, that is the cause.

**"screen not found"** — SIFT could not locate the camera view in the
screenshot. Note the screenshot is taken when the request arrives, so the screen
must look like the photo at that moment. Include distinctive UI (toolbars,
panels) in frame — a repeating texture such as a patterned canvas gives
ambiguous matches. Give the Photoshop document a textured (non-blank) background,
reduce glare, and shoot the monitor closer to head-on. Set `SAVE_DEBUG_IMAGES=true`
to inspect what the server actually received.

**"nothing listening on 127.0.0.1:10008"** — GIMP's Script-Fu server is off.
In GIMP: Filters > Script-Fu > Start Server.

**"GIMP is running but has no image open"** — create one with File > New. There
must be a document to paste into.

**"Photoshop does not appear to be running"** — open Photoshop with a document.
If auto-detection still fails, set `PHOTOSHOP_APP_NAME` explicitly.

**Phone can't reach the server** — use the machine's LAN IP, not `localhost`,
and confirm your firewall allows inbound connections on the port.
