# pARallax — mobile app

[Expo](https://expo.dev) / React Native client. Press and hold anywhere on the
camera view to **cut**; release while pointing at your monitor to **paste**.

## Setup

```bash
npm install
cp .env.example .env
```

Set `EXPO_PUBLIC_SERVER_URL` in `.env` to the **LAN IP** of the computer running
the local server:

```
EXPO_PUBLIC_SERVER_URL=http://192.168.1.29:8080
```

`localhost` will not resolve from a physical device.

## Run

```bash
npm start
```

Scan the QR code with [Expo Go](https://expo.dev/go). Phone and computer must be
on the same network.

## Structure

| File | Purpose |
|---|---|
| `App.tsx` | Camera view, permissions, press-to-cut / release-to-paste gesture |
| `components/Server.tsx` | HTTP client (`ping` / `cut` / `paste`) with timeouts |
| `components/ProgressIndicator.tsx` | Animated SVG overlay shown while processing |
| `components/Base64.tsx` | Base64 shim — React Native has no `atob`/`btoa` |
| `utils/config.ts` | Environment-driven configuration |

## Notes

- Expo SDK 50 pins the legacy `Camera` component. `expo-camera` has since moved
  to `CameraView`; migrating is on the roadmap.
- The cut path resizes to 256×512 and crops a fixed 256×256 centre region, so
  framing the subject centrally matters.
