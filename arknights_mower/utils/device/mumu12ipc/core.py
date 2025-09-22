# MIT-licensed clean-room reimplementation for MuMu12 IPC bindings.
# This file intentionally avoids copying any GPL-licensed implementation details.
# It only binds to the public C API exposed by external_renderer_ipc.dll.

import ctypes
import functools
import json
import os
import subprocess
import sys
import time
from typing import Any, Callable, Optional

import numpy as np

from arknights_mower.utils import config
from arknights_mower.utils.csleep import MowerExit
from arknights_mower.utils.log import logger
from arknights_mower.utils.simulator import restart_simulator


def retry_wrapper(max_retries: int = 3, delay: float = 0.5):
    """
    通用重试装饰器（适配 @retry_wrapper(3) 用法）
    - 捕获异常 -> 重置连接状态 -> 尝试重启模拟器 -> 睡眠 -> 重试
    - 命中 MowerExit 直接向上抛出，避免吞掉退出信号
    """

    def decorator(func):
        @functools.wraps(func)
        def wrapper(self, *args, **kwargs):
            last_exc = None
            for attempt in range(1, max_retries + 1):
                try:
                    return func(self, *args, **kwargs)
                except MowerExit:
                    raise
                except RuntimeError as e:
                    last_exc = e
                    logger.info(
                        f"{func.__name__} runtime error (attempt {attempt}/{max_retries}): {e}"
                    )
                    try:
                        # 若有该方法则调用
                        if hasattr(self, "device") and hasattr(
                            self.device, "check_current_focus"
                        ):
                            self.device.check_current_focus()
                    except Exception as inner:
                        logger.info(f"check_current_focus failed: {inner}")
                except Exception as e:
                    last_exc = e
                    logger.info(
                        f"{func.__name__} failed (attempt {attempt}/{max_retries}): {e}"
                    )

                    try:
                        if hasattr(self, "_conn"):
                            self._conn = 0
                        if hasattr(self, "_display_id"):
                            self._display_id = -1
                        restart_simulator()
                    except Exception as inner:
                        logger.error(f"restart_simulator failed: {inner}")
                time.sleep(delay)
            if last_exc is not None:
                raise last_exc
            raise RuntimeError(f"{func.__name__} failed after {max_retries} retries")

        return wrapper

    return decorator


class MuMuIpcError(RuntimeError):
    pass


