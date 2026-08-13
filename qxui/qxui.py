import os
os.environ["QT_QUICK_CONTROLS_STYLE"] = "Basic"

import sys
import ctypes
from typing import Any
from ctypes import wintypes
from collections.abc import Callable

from PySide6.QtCore import Property
from PySide6.QtWidgets import QApplication
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtCore import QObject, Signal, Slot
from PySide6.QtCore import Qt, QAbstractNativeEventFilter

from .core import QMLGenerator
from .standard import StandardProfile

# ---------------------------------------------------------------------------------------------------------

SWP_NOSIZE       = 0x0001
SWP_NOMOVE       = 0x0002
SWP_NOZORDER     = 0x0004
SWP_NOACTIVATE   = 0x0010
SWP_FRAMECHANGED = 0x0020
SWP_SHOWWINDOW   = 0x0040

HWND_TOPMOST     = -1
HWND_NOTOPMOST   = -2
HWND_TOP         = 0
HWND_BOTTOM      = 1

WM_NCCALCSIZE    = 0x0083
WM_NCHITTEST     = 0x0084

HTLEFT        = 10
HTRIGHT       = 11
HTTOP         = 12
HTTOPLEFT     = 13
HTTOPRIGHT    = 14
HTBOTTOM      = 15
HTBOTTOMLEFT  = 16
HTBOTTOMRIGHT = 17

# ---------------------------------------------------------------------------------------------------------

class WinFilter(QAbstractNativeEventFilter):
    def __init__(self):
        super().__init__()
        self.frameless_hwnds: set[int] = set()

    def nativeEventFilter(self, eventType, message):  # type: ignore
        msg = wintypes.MSG.from_address(int(message)) # type: ignore
        if msg.hWnd == None or int(msg.hWnd) not in self.frameless_hwnds: return False, 0

        if msg.message == WM_NCCALCSIZE: return True, 0

        if msg.message == WM_NCHITTEST:
            rect = wintypes.RECT()
            ctypes.windll.user32.GetWindowRect(msg.hWnd, ctypes.byref(rect))

            x = ctypes.c_int16(msg.lParam & 0xFFFF).value
            y = ctypes.c_int16((msg.lParam >> 16) & 0xFFFF).value

            p = 8
            l, r = x < rect.left + p, x >= rect.right - p
            t, b = y < rect.top + p, y >= rect.bottom - p

            if t and l:  return True, HTTOPLEFT
            if t and r:  return True, HTTOPRIGHT
            if b and l:  return True, HTBOTTOMLEFT
            if b and r:  return True, HTBOTTOMRIGHT

            if l:        return True, HTLEFT
            if r:        return True, HTRIGHT
            if t:        return True, HTTOP
            if b:        return True, HTBOTTOM

        return False, 0

# ---------------------------------------------------------------------------------------------------------

class State:
    def __init__(self, initial: dict | None = None):
        self.app: 'App | None' = None
        self.data = dict(initial or {})
        self.initial = dict(initial or {})

    def get(self, key: str, default: Any = None) -> Any:
        return self.data.get(key, default)

    def set(self, key: str, value: Any):
        self.data[key] = value
        if self.app: self.app.notify_state()

    def update(self, diff: dict):
        for k, v in diff.items(): self.data[k] = v
        if self.app: self.app.notify_state()

    def reset(self):
        self.data = dict(self.initial)
        if self.app: self.app.notify_state()

    def to_dict(self): return dict(self.data)
    def items(self): return self.to_dict().items()
    def keys(self):  return self.to_dict().keys()

    def __getitem__(self, key: str) -> Any: return self.get(key)
    def __setitem__(self, key: str, value: Any): self.set(key, value)

# ---------------------------------------------------------------------------------------------------------

class Bridge(QObject):
    stateChanged = Signal()

    def __init__(self, window: 'Window'):
        super().__init__()
        self.window = window
        self.app    = window.app

    @Property(dict, notify=stateChanged)
    def state(self) -> dict:
        return self.app.state.to_dict()

    @Slot(str, object)
    def setState(self, key, value):
        self.app.state.set(key, value)

    @Slot(str)
    @Slot(str, object)
    def dispatch(self, name: str, payload: Any = None):
        action = self.app.actions.get(name)
        if not action: sys.stderr.write(f"[qxui] missing action: {name}\n"); return
        action(ActionContext(self.app, self.window, payload))

# ---------------------------------------------------------------------------------------------------------

class ActionContext:
    def __init__(self, app: 'App', window: 'Window | None', payload: Any = None):
        self.app     = app
        self.window  = window
        self.payload = payload

    @property
    def state(self) -> State:
        return self.app.state

    def set_state(self, key: str, value: Any):
        self.state.set(key, value)

    def update_state(self, values: dict):
        self.state.update(values)

