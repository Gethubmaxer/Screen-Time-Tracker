import ctypes
import ctypes.wintypes
import threading
import time
import logging
from datetime import datetime
from database import Database

logger = logging.getLogger(__name__)

# --- Windows API Constants ---
EVENT_SYSTEM_FOREGROUND = 0x0003
WINEVENT_OUTOFCONTEXT = 0x0000

PROCESS_QUERY_INFORMATION = 0x0400
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000

# --- Windows API Structures ---
class LASTINPUTINFO(ctypes.Structure):
    _fields_ = [
        ("cbSize", ctypes.c_uint),
        ("dwTime", ctypes.c_uint)
    ]

class RECT(ctypes.Structure):
    _fields_ = [
        ("left", ctypes.c_long),
        ("top", ctypes.c_long),
        ("right", ctypes.c_long),
        ("bottom", ctypes.c_long),
    ]

class MONITORINFO(ctypes.Structure):
    _fields_ = [
        ("cbSize", ctypes.c_ulong),
        ("rcMonitor", RECT),
        ("rcWork", RECT),
        ("dwFlags", ctypes.c_ulong),
    ]

# --- Setup ctypes ---
user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32
psapi = ctypes.windll.psapi

WinEventProcType = ctypes.WINFUNCTYPE(
    None, 
    ctypes.wintypes.HANDLE, 
    ctypes.wintypes.DWORD, 
    ctypes.wintypes.HWND, 
    ctypes.wintypes.LONG, 
    ctypes.wintypes.LONG, 
    ctypes.wintypes.DWORD, 
    ctypes.wintypes.DWORD
)

user32.GetLastInputInfo.argtypes = [ctypes.POINTER(LASTINPUTINFO)]
user32.GetLastInputInfo.restype = ctypes.wintypes.BOOL

# PostThreadMessageW for clean thread shutdown (WM_QUIT)
user32.PostThreadMessageW.argtypes = [
    ctypes.wintypes.DWORD,  # thread id
    ctypes.wintypes.UINT,   # msg
    ctypes.wintypes.WPARAM, # wParam
    ctypes.wintypes.LPARAM, # lParam
]
user32.PostThreadMessageW.restype = ctypes.wintypes.BOOL

kernel32.OpenProcess.argtypes = [ctypes.wintypes.DWORD, ctypes.wintypes.BOOL, ctypes.wintypes.DWORD]
kernel32.OpenProcess.restype = ctypes.wintypes.HANDLE

kernel32.GetCurrentThreadId.restype = ctypes.wintypes.DWORD

kernel32.QueryFullProcessImageNameW.argtypes = [
    ctypes.wintypes.HANDLE,
    ctypes.wintypes.DWORD,
    ctypes.wintypes.LPWSTR,
    ctypes.POINTER(ctypes.wintypes.DWORD)
]
kernel32.QueryFullProcessImageNameW.restype = ctypes.wintypes.BOOL

MONITOR_DEFAULTTONEAREST = 2

user32.GetWindowRect.argtypes = [ctypes.wintypes.HWND, ctypes.POINTER(RECT)]
user32.GetWindowRect.restype = ctypes.wintypes.BOOL

user32.MonitorFromWindow.argtypes = [ctypes.wintypes.HWND, ctypes.c_ulong]
user32.MonitorFromWindow.restype = ctypes.wintypes.HANDLE

user32.GetMonitorInfoW.argtypes = [ctypes.wintypes.HANDLE, ctypes.POINTER(MONITORINFO)]
user32.GetMonitorInfoW.restype = ctypes.wintypes.BOOL

