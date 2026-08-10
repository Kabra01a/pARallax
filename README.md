<p align="center">
  <img src="assets/logo.svg" alt="pARallax" width="100%">
</p>

<p align="center">
  <img alt="platform" src="https://img.shields.io/badge/platform-iOS%20%7C%20Android-informational">
  <img alt="server" src="https://img.shields.io/badge/server-Python%203.9%2B-blue">
  <img alt="app" src="https://img.shields.io/badge/app-Expo%20SDK%2050-000020">
  <img alt="license" src="https://img.shields.io/badge/license-MIT-green">
</p>

---

Point your phone at a real object, press and hold to **cut** it out of the world.
Point at your monitor and release to **paste** it straight into Photoshop —
background already removed, landing exactly where you pointed.

An AR + computer vision system that closes the gap between the physical desk and
the digital canvas.

> *Parallax* — the displacement of an object viewed along two different lines of
> sight. Reconciling those two views is precisely the problem this solves: a
> homography maps the camera's view of your monitor back into screen coordinates.

> **Status:** research prototype, actively being rebuilt.
> pARallax grew out of [cyrildiagne/ar-cutpaste](https://github.com/cyrildiagne/ar-cutpaste)
> (MIT, 2020) and has since been substantially rewritten — see
> [What's different](#whats-different-from-upstream).

---

## How it works

```
┌─────────────┐   photo    ┌──────────────┐   photo   ┌────────────────────┐
│  Mobile app │ ─────────► │ Local server │ ────────► │ Segmentation       │
│ (Expo / RN) │            │   (Flask)    │ ◄──────── │ service (HTTP)     │
└─────────────┘   cutout   └──────────────┘   mask    └────────────────────┘
       │                          │
       │  photo of the monitor    │ screenshot + SIFT homography
       └────────────────────────► │        ▼
                                  │  screen coordinates
                                  │        ▼
                                  │  ┌──────────────────┐
                                  └─►│ Adobe Photoshop  │
                                     │ (AppleScript/JSX)│
                                     └──────────────────┘
```

**Cut** — the app captures a frame and POSTs it to the local server, which
forwards it to a background-removal service. The returned saliency mask is
composited into the alpha channel and the transparent PNG is sent back to the
phone (and cached for the paste step).

**Paste** — the app captures a frame containing the monitor. The server grabs a
screenshot, then uses SIFT keypoints + FLANN matching + a RANSAC homography to
work out *where on the screen* the camera was pointing. Those coordinates are
converted into a document-relative offset and the cached cutout is pasted into
the active Photoshop document as a new layer.

---

## Repository layout

```
app/                    Expo / React Native mobile client
  App.tsx               Camera view, press-to-cut / release-to-paste gesture
  components/
    Server.tsx          HTTP client for the local server
    ProgressIndicator.tsx  Animated SVG feedback overlay
    Base64.tsx          Base64 shim (no atob/btoa in React Native)
  utils/config.ts       Env-driven configuration

server/                 Flask local server
  src/
    main.py             HTTP API: /ping, /cut, /paste
    config.py           Env-driven configuration
    screenpoint.py      SIFT homography: locate camera view within screenshot
    ps.py               Photoshop integration (macOS, AppleScript + ExtendScript)
  tools/
    check_photoshop.py  Diagnostic for the Photoshop integration
```

---

## Setup

### Prerequisites

- Python 3.9+ and Node 18+
- A phone with the [Expo Go](https://expo.dev/go) app, on the **same Wi-Fi**
  as your computer
- Adobe Photoshop (macOS) with a document open
- A reachable background-removal HTTP service (see below)

### 1. Segmentation service

The `/cut` endpoint delegates background removal to an HTTP service that accepts
an image and returns a grayscale saliency mask.

> ⚠️ Upstream pointed at a public CoreWeave U²-Net endpoint from 2020. **Do not
> rely on it** — it is no longer guaranteed to exist. Run your own service and
> set `SEGMENTATION_SERVICE_URL` accordingly.

### 2. Local server

```bash
cd server
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

cp .env.example .env      # then edit .env
python src/main.py
```

Verify it's alive: `curl http://localhost:8080/ping`

Verify Photoshop is wired up: `python tools/check_photoshop.py`

### 3. Mobile app

```bash
cd app
npm install

cp .env.example .env      # set EXPO_PUBLIC_SERVER_URL to your computer's LAN IP
npm start
```

Scan the QR code with Expo Go.

> `localhost` will not work from a physical device — you must use the LAN IP of
> the machine running the server (e.g. `http://192.168.1.29:8080`).

### 4. Photoshop

Open a document with a non-blank background. A blank canvas gives SIFT too few
features to match against, and the paste will land in the wrong place or fail.

---

## Configuration

All configuration is environment-driven. Nothing secret lives in source.

| Variable | Where | Default | Purpose |
|---|---|---|---|
| `SEGMENTATION_SERVICE_URL` | server | `http://localhost:8081` | Background-removal endpoint |
| `SEGMENTATION_TIMEOUT` | server | `30` | Request timeout (seconds) |
| `SERVER_HOST` / `SERVER_PORT` | server | `0.0.0.0` / `8080` | Bind address |
| `CORS_ORIGINS` | server | `*` | Comma-separated allowed origins |
| `SAVE_DEBUG_IMAGES` | server | `false` | Dump intermediates to `server/tmp/` |
| `MAX_VIEW_SIZE` | server | `700` | Downscale cap for the camera frame |
| `MAX_SCREENSHOT_SIZE` | server | `400` | Downscale cap for the screenshot |
| `PHOTOSHOP_APP_NAME` | server | *(auto-detect)* | Override e.g. `Adobe Photoshop 2025` |
| `EXPO_PUBLIC_SERVER_URL` | app | `http://localhost:8080` | Local server address |
| `EXPO_PUBLIC_REQUEST_TIMEOUT_MS` | app | `30000` | Client request timeout |

---

## API

| Method | Route | Body | Returns |
|---|---|---|---|
| `GET` | `/ping` | — | `{ status, message, segmentation_service }` |
| `POST` | `/cut` | multipart `data` (image) | `image/png` with alpha |
| `POST` | `/paste` | multipart `data` (image) | `{ status, x, y }` |

Errors return `{ "status": "error", "error": "<message>" }` with a meaningful
HTTP status. `/paste` returns `{ "status": "screen not found" }` (HTTP 200) when
the homography fails — this is an expected outcome, not an error.

---

## What's different from upstream

Upstream is a 2020 research prototype. pARallax:

- **Replaced the `screenpoint` dependency** with a local implementation
  (`server/src/screenpoint.py`) — inlier validation, bounds checking, tuned
  ratio/RANSAC thresholds, structured logging.
- **Modernised the stack** — Flask 3, OpenCV 4.9, Pillow 10, Expo SDK 50,
  React Native 0.73, TypeScript throughout.
- **Removed all hardcoded configuration** — the upstream fork carried a
  Photoshop password and a LAN IP in source. Everything is now env-driven.
- **Photoshop version auto-detection** instead of a pinned `"Adobe Photoshop 2025"`
  string, plus JSON-escaped script injection so filenames can't break the payload.
- **Real error handling** — CORS preflight, timeouts, upstream failure
  propagation, no silent `except: pass`.
- **Mobile UX** — animated SVG progress overlay, haptic feedback on cut/paste
  success and failure, in-app permission and connection errors.

---

## Known limitations

- **macOS only** for the Photoshop integration (AppleScript).
- **SIFT is the weak link.** Low-texture screens, steep viewing angles and
  glare all cause "screen not found".
- The cut path crops to a **fixed centre region**, so framing matters.
- Paste assumes **fixed document dimensions**; other sizes drift.
- Requires a **network round-trip** per cut, so latency tracks your service.
- Struggles with **transparent, reflective and very thin** structures.

---

## Roadmap

- [ ] Replace BASNet-era segmentation with a modern dichotomous / matting model
- [ ] Benchmark old vs. new on a fixed test set (measured MAE / F-measure, not cited)
- [ ] Swap SIFT for a learned matcher (LightGlue / LoFTR) to kill "screen not found"
- [ ] On-device inference (ONNX / CoreML / TFLite) — remove the server round-trip
- [ ] Photoshop **UXP plugin** to replace AppleScript and go cross-platform
- [ ] Additional paste targets: Figma, Blender, system clipboard
- [ ] Interactive crop / refine step instead of the fixed centre crop
- [ ] Upgrade Expo SDK and migrate the deprecated `Camera` API to `CameraView`

---

## Credits

Built on [cyrildiagne/ar-cutpaste](https://github.com/cyrildiagne/ar-cutpaste) by
Cyril Diagne (MIT).

- **BASNet** — Qin et al., *Boundary-Aware Salient Object Detection*, CVPR 2019
- **PiCANet** — Liu et al., *Learning Pixel-wise Contextual Attention*, CVPR 2018
- **FPN** — Lin et al., *Feature Pyramid Networks*, CVPR 2017
- Photoshop paste technique adapted from
  [RunwayML for Photoshop](https://github.com/runwayml/RunwayML-for-Photoshop)

Originally developed by Samarth Sharma as a Machine Learning project at the
School of Information Technology, Artificial Intelligence and Cyber Security,
Rashtriya Raksha University.

## License

MIT — see [LICENSE](LICENSE).
