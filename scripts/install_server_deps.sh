#!/usr/bin/env bash
# System dependencies for running this service on a headless Ubuntu/Debian host.
#
#   sudo bash scripts/install_server_deps.sh
#
# Then, in the virtualenv:  pip install -r requirements.txt
#
# WHY THESE ARE NEEDED
# --------------------
# ffmpeg            demuxes answer clips (app/utils/ffmpeg_utils.py) and is the
#                   fallback decoder for answer audio.
# libgl1,           OpenCV's Python wheel links against libGL and glib even for
# libglib2.0-0      purely offscreen work. A minimal server image has neither,
#                   and `import cv2` then fails with
#                   "libGL.so.1: cannot open shared object file", which takes
#                   down run_workers.py entirely - not just A/V proctoring.
#
# Why not use the *-headless OpenCV wheels instead, which need no system libs:
# mediapipe requires `opencv-contrib-python` by name, and ultralytics, deepface
# and retina-face require `opencv-python`. A headless distribution has a
# different name, so it does not satisfy them - pip reinstalls the GUI build as
# a transitive dependency (unpinned, so it also jumps major version) and the
# headless install is silently overwritten. Verified, not assumed.
#
# Forcing headless afterwards does work at runtime, but leaves `pip check`
# reporting a broken dependency and means any later `pip install -r
# requirements.txt` silently re-breaks the host. Installing two system
# libraries is the stable option.

set -euo pipefail

if [[ "${EUID}" -ne 0 ]]; then
  echo "Run with sudo: sudo bash scripts/install_server_deps.sh" >&2
  exit 1
fi

echo "==> Updating package lists"
apt-get update -qq

echo "==> Installing ffmpeg and OpenCV runtime libraries"
apt-get install -y --no-install-recommends \
  ffmpeg \
  libgl1 \
  libglib2.0-0

echo
echo "==> Verifying"
if ! command -v ffmpeg >/dev/null 2>&1; then
  echo "FAILED: ffmpeg is still not on PATH" >&2
  exit 1
fi
ffmpeg -hide_banner -version | head -1

python3 - <<'PY'
import sys
try:
    import cv2
    print(f"cv2 {cv2.__version__} imports cleanly")
except ImportError as e:
    # Only meaningful once requirements.txt has been installed; before that a
    # missing module is expected rather than a failure of this script.
    if "libGL" in str(e) or "libgthread" in str(e) or "libxcb" in str(e):
        print(f"FAILED: OpenCV still cannot load a system library: {e}", file=sys.stderr)
        sys.exit(1)
    print(f"(cv2 not installed yet: {e})")
PY

echo
echo "Done. Next: pip install -r requirements.txt"
echo "Then check ffmpeg resolution with:"
echo "  python -c \"from app.utils import ffmpeg_utils; print(ffmpeg_utils.version())\""
