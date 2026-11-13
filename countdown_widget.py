#!/usr/bin/env python3
"""独立倒计时挂件：显示距离 mower 下次任务的剩余时间，并在临界点弹桌面通知。

数据来自 mower Web 服务的 /status 接口，该接口要求当前实例的访问令牌：
先在 mower 设置里填写 Web UI token，再用右键菜单「设置令牌…」或 --token 填同一个值。

端口默认自动发现：扫描实例登记文件（<数据目录>/tmp/updates/*/instances/*.json，
兼容旧布局 <数据目录>/updates/*/instances/*.json），按心跳时间优先连接能响应的实例。
数据目录取 %LOCALAPPDATA%/arknights-mower、程序自身目录及当前工作目录；
也可以用 --port 手动指定，指定的端口连不上时仍会回退到自动发现。

功能：
- 置顶小窗（带系统标题栏，可最小化/关闭），实时倒计时（休眠中）/ 工作中 / 未运行；
- 剩余 60 / 30 / 10 秒时弹 Windows 系统通知 + 提示音 + 窗口闪烁（阈值可用
  --thresholds 自定义），最后 10 秒倒计时数字平滑循环变色；
- 显示下次任务名与时间；窗口可拖动（位置自动记忆），右键菜单可测试通知、
  设置服务器、设置访问令牌、开关置顶/声音或退出；
- 支持 HTTP / HTTPS：目标写成 https://host:port 即走 TLS（先试 http、失败再试
  https），自签名证书可勾选「忽略证书校验」（等价 curl -k）。

用法：
    python countdown_widget.py                 # 自动发现正在运行的实例
    python countdown_widget.py --port 58000    # 指定端口
    python countdown_widget.py --token <令牌>  # 指定 mower 的 Web UI token
    python countdown_widget.py --host https://192.168.1.5:8443 --insecure
    pythonw countdown_widget.py                # 无控制台窗口启动
"""

from __future__ import annotations

import argparse
import base64
import colorsys
import ctypes
import datetime
import http.client
import json
import math
import os
import shutil
import ssl
import subprocess
import sys
import threading
import time
import tkinter as tk
import tkinter.font as tkfont
import traceback
import urllib.parse
from pathlib import Path
from tkinter import messagebox, simpledialog

IS_WINDOWS = sys.platform == "win32"
if IS_WINDOWS:
    import winreg
    import winsound

POWERSHELL = shutil.which("powershell.exe") or "powershell.exe"
STATE_PATH = Path.home() / ".mower-countdown.json"
LOG_PATH = Path.home() / ".mower-countdown.log"
APP_ID = "Mower.Countdown"
DEFAULT_THRESHOLDS = (60, 30, 10)
RAINBOW_SECONDS = 60  # 最后一分钟内倒计时数字循环变色
TASK_NAME_WIDTH = 30  # 队列行显示宽度（中文按 2 计），完整内容悬停可看
RAINBOW_SPEED = 0.35  # 彩虹色循环速度（圈/秒）
STALE_RECORD_SECONDS = 120  # 超过这个时间没有心跳的实例登记视为残留

# --- 主题（深色 / 浅色 / 跟随系统） ---

THEMES = {
    "dark": {
        "bg": "#2b2e3b",
        "fg": "#eceff4",
        "sub": "#949cb0",
        "task": "#d8dee9",
        "ok": "#a3be8c",
        "warn": "#ebcb8b",
        "flash": "#d08770",
        "close": "#d07079",
        "tip_bg": "#404659",
        "tip_fg": "#eceff4",
        "border": "#404659",
        "tip_border": "#4a5268",
        "time": "#88c0d0",
        "chip_bg": "#353a4a",
        "chip_border": "#4a5268",
    },
    "light": {
        "bg": "#f5f7fb",
        "fg": "#2a303c",
        "sub": "#6c768a",
        "task": "#434c5e",
        "ok": "#2e7d5b",
        "warn": "#c47222",
        "flash": "#f0d7a3",
        "close": "#c93850",
        "tip_bg": "#ffffff",
        "tip_fg": "#2a303c",
        "border": "#d8dfea",
        "tip_border": "#cbd5e4",
        "time": "#45689c",
        "chip_bg": "#e9eef6",
        "chip_border": "#cbd5e4",
    },
}

THEME_LABELS = (("system", "跟随系统"), ("dark", "深色"), ("light", "浅色"))

# 当前调色板。apply_theme() 会就地更新这些常量，界面代码直接引用即可。
BG = THEMES["dark"]["bg"]
FG = THEMES["dark"]["fg"]
SUB = THEMES["dark"]["sub"]
TASK_FG = THEMES["dark"]["task"]
OK = THEMES["dark"]["ok"]
WARN = THEMES["dark"]["warn"]
FLASH = THEMES["dark"]["flash"]
CLOSE_HOVER = THEMES["dark"]["close"]
TIP_BG = THEMES["dark"]["tip_bg"]
TIP_FG = THEMES["dark"]["tip_fg"]
BORDER = THEMES["dark"]["border"]
TIP_BORDER = THEMES["dark"]["tip_border"]
TIME_FG = THEMES["dark"]["time"]
CHIP_BG = THEMES["dark"]["chip_bg"]
CHIP_BORDER = THEMES["dark"]["chip_border"]

STATUS_TEXT = {"stopped": "未运行", "sleeping": "休眠中", "working": "工作中"}


def system_theme() -> str:
    """读注册表判断系统当前的应用主题（浅色 / 深色）。"""
    if IS_WINDOWS:
        try:
            with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"SOFTWARE\Microsoft\Windows\CurrentVersion\Themes\Personalize",
            ) as key:
                light = winreg.QueryValueEx(key, "AppsUseLightTheme")[0]
            return "light" if light else "dark"
        except OSError:
            pass
    return "dark"


def resolve_theme(preference: str) -> str:
    """把「跟随系统」解析成具体主题名。"""
    if preference in THEMES:
        return preference
    return system_theme()


def apply_theme(name: str):
    """按主题名更新模块级颜色常量（界面随后重绘即为新配色）。"""
    global BG, FG, SUB, TASK_FG, OK, WARN, FLASH, CLOSE_HOVER
    global TIP_BG, TIP_FG, BORDER, TIP_BORDER, TIME_FG, CHIP_BG, CHIP_BORDER
    palette = THEMES.get(name, THEMES["dark"])
    BG = palette["bg"]
    FG = palette["fg"]
    SUB = palette["sub"]
    TASK_FG = palette["task"]
    OK = palette["ok"]
    WARN = palette["warn"]
    FLASH = palette["flash"]
    CLOSE_HOVER = palette["close"]
    TIP_BG = palette["tip_bg"]
    TIP_FG = palette["tip_fg"]
    BORDER = palette["border"]
    TIP_BORDER = palette["tip_border"]
    TIME_FG = palette["time"]
    CHIP_BG = palette["chip_bg"]
    CHIP_BORDER = palette["chip_border"]


# --- 小工具函数 ---


def enable_dpi_awareness():
    """Windows 高分屏下让窗口保持清晰。"""
    if not IS_WINDOWS:
        return
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass


def resource_path(name: str) -> Path:
    """定位随程序分发的资源：打包后取解包目录，源码运行取脚本同级目录。"""
    base = getattr(sys, "_MEIPASS", None)
    if base:
        return Path(base) / name
    return Path(__file__).resolve().parent / name


def window_scale(root: tk.Tk) -> float:
    """窗口所在显示器的缩放系数（96 DPI = 1.0）。"""
    if IS_WINDOWS:
        try:
            hwnd = int(root.wm_frame(), 16)
            return max(1.0, ctypes.windll.user32.GetDpiForWindow(hwnd) / 96)
        except Exception:
            pass
    return 1.0