class Tracker:
    def __init__(self, db: Database, idle_threshold_seconds: int = 60, exclude_names: list = None,
                 on_app_change=None, on_idle=None, on_resume=None, on_session_end=None):
        """
        on_app_change:  callback(app_name, window_title, exe_path, session_start)
        on_idle:        callback() - system went idle
        on_resume:      callback() - system resumed from idle
        on_session_end: callback(app_name, window_title, exe_path, category,
                                 start_time, end_time, duration_seconds)
        """
        self.db = db
        self.idle_threshold_seconds = idle_threshold_seconds
        self.exclude_names = [n.lower() for n in exclude_names] if exclude_names else []
        
        self.on_app_change = on_app_change
        self.on_idle = on_idle
        self.on_resume = on_resume
        self.on_session_end = on_session_end
        
        self.hook = None
        self.callback = WinEventProcType(self._winevent_callback)
        
        self.current_app_id = None
        self.current_session_id = None
        self.current_session_start = None
        self.current_app_name = None
        self.current_exe_path = None
        self.current_window_title = None
        
        self.is_idle = False
        self.running = False
        
        # OS thread ID of the message-pump thread (set in start())
        self._msg_thread_tid = None
        
        self.lock = threading.RLock()

    def _get_window_info(self, hwnd):
        """Extracts the executable path, name, and window title from a window handle."""
        if not hwnd:
            return None, None, None

        # Get Window Title
        length = user32.GetWindowTextLengthW(hwnd)
        buf = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buf, length + 1)
        window_title = buf.value

        # Get Process ID
        pid = ctypes.wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))

        # Get Process Path
        exe_path = ""
        # Try PROCESS_QUERY_LIMITED_INFORMATION first as it requires fewer privileges
        h_process = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if h_process:
            size = ctypes.wintypes.DWORD(260) # MAX_PATH
            path_buf = ctypes.create_unicode_buffer(size.value)
            if kernel32.QueryFullProcessImageNameW(h_process, 0, path_buf, ctypes.byref(size)):
                exe_path = path_buf.value
            kernel32.CloseHandle(h_process)
            
        if not exe_path:
            return None, None, None
            
        app_name = exe_path.split("\\")[-1]
        
        # Edge cases for UWP apps could be handled here (ApplicationFrameHost.exe)
        if app_name.lower() == "applicationframehost.exe":
            # Real UWP app logic requires more complex UI Automation, keeping it simple for now
            pass
            
        return exe_path, app_name, window_title

    def _handle_window_change(self, hwnd):
        """Called when the active window changes or system comes back from idle."""
        exe_path, app_name, window_title = self._get_window_info(hwnd)
        
        if not exe_path:
            return

        # Exclude app based on names
        app_name_lower = app_name.lower()
        title_lower = window_title.lower()
        path_lower = exe_path.lower()
        for name in self.exclude_names:
            if name in app_name_lower or name in title_lower or name in path_lower:
                return

        with self.lock:
            new_app_id = self.db.get_or_create_app(exe_path, app_name)

            # Same app, not idle, has an active session — tab switch only.
            # If current_session_id is None (e.g. after idle close), always create a new session.
            is_same_app = (new_app_id == self.current_app_id
                           and not self.is_idle
                           and self.current_session_id is not None)
            title_changed = window_title != self.current_window_title

            if is_same_app:
                if title_changed:
                    self.current_window_title = window_title
                    if self.current_session_id:
                        self.db.update_session_window_title(self.current_session_id, window_title)
                    if self.on_app_change:
                        self.on_app_change(app_name, window_title, exe_path, self.current_session_start)
                return

            # End current session if exists
            self._close_current_session()
            
            # Start new session
            self.current_app_id = new_app_id
            self.current_app_name = app_name
            self.current_exe_path = exe_path
            self.current_window_title = window_title
            self.current_session_id = self.db.start_session(self.current_app_id, window_title)
            self.current_session_start = datetime.now()
            logger.info(f"Switched to: {app_name} - {window_title}")
            
            # Notify cloud sync
            if self.on_app_change:
                self.on_app_change(app_name, window_title, exe_path, self.current_session_start)

    def _close_current_session(self):
        """Updates the end time of the current session."""
        if self.current_session_id and self.current_session_start:
            end_time = datetime.now()
            duration = int((end_time - self.current_session_start).total_seconds())
            self.db.update_session(self.current_session_id, self.current_session_start)
            
            # Notify cloud sync about completed session
            if self.on_session_end and self.current_app_name:
                self.on_session_end(
                    self.current_app_name,
                    self.current_window_title or "",
                    self.current_exe_path or "",
                    "neutral",  # category - could be extended
                    self.current_session_start,
                    end_time,
                    duration,
                )
            
            self.current_session_id = None
            self.current_session_start = None
            self.current_app_name = None
            self.current_window_title = None
            self.current_exe_path = None

    def _winevent_callback(self, hWinEventHook, event, hwnd, idObject, idChild, dwEventThread, dwmsEventTime):
        """Callback for Windows events."""
        if event == EVENT_SYSTEM_FOREGROUND:
            self._handle_window_change(hwnd)

    def _get_idle_time(self):
        """Returns the system idle time in seconds."""
        lii = LASTINPUTINFO()
        lii.cbSize = ctypes.sizeof(LASTINPUTINFO)
        if user32.GetLastInputInfo(ctypes.byref(lii)):
            millis = kernel32.GetTickCount() - lii.dwTime
            return millis / 1000.0
        return 0

    def _is_fullscreen(self, hwnd):
        """Check if the given window covers >= 95% of the monitor (fullscreen video/game/presentation)."""
        if not hwnd:
            return False
        rect = RECT()
        if not user32.GetWindowRect(hwnd, ctypes.byref(rect)):
            return False
        monitor = user32.MonitorFromWindow(hwnd, MONITOR_DEFAULTTONEAREST)
        if not monitor:
            return False
        mi = MONITORINFO()
        mi.cbSize = ctypes.sizeof(MONITORINFO)
        if not user32.GetMonitorInfoW(monitor, ctypes.byref(mi)):
            return False
        win_w = rect.right - rect.left
        win_h = rect.bottom - rect.top
        mon_w = mi.rcMonitor.right - mi.rcMonitor.left
        mon_h = mi.rcMonitor.bottom - mi.rcMonitor.top
        if mon_w == 0 or mon_h == 0:
            return False
        return (win_w / mon_w >= 0.95 and win_h / mon_h >= 0.95)

    def _idle_monitor_thread(self):
        """Background thread to monitor system idle time and update DB incrementally."""
        while self.running:
            idle_time = self._get_idle_time()
            
            with self.lock:
                if idle_time >= self.idle_threshold_seconds:
                    if not self.is_idle:
                        # Don't go idle if foreground window is fullscreen (video, game, etc.)
                        fg_hwnd = user32.GetForegroundWindow()
                        if self._is_fullscreen(fg_hwnd):
                            pass  # Fullscreen content — suppress idle
                        else:
                            logger.info("System is idle. Pausing tracking.")
                            self.is_idle = True
                            self._close_current_session()
                            if self.on_idle:
                                self.on_idle()
                else:
                    if self.is_idle:
                        logger.info("System resumed.")
                        self.is_idle = False
                        if self.on_resume:
                            self.on_resume()
                        # Resume tracking foreground window
                        hwnd = user32.GetForegroundWindow()
                        self._handle_window_change(hwnd)
                
                # Periodically sync active session to DB every few seconds (to prevent data loss)
                if self.current_session_id and self.current_session_start and not self.is_idle:
                    self.db.update_session(self.current_session_id, self.current_session_start)

                    # Poll foreground window for tab switches within the same app (Edge tabs, etc.)
                    fg = user32.GetForegroundWindow()
                    if fg:
                        length = user32.GetWindowTextLengthW(fg)
                        buf = ctypes.create_unicode_buffer(length + 1)
                        user32.GetWindowTextW(fg, buf, length + 1)
                        new_title = buf.value
                        if new_title and new_title != self.current_window_title:
                            self.current_window_title = new_title
                            if self.current_session_id:
                                self.db.update_session_window_title(self.current_session_id, new_title)
                            if self.on_app_change and self.current_app_name:
                                self.on_app_change(self.current_app_name, new_title,
                                                   self.current_exe_path or "", self.current_session_start)

            time.sleep(5) # Low-impact poll

    def start(self):
        """Starts the tracker."""
        if self.running:
            return
            
        self.running = True
        
        # Start idle monitor thread
        threading.Thread(target=self._idle_monitor_thread, daemon=True).start()
        
        # Set the hook for foreground window changes
        self.hook = user32.SetWinEventHook(
            EVENT_SYSTEM_FOREGROUND,
            EVENT_SYSTEM_FOREGROUND,
            0,
            self.callback,
            0,
            0,
            WINEVENT_OUTOFCONTEXT
        )
        
        if not self.hook:
            logger.error("Failed to set WinEventHook.")
            return

        # Store OS thread ID so stop() can post WM_QUIT to unblock the pump
        self._msg_thread_tid = kernel32.GetCurrentThreadId()

        # Start tracking current window immediately
        hwnd = user32.GetForegroundWindow()
        self._handle_window_change(hwnd)
        
        logger.info("Tracker started.")
        
        # Pump messages (required for the hook to receive events in the main thread)
        msg = ctypes.wintypes.MSG()
        while self.running:
            bRet = user32.GetMessageW(ctypes.byref(msg), 0, 0, 0)
            if bRet <= 0:
                break
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))

    def stop(self):
        """Stops the tracker."""
        self.running = False
        if self.hook:
            user32.UnhookWinEvent(self.hook)
            self.hook = None

        with self.lock:
            self._close_current_session()

        # Post WM_QUIT to unblock the message pump (GetMessageW)
        if self._msg_thread_tid is not None:
            user32.PostThreadMessageW(self._msg_thread_tid, 0x0012, 0, 0)

        logger.info("Tracker stopped.")
