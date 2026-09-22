#!/usr/bin/env python3
"""独立倒计时挂件：显示距离 mower 下次任务的剩余时间，并在临界点弹桌面通知。

数据来自 mower Web 服务的 /status 接口（无需 token）。端口默认自动发现：
扫描 %LOCALAPPDATA%/arknights-mower/updates/*/instances/*.json 实例注册文件，
按心跳时间优先连接能响应的实例；也可以用 --port 手动指定。

功能：
- 置顶小窗（带系统标题栏，可最小化/关闭），实时倒计时（休眠中）/ 工作中 / 未运行；
- 剩余 60 / 30 / 10 秒时弹 Windows 系统通知 + 提示音 + 窗口闪烁（阈值可用
  --thresholds 自定义），最后 10 秒倒计时数字平滑循环变色；
- 显示下次任务名与时间；窗口可拖动（位置自动记忆），右键菜单可测试通知、
  设置服务器、开关置顶/声音或退出；
- 支持 HTTP / HTTPS：目标写成 https://host:port 即走 TLS（先试 http、失败再试
  https），自签名证书可勾选「忽略证书校验」（等价 curl -k）。

用法：
    python countdown_widget.py                 # 自动发现正在运行的实例
    python countdown_widget.py --port 58000    # 指定端口
    python countdown_widget.py --host https://192.168.1.5:8443 --insecure
    pythonw countdown_widget.py                # 无控制台窗口启动
"""

from __future__ import annotations

import argparse
import base64
import colorsys
import ctypes
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
import traceback
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
TASK_NAME_WIDTH = 26  # 任务名单行显示宽度（中文按 2 计），完整名称悬停可看
RAINBOW_SPEED = 0.35  # 彩虹色循环速度（圈/秒）

# --- 主题（深色 / 浅色 / 跟随系统） ---

