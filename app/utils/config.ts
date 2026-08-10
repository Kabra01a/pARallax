/**
 * App configuration.
 *
 * The server URL is read from the Expo runtime config so it is never
 * hardcoded in source. Set it in `app/.env`:
 *
 *   EXPO_PUBLIC_SERVER_URL=http://192.168.1.29:8080
 *
 * See `.env.example`. Expo inlines any `EXPO_PUBLIC_*` variable at build time.
 */

const DEFAULT_SERVER_URL = "http://localhost:8080";

export const SERVER_URL =
  process.env.EXPO_PUBLIC_SERVER_URL ?? DEFAULT_SERVER_URL;

/** Request timeout in milliseconds for server calls. */
export const REQUEST_TIMEOUT_MS = Number(
  process.env.EXPO_PUBLIC_REQUEST_TIMEOUT_MS ?? 30000
);

if (SERVER_URL === DEFAULT_SERVER_URL) {
  console.warn(
    "[config] EXPO_PUBLIC_SERVER_URL is not set - falling back to " +
      DEFAULT_SERVER_URL +
      ". A physical device cannot reach your machine on localhost; set the " +
      "LAN IP of the computer running the server."
  );
}
