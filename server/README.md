# pARallax — local server

Flask service bridging the mobile app, the segmentation service and Photoshop.

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
curl http://localhost:8080/ping          # server up, shows configured service
python tools/check_photoshop.py          # detects Photoshop, pastes a test layer
```

## Endpoints

| Method | Route | Body | Returns |
|---|---|---|---|
| `GET` | `/ping` | — | JSON status |
| `POST` | `/cut` | multipart `data` | `image/png` with alpha |
| `POST` | `/paste` | multipart `data` | `{ status, x, y }` |

`/paste` reuses the most recent `/cut` result, cached at `server/tmp/cut_current.png`.
Calling `/paste` first returns HTTP 409.

## Troubleshooting

**"segmentation service unreachable"** — `SEGMENTATION_SERVICE_URL` is wrong or
the service is down. Check with `curl`.

**"screen not found"** — SIFT could not locate the camera view in the
screenshot. Give the Photoshop document a textured (non-blank) background,
reduce glare, and shoot the monitor closer to head-on. Set `SAVE_DEBUG_IMAGES=true`
to inspect what the server actually received.

**"Photoshop does not appear to be running"** — open Photoshop with a document.
If auto-detection still fails, set `PHOTOSHOP_APP_NAME` explicitly.

**Phone can't reach the server** — use the machine's LAN IP, not `localhost`,
and confirm your firewall allows inbound connections on the port.