def _data_roots():
    """可能存放 mower 数据目录的位置，供实例登记扫描使用。

    打包版把数据放在程序目录（便携布局），开发时就在仓库根目录，macOS 放在
    Application Support，因此这里同时看环境变量、程序自身目录和工作目录，
    并向上多找两级，覆盖「挂件放在安装目录的子目录里」的情况。
    """
    seeds = []
    for name in ("LOCALAPPDATA", "APPDATA"):
        value = os.environ.get(name)
        if value:
            seeds.append(Path(value) / "arknights-mower")
    anchors = [Path(__file__).resolve().parent, Path.cwd()]
    if sys.executable:
        anchors.insert(0, Path(sys.executable).resolve().parent)
    for anchor in anchors:
        for candidate in (anchor, anchor.parent, anchor.parent.parent):
            seeds.append(candidate)
            seeds.append(candidate / "arknights-mower")
    roots = []
    seen = set()
    for seed in seeds:
        try:
            normalized = seed.resolve()
        except OSError:
            continue
        if normalized in seen:
            continue
        seen.add(normalized)
        roots.append(normalized)
    return roots


def instance_records():
    """遍历 mower 的实例注册文件，返回所有带端口的记录。"""
    records = []
    for root in _data_roots():
        for parent in (root / "tmp" / "updates", root / "updates"):
            for path in sorted(parent.glob("*/instances/*.json")):
                try:
                    record = json.loads(path.read_text(encoding="utf-8"))
                except (OSError, ValueError):
                    continue
                if isinstance(record, dict) and isinstance(record.get("port"), int):
                    records.append(record)
    return records


def discover_ports():
    """候选端口列表，最近有心跳的实例排在前面。"""
    now = time.time()
    fresh = []
    stale = []
    for record in instance_records():
        port = record["port"]
        if not 0 < port < 65536:
            continue
        heartbeat = float(record.get("heartbeat") or 0)
        target = fresh if now - heartbeat <= STALE_RECORD_SECONDS else stale
        target.append((heartbeat, port))
    rows = fresh or stale
    rows.sort(key=lambda item: item[0], reverse=True)
    return [port for _, port in rows]


def format_left(left: float) -> str:
    """把剩余秒数格式化为 mm:ss 或 h:mm:ss。"""
    seconds = max(0, math.ceil(left))
    if seconds >= 3600:
        hours, rem = divmod(seconds, 3600)
        minutes, secs = divmod(rem, 60)
        return f"{hours}:{minutes:02d}:{secs:02d}"
    minutes, secs = divmod(seconds, 60)
    return f"{minutes:02d}:{secs:02d}"


def humanize_threshold(seconds: int) -> str:
    if seconds >= 60 and seconds % 60 == 0:
        return f"{seconds // 60} 分钟"
    return f"{seconds} 秒"


def shorten(text: str, width: int) -> str:
    """按显示宽度截断（中文按 2 个字符计），超出部分用省略号。"""
    total = 0
    for index, char in enumerate(text):
        total += 2 if ord(char) > 0x2E80 else 1
        if total > width:
            return text[:index] + "…"
    return text


def clock_text(stamp: str) -> str:
    """把 /status 的时间戳压成 HH:MM；跨天时加「+N天」前缀。"""
    day, _, clock = stamp.partition(" ")
    clock = clock[:5]
    if not clock:
        return ""
    try:
        target = datetime.date.fromisoformat(day)
    except ValueError:
        return clock
    ahead = (target - datetime.date.today()).days
    return clock if ahead <= 0 else f"+{ahead}天 {clock}"


def queue_line(when: str, name: str, width: int) -> str:
    """队列行的显示文本：后续任务行把时间放最前（下次任务的时间在状态行）。"""
    return shorten(f"{when} {name}".strip() if when else name, width)


def queue_detail(when: str, name: str, when2: str, name2: str) -> str:
    """悬停提示与右键复制的完整队列说明（窗口内只显示截断后的一行）。"""
    lines = []
    for stamp, text in ((when, name), (when2, name2)):
        if not text and not stamp:
            continue
        lines.append(f"{stamp} {text}".strip())
    return "\n".join(lines)


def wrap_lines(text: str, width: int = 52) -> list[str]:
    """按显示宽度把多行文本切分成适合逐行渲染的单行列表（中文按 2 计）。"""
    lines: list[str] = []
    for paragraph in str(text).splitlines():
        if not paragraph:
            lines.append("")
            continue
        buf: list[str] = []
        used = 0
        for char in paragraph:
            char_w = 2 if ord(char) > 0x2E80 else 1
            if buf and used + char_w > width:
                lines.append("".join(buf))
                buf = [char]
                used = char_w
            else:
                buf.append(char)
                used += char_w
        if buf:
            lines.append("".join(buf))
    return lines


def rainbow_color(phase: float) -> str:
    """按相位取一个高亮彩虹色（深色背景上足够醒目）。"""
    red, green, blue = colorsys.hsv_to_rgb(phase % 1.0, 0.85, 1.0)
    return f"#{int(red * 255):02x}{int(green * 255):02x}{int(blue * 255):02x}"


def load_settings() -> dict:
    try:
        data = json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def log_line(message: str):
    """把关键事件追加到日志文件，方便无控制台时排查（>256KB 时重写）。"""
    try:
        if LOG_PATH.exists() and LOG_PATH.stat().st_size > 256 * 1024:
            LOG_PATH.unlink(missing_ok=True)
        stamp = time.strftime("%Y-%m-%d %H:%M:%S")
        with LOG_PATH.open("a", encoding="utf-8") as stream:
            stream.write(f"{stamp} {message}\n")
    except OSError:
        pass


def install_exception_logging(root: tk.Misc | None = None):
    """把未捕获异常写进日志，方便无控制台运行时定位崩溃。"""

    def handle(exc_type, exc, tb):
        log_line(
            "未捕获异常：" + "".join(traceback.format_exception(exc_type, exc, tb))
        )

    sys.excepthook = handle
    if root is not None:
        root.report_callback_exception = handle


def save_settings(**updates):
    data = load_settings()
    data.update(updates)
    try:
        STATE_PATH.write_text(json.dumps(data), encoding="utf-8")
    except OSError:
        pass


def parse_endpoint(text: str):
    """解析地址文本为 (host, port, secure)。

    接受「58000」/「127.0.0.1:58000」/「http://host:58000」/「https://host」，
    带协议但省略端口时用默认端口（https=443 / http=80）。

    返回 (None, None, None) 表示输入无效；
    返回 (host, None, secure) 表示改回自动发现端口；
    secure 为 None 表示没指定协议（连接时先试 http，失败再试 https）。
    """
    value = text.strip()
    if not value:
        return "127.0.0.1", None, None
    secure = None
    if "://" in value:
        scheme, _, value = value.partition("://")
        scheme = scheme.strip().lower()
        if scheme in ("http", "https"):
            secure = scheme == "https"
        # 只保留主机部分：路径（/status）由请求固定，不需要用户填
        value = value.strip("/").split("/", 1)[0].strip()
        if not value:
            return "127.0.0.1", None, secure
    if ":" in value:
        host, _, port_text = value.rpartition(":")
        host = host.strip() or "127.0.0.1"
        if host.startswith("[") and host.endswith("]"):
            host = host[1:-1]  # IPv6 字面量：[::1]:8443 → ::1
    elif secure is None:
        host, port_text = "127.0.0.1", value  # 只写了端口
    else:
        host, port_text = value, str(443 if secure else 80)  # 带协议但省了端口
    try:
        port = int(port_text)
    except ValueError:
        return None, None, None
    if not 0 < port < 65536:
        return None, None, None
    return host, port, secure


