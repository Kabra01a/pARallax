"""GIMP paste target, driven through the Script-Fu server.

GIMP ships a Script-Fu server that evaluates Scheme sent over TCP. Enable it
with Filters > Script-Fu > Start Server (default port 10008).

Expect two things that look like faults and are not: GIMP's UI goes sluggish
while the server runs, because the plugin blocks the main thread; and the
Script-Fu Server Options window stays on screen permanently, unresponsive and
impossible to close, because that plugin never returns. Both are normal. The
socket keeps working throughout.

If requests do start timing out, GIMP itself is wedged — usually from memory
pressure — and the fix is to quit and reopen it, then restart the server.

This is a cleaner integration than the Photoshop one: a socket and a Scheme
string, with no shell, no osascript and no nested quoting. It also works on
Linux and Windows, where the AppleScript path cannot.

SECURITY: the Script-Fu server has no authentication — anything that can reach
the port can execute arbitrary Scheme. Bind it to 127.0.0.1. Never expose it.

VERSION COMPATIBILITY: GIMP reworked the PDB across 2.10, 3.0 and 3.2.
Procedures were renamed (`gimp-image-list` -> `gimp-get-images`,
`gimp-image-width` -> `gimp-image-get-width`) and array returns lost their
separate length. Rather than branch on a version number — which broke twice
during development — this module *discovers* which procedure names are bound and
which return shape it gets, then builds its Scheme accordingly. Run
`python tools/gimp_probe.py` to see the same discovery as a report.
"""

import logging
import re
import socket
import struct

import config

from .base import PasteTarget

logger = logging.getLogger(__name__)

MAGIC = b"G"
SUCCESS, ERROR = 0, 1

# Candidate PDB names per capability, newest naming first.
CANDIDATES = {
    "images": ["gimp-get-images", "gimp-image-list"],
    "image_w": ["gimp-image-get-width", "gimp-image-width"],
    "image_h": ["gimp-image-get-height", "gimp-image-height"],
    "layer_w": ["gimp-drawable-get-width", "gimp-drawable-width"],
    "layer_h": ["gimp-drawable-get-height", "gimp-drawable-height"],
    "load_layer": ["gimp-file-load-layer"],
    "insert_layer": ["gimp-image-insert-layer"],
    "set_name": ["gimp-item-set-name", "gimp-layer-set-name"],
    "set_offsets": ["gimp-layer-set-offsets"],
    "scale": ["gimp-layer-scale"],
    "flush": ["gimp-displays-flush"],
}


class ScriptFuError(RuntimeError):
    """GIMP evaluated the script and reported an error."""