# ---------------------------------------------------------------------------------------------------------

class Window:
    def __init__(
        self,
        app: 'App',
        source: str,
        title: str = "",
        size: tuple[int, int] = (1280, 800),
        background: str = "#000000",
        styles: str = "",
        frameless: bool = True,
        profiles: list | None = None,
    ):
        self.app       = app
        self.source    = source
        self.title     = title
        self.width     = size[0]
        self.height    = size[1]
        self.bg        = background
        self.styles    = styles
        self.frameless = frameless
        self.profiles  = list(profiles or [StandardProfile()])

        self.engine: QQmlApplicationEngine = None # type:ignore
        self.bridge: Bridge = None # type:ignore
        self.root_object: Any = None

        self.build_window()

    def build_window(self):
        window_def = {
            "type":       "Window",
            "id":         "root",
            "title":      self.title,
            "width":      self.width,
            "height":     self.height,
            "background": self.bg,
        }

        app_spec = {
            "window": window_def,
            "styles": self.styles,
            "ui":     self.source,
        }

        generator = QMLGenerator(profiles=self.profiles, components=self.app.components)
        qml_code  = generator.generate_app(app_spec)

        self.bridge = Bridge(self)
        engine = QQmlApplicationEngine()
        engine.rootContext().setContextProperty("backend", self.bridge) # type: ignore
        engine.loadData(qml_code.encode("utf-8"))

        if not engine.rootObjects():
            raise RuntimeError("failed to load QML root object")

        self.engine      = engine
        self.root_object = engine.rootObjects()[0]

        if self.frameless:
            if sys.platform == "win32": self.win32_frameless()
            else: self.root_object.setFlags(self.root_object.flags() | Qt.WindowType.FramelessWindowHint)

    def win32_pos(self, flags: int, insert_after: int = 0, x: int = 0, y: int = 0, cx: int = 0, cy: int = 0):
        if not self.root_object: return
        if not sys.platform == "win32": return

        hwnd = int(self.root_object.winId())
        ctypes.windll.user32.SetWindowPos(hwnd, insert_after, x, y, cx, cy, flags)

    def win32_frameless(self):
        if not self.root_object: return
        if not self.app.win_filter: return

        hwnd = int(self.root_object.winId())
        self.app.win_filter.frameless_hwnds.add(hwnd)
        self.win32_pos(SWP_NOMOVE | SWP_NOSIZE | SWP_FRAMECHANGED)

    def minimize(self):
        if not self.root_object: return
        self.root_object.showMinimized()

    def maximize(self):
        if not self.root_object: return
        if self.root_object.windowState().value & 2: self.root_object.showNormal()
        else: self.root_object.showMaximized()

    def close(self):
        if not self.root_object: return
        self.root_object.close()

# ---------------------------------------------------------------------------------------------------------

class App:
    def __init__(self, state: State | None = None):
        self.qapp = QApplication.instance() or QApplication(sys.argv)
        self.win_filter: WinFilter | None = None
        self.windows: list[Window] = []

        if sys.platform == "win32":
            self.win_filter = WinFilter()
            self.qapp.installNativeEventFilter(self.win_filter)

        self.state     = state or State()
        self.state.app = self

        self.actions    = {}
        self.components = {}

        @self.action("minimize")
        def handle_min(ctx: ActionContext):
            if ctx.window: ctx.window.minimize()

        @self.action("maximize")
        def handle_max(ctx: ActionContext):
            if ctx.window: ctx.window.maximize()

        @self.action("close")
        def handle_close(ctx: ActionContext):
            if ctx.window: ctx.window.close()

    def notify_state(self):
        for win in self.windows:
            win.bridge.stateChanged.emit()

    def action(self, action_name: str):
        def decorator(func: Callable[[ActionContext], None]):
            self.actions[action_name] = func
            return func
        return decorator

    def component(self, name: str, source: str, props: dict | None = None):
        self.components[name] = (source, dict(props or {}))

    def create_window(
        self,
        source: str,
        title: str = "",
        size: tuple[int, int] = (1280, 800),
        background: str = "#000000",
        styles: str = "",
        frameless: bool = True,
        profiles: list | None = None,
    ) -> Window:

        win = Window(
            app        = self,
            source     = source,
            title      = title,
            size       = size,
            background = background,
            styles     = styles,
            frameless  = frameless,
            profiles   = profiles,
        )
        self.windows.append(win)
        return win

    def run(self) -> int:
        return self.qapp.exec()