def toast_script(
    title: str, message: str, app_id: str = APP_ID, with_sound: bool = True
) -> str:
    """生成 PowerShell 脚本：确保 AppUserModelID 已注册后弹出一条 Toast。

    未注册的 AppUserModelID 会被 Windows 静默处理——通知只进通知中心，不弹横幅，
    因此每次发送前先在当前用户下补好注册表项（DisplayName/IconUri）。
    通知本身用 duration="long" 让横幅停留更久，并按设置附带提示音。
    脚本以 UTF-16LE Base64 通过 powershell.exe -EncodedCommand 执行。
    """

    def escape(text: str) -> str:
        return (
            str(text)
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;")
            .replace("'", "''")
        )

    audio = (
        '<audio src="ms-winsoundevent:Notification.Reminder"/>'
        if with_sound
        else '<audio silent="true"/>'
    )
    xml = (
        '<toast duration="long"><visual><binding template="ToastGeneric">'
        f"<text>{escape(title)}</text><text>{escape(message)}</text>"
        f"</binding></visual>{audio}</toast>"
    )
    icon = str(Path(sys.executable))
    return (
        '$ErrorActionPreference = "Stop"\n'
        '$ProgressPreference = "SilentlyContinue"\n'
        f'$appId = "{app_id}"\n'
        '$key = "HKCU:\\SOFTWARE\\Classes\\AppUserModelId\\$appId"\n'
        "New-Item -Path $key -Force > $null\n"
        'Set-ItemProperty -Path $key -Name "DisplayName" -Value "Mower 倒计时"\n'
        f'Set-ItemProperty -Path $key -Name "IconUri" -Value "{icon}"\n'
        "[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications,"
        " ContentType = WindowsRuntime] > $null\n"
        "[Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom.XmlDocument,"
        " ContentType = WindowsRuntime] > $null\n"
        "$xml = New-Object Windows.Data.Xml.Dom.XmlDocument\n"
        f"$xml.LoadXml('{xml}')\n"
        "$toast = New-Object Windows.UI.Notifications.ToastNotification $xml\n"
        "[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier("
        "$appId).Show($toast)\n"
        'Write-Output "TOAST_OK"\n'
    )


# --- 状态轮询 ---


class AuthRequired(Exception):
    """状态接口要求访问令牌（HTTP 403）。"""


class StatusPoller(threading.Thread):
    """后台线程：轮询 /status 维护快照；断线时自动重新发现端口。"""

    def __init__(
        self,
        host="127.0.0.1",
        port=None,
        interval=1.0,
        verbose=False,
        secure: bool | None = None,
        insecure: bool = False,
        token: str = "",
    ):
        super().__init__(daemon=True, name="mower-status-poller")
        self.host = host
        self.fixed_port = port
        self.interval = max(0.2, float(interval))
        self.verbose = verbose
        # secure=None 表示自动：先按 http 试，失败再用 https
        self.secure = secure
        self.insecure = insecure  # True = 不校验证书（自签名证书）
        self.token = (token or "").strip()
        self.auth_failed = False  # 最近一次连接是否因缺少/错误令牌被拒绝
        self.snapshot: dict | None = None
        self.endpoint: int | None = None
        self.endpoint_secure = False
        self._ssl_context: ssl.SSLContext | None = None
        self._wake = threading.Event()
        self.avatar_size = 20
        self._avatars: dict[tuple[str, int], str] = {}
        self._missing_avatars: set[tuple[str, int]] = set()
        self._avatar_lock = threading.Lock()

    def set_avatar_size(self, size: int):
        """设置需要的圆形头像像素尺寸（由界面按 DPI 缩放更新）。"""
        self.avatar_size = max(16, min(48, int(size)))

    def get_avatar(self, name: str, size: int) -> str | None:
        """线程安全地读取已缓存的 Base64 PNG 圆形头像。"""
        with self._avatar_lock:
            return self._avatars.get((name, int(size)))

    def reset(self):
        """请求立即重新发现端口（右键菜单「重新连接」）。"""
        self._wake.set()

    def configure(
        self,
        host: str,
        port: int | None,
        secure: bool | None = None,
        insecure: bool | None = None,
        token: str | None = None,
    ):
        """运行时切换目标服务器（右键菜单「设置服务器…」）。

        secure=None 表示「自动」；insecure=None 与 token=None 表示保持原值不变。
        """
        self.host = host
        self.fixed_port = port
        self.secure = secure
        if token is not None:
            self.token = token.strip()
        if insecure is not None:
            self.insecure = bool(insecure)
            self._ssl_context = None
        self.endpoint = None
        self.endpoint_secure = False
        self.snapshot = None
        with self._avatar_lock:
            self._avatars.clear()
            self._missing_avatars.clear()
        self._wake.set()

    def _log(self, message: str):
        if self.verbose:
            print(f"[poll] {message}", flush=True)

    def _tls_context(self) -> ssl.SSLContext:
        """HTTPS 用的 SSL 上下文，只在第一次需要时创建（加载根证书较慢）。"""
        if self._ssl_context is None:
            context = ssl.create_default_context()
            if self.insecure:
                # 自签名 / 自建 CA 证书：跳过校验，等价 curl -k
                context.check_hostname = False
                context.verify_mode = ssl.CERT_NONE
            self._ssl_context = context
        return self._ssl_context

    def _request(self, port: int, secure: bool = False, path: str = "/status") -> dict:
        """用标准库发一个 HTTP(S) GET。

        刻意不用 requests：它会把 cryptography/OpenSSL 等一大堆用不到的
        依赖（打包后多出十几 MB）带进绿色版 exe；HTTPS 直接用标准库 ssl。
        """
        if secure:
            connection = http.client.HTTPSConnection(
                self.host, port, timeout=1.3, context=self._tls_context()
            )
        else:
            connection = http.client.HTTPConnection(self.host, port, timeout=1.3)
        try:
            headers = {"token": self.token} if self.token else {}
            connection.request("GET", path, headers=headers)
            response = connection.getresponse()
            body = response.read()
            if response.status == 403:
                raise AuthRequired("状态接口要求访问令牌")
            if response.status != 200:
                raise ValueError(f"状态接口返回 HTTP {response.status}")
        finally:
            connection.close()
        data = json.loads(body.decode("utf-8", "replace"))
        if not isinstance(data, dict):
            raise ValueError("状态接口返回了非 JSON 对象")
        return data

    def _sync_avatars(self, port: int, secure: bool, details: tuple):
        """按需向 /status 拉取队列干员的圆形 PNG 头像并缓存在内存中。"""
        size = max(16, min(48, int(self.avatar_size)))
        needed: list[str] = []
        with self._avatar_lock:
            for detail in details:
                if not isinstance(detail, dict):
                    continue
                for room in detail.get("rooms") or ():
                    for name in room.get("operators") or ():
                        if not name or name == "保持当前":
                            continue
                        key = (name, size)
                        if (
                            key not in self._avatars
                            and key not in self._missing_avatars
                            and name not in needed
                        ):
                            needed.append(name)
        if not needed:
            return
        query = urllib.parse.urlencode(
            {"avatar_size": str(size), "avatars": ",".join(needed[:32])}
        )
        try:
            extra = self._request(port, secure, path=f"/status?{query}")
        except Exception:
            return
        received = extra.get("task_avatars")
        if not isinstance(received, dict):
            return
        with self._avatar_lock:
            if len(self._avatars) > 256:
                self._avatars.clear()
            for name in needed[:32]:
                encoded = received.get(name)
                if isinstance(encoded, str) and encoded:
                    self._avatars[(name, size)] = encoded
                else:
                    self._missing_avatars.add((name, size))

    def _adopt(self, port: int, data: dict, secure: bool = False):
        self.endpoint = port
        self.endpoint_secure = secure
        next_detail = data.get("next_task_detail")
        next_next_detail = data.get("next_next_task_detail")
        self._sync_avatars(port, secure, (next_detail, next_next_detail))
        self.snapshot = {
            "status": data.get("status"),
            "remaining": data.get("remaining_seconds"),
            "next_task": data.get("next_task_time"),
            "next_task_name": data.get("next_task_name"),
            "next_task_detail": next_detail,
            "next_next_task": data.get("next_next_task_time"),
            "next_next_task_name": data.get("next_next_task_name"),
            "next_next_task_detail": next_next_detail,
            "task_count": data.get("task_count"),
            "plan_condition": data.get("plan_condition") or [],
            "received": time.monotonic(),
        }

    def _schemes(self) -> tuple[bool, ...]:
        """本次扫描要尝试的连接方式；secure=None 时先 http 再 https。"""
        if self.secure is None:
            return (False, True)
        return (bool(self.secure),)

    def target_label(self) -> str:
        """当前连接目标的显示文本，如 https://127.0.0.1:58000。"""
        if self.endpoint is None:
            return "?"
        scheme = "https" if self.endpoint_secure else "http"
        return f"{scheme}://{self.host}:{self.endpoint}"

    def _scan(self) -> bool:
        # 先试手动指定的端口，再看实例登记：端口固定值过期时不至于一直连不上
        candidates = [self.fixed_port] if self.fixed_port else []
        candidates.extend(port for port in discover_ports() if port not in candidates)
        denied = False
        for port in candidates:
            for secure in self._schemes():
                try:
                    data = self._request(port, secure)
                except AuthRequired:
                    denied = True
                    self._log(f"端口 {port} 要求访问令牌")
                    continue
                except Exception:
                    continue
                self.auth_failed = False
                self._adopt(port, data, secure)
                label = self.target_label()
                self._log(f"已连接 mower {label}")
                log_line(f"[poll] 已连接 mower {label}")
                return True
        self.auth_failed = denied
        return False

    def run(self):
        failures = 0
        while True:
            if self._wake.is_set():
                self._wake.clear()
                self.endpoint = None
                failures = 0
            try:
                if self.endpoint is not None:
                    self._adopt(
                        self.endpoint,
                        self._request(self.endpoint, self.endpoint_secure),
                        self.endpoint_secure,
                    )
                    self.auth_failed = False
                    failures = 0
                elif self._scan():
                    failures = 0
                else:
                    self.snapshot = None
                    failures += 1
            except AuthRequired:
                if self.endpoint is not None:
                    self._log(f"端口 {self.endpoint} 要求访问令牌")
                self.auth_failed = True
                self.snapshot = None
                failures += 1
                if failures >= 2:
                    self.endpoint = None  # 下轮重新扫描
            except Exception as exc:
                if self.endpoint is not None:
                    self._log(f"端口 {self.endpoint} 连接失败：{exc}")
                self.snapshot = None
                failures += 1
                if failures >= 2:
                    self.endpoint = None  # 下轮重新扫描
            delay = self.interval if failures < 3 else 3.0
            self._wake.wait(timeout=delay)


