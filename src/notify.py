"""Windows 系統通知（toast）。
使用內建的 Windows.UI.Notifications，不需額外安裝套件。
非 Windows 平台會直接 no-op。
"""
import platform
import subprocess


def notify(title: str, message: str) -> None:
    if platform.system() != "Windows":
        return

    title_safe = title.replace("'", "''")
    message_safe = message.replace("'", "''")

    script = f"""
$ErrorActionPreference = 'SilentlyContinue'
[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType=WindowsRuntime] | Out-Null
[Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom.XmlDocument, ContentType=WindowsRuntime] | Out-Null
$template = [Windows.UI.Notifications.ToastNotificationManager]::GetTemplateContent([Windows.UI.Notifications.ToastTemplateType]::ToastText02)
$texts = $template.GetElementsByTagName('text')
$null = $texts.Item(0).AppendChild($template.CreateTextNode('{title_safe}'))
$null = $texts.Item(1).AppendChild($template.CreateTextNode('{message_safe}'))
$toast = [Windows.UI.Notifications.ToastNotification]::new($template)
[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier('Readmoo Sync').Show($toast)
"""
    try:
        subprocess.run(
            ["powershell", "-NoProfile", "-WindowStyle", "Hidden", "-Command", script],
            timeout=15,
            capture_output=True,
        )
    except Exception:
        # 通知失敗不該讓主程式崩潰
        pass