class MuMu12IPC:
    """
    Drop-in replacement implementing display capture and input injection via MuMu 12
    external_renderer_ipc.dll.

    Public methods preserved for compatibility:
      - connect(), get_display_id(), capture_display()
      - key_down(), key_up(), touch_down(), touch_up()
      - finger_touch_down(), finger_touch_up()
      - tap(), send_keyevent(), back()
      - swipe(), swipe_ext(), kill_server(), reset_when_exit()
    """

    _W = 1920
    _H = 1080
    _BYTES = _W * _H * 4

    def __init__(self, device):
        self.device = device
        # Normalize emulator folder from config (compatible with your project layout)
        sim_folder_from_config = os.path.normpath(config.conf.simulator.simulator_folder)
        self.manager_path = os.path.join(sim_folder_from_config, "MuMuManager.exe")
        self._emu_root = os.path.dirname(sim_folder_from_config)

        self._index: int = int(config.conf.simulator.index)
        self._conn: int = 0
        self._display_id: int = -1
        self._app_index: int = (
            0  # 0 works for single-game bind; adjust if multi instance mapping needed
        )

        # Manager path (CLI JSON for version/status)
        self._manager = os.path.join(
            config.conf.simulator.simulator_folder, "MuMuManager.exe"
        )

        # Lazy-initialized members
        self._dll = None
        self._buffer = None  # single reusable framebuffer
        self._is_new_coord: Optional[bool] = None  # coord system flag (>= 4.1.21)

        # Preload to fail-fast with clear diagnostics
        self._load_renderer()

    # -----------------------
    # Loading / version logic
    # -----------------------
    def _load_renderer(self):
        """
        Load external_renderer_ipc.dll from typical MuMu 12 locations.
        """
        candidates = [
            os.path.join(self._emu_root, "shell", "sdk", "external_renderer_ipc.dll"),
            os.path.join(self._emu_root, "nx_main", "sdk", "external_renderer_ipc.dll"),
        ]
        last_err = None
        for path in candidates:
            try:
                self._dll = ctypes.CDLL(path)
                logger.debug(f"Loaded MuMu renderer DLL: {path}")
                break
            except OSError as e:
                last_err = e
                logger.debug(f"Failed to load renderer from {path}: {e}")
        if self._dll is None:
            msg = f"Cannot load external_renderer_ipc.dll. Checked: {candidates}. Last error: {last_err}"
            logger.error(msg)
            raise MuMuIpcError(msg)

        # Bind types only after successful load
        self._dll.nemu_connect.argtypes = [ctypes.c_wchar_p, ctypes.c_int]
        self._dll.nemu_connect.restype = ctypes.c_int

        self._dll.nemu_disconnect.argtypes = [ctypes.c_int]
        self._dll.nemu_disconnect.restype = None

        self._dll.nemu_get_display_id.argtypes = [
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_int,
        ]
        self._dll.nemu_get_display_id.restype = ctypes.c_int

        self._dll.nemu_capture_display.argtypes = [
            ctypes.c_int,
            ctypes.c_uint,
            ctypes.c_int,
            ctypes.POINTER(ctypes.c_int),
            ctypes.POINTER(ctypes.c_int),
            ctypes.POINTER(ctypes.c_ubyte),
        ]
        self._dll.nemu_capture_display.restype = ctypes.c_int

        self._dll.nemu_input_event_touch_down.argtypes = [
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
        ]
        self._dll.nemu_input_event_touch_down.restype = ctypes.c_int

        self._dll.nemu_input_event_touch_up.argtypes = [ctypes.c_int, ctypes.c_int]
        self._dll.nemu_input_event_touch_up.restype = ctypes.c_int

        self._dll.nemu_input_event_finger_touch_down.argtypes = [
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
        ]
        self._dll.nemu_input_event_finger_touch_down.restype = ctypes.c_int

        self._dll.nemu_input_event_finger_touch_up.argtypes = [
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
        ]
        self._dll.nemu_input_event_finger_touch_up.restype = ctypes.c_int

        self._dll.nemu_input_event_key_down.argtypes = [
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
        ]
        self._dll.nemu_input_event_key_down.restype = ctypes.c_int

        self._dll.nemu_input_event_key_up.argtypes = [
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
        ]
        self._dll.nemu_input_event_key_up.restype = ctypes.c_int


    def _manager_json(self, subcmd: str) -> dict:
        """ 封装执行 MuMuManager.exe 命令的通用逻辑 """
        cmd = [self._manager, subcmd, "-v", str(self._index), "-a"]
        
        # 为 Windows 设置 creationflags 以隐藏窗口
        creation_flags = 0
        if sys.platform == "win32":
            creation_flags = subprocess.CREATE_NO_WINDOW
        
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                check=True,
                encoding='utf-8', # 明确指定编码
                creationflags=creation_flags
            )
            
            # 优先使用 stdout，如果为空则尝试 stderr
            output = result.stdout.strip()
            if not output and result.stderr:
                logger.debug("Command output was found in stderr.")
                output = result.stderr.strip()

            if not output:
                # 命令成功执行但没有输出
                logger.warning(f"命令 {' '.join(cmd)} 成功执行，但没有输出。")
                return {} # 返回一个空字典以避免后续错误
            
            return json.loads(output)
        
        except subprocess.CalledProcessError as e:
            # 安全地获取错误信息，处理 stdout/stderr 可能为 None 的情况
            error_output = e.stderr if e.stderr else e.stdout
            error_message = error_output.strip() if error_output else "[命令执行失败，且没有任何输出]"
        
            logger.error(f"执行 MuMuManager 命令失败，返回码: {e.returncode}，错误: {error_message}")
            raise
        except json.JSONDecodeError as e:
            # 输出不是有效的 JSON
            raw_output = result.stdout.strip() if 'result' in locals() and result.stdout else "N/A"
            logger.error(f"解析 MuMuManager 的 JSON 输出失败: {e}。原始输出: {raw_output}")
            raise
        except FileNotFoundError:
            logger.error(f"无法找到 MuMuManager.exe，请检查路径: {self._manager}")
            raise
        except Exception as e:
            # 捕获其他所有异常
            logger.error(f"执行 MuMuManager 命令时发生未知错误: {e}")
            raise

    def _emu_version(self) -> tuple:
        """
        Returns (major, minor, patch) for decision-making. Caches coord mapping rule.
        """
        data = self._manager_json("setting")
        version = str(data.get("core_version", "0.0.0"))
        parts = tuple(int(x) for x in version.split(".")[:3])
        if self._is_new_coord is None:
            # MuMu 12 changed coordinate arguments since 4.1.21
            self._is_new_coord = parts >= (4, 1, 21)
        return parts

    def _emu_state(self) -> str:
        """
        'running' | 'launching' | 'stopped'
        """
        info = self._manager_json("info")
        if (
            info.get("is_android_started")
            or info.get("player_state") == "start_finished"
        ):
            return "running"
        if info.get("is_process_started"):
            return "launching"
        return "stopped"

    # -----------------------
    # Connection & display
    # -----------------------
    def connect(self):
        """
        Establish IPC connection to emulator if running.
        """
        if self._emu_state() != "running":
            raise Exception("模拟器未启动，请启动模拟器")
        path = ctypes.c_wchar_p(self._emu_root)
        self._conn = self._dll.nemu_connect(path, self._index)
        if self._conn == 0:
            raise Exception("连接模拟器失败，请启动模拟器")
        logger.info("MuMu IPC connected.")

    def get_display_id(self):
        """
        获取指定应用的 Display ID，并增加等待和重试机制。
        应用启动需要时间，因此需要轮询。
        """
        pkg_name = config.conf.APPNAME.encode("utf-8")
        timeout_seconds = 20  # 等待应用启动的总超时时间，可以根据需要调整
        start_time = time.time()

        logger.info(f"正在等待应用 '{config.conf.APPNAME}' 启动并获取其 Display ID...")

        while time.time() - start_time < timeout_seconds:
            self._display_id = self._dll.nemu_get_display_id(
                self._conn, pkg_name, self._app_index
            )

            if self._display_id >= 0:
                logger.info(f"成功获取 Display ID: {self._display_id}")
                return  # 成功获取，退出函数

            # 如果获取失败，记录返回码并等待后重试
            logger.debug(f"获取 Display ID 失败 (返回码: {self._display_id})，将在 1 秒后重试...")
            time.sleep(1)

        # 如果循环结束（超时），仍未获取成功，则抛出最终的异常
        logger.error(f"在 {timeout_seconds} 秒内未能获取到 Display ID，应用可能未能正常启动或置于前台。")
        raise RuntimeError("获取Display ID失败")

    @retry_wrapper(3)  # type: ignore
    def _ensure_ready(self):
        """
        Ensure connection and display id are valid; auto-recover if needed.
        """
        if self._conn == 0:
            self.connect()
        if self._display_id < 0:
            self.get_display_id()

    def _ensure_buffer(self):
        if self._buffer is None:
            self._buffer = (ctypes.c_ubyte * self._BYTES)()

    def capture_display(self) -> np.ndarray:
        """
        Capture RGBA frame into reusable buffer, return HxWx3 (RGB) numpy array flipped to upright.
        """
        # Try a few times before giving up. Many IPC errors are transient (simulator focus,
        # display not ready, temporary renderer loss, etc.). On failure we attempt soft
        # reconnects; only after exhausting retries we exit the device.
        attempts = 3
        for attempt in range(1, attempts + 1):
            try:
                self._ensure_ready()
                self._ensure_buffer()

                w = ctypes.c_int(self._W)
                h = ctypes.c_int(self._H)
                ret = self._dll.nemu_capture_display(
                    self._conn,
                    self._display_id,
                    self._BYTES,
                    ctypes.byref(w),
                    ctypes.byref(h),
                    self._buffer,
                )

                if ret == 0:
                    # Interpret buffer: RGBA -> RGB, flip vertically
                    frame = np.frombuffer(self._buffer, dtype=np.uint8).reshape(
                        (self._H, self._W, 4)
                    )[:, :, :3]
                    return np.flipud(frame)

                # Non-zero return: log and try to recover. Treat some return codes as transient.
                logger.warning(
                    f"nemu_capture_display returned {ret} (attempt {attempt}/{attempts})"
                )

                # soft reset state so next attempt will re-establish connection/display id
                self._conn = 0
                self._display_id = -1

                # Try to reconnect immediately for next attempt (best-effort)
                try:
                    self.connect()
                    self.get_display_id()
                except Exception as inner:
                    logger.debug(f"reconnect attempt failed: {inner}")

                # short backoff before retrying
                time.sleep(0.2)

            except MowerExit:
                raise
            except Exception as e:
                logger.error(f"capture_display error on attempt {attempt}: {e}")
                # prepare for next loop iteration
                self._conn = 0
                self._display_id = -1
                time.sleep(0.2)

        # All attempts exhausted. Perform final cleanup and signal device exit.
        logger.error("capture_display failed after retries, exiting device")
        try:
            self.device.exit()
        except Exception:
            pass
        return np.zeros((self._H, self._W, 3), dtype=np.uint8)

    def _map_xy(self, x: int, y: int) -> tuple[int, int]:
        """
        Map logical coordinates to MuMu IPC expected arguments depending on version.
        """
        if self._is_new_coord is None:
            self._emu_version()
        if self._is_new_coord:
            return int(x), int(y)
        return int(self._H - y), int(x)

    def key_down(self, key_code: int):
        try:
            self._ensure_ready()
            rc = self._dll.nemu_input_event_key_down(
                self._conn, self._display_id, int(key_code)
            )
            if rc != 0:
                raise MuMuIpcError(f"key_down failed: {rc}")
        except Exception as e:
            logger.error(f"key_down error: {e}")
            self._conn = 0
            self._display_id = -1
            self.device.exit()

    def key_up(self, key_code: int):
        try:
            self._ensure_ready()
            rc = self._dll.nemu_input_event_key_up(
                self._conn, self._display_id, int(key_code)
            )
            if rc != 0:
                raise MuMuIpcError(f"key_up failed: {rc}")
        except Exception as e:
            logger.error(f"key_up error: {e}")
            self._conn = 0
            self._display_id = -1
            self.device.exit()

    def touch_down(self, x: int, y: int):
        try:
            self._ensure_ready()
            tx, ty = self._map_xy(x, y)
            rc = self._dll.nemu_input_event_touch_down(
                self._conn, self._display_id, tx, ty
            )
            if rc != 0:
                raise MuMuIpcError(f"touch_down failed: {rc}")
        except Exception as e:
            logger.error(f"touch_down error: {e}")
            self._conn = 0
            self._display_id = -1
            self.device.exit()

    def touch_up(self):
        try:
            self._ensure_ready()
            rc = self._dll.nemu_input_event_touch_up(self._conn, self._display_id)
            if rc != 0:
                raise MuMuIpcError(f"touch_up failed: {rc}")
        except Exception as e:
            logger.error(f"touch_up error: {e}")
            self._conn = 0
            self._display_id = -1
            self.device.exit()

    def finger_touch_down(self, finger_id: int, x: int, y: int):
        try:
            self._ensure_ready()
            tx, ty = self._map_xy(x, y)
            rc = self._dll.nemu_input_event_finger_touch_down(
                self._conn, self._display_id, int(finger_id), tx, ty
            )
            if rc != 0:
                raise MuMuIpcError(f"finger_touch_down failed: {rc}")
        except Exception as e:
            logger.error(f"finger_touch_down error: {e}")
            self._conn = 0
            self._display_id = -1
            self.device.exit()

    def finger_touch_up(self, finger_id: int):
        try:
            self._ensure_ready()
            rc = self._dll.nemu_input_event_finger_touch_up(
                self._conn, self._display_id, int(finger_id)
            )
            if rc != 0:
                raise MuMuIpcError(f"finger_touch_up failed: {rc}")
        except Exception as e:
            logger.error(f"finger_touch_up error: {e}")
            self._conn = 0
            self._display_id = -1
            self.device.exit()

    def tap(self, x: int, y: int, hold_time: float = 0.07):
        self.touch_down(x, y)
        time.sleep(hold_time)
        self.touch_up()

    def send_keyevent(self, key_code: int, hold_time: float = 0.1):
        self.key_down(key_code)
        time.sleep(hold_time)
        self.key_up(key_code)

    def back(self):
        self.send_keyevent(1)

    def swipe(
        self,
        x0: int,
        y0: int,
        x1: int,
        y1: int,
        duration: float = 0.5,
        steps: int = 30,
        fall: bool = True,
        lift: bool = True,
        interval: float = 0.0,
    ):
        if fall:
            self.touch_down(x0, y0)

        # 每步耗时
        dt = duration / steps

        for i in range(1, steps + 1):
            tx = int(x0 + (x1 - x0) * (i / steps))
            ty = int(y0 + (y1 - y0) * (i / steps))
            self.touch_down(tx, ty)
            time.sleep(dt)

        if lift:
            if interval:
                time.sleep(interval)
            self.touch_up()

    def swipe_ext(
        self,
        points: list[tuple[int, int]],
        durations: list[int],
        update: bool = False,
        interval: float = 0.0,
        func: Callable[[np.ndarray], Any] = lambda _: None,
    ):
        if len(points) < 2 or len(durations) != len(points) - 1:
            raise ValueError(
                "swipe_ext requires at least 2 points and len(durations)==len(points)-1"
            )

        for i, (p0, p1, d_ms) in enumerate(zip(points[:-1], points[1:], durations)):
            self.swipe(
                p0[0],
                p0[1],
                p1[0],
                p1[1],
                duration=max(0.01, d_ms / 1000.0),
                fall=(i == 0),
                lift=(i == len(durations) - 1),
                update=(i == len(durations) - 1) and update,
                interval=interval if i == len(durations) - 1 else 0.0,
                func=func,
            )