# --- 界面 ---


class CountdownWidget:
    """置顶小窗 + 临界提醒。"""

    REFRESH_MS = 60  # 高频刷新让彩虹渐变更顺滑

    def __init__(
        self,
        poller: StatusPoller,
        *,
        thresholds=DEFAULT_THRESHOLDS,
        toast=True,
        sound=True,
        verbose=False,
    ):
        self.poller = poller
        self.thresholds = tuple(sorted({int(t) for t in thresholds}, reverse=True))
        self.toast_enabled = toast
        self.verbose = verbose

        self._prev = None
        self._fired: set[int] = set()
        self._cycle = ""
        self._drag = None
        self._toast_error = False
        self._detail_text = ""
        self._last_snapshot = None
        self._photo_cache: dict[tuple[str, int], tk.PhotoImage] = {}
        self._tip = None
        self._tip_job = None
        self._scale = 1.0

        # 主题：先按偏好准备好调色板，再创建控件（创建时就会取到正确颜色）
        self.theme_pref = str(load_settings().get("theme") or "system")
        self._system_theme = system_theme()
        self._theme_check = 0
        apply_theme(resolve_theme(self.theme_pref))

        self.root = tk.Tk()
        self.root.title("Mower 倒计时")
        self.root.configure(bg=BG)
        self.theme_var = tk.StringVar(value=self.theme_pref)
        install_exception_logging(self.root)
        try:
            self.root.attributes("-topmost", True)
        except tk.TclError:
            pass
        icon = resource_path("countdown_widget.ico")
        if icon.exists():
            try:
                self.root.iconbitmap(default=str(icon))
            except tk.TclError:
                pass

        self._build_ui()
        self._restore_position()
        self._style_window()
        self.root.after(self.REFRESH_MS, self._tick)

    # -- 构建 --

    def _build_ui(self):
        self.frame = tk.Frame(
            self.root,
            bg=BG,
            padx=14,
            pady=8,
            highlightthickness=1,
            highlightbackground=BORDER,
        )
        self.frame.pack(fill="both", expand=True)

        self.countdown = tk.Label(
            self.frame,
            text="--:--",
            font=("Segoe UI", 26, "bold"),
            fg=FG,
            bg=BG,
            anchor="w",
        )
        self.countdown.pack(anchor="w")

        self.info = tk.Label(
            self.frame,
            text="等待 mower 启动…",
            font=("Microsoft YaHei UI", 10),
            fg=SUB,
            bg=BG,
            anchor="w",
        )
        self.info.pack(anchor="w", pady=(2, 0))

        self.task = tk.Canvas(
            self.frame,
            width=220,
            height=24,
            bg=BG,
            bd=0,
            highlightthickness=0,
        )
        self.task.pack(anchor="w", pady=(1, 0))

        self.task2 = tk.Canvas(
            self.frame,
            width=220,
            height=24,
            bg=BG,
            bd=0,
            highlightthickness=0,
        )
        self.task2.pack(anchor="w")

        self.link = tk.Label(
            self.frame,
            text="○ 未连接（自动重试）",
            font=("Microsoft YaHei UI", 9),
            fg=SUB,
            bg=BG,
            anchor="w",
        )
        self.link.pack(anchor="w")

        # 自绘的最小化/关闭按钮（替代系统标题栏，放在右上角）
        self.min_button = tk.Label(
            self.frame,
            text="–",
            font=("Segoe UI", 10),
            fg=SUB,
            bg=BG,
            cursor="hand2",
        )
        self.close_button = tk.Label(
            self.frame,
            text="✕",
            font=("Segoe UI", 8),
            fg=SUB,
            bg=BG,
            cursor="hand2",
        )
        self.min_button.place(relx=1.0, x=-16, y=7, anchor="ne")
        self.close_button.place(relx=1.0, x=0, y=7, anchor="ne")
        self._apply_scale(force=True)
        self.min_button.bind("<Button-1>", lambda _event: self._minimize())
        self.close_button.bind("<Button-1>", lambda _event: self.quit())
        self.min_button.bind("<Enter>", lambda _event: self.min_button.configure(fg=FG))
        self.min_button.bind(
            "<Leave>", lambda _event: self.min_button.configure(fg=SUB)
        )
        self.close_button.bind(
            "<Enter>", lambda _event: self.close_button.configure(fg=CLOSE_HOVER)
        )
        self.close_button.bind(
            "<Leave>", lambda _event: self.close_button.configure(fg=SUB)
        )

        for widget in (
            self.frame,
            self.countdown,
            self.info,
            self.task,
            self.task2,
            self.link,
        ):
            widget.bind("<ButtonPress-1>", self._start_drag)
            widget.bind("<B1-Motion>", self._drag_move)
            widget.bind("<ButtonRelease-1>", self._end_drag)
            widget.bind("<Button-3>", self._popup_menu)
            widget.bind("<Enter>", self._tooltip_enter, add="+")
            widget.bind("<Leave>", self._tooltip_leave, add="+")

        self.pin_var = tk.BooleanVar(value=True)
        self.sound_var = tk.BooleanVar(value=True)
        self.secure_var = tk.BooleanVar(value=bool(self.poller.secure))
        self.insecure_var = tk.BooleanVar(value=bool(self.poller.insecure))
        self.menu = tk.Menu(self.root, tearoff=False)
        self.menu.add_checkbutton(
            label="窗口置顶", variable=self.pin_var, command=self._toggle_pin
        )
        self.menu.add_checkbutton(label="声音提醒", variable=self.sound_var)
        theme_menu = tk.Menu(self.menu, tearoff=False)
        for value, label in THEME_LABELS:
            theme_menu.add_radiobutton(
                label=label,
                value=value,
                variable=self.theme_var,
                command=self._change_theme,
            )
        self.menu.add_cascade(label="主题", menu=theme_menu)
        self.menu.add_command(label="发送测试通知", command=self._test_toast)
        self.menu.add_command(label="查看完整任务队列", command=self._copy_task_name)
        self.menu.add_command(label="重新连接", command=self.poller.reset)
        self.menu.add_command(label="设置服务器…", command=self._configure_server)
        self.menu.add_command(label="设置令牌…", command=self._configure_token)
        self.menu.add_checkbutton(
            label="使用 HTTPS", variable=self.secure_var, command=self._toggle_secure
        )
        self.menu.add_checkbutton(
            label="忽略证书校验（自签名证书）",
            variable=self.insecure_var,
            command=self._toggle_insecure,
        )
        self.menu.add_separator()
        self.menu.add_command(label="退出", command=self.quit)

    # -- 窗口拖动与位置记忆 --

    def _start_drag(self, event):
        self._tooltip_leave()  # 拖动时收起悬停提示，避免提示框跟着乱跑
        self._drag = (
            event.x_root - self.root.winfo_x(),
            event.y_root - self.root.winfo_y(),
        )

    def _drag_move(self, event):
        if self._drag is None:
            return
        dx, dy = self._drag
        x, y = event.x_root - dx, event.y_root - dy
        if IS_WINDOWS:
            try:
                # 直接 SetWindowPos 移动窗口：不改尺寸、不改样式、不阻塞事件循环。
                # （之前用的 SendMessage(WM_NCLBUTTONDOWN) 会卡死事件循环并崩溃；
                #   Tk 的 geometry 逐帧拖动则会花屏。）
                ctypes.windll.user32.SetWindowPos(
                    int(self.root.wm_frame(), 16),
                    0,
                    x,
                    y,
                    0,
                    0,
                    0x0001 | 0x0004 | 0x0010,  # NOSIZE | NOZORDER | NOACTIVATE
                )
                return
            except Exception:
                pass
        self.root.geometry(f"+{x}+{y}")

    def _px(self, value: float) -> int:
        return round(value * self._scale)

    def _apply_scale(self, force: bool = False):
        """按当前显示器缩放系数同步更新内边距、行间距与右上角按钮位置。"""
        scale = window_scale(self.root)
        if not force and abs(scale - self._scale) < 0.01:
            return
        self._scale = scale
        self.frame.configure(padx=self._px(14), pady=self._px(10))
        self.countdown.configure(pady=self._px(1))
        self.countdown.pack_configure(pady=(0, self._px(2)))
        self.info.configure(pady=self._px(2))
        self.info.pack_configure(pady=(self._px(3), 0))
        self.task.pack_configure(pady=(self._px(3), 0))
        self.task2.pack_configure(pady=(self._px(3), 0))
        self.poller.set_avatar_size(self._avatar_px())
        self.link.configure(pady=self._px(2))
        self.link.pack_configure(pady=(self._px(4), 0))
        self.min_button.place(relx=1.0, x=-self._px(20), y=self._px(6), anchor="ne")
        self.close_button.place(relx=1.0, x=0, y=self._px(6), anchor="ne")

    def _end_drag(self, event):
        self._drag = None
        self.root.update_idletasks()
        self._save_position()

    def _restore_position(self):
        """只恢复窗口位置：尺寸完全交给 Tk 按内容决定（不做任何像素计算）。

        overrideredirect 窗口没有系统边框，Tk 的「客户区 = 窗口」成立，内容多宽
        窗口就多宽；自己算尺寸反而会在不同缩放设置的机器上留白或裁掉内容。
        """
        self.root.update_idletasks()
        screen_w = self.root.winfo_screenwidth()
        screen_h = self.root.winfo_screenheight()
        width = self.root.winfo_reqwidth()
        height = self.root.winfo_reqheight()
        saved = self._load_position()
        if saved is None:
            x, y = screen_w - width - 24, 72
        else:
            x, y = saved
        x = min(max(0, x), max(0, screen_w - width))
        y = min(max(0, y), max(0, screen_h - height))
        self.root.geometry(f"+{x}+{y}")

    def _style_window(self):
        """把窗口做成无系统边框的挂件（自绘最小化/关闭按钮）。

        用 Tk 的 overrideredirect 而不是手动摘 WS_CAPTION：Tk 自己知道窗口没有
        边框，尺寸就完全按内容自适应（手动改样式时 Tk 还会多算一圈装饰，在不同
        缩放设置的机器上会留白或把内容裁掉）。代价是无边框窗口默认没有任务栏
        按钮，所以额外加上 WS_EX_APPWINDOW，最小化后也能从任务栏找回。
        """
        try:
            self.root.overrideredirect(True)
        except tk.TclError:
            pass
        if not IS_WINDOWS:
            return
        try:
            hwnd = int(self.root.wm_frame(), 16)
            user32 = ctypes.windll.user32
            gwl_exstyle = -20
            ws_ex_appwindow = 0x00040000
            ex_style = user32.GetWindowLongW(hwnd, gwl_exstyle)
            user32.SetWindowLongW(hwnd, gwl_exstyle, ex_style | ws_ex_appwindow)
            try:
                # DWMWA_WINDOW_CORNER_PREFERENCE = 33, DWMWCP_ROUND = 2
                corner = ctypes.c_int(2)
                ctypes.windll.dwmapi.DwmSetWindowAttribute(
                    hwnd, 33, ctypes.byref(corner), ctypes.sizeof(corner)
                )
            except Exception:
                pass
        except Exception:
            pass
        self._apply_icon()

    def _apply_icon(self):
        """设置窗口/任务栏图标（任务栏取窗口大图标，缺失时会退回 exe 图标）。"""
        icon = resource_path("countdown_widget.ico")
        if not icon.exists():
            return
        try:
            self.root.iconbitmap(str(icon))
        except tk.TclError:
            pass

    def _minimize(self):
        """最小化到任务栏：无标题栏窗口用 ShowWindow(SW_MINIMIZE) 最可靠。"""
        if IS_WINDOWS:
            try:
                hwnd = int(self.root.wm_frame(), 16)
                ctypes.windll.user32.ShowWindow(hwnd, 6)  # SW_MINIMIZE
                return
            except Exception:
                pass
        try:
            self.root.iconify()
        except tk.TclError:
            pass

    def _load_position(self):
        data = load_settings()
        try:
            return int(data["x"]), int(data["y"])
        except (KeyError, TypeError, ValueError):
            return None

    def _save_position(self):
        save_settings(x=self.root.winfo_x(), y=self.root.winfo_y())

    # -- 渲染 --

    def _set(self, label: tk.Label, text: str, fg: str | None = None):
        if label.cget("text") != text:
            label.configure(text=text)
        if fg is not None and label.cget("fg") != fg:
            label.configure(fg=fg)

    def _tick(self):
        snapshot = self.poller.snapshot
        left = None
        if snapshot is not None:
            remaining = snapshot.get("remaining")
            if remaining is not None and snapshot.get("status") != "stopped":
                left = max(
                    0.0,
                    float(remaining) - (time.monotonic() - snapshot["received"]),
                )
        self._render(snapshot, left)
        self._apply_countdown_color(left)
        shown = None if left is None else math.ceil(left)
        self._check_thresholds(shown, snapshot)
        self._follow_system_theme()
        self.root.after(self.REFRESH_MS, self._tick)

    def _follow_system_theme(self):
        """「跟随系统」时每 ~5 秒检测一次系统主题变化。"""
        if self.theme_pref != "system":
            return
        self._theme_check += 1
        if self._theme_check < 80:
            return
        self._theme_check = 0
        current = system_theme()
        if current != self._system_theme:
            self._system_theme = current
            self._apply_theme()

    def _avatar_px(self, scale: float | None = None) -> int:
        active = self._scale if scale is None else scale
        return max(16, min(48, round(20 * active)))

    def _avatar_photo(self, name: str, size: int) -> tk.PhotoImage | None:
        key = (name, size)
        cached = self._photo_cache.get(key)
        if cached is not None:
            return cached
        encoded = self.poller.get_avatar(name, size)
        if not encoded:
            return None
        try:
            photo = tk.PhotoImage(master=self.root, data=encoded)
        except tk.TclError:
            return None
        if len(self._photo_cache) > 256:
            self._photo_cache.clear()
        self._photo_cache[key] = photo
        return photo

    def _row_fonts(self, muted: bool):
        return {
            "time": tkfont.Font(root=self.root, family="Segoe UI", size=9, weight="bold"),
            "type": tkfont.Font(
                root=self.root,
                family="Microsoft YaHei UI",
                size=10,
                weight="normal" if muted else "bold",
            ),
            "text": tkfont.Font(root=self.root, family="Microsoft YaHei UI", size=10),
            "badge": tkfont.Font(root=self.root, family="Microsoft YaHei UI", size=8),
        }

    def _draw_stay_badge(self, canvas: tk.Canvas, x: int, cy: int, size: int, font):
        r = size // 2
        canvas.create_oval(
            x,
            cy - r,
            x + size - 1,
            cy + r - (0 if size % 2 else 1),
            fill=CHIP_BG,
            outline="",
            width=0,
        )
        canvas.create_text(
            x + size / 2,
            cy,
            text="留",
            font=font,
            fill=SUB,
            anchor="center",
        )
        return size

    def _draw_task_row(
        self,
        canvas: tk.Canvas,
        *,
        when: str,
        text: str,
        detail: dict | None,
        muted: bool,
    ):
        avatar_px = self._avatar_px()
        row_h = max(avatar_px + self._px(4), self._px(24))
        rooms = detail.get("rooms") if isinstance(detail, dict) else None
        avatar_states = tuple(
            (name, bool(self._avatar_photo(name, avatar_px)))
            for room in (rooms or ())
            for name in (room.get("operators") or ())
            if name and name != "保持当前"
        )
        sig = (
            when,
            text,
            json.dumps(detail, sort_keys=True, ensure_ascii=False)
            if isinstance(detail, dict)
            else None,
            muted,
            avatar_states,
            round(self._scale, 2),
            BG,
            SUB,
            TASK_FG,
            OK,
            TIME_FG,
            CHIP_BG,
            CHIP_BORDER,
        )
        if getattr(canvas, "_render_sig", None) == sig:
            return
        canvas._render_sig = sig
        canvas.delete("all")
        canvas.configure(bg=BG)

        fonts = self._row_fonts(muted)
        cy = row_h // 2
        x = 0
        max_w = self._px(252)
        min_w = self._px(196)
        gap_sm = self._px(4)
        gap_md = self._px(6)
        ellipsis_w = fonts["text"].measure("…") + self._px(2)

        def append_text(segment: str, font_key: str, color: str) -> bool:
            nonlocal x
            if not segment:
                return True
            w = fonts[font_key].measure(segment)
            if x > 0 and x + w > max_w - ellipsis_w:
                return False
            canvas.create_text(x, cy, text=segment, font=fonts[font_key], fill=color, anchor="w")
            x += w
            return True

        has_rooms = isinstance(detail, dict) and bool(rooms)
        if not has_rooms:
            if muted and when:
                append_text(when, "time", TIME_FG)
                x += gap_md
            plain = shorten(text, TASK_NAME_WIDTH) if text else "　"
            w = fonts["text"].measure(plain)
            canvas.create_text(
                x,
                cy,
                text=plain,
                font=fonts["text"],
                fill=SUB if (muted or not text) else TASK_FG,
                anchor="w",
            )
            x += w
            canvas.configure(width=max(min_w, x), height=row_h)
            return

        if muted and when:
            if append_text(when, "time", TIME_FG):
                x += gap_md

        action_type = str(detail.get("type") or "")
        truncated = False
        if action_type:
            if not append_text(action_type, "type", SUB if muted else TASK_FG):
                truncated = True
            else:
                x += gap_md

        for room_idx, room in enumerate(rooms):
            if truncated:
                break
            if room_idx > 0:
                if not append_text("·", "text", SUB):
                    truncated = True
                    break
                x += gap_sm
            room_name = str(room.get("room") or "")
            if room_name:
                if not append_text(room_name, "text", OK):
                    truncated = True
                    break
                x += gap_sm
            for op_idx, op_name in enumerate(room.get("operators") or ()):
                if op_name == "保持当前":
                    if x + avatar_px > max_w - ellipsis_w:
                        truncated = True
                        break
                    self._draw_stay_badge(canvas, x, cy, avatar_px, fonts["badge"])
                    x += avatar_px + gap_sm
                    continue
                photo = self._avatar_photo(op_name, avatar_px)
                if photo is not None:
                    if x + avatar_px > max_w - ellipsis_w:
                        truncated = True
                        break
                    canvas.create_image(x, cy, image=photo, anchor="w")
                    x += avatar_px + gap_sm
                else:
                    label = op_name if op_idx == 0 else f" {op_name}"
                    if not append_text(label, "text", SUB if muted else TASK_FG):
                        truncated = True
                        break
                    x += gap_sm

        if truncated:
            canvas.create_text(x, cy, text="…", font=fonts["text"], fill=SUB, anchor="w")
            x += fonts["text"].measure("…")
        canvas.configure(width=max(min_w, min(max_w, x + self._px(2))), height=row_h)

    def _paint_task_canvas(self, canvas: tk.Canvas, color: str):
        canvas.configure(bg=color)

    def _render(self, snapshot: dict | None, left: float | None):
        self._last_snapshot = snapshot
        if snapshot is None:
            self._set(self.countdown, "--:--")
            self._set(self.info, "等待 mower 启动…")
            self._draw_task_row(self.task, when="", text="　", detail=None, muted=False)
            self._draw_task_row(self.task2, when="", text="　", detail=None, muted=True)
            if self.poller.auth_failed:
                self._set(self.link, "○ 需要访问令牌（右键 设置令牌…）", fg=WARN)
            else:
                self._set(self.link, "○ 未连接（自动重试）", fg=SUB)
            self._detail_text = ""
            return

        status = snapshot.get("status")
        next_task = snapshot.get("next_task") or ""
        clock = next_task.split(" ")[-1] if next_task else ""
        when = clock_text(next_task)
        when2 = clock_text(snapshot.get("next_next_task") or "")
        task_name = snapshot.get("next_task_name") or ""
        task2_name = snapshot.get("next_next_task_name") or ""
        detail1 = snapshot.get("next_task_detail")
        detail2 = snapshot.get("next_next_task_detail")

        if status == "sleeping" and left is not None:
            self._set(self.countdown, format_left(left))
            self._set(self.info, f"下次任务 {clock} · 休眠中" if clock else "休眠中")
        elif status == "working":
            self._set(self.countdown, "工作中")
            self._set(self.info, f"下次任务 {clock}" if clock else "执行任务中…")
        else:
            self._set(self.countdown, "--:--")
            self._set(self.info, STATUS_TEXT.get(status, "状态未知"))

        # 队列两行：有结构化信息时按日志风格画圆形头像与绿色房间名；否则退回文本。
        self._detail_text = queue_detail(when, task_name, when2, task2_name)
        self._draw_task_row(
            self.task,
            when="",
            text=task_name if task_name else "　",
            detail=detail1,
            muted=False,
        )
        self._draw_task_row(
            self.task2,
            when=when2 if task2_name else "",
            text=task2_name if task2_name else "暂无后续任务",
            detail=detail2 if task2_name else None,
            muted=True,
        )

        # 目标文本限长：长 URL 会超过固定窗口宽度而被裁掉
        target = shorten(self.poller.target_label(), 24)
        if self._toast_error:
            self._set(self.link, f"● 已连接 {target}（通知发送失败）", fg=WARN)
        else:
            self._set(self.link, f"● 已连接 {target}", fg=OK)

    def _apply_countdown_color(self, left: float | None):
        """最后 10 秒让倒计时数字平滑循环变色，其余时间保持白色。"""
        if left is not None and left <= RAINBOW_SECONDS:
            self.countdown.configure(fg=rainbow_color(time.monotonic() * RAINBOW_SPEED))
        elif self.countdown.cget("fg") != FG:
            self.countdown.configure(fg=FG)

    # -- 临界提醒 --

    def _check_thresholds(self, shown: int | None, snapshot: dict | None):
        cycle = (snapshot or {}).get("next_task") or ""
        if cycle != self._cycle:
            self._cycle = cycle
            self._fired.clear()
            self._prev = None
        if shown is None:
            self._prev = None
            return
        if self._prev is not None:
            for threshold in self.thresholds:
                if threshold not in self._fired and self._prev > threshold >= shown:
                    self._fired.add(threshold)
                    self._fire(threshold, snapshot)
        self._prev = shown

    def _fire(self, threshold: int, snapshot: dict | None):
        task_name = (snapshot or {}).get("next_task_name") or ""
        when = ""
        next_task = (snapshot or {}).get("next_task") or ""
        if next_task:
            when = next_task.split(" ")[-1]
        title = f"还有 {humanize_threshold(threshold)}开始任务"
        details = [shorten(task_name, 60)] if task_name else []
        if when:
            details.append(when)
        message = " · ".join(details) or "Mower 倒计时"
        if self.verbose:
            print(f"[notify] {title}｜{message}", flush=True)
        sound_on = bool(self.sound_var.get())
        if sound_on:
            self._play_sound()
        self._flash()
        if self.toast_enabled:
            threading.Thread(
                args=(title, message, sound_on),
                daemon=True,
            ).start()

    def _play_sound(self):
        if IS_WINDOWS:
            try:
                winsound.MessageBeep(winsound.MB_ICONEXCLAMATION)
                return
            except RuntimeError:
                pass
            try:
                winsound.Beep(1000, 180)
            except Exception:
                pass
            return
        try:
            self.root.bell()
        except tk.TclError:
            pass

    def _flash(self, pulses: int = 2):
        for index in range(pulses):
            self.root.after(index * 320, lambda: self._paint(FLASH))
            self.root.after(index * 320 + 160, lambda: self._paint(BG))

    def _paint(self, color: str):
        self.frame.configure(bg=color)
        for label in (
            self.countdown,
            self.info,
            self.link,
            self.min_button,
            self.close_button,
        ):
            label.configure(bg=color)
        self._paint_task_canvas(self.task, color)
        self._paint_task_canvas(self.task2, color)

    def _show_toast(self, title: str, message: str, with_sound: bool = True) -> bool:
        """弹出系统通知；返回是否成功（结果写入日志，便于排障）。"""
        if not IS_WINDOWS:
            return False
        try:
            encoded = base64.b64encode(
                toast_script(title, message, with_sound=with_sound).encode("utf-16-le")
            ).decode("ascii")
            completed = subprocess.run(
                [
                    POWERSHELL,
                    "-NoProfile",
                    "-NonInteractive",
                    "-EncodedCommand",
                    encoded,
                ],
                timeout=25,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                stdin=subprocess.DEVNULL,
                capture_output=True,
            )
        except Exception as exc:
            log_line(f"[toast] 调用失败：{exc}")
            return False
        output = (completed.stdout or b"").decode("utf-8", "replace").strip()
        error = (completed.stderr or b"").decode("utf-8", "replace").strip()
        if completed.returncode == 0 and "TOAST_OK" in output:
            log_line(f"[toast] 已发送：{title}｜{message}")
            return True
        log_line(f"[toast] 失败 rc={completed.returncode} out={output!r} err={error!r}")
        return False

    def _notify_toast(self, title: str, message: str, with_sound: bool = True):
        """后台线程入口：发送通知，并记录失败状态供状态行提示。"""
        if self._show_toast(title, message, with_sound):
            self._toast_error = False
        else:
            self._toast_error = True

    def _test_toast(self):
        """右键菜单：手动发一条测试通知，失败时直接给出日志。"""
        sound_on = bool(self.sound_var.get())
        ok = self._show_toast(
            "Mower 倒计时",
            "测试通知：看到这条说明通知功能正常（若未出现请检查系统通知/专注助手设置）",
            sound_on,
        )
        if ok:
            messagebox.showinfo(
                "测试通知", "已发送，请查看屏幕右下角的通知。", parent=self.root
            )
            return
        try:
            tail = "\n".join(LOG_PATH.read_text(encoding="utf-8").splitlines()[-5:])
        except OSError:
            tail = "（没有日志）"
        messagebox.showwarning(
            "测试通知", f"发送失败，日志最后几行：\n\n{tail}", parent=self.root
        )

    # -- 交互 --

    def _toggle_pin(self):
        try:
            self.root.attributes("-topmost", self.pin_var.get())
        except tk.TclError:
            pass

    def _change_theme(self):
        """右键菜单切换主题：记住偏好并立即重绘。"""
        self.theme_pref = self.theme_var.get()
        save_settings(theme=self.theme_pref)
        self._apply_theme()

    def _apply_theme(self):
        """把当前主题应用到所有控件（含提示框）。"""
        apply_theme(resolve_theme(self.theme_pref))
        self.root.configure(bg=BG)
        self.frame.configure(bg=BG, highlightbackground=BORDER)
        for label in (
            self.countdown,
            self.info,
            self.link,
            self.min_button,
            self.close_button,
        ):
            label.configure(bg=BG)
        self.countdown.configure(fg=FG)
        self.info.configure(fg=SUB)
        self.link.configure(fg=WARN if self._toast_error else OK)
        self._render(self._last_snapshot, None)
        self._hide_tooltip()

    def _copy_task_name(self):
        """右键菜单：显示并复制完整任务队列（窗口内单行显示，超出部分截断）。"""
        text = self._detail_text
        if not text:
            messagebox.showinfo("任务队列", "当前没有待执行任务。", parent=self.root)
            return
        self.root.clipboard_clear()
        self.root.clipboard_append(text)
        messagebox.showinfo("任务队列", f"已复制到剪贴板：\n\n{text}", parent=self.root)

    # -- 悬停提示（显示完整任务名） --

    def _tooltip_enter(self, event=None):
        if self._tip_job is None and self._tip is None:
            self._tip_job = self.root.after(350, self._show_tooltip)

    def _tooltip_leave(self, event=None):
        if self._tip_job is not None:
            self.root.after_cancel(self._tip_job)
            self._tip_job = None
        self._hide_tooltip()

    def _show_tooltip(self):
        self._tip_job = None
        text = self._detail_text
        if not text or self._tip is not None:
            return
        scale = window_scale(self.root)

        def px(value: float) -> int:
            return round(value * scale)
        tip = tk.Toplevel(self.root)
        tip.overrideredirect(True)
        try:
            tip.attributes("-topmost", True)
        except tk.TclError:
            pass
        frame = tk.Frame(
            tip,
            bg=TIP_BG,
            padx=px(12),
            pady=px(8),
            highlightthickness=1,
            highlightbackground=TIP_BORDER,
        )
        frame.pack()
        snapshot = self._last_snapshot or {}
        structured = []
        for stamp, detail, fallback in (
            (
                clock_text(snapshot.get("next_task") or ""),
                snapshot.get("next_task_detail"),
                snapshot.get("next_task_name") or "",
            ),
            (
                clock_text(snapshot.get("next_next_task") or ""),
                snapshot.get("next_next_task_detail"),
                snapshot.get("next_next_task_name") or "",
            ),
        ):
            if isinstance(detail, dict) and (detail.get("rooms") or detail.get("type")):
                structured.append((stamp, detail))
            elif stamp or fallback:
                structured.append((stamp, {"type": fallback, "rooms": []}))

        avatar_px = self._avatar_px(scale)
        has_rich_rooms = any(d.get("rooms") for _, d in structured)
        if has_rich_rooms:
            tip_time_font = tkfont.Font(root=tip, family="Segoe UI", size=10, weight="bold")
            tip_title_font = tkfont.Font(
                root=tip, family="Microsoft YaHei UI", size=10, weight="bold"
            )
            tip_text_font = tkfont.Font(root=tip, family="Microsoft YaHei UI", size=10)
            tip_badge_font = tkfont.Font(root=tip, family="Microsoft YaHei UI", size=8)
            line_h = max(avatar_px + px(4), px(22))
            for block_idx, (stamp, detail) in enumerate(structured):
                header_row = tk.Frame(frame, bg=TIP_BG)
                header_row.pack(anchor="w", pady=(px(6) if block_idx else 0, px(2)))
                if stamp:
                    tk.Label(
                        header_row,
                        text=stamp,
                        font=tip_time_font,
                        fg=TIME_FG,
                        bg=TIP_BG,
                    ).pack(side="left", padx=(0, px(6)))
                if detail.get("type"):
                    tk.Label(
                        header_row,
                        text=str(detail["type"]),
                        font=tip_title_font,
                        fg=TIP_FG,
                        bg=TIP_BG,
                    ).pack(side="left")
                for room in detail.get("rooms") or ():
                    operators = list(room.get("operators") or ())
                    chunks = [operators[i : i + 4] for i in range(0, len(operators), 4)] or [[]]
                    for chunk_idx, chunk in enumerate(chunks):
                        row_canvas = tk.Canvas(
                            frame,
                            height=line_h,
                            bg=TIP_BG,
                            bd=0,
                            highlightthickness=0,
                        )
                        row_canvas.pack(anchor="w", pady=(px(2), 0))
                        cy = line_h // 2
                        rx = px(6)
                        if chunk_idx == 0 and room.get("room"):
                            room_label = str(room["room"])
                            row_canvas.create_text(
                                rx,
                                cy,
                                text=room_label,
                                font=tip_text_font,
                                fill=OK,
                                anchor="w",
                            )
                            rx += tip_text_font.measure(room_label) + px(6)
                        elif room.get("room"):
                            rx += tip_text_font.measure(str(room["room"])) + px(6)
                        for op_name in chunk:
                            if op_name == "保持当前":
                                self._draw_stay_badge(
                                    row_canvas, rx, cy, avatar_px, tip_badge_font
                                )
                                rx += avatar_px + px(4)
                                row_canvas.create_text(
                                    rx,
                                    cy,
                                    text=op_name,
                                    font=tip_text_font,
                                    fill=SUB,
                                    anchor="w",
                                )
                                rx += tip_text_font.measure(op_name) + px(8)
                                continue
                            photo = self._avatar_photo(op_name, avatar_px)
                            if photo is not None:
                                row_canvas.create_image(rx, cy, image=photo, anchor="w")
                                rx += avatar_px + px(4)
                            row_canvas.create_text(
                                rx,
                                cy,
                                text=op_name,
                                font=tip_text_font,
                                fill=TIP_FG,
                                anchor="w",
                            )
                            rx += tip_text_font.measure(op_name) + px(8)
                        row_canvas.configure(width=max(px(120), rx), height=line_h)
        else:
            for index, line in enumerate(wrap_lines(text, 52)):
                tk.Label(
                    frame,
                    text=line,
                    font=("Microsoft YaHei UI", 10),
                    fg=TIP_FG,
                    bg=TIP_BG,
                    justify="left",
                    anchor="w",
                    pady=px(2),
                ).pack(anchor="w", pady=(px(3) if index else 0, 0))
        tip.update_idletasks()
        width = tip.winfo_reqwidth()
        height = tip.winfo_reqheight()
        screen_w = self.root.winfo_screenwidth()
        screen_h = self.root.winfo_screenheight()
        margin = px(8)
        gap = px(6)
        x = min(
            self.root.winfo_rootx() + px(12),
            max(margin, screen_w - width - margin),
        )
        y = self.root.winfo_rooty() + self.root.winfo_height() + gap
        if y + height > screen_h - margin:
            y = max(margin, self.root.winfo_rooty() - height - gap)
        tip.geometry(f"+{max(margin, x)}+{y}")
        self._tip = tip

    def _hide_tooltip(self):
        if self._tip is not None:
            self._tip.destroy()
            self._tip = None

    def _configure_server(self):
        """手动指定 mower 地址（绿色版拷到其它机器、连不上时使用）。"""
        current = self.poller.host
        target = self.poller.fixed_port or self.poller.endpoint
        if target:
            scheme = "https://" if self.poller.endpoint_secure else ""
            current = f"{scheme}{current}:{target}"
        text = simpledialog.askstring(
            "设置 Mower 服务器",
            "输入端口（如 58000）或地址：\n"
            "58000 / 192.168.1.5:58000 / https://mower.example.com\n"
            "留空表示自动发现；https:// 开头会启用加密连接",
            initialvalue=current,
            parent=self.root,
        )
        if text is None:
            return
        host, port, secure = parse_endpoint(text)
        if host is None:
            messagebox.showerror(
                "设置失败",
                "地址格式不对，示例：58000 / 192.168.1.5:58000 / https://host:8443",
                parent=self.root,
            )
            return
        self.poller.configure(host, port, secure=secure)
        self.secure_var.set(bool(secure))
        save_settings(host=host, port=port, secure=secure)

    def _configure_token(self):
        """填写 mower 的 Web UI token：/status 需要它才能读取状态。"""
        token = simpledialog.askstring(
            "设置访问令牌",
            "输入 mower 设置里的 Web UI token：\n"
            "留空表示不使用令牌；令牌保存在用户主目录的 .mower-countdown.json",
            initialvalue=self.poller.token,
            show="*",
            parent=self.root,
        )
        if token is None:
            return
        token = token.strip()
        self.poller.configure(
            self.poller.host,
            self.poller.fixed_port,
            secure=self.poller.secure,
            token=token,
        )
        save_settings(token=token)

    def _toggle_secure(self):
        """右键菜单：在 HTTP / HTTPS 之间切换，改完立即重连。"""
        secure = bool(self.secure_var.get())
        self.poller.configure(self.poller.host, self.poller.fixed_port, secure=secure)
        save_settings(secure=secure)

    def _toggle_insecure(self):
        """右键菜单：自签名证书时跳过证书校验（等价 curl -k）。"""
        insecure = bool(self.insecure_var.get())
        self.poller.configure(
            self.poller.host,
            self.poller.fixed_port,
            secure=self.poller.secure,
            insecure=insecure,
        )
        save_settings(insecure=insecure)

    def _popup_menu(self, event):
        try:
            self.menu.tk_popup(event.x_root, event.y_root)
        finally:
            self.menu.grab_release()

    def quit(self):
        self._save_position()
        self.root.destroy()

    def run(self):
        self.root.mainloop()


