# -*- coding: UTF-8 -*-
"""
Windows toast notifications via PowerShell + WinRT.

No third-party dependency. The payload is passed as base64 and decoded inside
the script, so notification text can never break out into PowerShell syntax.
"""

import base64
import subprocess
import sys
from xml.sax.saxutils import escape

# Toasts must be shown under a registered AppUserModelID; PowerShell's own is
# always present on Windows 10/11.
APP_ID = r"{1AC14E77-02E7-4E5D-B744-2EB1AE5198B7}\WindowsPowerShell\v1.0\powershell.exe"

_SCRIPT = r"""
$ErrorActionPreference = 'Stop'
[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] | Out-Null
[Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom, ContentType = WindowsRuntime] | Out-Null
$xml = [System.Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('{payload}'))
$doc = [Windows.Data.Xml.Dom.XmlDocument]::new()
$doc.LoadXml($xml)
$toast = [Windows.UI.Notifications.ToastNotification]::new($doc)
[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier('{app_id}').Show($toast)
"""


def _build_xml(title: str, lines: list[str]) -> str:
    body = escape("\n".join(lines))
    return (
        '<toast duration="long"><visual><binding template="ToastGeneric">'
        f"<text>{escape(title)}</text><text>{body}</text>"
        "</binding></visual></toast>"
    )


def send_toast(title: str, lines: list[str]) -> bool:
    """Show a Windows toast. Returns False (without raising) if it cannot be shown."""
    if sys.platform != "win32":
        print("[Notify] Toast skipped — not running on Windows")
        return False

    payload = base64.b64encode(_build_xml(title, lines).encode("utf-8")).decode("ascii")
    script = _SCRIPT.replace("{payload}", payload).replace("{app_id}", APP_ID)
    encoded = base64.b64encode(script.encode("utf-16-le")).decode("ascii")

    try:
        result = subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-EncodedCommand", encoded],
            capture_output=True,
            text=True,
            timeout=30,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except Exception as e:
        print(f"[Notify] Toast failed: {e}")
        return False

    if result.returncode != 0:
        print(f"[Notify] Toast failed (exit {result.returncode}): {result.stderr.strip()}")
        return False
    return True