THEMES = {
    "dark": {
        "bg": "#1b1d23",
        "fg": "#f5f7fa",
        "sub": "#98a2b3",
        "task": "#cbd5e1",
        "ok": "#4ade80",
        "warn": "#f0b429",
        "flash": "#b45309",
        "close": "#ff6b6b",
        "tip_bg": "#232733",
        "tip_fg": "#e5e9f0",
        "border": "#303540",
        "tip_border": "#3a4150",
    },
    "light": {
        "bg": "#f7f8fa",
        "fg": "#12161f",
        "sub": "#6b7280",
        "task": "#374151",
        "ok": "#15803d",
        "warn": "#b45309",
        "flash": "#fdba74",
        "close": "#dc2626",
        "tip_bg": "#ffffff",
        "tip_fg": "#12161f",
        "border": "#d8dbe2",
        "tip_border": "#c7ccd6",
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
    global TIP_BG, TIP_FG, BORDER, TIP_BORDER
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


def instance_records():
    """遍历 mower 的实例注册文件，返回所有带端口的记录。"""
    base = Path(os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData/Local")))
    for path in sorted(
        (base / "arknights-mower" / "updates").glob("*/instances/*.json")
    ):
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if isinstance(record, dict) and isinstance(record.get("port"), int):
            yield record


def discover_ports():
    """候选端口列表，最近有心跳的实例排在前面。"""
    rows = [
        (float(record.get("heartbeat") or 0), record["port"])
        for record in instance_records()
        if 0 < record["port"] < 65536
    ]
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
    ):
        super().__init__(daemon=True, name="mower-status-poller")
        self.host = host
        self.fixed_port = port
        self.interval = max(0.2, float(interval))
        self.verbose = verbose
        # secure=None 表示自动：先按 http 试，失败再用 https
        self.secure = secure
        self.insecure = insecure  # True = 不校验证书（自签名证书）
        self.snapshot: dict | None = None
        self.endpoint: int | None = None
        self.endpoint_secure = False
        self._ssl_context: ssl.SSLContext | None = None
        self._wake = threading.Event()

    def reset(self):
        """请求立即重新发现端口（右键菜单「重新连接」）。"""
        self._wake.set()

    def configure(
        self,
        host: str,
        port: int | None,
        secure: bool | None = None,
        insecure: bool | None = None,
    ):
        """运行时切换目标服务器（右键菜单「设置服务器…」）。

        secure=None 表示「自动」；insecure=None 表示保持原值不变。
        """
        self.host = host
        self.fixed_port = port
        self.secure = secure
        if insecure is not None:
            self.insecure = bool(insecure)
            self._ssl_context = None
        self.endpoint = None
        self.endpoint_secure = False
        self.snapshot = None
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

    def _request(self, port: int, secure: bool = False) -> dict:
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
            connection.request("GET", "/status")
            response = connection.getresponse()
            body = response.read()
            if response.status != 200:
                raise ValueError(f"状态接口返回 HTTP {response.status}")
        finally:
            connection.close()
        data = json.loads(body.decode("utf-8", "replace"))
        if not isinstance(data, dict):
            raise ValueError("状态接口返回了非 JSON 对象")
        return data

    def _adopt(self, port: int, data: dict, secure: bool = False):
        self.endpoint = port
        self.endpoint_secure = secure
        self.snapshot = {
            "status": data.get("status"),
            "remaining": data.get("remaining_seconds"),
            "next_task": data.get("next_task_time"),
            "next_task_name": data.get("next_task_name"),
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
        candidates = [self.fixed_port] if self.fixed_port else discover_ports()
        for port in candidates:
            for secure in self._schemes():
                try:
                    data = self._request(port, secure)
                except Exception:
                    continue
                self._adopt(port, data, secure)
                label = self.target_label()
                self._log(f"已连接 mower {label}")
                log_line(f"[poll] 已连接 mower {label}")
                return True
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
                    failures = 0
                elif self._scan():
                    failures = 0
                else:
                    self.snapshot = None
                    failures += 1
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
        self._full_task_name = ""
        self._tip = None
        self._tip_job = None

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
        # 顺序很重要：Tk 的 geometry/resizable 会重设窗口样式，样式调整必须放最后
        self._restore_position()
        self._style_window()
        # 等布局稳定后按真实内容尺寸再校正一次，避免 Tk 与系统尺寸不一致
        self.root.after(80, self._resize_to_content)
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

        self.task = tk.Label(
            self.frame,
            text="　",
            font=("Microsoft YaHei UI", 10),
            fg=TASK_FG,
            bg=BG,
            anchor="w",
        )
        self.task.pack(anchor="w", pady=(1, 0))

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

        for widget in (self.frame, self.countdown, self.info, self.task, self.link):
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
        self.menu.add_command(label="查看完整任务名", command=self._copy_task_name)
        self.menu.add_command(label="重新连接", command=self.poller.reset)
        self.menu.add_command(label="设置服务器…", command=self._configure_server)
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

    def _end_drag(self, event):
        self._drag = None
        self.root.update_idletasks()
        self._save_position()

    def _restore_position(self):
        """恢复窗口位置；尺寸交给 Tk 按内容决定（任务名已截断，宽度不会失控）。

        这里刻意不用 geometry 指定宽高：手动改过窗口样式后，Tk 对
        「客户区尺寸 + 装饰补偿」的换算会和窗口实际值对不上，Tk 记录的尺寸
        与实际窗口不一致时，拖动会出现尺寸跳变甚至崩溃。
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
        self.root.resizable(False, False)

    def _style_window(self):
        """去掉系统标题栏（改用窗口内自绘按钮），并加上圆角与深色边框。

        只移除 WS_CAPTION，保留最小化能力，所以窗口仍可最小化到任务栏
        （见 _minimize：直接调 ShowWindow(SW_MINIMIZE)）。
        """
        if not IS_WINDOWS:
            return
        try:
            self.root.update_idletasks()
            hwnd = int(self.root.wm_frame(), 16)
            user32 = ctypes.windll.user32
            gwl_style = -16
            ws_caption = 0x00C00000
            ws_thickframe = 0x00040000
            ws_maximizebox = 0x00010000
            style = user32.GetWindowLongW(hwnd, gwl_style)
            # 去掉标题栏与可最大化/拉伸样式：系统拖动时才不会触发贴靠/最大化
            # （那会把固定尺寸的窗口突然改大，布局跟不上就崩了）
            style &= ~(ws_caption | ws_thickframe | ws_maximizebox)
            user32.SetWindowLongW(hwnd, gwl_style, style)
            swp_nosize, swp_nomove, swp_nozorder, swp_framechanged = (
                0x0001,
                0x0002,
                0x0004,
                0x0020,
            )
            user32.SetWindowPos(
                hwnd,
                0,
                0,
                0,
                0,
                0,
                swp_nosize | swp_nomove | swp_nozorder | swp_framechanged,
            )
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

    def _resize_to_content(self):
        """布局稳定后按真实内容尺寸再固定一次。

        构造阶段字体还没量出真实行高、样式也刚变过，此时算出的尺寸不准；
        等窗口显示后再用 Tk 的 geometry 校正一遍，保证 Tk 记录的尺寸与窗口
        实际尺寸一致——两者不一致时拖动窗口会出现尺寸跳变甚至崩溃。
        """
        self._restore_position()
        self._style_window()

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

    def _render(self, snapshot: dict | None, left: float | None):
        if snapshot is None:
            self._set(self.countdown, "--:--")
            self._set(self.info, "等待 mower 启动…")
            self._set(self.task, "　")
            self._set(self.link, "○ 未连接（自动重试）", fg=SUB)
            return

        status = snapshot.get("status")
        next_task = snapshot.get("next_task") or ""
        when = next_task.split(" ")[-1] if next_task else ""
        task_name = snapshot.get("next_task_name") or ""

        if status == "sleeping" and left is not None:
            self._set(self.countdown, format_left(left))
            self._set(self.info, f"下次任务 {when} · 休眠中" if when else "休眠中")
        elif status == "working":
            self._set(self.countdown, "工作中")
            self._set(self.info, f"下次任务 {when}" if when else "执行任务中…")
        else:
            self._set(self.countdown, "--:--")
            self._set(self.info, STATUS_TEXT.get(status, "状态未知"))

        # 任务名单独一行区域（最多两行）；截断后剩余的完整名称仍可从右键菜单复制
        self._full_task_name = task_name
        self._set(self.task, shorten(task_name, TASK_NAME_WIDTH) if task_name else "　")

        target = shorten(self.poller.target_label(), 40)
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
            self.task,
            self.link,
            self.min_button,
            self.close_button,
        ):
            label.configure(bg=color)

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
            self.task,
            self.link,
            self.min_button,
            self.close_button,
        ):
            label.configure(bg=BG)
        self.countdown.configure(fg=FG)
        self.info.configure(fg=SUB)
        self.task.configure(fg=TASK_FG)
        self.link.configure(fg=WARN if self._toast_error else OK)
        self._hide_tooltip()

    def _copy_task_name(self):
        """右键菜单：显示并复制完整任务名（窗口内单行显示，超出部分截断）。"""
        name = self._full_task_name
        if not name:
            messagebox.showinfo("下次任务", "当前没有下次任务。", parent=self.root)
            return
        self.root.clipboard_clear()
        self.root.clipboard_append(name)
        messagebox.showinfo("下次任务", f"已复制到剪贴板：\n\n{name}", parent=self.root)

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
        name = self._full_task_name
        if not name or self._tip is not None:
            return
        tip = tk.Toplevel(self.root)
        tip.overrideredirect(True)
        try:
            tip.attributes("-topmost", True)
        except tk.TclError:
            pass
        frame = tk.Frame(
            tip,
            bg=TIP_BG,
            padx=10,
            pady=6,
            highlightthickness=1,
            highlightbackground=TIP_BORDER,
        )
        frame.pack()
        tk.Label(
            frame,
            text=name,
            font=("Microsoft YaHei UI", 10),
            fg=TIP_FG,
            bg=TIP_BG,
            justify="left",
            anchor="w",
            wraplength=520,
        ).pack()
        tip.update_idletasks()
        width = tip.winfo_reqwidth()
        height = tip.winfo_reqheight()
        screen_w = self.root.winfo_screenwidth()
        screen_h = self.root.winfo_screenheight()
        x = min(self.root.winfo_rootx() + 12, max(8, screen_w - width - 8))
        y = self.root.winfo_rooty() + self.root.winfo_height() + 6
        if y + height > screen_h - 8:
            y = max(8, self.root.winfo_rooty() - height - 6)
        tip.geometry(f"+{max(8, x)}+{y}")
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
    poller = StatusPoller(
        host=host,
        port=port,
        interval=args.interval,
        verbose=args.verbose,
        secure=secure,
        insecure=insecure,
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