# --- 入口 ---


def parse_thresholds(value: str) -> tuple[int, ...]:
    thresholds = set()
    for item in str(value).split(","):
        item = item.strip()
        if not item:
            continue
        seconds = int(item)
        if seconds > 0:
            thresholds.add(seconds)
    return tuple(sorted(thresholds, reverse=True)) or DEFAULT_THRESHOLDS


def main(argv=None):
    if sys.stdout is None:  # pythonw 启动时没有控制台
        sys.stdout = open(os.devnull, "w", encoding="utf-8")
    if sys.stderr is None:
        sys.stderr = open(os.devnull, "w", encoding="utf-8")

    parser = argparse.ArgumentParser(description="mower 下次任务倒计时挂件")
    parser.add_argument(
        "--port", type=int, default=None, help="mower Web 端口；默认自动发现"
    )
    parser.add_argument(
        "--host",
        default=None,
        help="mower Web 主机（默认 127.0.0.1），也可写完整地址如 https://host:8443",
    )
    parser.add_argument("--https", action="store_true", help="强制使用 HTTPS 连接")
    parser.add_argument(
        "--insecure", action="store_true", help="HTTPS 时不校验证书（自签名证书）"
    )
    parser.add_argument(
        "--token",
        default=None,
        help="mower 的 Web UI token（/status 需要）；默认用上次保存的值",
    )
    parser.add_argument(
        "--thresholds",
        default=",".join(str(t) for t in DEFAULT_THRESHOLDS),
        help="临界提醒的秒数，逗号分隔（默认 60,30,10）",
    )
    parser.add_argument(
        "--interval", type=float, default=1.0, help="状态轮询间隔（秒）"
    )
    parser.add_argument("--no-toast", action="store_true", help="不弹系统通知")
    parser.add_argument("--no-sound", action="store_true", help="不响提示音")
    parser.add_argument("--verbose", action="store_true", help="输出调试日志")
    args = parser.parse_args(argv)

    enable_dpi_awareness()
    install_exception_logging()
    settings = load_settings()
    host = args.host or settings.get("host") or "127.0.0.1"
    port = args.port if args.port is not None else settings.get("port")
    secure = settings.get("secure")
    if args.host:
        # --host 允许直接写完整地址（含协议），也兼容只写主机名
        if "://" in args.host:
            parsed_host, parsed_port, parsed_secure = parse_endpoint(args.host)
            if parsed_host is None:
                parser.error(f"无法解析主机地址：{args.host}")
            host = parsed_host
            secure = parsed_secure
            if parsed_port is not None:
                port = parsed_port
        else:
            host = args.host.strip()
    if args.port is not None:
        port = args.port
    if args.https:
        secure = True
    insecure = bool(args.insecure or settings.get("insecure"))
    token = args.token if args.token is not None else (settings.get("token") or "")
    poller = StatusPoller(
        host=host,
        port=port,
        interval=args.interval,
        verbose=args.verbose,
        secure=secure,
        insecure=insecure,
        token=token,
    )
    poller.start()
    widget = CountdownWidget(
        poller,
        thresholds=parse_thresholds(args.thresholds),
        toast=not args.no_toast,
        sound=not args.no_sound,
        verbose=args.verbose,
    )
    widget.run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
