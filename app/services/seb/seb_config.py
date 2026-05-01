import plistlib
from app.core import config as consts
from urllib.parse import urlparse


def build_seb_config(session_id: str, interview_url: str, hashed_exam_exit_password: str) -> bytes:
    interview_domain = urlparse(interview_url).netloc
    base_domain = urlparse(consts.BASE_URL).netloc

    config = {
        "startURL": interview_url,
        "restartExamURL": f"{consts.BASE_URL}/api/seb/join/{session_id}",
        "restartExamText": "Restart Interview",
        "quitURL": f"{consts.HOST}/interview/submitted",
        "browserExamKey": consts.SEB_BROWSER_EXAM_KEY,
        "sendBrowserExamKey": True,
        "sendConfigKey": False,
        "URLFilterEnable": True,
        "URLFilterEnableContentFilter": False,
        "allowedURLs": [
            {"address": consts.BASE_URL, "includeSubdomains": True},
            {"address": f"https://{interview_domain}", "includeSubdomains": True},
            {"address": consts.HOST, "includeSubdomains": True},
        ],
        "prohibitedProcesses": [
            {
                "executable": "Slack",
                "identifier": "com.tinyspeck.slackmacgap",
                "active": True,
            },
            {"executable": "Discord", "identifier": "com.hnc.Discord", "active": True},
            {"executable": "Zoom", "identifier": "us.zoom.xos", "active": True},
            {
                "executable": "Teams",
                "identifier": "com.microsoft.teams",
                "active": True,
            },
            {
                "executable": "ms-teams",
                "identifier": "com.microsoft.teams2",
                "active": True,
            },
            {
                "executable": "OBS",
                "identifier": "com.obsproject.obs-studio",
                "active": True,
            },
            {
                "executable": "obs64",
                "identifier": "com.obsproject.obs-studio",
                "active": True,
            },
            {
                "executable": "AnyDesk",
                "identifier": "com.philandro.anydesk",
                "active": True,
            },
            {
                "executable": "TeamViewer",
                "identifier": "com.teamviewer.TeamViewer",
                "active": True,
            },
            {"executable": "chrome", "identifier": "com.google.Chrome", "active": True},
            {
                "executable": "firefox",
                "identifier": "org.mozilla.firefox",
                "active": True,
            },
            {
                "executable": "msedge",
                "identifier": "com.microsoft.edgemac",
                "active": True,
            },
            {
                "executable": "Telegram",
                "identifier": "ru.keepcoder.Telegram",
                "active": True,
            },
            {
                "executable": "WhatsApp",
                "identifier": "net.whatsapp.WhatsApp",
                "active": True,
            },
            {"executable": "Skype", "identifier": "com.skype.skype", "active": True},
            {
                "executable": "VNC Viewer",
                "identifier": "com.realvnc.vncviewer",
                "active": True,
            },
            {
                "executable": "parsec",
                "identifier": "com.parsecgaming.parsec",
                "active": True,
            },
            {
                "executable": "rustdesk",
                "identifier": "com.rustdesk.rustdesk",
                "active": True,
            },
            {
                "executable": "Camtasia",
                "identifier": "com.techsmith.camtasia",
                "active": True,
            },
            {"executable": "ShareX", "active": True},
            {
                "executable": "Gyazo",
                "identifier": "com.gyazo.gyazo",
                "active": True,
            },
            {
                "executable": "Loom",
                "identifier": "com.loom.desktop",
                "active": True,
            },
        ],
        "allowSwitchToApplications": False,
        "showTaskBar": False,
        "showMenuBar": False,
        "enableRightMouse": False,
        "showReloadButton": False,
        "showBackForwardButtons": False,
        "showZoomButtons": False,
        "showTimeInTaskBar": False,
        "touchOptimized": False,
        "blockScreenCapture": True,
        "enablePrintScreen": False,
        "allowScreenSharing": False,
        "allowDisplayMirroring": False,
        "allowedDisplaysMaxNumber": 1,
        "allowVirtualMachine": False,
        "detectStoppedProcess": True,
        "terminateProcesses": True,
        "enableZoomPage": False,
        "enableZoomText": False,
        "allowSpellCheck": False,
        "allowDictionary": False,
        "allowFind": False,
        "enableBrowserWindowToolbar": False,
        "hideBrowserWindowToolbar": True,
        "enableAltMouseWheel": False,
        "enableBrowserWindowZoom": False,
        "enableEsc": False,
        "enableCtrlEsc": False,
        "enableAltEsc": False,
        "enableAltTab": False,
        "enableAltF4": True,
        "enableStartMenu": False,
        "enableRightMouse": False,
        "allowQuit": True,
        "hashedQuitPassword": hashed_exam_exit_password,
        "ignoreExitShortcut": True,
        # Enable DevTools inside SEB only when DEV_MODE is on — helps debug API issues
        "showDevelopmentTools": str(getattr(consts, "DEV_MODE", "false")).lower() == "true",
    }

    return plistlib.dumps(config)
