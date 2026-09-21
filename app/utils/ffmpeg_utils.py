"""Cross-platform ffmpeg discovery.

Every ffmpeg call in the project goes through here so that a Windows dev box
and an Ubuntu server resolve the binary the same way, and so a missing install
is reported once, clearly, at startup rather than as a wall of per-clip
failures in production.

Resolution order:
  1. FFMPEG_PATH from tb_interview_configuration or the environment.
  2. PATH lookup.
  3. Well-known absolute locations per platform.

The result is cached, because PATH lookups run per clip otherwise and the
answer cannot change without a restart.
"""

import logging
import os
import platform
import shutil
import subprocess
import threading

logger = logging.getLogger(__name__)

# Checked when PATH is unhelpful. Services started by systemd frequently
# inherit a minimal PATH that omits /usr/local/bin, which is exactly where a
# manually built ffmpeg tends to land.
_LINUX_CANDIDATES = (
    "/usr/bin/ffmpeg",
    "/usr/local/bin/ffmpeg",
    "/snap/bin/ffmpeg",
    "/opt/ffmpeg/bin/ffmpeg",
    "/usr/local/ffmpeg/bin/ffmpeg",
)

_WINDOWS_CANDIDATES = (
    r"C:\ffmpeg\bin\ffmpeg.exe",
    r"C:\Program Files\ffmpeg\bin\ffmpeg.exe",
    r"C:\ProgramData\chocolatey\bin\ffmpeg.exe",
)

_MACOS_CANDIDATES = (
    "/opt/homebrew/bin/ffmpeg",
    "/usr/local/bin/ffmpeg",
)

_lock = threading.Lock()
_cached_path = None
_resolution_logged = False


class FFmpegNotFound(RuntimeError):
    """Raised when no usable ffmpeg binary can be located."""


def _platform_candidates():
    system = platform.system()
    if system == "Windows":
        return _WINDOWS_CANDIDATES
    if system == "Darwin":
        return _MACOS_CANDIDATES
    return _LINUX_CANDIDATES


def _is_executable(path: str) -> bool:
    if not path:
        return False
    # os.access with X_OK is meaningless on Windows, so only the file check
    # applies there.
    if platform.system() == "Windows":
        return os.path.isfile(path)
    return os.path.isfile(path) and os.access(path, os.X_OK)


def _configured_path():
    """FFMPEG_PATH from config, falling back to the environment.

    Imported lazily: this module is used by workers that may load before the
    DB-backed config has been read.
    """
    try:
        from app.core import config as consts

        configured = getattr(consts, "FFMPEG_PATH", "") or ""
    except Exception:
        configured = ""
    return configured.strip() or os.environ.get("FFMPEG_PATH", "").strip()


def resolve(refresh: bool = False) -> str:
    """Return an absolute path to ffmpeg, or raise FFmpegNotFound."""
    global _cached_path, _resolution_logged

    with _lock:
        if _cached_path and not refresh:
            return _cached_path

        tried = []

        configured = _configured_path()
        if configured:
            if _is_executable(configured):
                _cached_path = configured
            else:
                # Explicit configuration that does not work is worth shouting
                # about rather than silently falling through to PATH.
                logger.warning(
                    f"FFMPEG_PATH is set to '{configured}' but that is not an "
                    "executable file; falling back to PATH lookup."
                )
                tried.append(f"FFMPEG_PATH={configured}")

        if not _cached_path:
            found = shutil.which("ffmpeg")
            if found:
                _cached_path = found
            else:
                tried.append("PATH")

        if not _cached_path:
            for candidate in _platform_candidates():
                if _is_executable(candidate):
                    _cached_path = candidate
                    break
                tried.append(candidate)

        if not _cached_path:
            raise FFmpegNotFound(
                "ffmpeg could not be found. Install it "
                "(Ubuntu: `sudo apt-get install -y ffmpeg`), or set FFMPEG_PATH "
                "in tb_interview_configuration or the environment. "
                f"Looked in: {', '.join(tried)}"
            )

        if not _resolution_logged:
            logger.info(f"ffmpeg resolved to: {_cached_path}")
            _resolution_logged = True

        return _cached_path


def version(timeout: int = 10) -> str:
    """Run `ffmpeg -version` and return its first line."""
    proc = subprocess.run(
        [resolve(), "-version"], capture_output=True, timeout=timeout
    )
    if proc.returncode != 0:
        raise FFmpegNotFound(
            "ffmpeg was found but did not run: "
            f"{proc.stderr.decode('utf-8', 'replace')[:300]}"
        )
    return proc.stdout.decode("utf-8", "replace").splitlines()[0]


def verify_at_startup(required: bool = False) -> bool:
    """Probe ffmpeg during boot so a missing binary surfaces immediately.

    Returns True when ffmpeg is usable. With `required=False` a failure is
    logged loudly but does not stop the process: the rest of the workers are
    unaffected by ffmpeg being absent, and taking the whole service down over
    an optional analysis feature would be a worse production outcome than
    running without it.
    """
    try:
        logger.info(f"ffmpeg check: {version()}")
        return True
    except Exception as e:
        message = (
            f"ffmpeg is NOT available ({e}). Answer-clip A/V proctoring and the "
            "audio fallback decoder will not work. "
            "Install with `sudo apt-get install -y ffmpeg` on Ubuntu, or set "
            "FFMPEG_PATH."
        )
        if required:
            logger.critical(message)
            raise
        logger.error(message)
        return False


def run(args, timeout: int = 300, check: bool = True):
    """Run ffmpeg with the given arguments (excluding the binary itself).

    Always invoked as an argument list with no shell, so paths containing
    spaces are safe on both platforms.
    """
    # -hide_banner keeps the multi-kilobyte build configuration out of stderr.
    # Without it the real error scrolls off the end of any truncated message
    # and a failure reads as a wall of --enable-* flags.
    cmd = [resolve(), "-hide_banner"] + list(args)
    proc = subprocess.run(cmd, capture_output=True, timeout=timeout)
    if check and proc.returncode != 0:
        stderr = proc.stderr.decode("utf-8", "replace").strip()
        # The operative line is last; keep the tail but drop progress spam.
        lines = [ln for ln in stderr.splitlines() if ln.strip()][-6:]
        raise RuntimeError(
            f"ffmpeg failed (exit {proc.returncode}): " + " | ".join(lines)
        )
    return proc
