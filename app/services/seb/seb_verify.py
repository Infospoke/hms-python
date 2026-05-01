import hashlib
import logging
from fastapi import Request, HTTPException, status
from app.core import config as consts

logger = logging.getLogger(__name__)


async def verify_seb(request: Request):

    # --- DEV_MODE bypass ---
    dev_mode = str(getattr(consts, "DEV_MODE", "false")).lower() == "true"
    if dev_mode:
        logger.warning("DEV_MODE is ON — SEB verification bypassed for this request.")
        return True

    seb_header = request.headers.get("X-SafeExamBrowser-RequestHash")
    if not seb_header:
        logger.warning(
            f"SEB header missing. Origin: {request.headers.get('origin', 'N/A')} | "
            f"URL: {str(request.url)} | Method: {request.method}"
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Request must come from Safe Exam Browser.",
        )

    full_url = str(request.url)
    browser_exam_key = consts.SEB_BROWSER_EXAM_KEY

    expected_hash = hashlib.sha256((full_url + browser_exam_key).encode()).hexdigest()

    if seb_header != expected_hash:
        logger.warning(
            f"SEB Hash mismatch.\n"
            f"  URL seen by backend : {full_url}\n"
            f"  Received hash       : {seb_header}\n"
            f"  Expected hash       : {expected_hash}\n"
            f"  BrowserExamKey len  : {len(browser_exam_key)} chars\n"
            f"  Tip: if URL contains 'localhost' but SEB used the IP, hashes will never match."
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="SEB configuration mismatch or invalid request hash.",
        )

    return True