class GimpTarget(PasteTarget):
    name = "gimp"
    display_name = "GIMP"

    _VERSION_RE = re.compile(r"(\d+)\.(\d+)(?:\.(\d+))?")

    def __init__(self, host=None, port=None, timeout=None):
        self.host = host or config.GIMP_HOST
        self.port = port or config.GIMP_PORT
        self.timeout = timeout or config.GIMP_TIMEOUT
        self._procs = None

    # --- Script-Fu protocol ------------------------------------------------
    #
    # Request:   b'G' | uint16 big-endian length | script bytes
    # Response:  b'G' | uint8 status | uint16 big-endian length | text bytes
    #
    # status 0 = success, 1 = the script raised.

    @staticmethod
    def _recv_exactly(sock, count: int) -> bytes:
        chunks, remaining = [], count
        while remaining > 0:
            chunk = sock.recv(remaining)
            if not chunk:
                raise ConnectionError(
                    f"GIMP closed the connection after {count - remaining} of {count} bytes"
                )
            chunks.append(chunk)
            remaining -= len(chunk)
        return b"".join(chunks)

    def evaluate(self, script: str) -> str:
        """Send Scheme to GIMP and return its printed result."""
        payload = script.encode("utf-8")
        if len(payload) > 0xFFFF:
            raise ValueError("script exceeds the 64 KB Script-Fu frame limit")

        try:
            with socket.create_connection((self.host, self.port), self.timeout) as sock:
                sock.settimeout(self.timeout)
                sock.sendall(MAGIC + struct.pack(">H", len(payload)) + payload)

                header = self._recv_exactly(sock, 4)
                if header[:1] != MAGIC:
                    raise ConnectionError(
                        f"unexpected reply from {self.host}:{self.port} — is that "
                        f"really GIMP's Script-Fu server?"
                    )
                status = header[1]
                length = struct.unpack(">H", header[2:4])[0]
                body = self._recv_exactly(sock, length).decode("utf-8", "replace")

        except socket.timeout as exc:
            raise TimeoutError(
                f"GIMP accepted the connection but did not respond within "
                f"{self.timeout}s, so its main thread is stuck. Usually GIMP is "
                f"overloaded — large layers and memory pressure do it. Quit GIMP, "
                f"reopen it, and restart the Script-Fu server. Note the Script-Fu "
                f"Server Options window staying on screen and unresponsive is "
                f"normal while the server runs; it is not the cause."
            ) from exc
        except ConnectionRefusedError as exc:
            raise ConnectionError(
                f"nothing listening on {self.host}:{self.port}. In GIMP: "
                f"Filters > Script-Fu > Start Server."
            ) from exc
        except OSError as exc:
            raise ConnectionError(f"could not reach GIMP: {exc}") from exc

        if status == ERROR:
            raise ScriptFuError(body.strip())
        return body.strip()

    # --- capability discovery ----------------------------------------------

    def version(self) -> str:
        raw = self.evaluate("(car (gimp-version))")
        match = self._VERSION_RE.search(raw)
        if not match:
            raise ScriptFuError(f"could not read a version from GIMP's reply: {raw!r}")
        return match.group(0)

    def _is_bound(self, name: str) -> bool:
        """Is this PDB procedure present?

        Evaluates the bare symbol, which has no side effects: an unbound name
        raises "unbound variable", a bound one returns a closure.
        """
        try:
            self.evaluate(name)
            return True
        except ScriptFuError as exc:
            return "unbound" not in str(exc).lower()

    def procs(self) -> dict:
        """Resolve and cache the PDB names this GIMP actually provides."""
        if self._procs is None:
            resolved, missing = {}, []
            for capability, names in CANDIDATES.items():
                winner = next((n for n in names if self._is_bound(n)), None)
                if winner:
                    resolved[capability] = winner
                else:
                    missing.append(f"{capability} (tried {', '.join(names)})")

            if missing:
                raise ScriptFuError(
                    "this GIMP is missing procedures pARallax needs: "
                    + "; ".join(missing)
                    + ". Run tools/gimp_probe.py for details."
                )

            self._procs = resolved
            logger.debug("resolved GIMP procedures: %s", resolved)
        return self._procs

    def _active_image_expr(self) -> str:
        """Scheme yielding the first open image id, across all known shapes.

        Observed return shapes for the image lister:
          GIMP 2.10  (count #(ids))
          GIMP 3.0+  (#(ids))
          possible   #(ids) bare, or a plain list of ids
        """
        lister = self.procs()["images"]
        return f"""(let* ((raw ({lister}))
       (v (cond ((vector? raw) raw)
                ((and (pair? raw) (vector? (car raw))) (car raw))
                ((and (pair? raw) (pair? (cdr raw)) (vector? (cadr raw))) (cadr raw))
                ((and (pair? raw) (number? (car raw))) (list->vector raw))
                (else #()))))
  (if (= (vector-length v) 0)
      (error "no image open in GIMP")
      (vector-ref v 0)))"""

    # --- PasteTarget -------------------------------------------------------

    def is_available(self):
        try:
            version = self.version()
        except Exception as exc:
            return False, str(exc)

        try:
            procs = self.procs()
        except ScriptFuError as exc:
            return False, f"GIMP {version}: {exc}"
        except Exception as exc:
            return False, str(exc)

        try:
            image = self.evaluate(f"(let ((i {self._active_image_expr()})) i)")
        except ScriptFuError as exc:
            detail = str(exc)
            if "no image open" in detail:
                return False, (f"GIMP {version} is running but has no image open — "
                               f"create one with File > New")
            return False, (f"GIMP {version} rejected the image lookup: {detail}. "
                           f"Run `python tools/gimp_probe.py` for details.")
        except Exception as exc:
            return False, str(exc)

        return True, f"GIMP {version}, active image {image} (via {procs['images']})"

    def paste(self, image_path: str, layer_name: str, x: int, y: int,
              screen_size=None):
        # Scheme string literals need only backslash and quote escaped.
        path = image_path.replace("\\", "\\\\").replace('"', '\\"')
        name = layer_name.replace("\\", "\\\\").replace('"', '\\"')

        try:
            p = self.procs()
            active = self._active_image_expr()
        except Exception as exc:
            return str(exc)

        # Cap the scale at 1.0 unless upscaling is explicitly allowed: enlarging
        # a small crop only magnifies its softness.
        max_scale = 100.0 if config.PASTE_ALLOW_UPSCALE else 1.0
        frac = config.PASTE_MAX_FRACTION

        if screen_size and screen_size[0] and screen_size[1]:
            # Map the pointed fraction of the screen onto the same fraction of
            # the canvas, then centre the scaled layer on that point.
            fx = min(max(x / screen_size[0], 0.0), 1.0)
            fy = min(max(y / screen_size[1], 0.0), 1.0)
        else:
            fx = fy = None

        # Scale first, then place, because placement depends on the final size.
        # All arithmetic uses float literals; integer division in TinyScheme
        # cannot be relied upon to produce a rational.
        if fx is None:
            place = f"    ({p['set_offsets']} layer {int(x)} {int(y)})"
        else:
            place = f"""    ({p['set_offsets']} layer
      (inexact->exact (round (- (* iw {fx:.6f}) (/ nw 2.0))))
      (inexact->exact (round (- (* ih {fy:.6f}) (/ nh 2.0)))))"""

        placement = f"""  (let* ((iw (car ({p['image_w']} image)))
         (ih (car ({p['image_h']} image)))
         (lw (car ({p['layer_w']} layer)))
         (lh (car ({p['layer_h']} layer)))
         (s (min (/ (* iw {frac:.6f}) lw) (/ (* ih {frac:.6f}) lh) {max_scale:.1f}))
         (nw (max 1 (inexact->exact (round (* lw s)))))
         (nh (max 1 (inexact->exact (round (* lh s))))))
    ({p['scale']} layer nw nh FALSE)
{place})"""

        script = f"""(let* ((image {active})
       (layer (car ({p['load_layer']} RUN-NONINTERACTIVE image "{path}"))))
  ({p['insert_layer']} image layer 0 -1)
  ({p['set_name']} layer "{name}")
{placement}
  ({p['flush']})
  "ok")"""

        try:
            result = self.evaluate(script)
        except Exception as exc:
            return str(exc)

        logger.info("pasted layer %r into GIMP near (%s, %s)", layer_name, x, y)
        return None if "ok" in result else f"unexpected GIMP response: {result}"
