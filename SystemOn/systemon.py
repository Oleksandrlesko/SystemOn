import sys
import os
import math
import time
import json
import ctypes
import tempfile
import shutil
import psutil
import subprocess
import importlib.util

from PyQt5.QtCore import Qt, QThread, pyqtSignal, QTimer
from PyQt5.QtGui import QIcon, QColor, QPalette, QFont
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QVBoxLayout, QHBoxLayout, QAction, QWidget,
    QDialog, QLabel, QTextBrowser, QProgressBar, QGridLayout, QFrame, QPushButton,
    QStackedWidget, QScrollArea, QCheckBox, QColorDialog, QComboBox, QSizePolicy
)
from components.graph import RGraph

PAGE_OVERVIEW = 0
PAGE_PROCESSES = 1
PAGE_PERFORMANCE = 2
PAGE_DRIVES = 3
PAGE_SENSORS = 4


def read_gpu_metrics():
    try:
        output = subprocess.check_output(
            "nvidia-smi --query-gpu=temperature.gpu,power.draw,power.limit --format=csv,noheader,nounits",
            stderr=subprocess.DEVNULL,
            shell=True,
            text=True,
            timeout=2
        )
        first_line = output.strip().splitlines()[0]
        parts = [part.strip() for part in first_line.split(",")]
        gpu_temp = f"{float(parts[0]):.1f} C" if len(parts) > 0 and parts[0] not in ("", "N/A", "[N/A]") else "N/A"
        gpu_power_usage = f"{float(parts[1]):.1f} W" if len(parts) > 1 and parts[1] not in ("", "N/A", "[N/A]") else "N/A"
        gpu_power_limit = f"{float(parts[2]):.1f} W" if len(parts) > 2 and parts[2] not in ("", "N/A", "[N/A]") else "N/A"
    except Exception:
        gpu_temp, gpu_power_usage, gpu_power_limit = "N/A", "N/A", "N/A"
    return gpu_temp, gpu_power_limit, gpu_power_usage


def format_bytes_gb(value_bytes):
    return f"{value_bytes / (1024 ** 3):.2f} GB"


def read_memory_frequency():
    try:
        output = subprocess.check_output(
            "wmic memorychip get Speed /value",
            stderr=subprocess.DEVNULL,
            shell=True,
            text=True,
            timeout=2
        )
        speeds = []
        for line in output.splitlines():
            if "Speed=" not in line:
                continue
            value = line.split("=", 1)[1].strip()
            if value.isdigit():
                speeds.append(int(value))
        if speeds:
            return f"{max(speeds)} MHz"
    except Exception:
        pass
    return "N/A"


def read_memory_details():
    vm = psutil.virtual_memory()
    used_memory = format_bytes_gb(vm.used)
    available_memory = format_bytes_gb(vm.available)
    return used_memory, available_memory


def load_icon(icon_name):
    icon_path = os.path.join(os.path.dirname(__file__), icon_name)
    if getattr(sys, 'frozen', False):
        icon_path = os.path.join(sys._MEIPASS, icon_name)
    if os.path.exists(icon_path):
        return QIcon(icon_path)
    return None



def plugin_search_directories():
    """User overrides first, then built-in examples next to systemon.py (and _MEIPASS when frozen)."""
    dirs = [os.path.join(os.path.expanduser("~"), "systemonplugins")]
    here = os.path.dirname(os.path.abspath(__file__))
    dirs.append(os.path.join(here, "systemonplugins"))
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        dirs.append(os.path.join(sys._MEIPASS, "systemonplugins"))
    return dirs


def load_plugins(app_context):
    loaded_plugins = []
    seen_mod_names = set()
    for plugins_dir in plugin_search_directories():
        try:
            os.makedirs(plugins_dir, exist_ok=True)
        except OSError:
            pass
        try:
            names = sorted(os.listdir(plugins_dir))
        except OSError:
            continue
        for filename in names:
            if not filename.endswith(".py") or filename.startswith("_"):
                continue
            mod_name = os.path.splitext(filename)[0]
            if mod_name in seen_mod_names:
                continue
            plugin_path = os.path.join(plugins_dir, filename)
            spec = importlib.util.spec_from_file_location(mod_name, plugin_path)
            if spec is None or spec.loader is None:
                continue
            module = importlib.util.module_from_spec(spec)
            try:
                spec.loader.exec_module(module)
                if hasattr(module, "register_plugin"):
                    module.register_plugin(app_context)
                    seen_mod_names.add(mod_name)
                    loaded_plugins.append(mod_name)
                    print(f"Plugin '{mod_name}' loaded successfully from {plugin_path}")
            except Exception as e:
                print(f"Failed to load plugin '{filename}' from {plugins_dir}: {e}")
    return loaded_plugins



def loadStyle():
    user_css_path = os.path.join(os.path.expanduser("~"), "rmstyle.css")
    stylesheet = None
    if os.path.exists(user_css_path):
        try:
            with open(user_css_path, 'r') as css_file:
                stylesheet = css_file.read()
            print(f"Loaded user CSS style from: {user_css_path}")
        except Exception as e:
            print(f"Error loading user CSS: {e}")
    else:
        css_file_path = os.path.join(os.path.dirname(__file__), 'style.css')
        if getattr(sys, 'frozen', False):
            css_file_path = os.path.join(sys._MEIPASS, 'style.css')
        try:
            with open(css_file_path, 'r') as css_file:
                stylesheet = css_file.read()
        except FileNotFoundError:
            print(f"Default CSS file not found: {css_file_path}")
    if stylesheet:
        app = QApplication.instance()
        if app:
            app.setStyleSheet(stylesheet)
        else:
            print("No QApplication instance found. Stylesheet not applied.")



def memory_string():
    memory = psutil.virtual_memory()
    total_memory = memory.total / (1024 ** 3)
    return f"{total_memory:.2f} GB"



def optimal_grid(n):
    best_rows, best_cols = None, None
    best_diff = float("inf")
    target_ratio = math.sqrt(n)
    for rows in range(1, n + 1):
        cols = math.ceil(n / rows)
        ratio = cols / rows
        diff = abs(ratio - target_ratio)
        if cols * rows >= n and diff < best_diff:
            best_rows, best_cols = rows, cols
            best_diff = diff
    return best_rows, best_cols


def _windows_console_codepages():
    """Return (oem_cp, ansi_cp) as Python codec names, e.g. ('cp866', 'cp1251')."""
    if os.name != "nt":
        return "cp437", "cp1252"
    try:
        k32 = ctypes.windll.kernel32
        oem = int(k32.GetOEMCP() or 437)
        acp = int(k32.GetACP() or 1252)
        return f"cp{oem}", f"cp{acp}"
    except Exception:
        return "cp866", "cp1251"


def _score_systeminfo_decoded(text):
    """Prefer real Cyrillic / known labels over mojibake (e.g. UTF-8 read as OEM)."""
    if not text:
        return -10**9
    score = 0
    if "\ufffd" in text:
        score -= 5000
    cyr = sum(1 for c in text if "\u0400" <= c <= "\u04ff")
    score += min(cyr, 800)
    good_needles = (
        "Майкрософт",
        "Microsoft",
        "Windows",
        "Назва ОС",
        "OS Name",
        "Host Name",
        "Ім'я вузла",
        "Processor(s)",
        "Процесор",
        "System Locale",
        "Локаль системи",
        "Часовий пояс",
        "Time Zone",
        "Total Physical Memory",
        "Повний обсяг",
    )
    for needle in good_needles:
        if needle in text:
            score += 80
    # Typical mojibake when UTF-8 is misread as single-byte Cyrillic OEM/ANSI
    junk = ("©€", "®б", "Њ ", "г€а", "«м", "я707")
    for j in junk:
        if j in text:
            score -= 400
    return score


def _decode_systeminfo_output(raw):
    """
    Decode Windows `systeminfo` console bytes. Output may be UTF-8 (after chcp 65001),
    OEM (console code page), ANSI (ACP), or UTF-16 when piped from cmd /U.
    """
    if not raw:
        return ""
    if len(raw) >= 2 and raw[:2] in (b"\xff\xfe", b"\xfe\xff"):
        for enc in ("utf-16-le", "utf-16-be"):
            try:
                return raw.decode(enc).lstrip("\ufeff")
            except UnicodeDecodeError:
                continue
    null_ratio = raw.count(b"\x00") / max(1, len(raw))
    if null_ratio > 0.08 and len(raw) % 2 == 0:
        for enc in ("utf-16-le", "utf-16-be"):
            try:
                t = raw.decode(enc).lstrip("\ufeff")
                if _score_systeminfo_decoded(t) > -10**6:
                    return t
            except UnicodeDecodeError:
                continue

    oem_enc, ansi_enc = _windows_console_codepages()
    encodings = (
        "utf-8-sig",
        "utf-8",
        oem_enc,
        ansi_enc,
        "cp866",
        "cp1251",
        "koi8-r",
        "mbcs",
        "latin-1",
    )
    seen = set()
    ordered = []
    for e in encodings:
        if e and e not in seen:
            seen.add(e)
            ordered.append(e)

    best_text, best_score = None, -10**9
    for enc in ordered:
        try:
            candidate = raw.decode(enc)
        except (UnicodeDecodeError, LookupError):
            continue
        sc = _score_systeminfo_decoded(candidate)
        if sc > best_score:
            best_text, best_score = candidate, sc
    if best_text is not None and best_score > -10**8:
        return best_text
    return raw.decode("utf-8", errors="replace")


def _run_systeminfo_bytes():
    """Run systeminfo; prefer UTF-8 console, then fall back to default console encoding."""
    creationflags = 0
    if os.name == "nt" and hasattr(subprocess, "CREATE_NO_WINDOW"):
        creationflags = subprocess.CREATE_NO_WINDOW
    # chcp 65001 makes many Windows builds emit UTF-8 from systeminfo; OEM is the usual failure mode without it.
    commands = (
        'cmd /c "chcp 65001 >nul 2>&1 && systeminfo"',
        "systeminfo",
    )
    last_err = b""
    for cmd in commands:
        try:
            proc = subprocess.run(
                cmd,
                shell=True,
                capture_output=True,
                creationflags=creationflags,
                timeout=120,
            )
        except subprocess.TimeoutExpired:
            last_err = b"Timeout running systeminfo"
            continue
        if proc.returncode == 0 and proc.stdout:
            return proc.returncode, proc.stdout, proc.stderr or b""
        last_err = proc.stderr or b""
    return 1, b"", last_err


def _get_volume_label_win32(root_path):
    """Windows volume label for root_path like 'C:\\'. Empty if unavailable."""
    if os.name != "nt":
        return ""
    root = root_path.rstrip("\\") + "\\"
    vol_name = ctypes.create_unicode_buffer(1024)
    fs_name = ctypes.create_unicode_buffer(256)
    # DWORD — через c_ulong (без ctypes.wintypes: у частини збірок атрибут недоступний)
    serial = ctypes.c_ulong()
    max_len = ctypes.c_ulong()
    flags = ctypes.c_ulong()
    try:
        ok = ctypes.windll.kernel32.GetVolumeInformationW(
            ctypes.c_wchar_p(root),
            vol_name,
            ctypes.sizeof(vol_name) // ctypes.sizeof(ctypes.c_wchar) - 1,
            ctypes.byref(serial),
            ctypes.byref(max_len),
            ctypes.byref(flags),
            fs_name,
            ctypes.sizeof(fs_name) // ctypes.sizeof(ctypes.c_wchar) - 1,
        )
    except Exception:
        return ""
    if not ok:
        return ""
    return (vol_name.value or "").strip()


def drive_card_title(disk):
    """
    Human-readable drive title: volume label and letter, e.g. 'Local Disk (C:)'.
    Avoids duplicate 'C:\\ (C:\\)' from raw psutil paths.
    """
    mount = (disk.mountpoint or "").rstrip("\\") or (disk.device or "").rstrip("\\")
    dev = (disk.device or "").rstrip("\\")
    if os.name == "nt":
        letter = None
        for candidate in (mount, dev):
            if len(candidate) >= 2 and candidate[1] == ":":
                letter = candidate[0].upper()
                break
        if letter:
            label = _get_volume_label_win32(f"{letter}:\\")
            if not label:
                label = "Local Disk"
            return f"{label} ({letter}:)"
        if mount:
            return mount
        return dev or "Drive"
    if mount and dev and mount != dev:
        return f"{dev} — {mount}"
    return mount or dev or "Drive"


class ProcessFetcher(QThread):
    update_processes = pyqtSignal(list)
    update_stats = pyqtSignal(float, float, str)
    update_graphs = pyqtSignal(list, float)
    update_drives = pyqtSignal(list)
    update_sensors = pyqtSignal(str, str, str, str, str, bool)

    def __init__(self, update_interval_s=0.5):
        super().__init__()
        self.update_interval_s = float(update_interval_s)

    def set_update_interval(self, update_interval_s):
        try:
            self.update_interval_s = max(0.15, float(update_interval_s))
        except Exception:
            self.update_interval_s = 0.5

    def run(self):
        last_process_emit = 0.0
        while True:
            now = time.monotonic()
            update_interval = float(getattr(self, "update_interval_s", 0.5))
            process_emit_interval = max(0.7, update_interval * 3.0)
            if (now - last_process_emit) >= process_emit_interval:
                processes_info = []
                for proc in psutil.process_iter(['pid', 'ppid', 'name', 'num_threads', 'username', 'memory_info', 'cpu_percent']):
                    if proc.info['name'] == "System Idle Process":
                        continue
                    processes_info.append([
                        proc.info['pid'],
                        proc.info['ppid'],
                        proc.info['name'],
                        proc.info['num_threads'],
                        proc.info['username'],
                        proc.info['memory_info'].rss / (1024 * 1024),
                        round(proc.info['cpu_percent'], 1)
                    ])
                self.update_processes.emit(processes_info)
                last_process_emit = now
            cpu_core_usages = psutil.cpu_percent(interval=update_interval, percpu=True)
            cpu_usage = sum(cpu_core_usages) / len(cpu_core_usages)
            memory_info = psutil.virtual_memory()
            _parts = psutil.disk_partitions()
            boot_drive = (_parts[0].mountpoint or _parts[0].device) if _parts else "C:\\"
            disk_info = psutil.disk_usage(boot_drive)
            total_disk = disk_info.total / (1024**3)
            used_disk = disk_info.used / (1024**3)
            used_percentage = used_disk / total_disk * 100
            disk_display = f"{used_percentage:.1f}%"
            self.update_stats.emit(cpu_usage, memory_info.percent, disk_display)
            self.update_graphs.emit(cpu_core_usages, memory_info.percent)
            self.update_drives.emit(psutil.disk_partitions())
            gpu_temp, _gpu_power_limit, gpu_power_usage = read_gpu_metrics()
            used_memory, available_memory = read_memory_details()
            gpu_ok = gpu_temp != "N/A" and gpu_power_usage != "N/A"
            self.update_sensors.emit(
                gpu_temp,
                gpu_power_usage,
                read_memory_frequency(),
                used_memory,
                available_memory,
                gpu_ok
            )


class BackgroundOperation(QThread):
    finished_message = pyqtSignal(str)

    def __init__(self, func):
        super().__init__()
        self.func = func

    def run(self):
        try:
            msg = self.func()
        except Exception as e:
            msg = f"Error: {e}"
        self.finished_message.emit(msg)



class SystemInfoDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("System Information")
        self.setGeometry(100, 100, 800, 600)
        if parent is not None and parent.styleSheet():
            self.setStyleSheet(parent.styleSheet())
        layout = QVBoxLayout(self)
        self.info_browser = QTextBrowser(self)
        self.info_browser.setFont(QFont("Segoe UI", 10))
        layout.addWidget(self.info_browser)
        self.display_system_info()

    def display_system_info(self):
        try:
            code, stdout_b, stderr_b = _run_systeminfo_bytes()
            if code == 0 and stdout_b:
                self.info_browser.setPlainText(_decode_systeminfo_output(stdout_b))
            else:
                err = _decode_systeminfo_output(stderr_b or b"")
                self.info_browser.setPlainText(f"Error running systeminfo command: {err}")
        except Exception as e:
            self.info_browser.setPlainText(f"An error occurred: {str(e)}")



class MetricCard(QFrame):
    def __init__(self, title, icon, color):
        super().__init__()
        self.setObjectName("metricCard")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(4)
        title_label = QLabel(f"{icon}  {title}")
        title_label.setObjectName("metricCardTitle")
        self.value_label = QLabel("0%")
        self.value_label.setObjectName("metricCardValue")
        self.value_label.setStyleSheet(f"color: {color};")
        layout.addWidget(title_label)
        layout.addWidget(self.value_label)

    def set_value(self, value):
        self.value_label.setText(value)

    def set_color(self, color):
        self.value_label.setStyleSheet(f"color: {color};")


class ProcessCard(QFrame):
    def __init__(self, process_info, frozen, callbacks, depth=0, has_children=False, collapsed=False, toggle_callback=None):
        super().__init__()
        process_id, _parent_pid, program_name, threads, user, memory, cpu = process_info
        self.pid = process_id
        self.checkbox = QCheckBox()
        self.checkbox.setProperty("pid", process_id)
        self.checkbox.setObjectName("processCheck")
        self.setObjectName("processCardChild" if depth > 0 else "processCard")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(8)

        top_row = QHBoxLayout()
        self.expand_button = QPushButton("▾")
        self.expand_button.setObjectName("expandButton")
        self.expand_button.setFixedWidth(26)
        if toggle_callback:
            self.expand_button.clicked.connect(lambda: toggle_callback(self.pid))

        self.title = QLabel()
        self.title.setObjectName("processTitle")
        top_row.addWidget(self.checkbox)
        top_row.addWidget(self.expand_button)
        top_row.addWidget(self.title)
        top_row.addStretch()
        self.state_label = QLabel()
        top_row.addWidget(self.state_label)
        layout.addLayout(top_row)

        self.detail = QLabel()
        self.detail.setObjectName("processDetail")
        layout.addWidget(self.detail)

        buttons_row = QHBoxLayout()
        buttons_row.addStretch()
        freeze_button = QPushButton("Freeze")
        unfreeze_button = QPushButton("Unfreeze")
        terminate_button = QPushButton("Terminate")
        freeze_button.clicked.connect(lambda: callbacks["freeze"]([self.pid]))
        unfreeze_button.clicked.connect(lambda: callbacks["unfreeze"]([self.pid]))
        terminate_button.clicked.connect(lambda: callbacks["terminate"]([self.pid]))
        buttons_row.addWidget(freeze_button)
        buttons_row.addWidget(unfreeze_button)
        buttons_row.addWidget(terminate_button)
        layout.addLayout(buttons_row)
        self.update_content(process_info, frozen, depth, has_children, collapsed)

    def update_content(self, process_info, frozen, depth, has_children, collapsed):
        process_id, _parent_pid, program_name, threads, user, memory, cpu = process_info
        prefix = ("  " * depth) + ("↳ " if depth > 0 else "")
        self.title.setText(f"{prefix}{program_name}  (PID {process_id})")
        self.detail.setText(
            f"CPU {cpu:.1f}%   |   Memory {memory:.2f} MB   |   Threads {threads}   |   User {user or 'N/A'}"
        )
        self.expand_button.setVisible(has_children)
        if has_children:
            self.expand_button.setText("▸" if collapsed else "▾")
        self.state_label.setText("Frozen" if frozen else "Running")
        self.state_label.setObjectName("processStateFrozen" if frozen else "processStateRunning")
        self.state_label.style().unpolish(self.state_label)
        self.state_label.style().polish(self.state_label)
        self.setObjectName("processCardChild" if depth > 0 else "processCard")
        self.style().unpolish(self)
        self.style().polish(self)


class SystemOn(QMainWindow):
    def __init__(self):
        super().__init__()
        self._is_initializing = True
        self.setWindowTitle("SystemOn")
        self.setWindowIcon(load_icon('systemon.png'))
        self.setGeometry(100, 100, 770, 700)
        self.always_on_top = False
        self.selected_pid = None
        self.selected_pids = set()
        self.frozen_pids = set()
        self.collapsed_pids = set()
        self.latest_process_data = []
        self.last_process_render_ts = 0.0
        self.last_process_signature = None
        self.process_cards = {}
        self.visible_process_order = []
        self.initial_collapse_done = False
        self.prev_drive = None
        self.latest_drive_data = []
        self.sensor_gpu_temp_graph = None
        self.sensor_gpu_power_graph = None
        self.performance_mode = "overall"
        self._pending_cpu_usages = []
        self._pending_memory_usage = 0.0
        self._pending_sensor_bundle = None
        self._cpu_graph_pool = []
        self._overall_cpu_graph = None
        self._logical_cpu_count = psutil.cpu_count(logical=True) or 1
        self._physical_cpu_count = psutil.cpu_count(logical=False) or self._logical_cpu_count
        self.theme_mode = "dark"
        self.accent_color = "#6366f1"
        self.refresh_interval_s = 0.5
        self.last_page_index = 0
        self._graph_refresh_timer = QTimer(self)
        self._graph_refresh_timer.setSingleShot(True)
        self._graph_refresh_timer.timeout.connect(self._flush_visible_graphs)
        self.load_settings()
        self.init_ui()
        self.fetcher = ProcessFetcher(update_interval_s=self.refresh_interval_s)
        self.fetcher.update_processes.connect(self.update_process_table)
        self.fetcher.update_graphs.connect(self.update_graphs)
        self.fetcher.update_drives.connect(self.update_drives)
        self.fetcher.update_stats.connect(self.update_stats)
        self.fetcher.update_sensors.connect(self.update_sensors)
        self.fetcher.start()
        app_context = {"main_window": self}
        self.plugins = load_plugins(app_context)
        if self.always_on_top:
            self.set_always_on_top_state(True)
        self._is_initializing = False

    def init_ui(self):
        loadStyle()
        self.base_stylesheet = self.styleSheet()

        main_widget = QWidget(self)
        main_widget.setObjectName("appRoot")
        self.setCentralWidget(main_widget)
        root_layout = QHBoxLayout(main_widget)
        root_layout.setContentsMargins(12, 12, 12, 12)
        root_layout.setSpacing(12)

        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(210)
        sidebar_layout = QVBoxLayout(sidebar)
        sidebar_layout.setContentsMargins(12, 14, 12, 14)
        sidebar_layout.setSpacing(8)
        title = QLabel("SystemOn")
        title.setObjectName("sidebarTitle")
        subtitle = QLabel("Monitoring Dashboard")
        subtitle.setObjectName("sidebarSubtitle")
        sidebar_layout.addWidget(title)
        sidebar_layout.addWidget(subtitle)

        self.page_stack = QStackedWidget()
        self.nav_buttons = []
        nav_specs = [
            ("🏠  Overview", 0),
            ("🧩  Processes", 1),
            ("📈  Performance", 2),
            ("💽  Drives", 3),
            ("🌡  Sensors", 4),
        ]
        for text, page_index in nav_specs:
            button = QPushButton(text)
            button.setObjectName("navButton")
            button.setCheckable(True)
            button.clicked.connect(lambda _checked, i=page_index: self.switch_page(i))
            sidebar_layout.addWidget(button)
            self.nav_buttons.append(button)
        sidebar_layout.addStretch()
        root_layout.addWidget(sidebar)

        content_wrapper = QWidget()
        content_layout = QVBoxLayout(content_wrapper)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(12)

        overview_page = QWidget()
        overview_layout = QVBoxLayout(overview_page)
        overview_layout.setContentsMargins(0, 0, 0, 0)
        overview_layout.setSpacing(12)
        cards_row = QHBoxLayout()
        self.cpu_card = MetricCard("CPU Usage", "⚙", "#4f46e5")
        self.memory_card = MetricCard("Memory Usage", "🧠", "#0891b2")
        _boot_parts = psutil.disk_partitions()
        _boot = _boot_parts[0] if _boot_parts else None
        boot_title = drive_card_title(_boot) if _boot else "Boot Drive"
        self.disk_card = MetricCard(f"Boot Drive · {boot_title}", "💽", "#0f766e")
        cards_row.addWidget(self.cpu_card)
        cards_row.addWidget(self.memory_card)
        cards_row.addWidget(self.disk_card)
        overview_layout.addLayout(cards_row)

        quick_panel = QFrame()
        quick_panel.setObjectName("panelCard")
        quick_layout = QVBoxLayout(quick_panel)
        quick_layout.setContentsMargins(16, 14, 16, 14)
        quick_title = QLabel("Quick Actions")
        quick_title.setObjectName("panelTitle")
        quick_layout.addWidget(quick_title)

        refresh_row = QHBoxLayout()
        refresh_label = QLabel("Update speed")
        refresh_label.setObjectName("sensorValue")
        self.refresh_speed_combo = QComboBox()
        self.refresh_speed_combo.addItem("Very fast", 0.25)
        self.refresh_speed_combo.addItem("Fast", 0.5)
        self.refresh_speed_combo.addItem("Balanced", 1.0)
        self.refresh_speed_combo.addItem("Low CPU", 2.0)
        self._set_refresh_combo_from_interval(self.refresh_interval_s)
        self.refresh_speed_combo.currentIndexChanged.connect(self.on_refresh_speed_changed)
        refresh_row.addWidget(refresh_label)
        refresh_row.addWidget(self.refresh_speed_combo, 1)
        quick_layout.addLayout(refresh_row)

        theme_row = QHBoxLayout()
        dark_btn = QPushButton("Dark Gray")
        dark_btn.clicked.connect(lambda: self.apply_theme("dark"))
        light_btn = QPushButton("Light")
        light_btn.clicked.connect(lambda: self.apply_theme("light"))
        accent_btn = QPushButton("Accent Color")
        accent_btn.clicked.connect(self.pick_accent_color)
        theme_row.addWidget(dark_btn)
        theme_row.addWidget(light_btn)
        theme_row.addWidget(accent_btn)
        theme_row.addStretch()
        quick_layout.addLayout(theme_row)

        functions_panel = QFrame()
        functions_panel.setObjectName("panelCard")
        functions_layout = QVBoxLayout(functions_panel)
        functions_layout.setContentsMargins(16, 14, 16, 14)
        functions_title = QLabel("Functions")
        functions_title.setObjectName("panelTitle")
        functions_layout.addWidget(functions_title)

        sysinfo_btn = QPushButton("System Information")
        sysinfo_btn.clicked.connect(self.view_system_info)
        pin_btn = QPushButton("Toggle Always On Top")
        pin_btn.clicked.connect(self.toggle_always_on_top)
        ram_btn = QPushButton("Clear RAM Cache")
        ram_btn.clicked.connect(self.clear_ram_cache_with_progress)
        temp_btn = QPushButton("Clean Temp Folder")
        temp_btn.clicked.connect(self.clean_temp_folder_with_progress)
        exit_btn = QPushButton("Exit Application")
        exit_btn.clicked.connect(self.close)

        for button in (
            sysinfo_btn,
            pin_btn,
            ram_btn,
            temp_btn,
            exit_btn,
        ):
            functions_layout.addWidget(button)
        self.overview_status_label = QLabel("")
        self.overview_status_label.setObjectName("overviewStatus")
        functions_layout.addWidget(self.overview_status_label)
        self.overview_progress = QProgressBar()
        self.overview_progress.setObjectName("overviewProgress")
        self.overview_progress.setVisible(False)
        self.overview_progress.setTextVisible(False)
        functions_layout.addWidget(self.overview_progress)
        functions_layout.addStretch()

        overview_layout.addWidget(quick_panel)
        overview_layout.addWidget(functions_panel)
        overview_layout.addStretch()
        self.page_stack.addWidget(overview_page)

        processes_page = QWidget()
        processes_layout = QVBoxLayout(processes_page)
        processes_layout.setContentsMargins(0, 0, 0, 0)
        processes_layout.setSpacing(10)
        process_actions = QHBoxLayout()
        for text, handler in (
            ("Freeze selected", self.freeze_selected_processes),
            ("Unfreeze selected", self.unfreeze_selected_processes),
            ("Terminate selected", self.force_terminate_selected_processes),
        ):
            btn = QPushButton(text)
            btn.clicked.connect(handler)
            process_actions.addWidget(btn)
        process_actions.addStretch()
        processes_layout.addLayout(process_actions)
        self.process_summary_label = QLabel("Process cards refresh every cycle")
        self.process_summary_label.setStyleSheet("font-size: 12px; color: #52607f;")
        processes_layout.addWidget(self.process_summary_label)
        self.process_scroll = QScrollArea()
        self.process_scroll.setWidgetResizable(True)
        self.process_container = QWidget()
        self.process_cards_layout = QVBoxLayout(self.process_container)
        self.process_cards_layout.setContentsMargins(0, 0, 0, 0)
        self.process_cards_layout.setSpacing(8)
        self.process_scroll.setWidget(self.process_container)
        processes_layout.addWidget(self.process_scroll)
        self.page_stack.addWidget(processes_page)

        self.graphs_tab = QWidget()
        self.graphs_tab_layout = QVBoxLayout(self.graphs_tab)
        self.graphs_tab_layout.setAlignment(Qt.AlignTop)
        self.graphs_tab_layout.setContentsMargins(0, 0, 0, 0)
        self.performance_buttons = {}
        mode_row = QHBoxLayout()
        for mode_key, mode_label in (
            ("overall", "Overall"),
            ("cores", "Cores"),
            ("threads", "Threads"),
        ):
            button = QPushButton(mode_label)
            button.setCheckable(True)
            button.clicked.connect(lambda _checked, m=mode_key: self.set_performance_mode(m))
            mode_row.addWidget(button)
            self.performance_buttons[mode_key] = button
        mode_row.addStretch()
        self.graphs_tab_layout.addLayout(mode_row)
        self.cpu_graphs = []
        self.cpu_graph_layout = QGridLayout()
        self.cpu_graph_layout.setSpacing(8)
        self.cpu_graph_layout.setContentsMargins(0, 0, 0, 0)
        self.graphs_tab_layout.addLayout(self.cpu_graph_layout)
        self.graph_height = 170
        self._ensure_cpu_graph_pool()
        self.memory_graph = RGraph(
            x_points=60,
            y_points=100,
            hue_offset=270,
            label=f"Memory ({memory_string()})",
            compact=False,
        )
        self.memory_graph.setFixedHeight(self.graph_height)
        self.memory_graph.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.graphs_tab_layout.addWidget(self.memory_graph, 0)
        self.set_performance_mode("overall")
        self.page_stack.addWidget(self.graphs_tab)

        self.disk_tab = QWidget()
        self.disk_tab_layout = QVBoxLayout(self.disk_tab)
        self.disk_tab_layout.setAlignment(Qt.AlignTop)
        self.page_stack.addWidget(self.disk_tab)

        self.sensors_tab = QWidget()
        self.sensors_layout = QVBoxLayout(self.sensors_tab)
        self.sensors_layout.setAlignment(Qt.AlignTop)
        self.sensor_gpu_label = QLabel("GPU Temperature: N/A")
        self.sensor_gpu_power_usage_label = QLabel("GPU Power Usage: N/A")
        self.sensor_memory_frequency_label = QLabel("Memory Frequency: N/A")
        self.sensor_memory_used_label = QLabel("Memory Used: N/A")
        self.sensor_memory_available_label = QLabel("Memory Available: N/A")
        self.sensor_status_label = QLabel("Sensor Source: NVIDIA SMI")

        gpu_temp_card = QFrame()
        gpu_temp_card.setObjectName("sensorCard")
        gpu_temp_layout = QVBoxLayout(gpu_temp_card)
        gpu_temp_layout.setContentsMargins(12, 10, 12, 10)
        self.sensor_gpu_label.setObjectName("sensorValue")
        gpu_temp_layout.addWidget(self.sensor_gpu_label)
        self.sensor_gpu_temp_graph = RGraph(x_points=60, y_points=120, hue_offset=20, label="GPU Temperature")
        self.sensor_gpu_temp_graph.setFixedHeight(self.graph_height)
        gpu_temp_layout.addWidget(self.sensor_gpu_temp_graph)
        self.sensors_layout.addWidget(gpu_temp_card)

        gpu_power_card = QFrame()
        gpu_power_card.setObjectName("sensorCard")
        gpu_power_layout = QVBoxLayout(gpu_power_card)
        gpu_power_layout.setContentsMargins(12, 10, 12, 10)
        self.sensor_gpu_power_usage_label.setObjectName("sensorValue")
        gpu_power_layout.addWidget(self.sensor_gpu_power_usage_label)
        self.sensor_gpu_power_graph = RGraph(x_points=60, y_points=450, hue_offset=330, label="GPU Voltage/Power")
        self.sensor_gpu_power_graph.setFixedHeight(self.graph_height)
        gpu_power_layout.addWidget(self.sensor_gpu_power_graph)
        self.sensors_layout.addWidget(gpu_power_card)

        for label in (
            self.sensor_memory_frequency_label,
            self.sensor_memory_used_label,
            self.sensor_memory_available_label,
        ):
            card = QFrame()
            card.setObjectName("sensorCard")
            card_layout = QVBoxLayout(card)
            card_layout.setContentsMargins(12, 10, 12, 10)
            label.setObjectName("sensorValue")
            card_layout.addWidget(label)
            self.sensors_layout.addWidget(card)
        self.sensor_status_label.setStyleSheet(f"font-size: 14px; font-weight: bold; color: {self.accent_color}; padding-top: 8px;")
        self.sensors_layout.addWidget(self.sensor_status_label)
        self.page_stack.addWidget(self.sensors_tab)

        content_layout.addWidget(self.page_stack)
        root_layout.addWidget(content_wrapper, 1)

        self.menuBar().setVisible(False)
        self.switch_page(self.last_page_index if 0 <= self.last_page_index < self.page_stack.count() else 0)
        self.apply_theme(self.theme_mode)

    def switch_page(self, index):
        self.page_stack.setCurrentIndex(index)
        for i, button in enumerate(self.nav_buttons):
            button.setChecked(i == index)
        self.last_page_index = index
        if index == PAGE_PERFORMANCE:
            self._apply_pending_graph_data()
        elif index == PAGE_PROCESSES and self.latest_process_data:
            self.last_process_signature = None
            self.update_process_table(self.latest_process_data)
        elif index == PAGE_DRIVES and self.latest_drive_data:
            self.prev_drive = None
            self.update_drives(self.latest_drive_data)
        elif index == PAGE_SENSORS and self._pending_sensor_bundle:
            self._render_sensors(**self._pending_sensor_bundle)
        self._schedule_graph_refresh(force=True)
        self.save_settings()

    def _ensure_cpu_graph_pool(self):
        if self._cpu_graph_pool:
            return
        for i in range(self._logical_cpu_count):
            graph = RGraph(
                x_points=60,
                y_points=100,
                hue_offset=0,
                label=f"Thread #{i}",
                compact=True,
            )
            graph.setFixedHeight(self.graph_height)
            graph.setMinimumWidth(1)
            graph.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            self._cpu_graph_pool.append(graph)
        self._overall_cpu_graph = RGraph(
            x_points=60,
            y_points=100,
            hue_offset=0,
            label="CPU Total",
            compact=False,
        )
        self._overall_cpu_graph.setFixedHeight(self.graph_height)
        self._overall_cpu_graph.setMinimumWidth(1)
        self._overall_cpu_graph.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

    def _schedule_graph_refresh(self, force=False):
        if force:
            self._flush_visible_graphs()
            return
        timer = getattr(self, "_graph_refresh_timer", None)
        if timer is None:
            self._flush_visible_graphs()
            return
        if not timer.isActive():
            timer.start(130)

    def _flush_visible_graphs(self):
        if not hasattr(self, "page_stack"):
            return
        idx = self.page_stack.currentIndex()
        if idx == PAGE_PERFORMANCE:
            for graph in self.cpu_graphs:
                graph.flush_draw()
            if self.memory_graph is not None:
                self.memory_graph.flush_draw()
        elif idx == PAGE_SENSORS:
            for graph in (self.sensor_gpu_temp_graph, self.sensor_gpu_power_graph):
                if graph is not None:
                    graph.flush_draw()

    def _apply_pending_graph_data(self):
        cpu_usages = self._pending_cpu_usages or []
        memory_usage = self._pending_memory_usage
        if not self.cpu_graphs:
            return
        if self.performance_mode == "overall":
            total_usage = sum(cpu_usages) / max(1, len(cpu_usages))
            self.cpu_graphs[0].push_value(total_usage)
        elif self.performance_mode == "cores":
            core_values = self._aggregate_core_usage(cpu_usages)
            for i, usage in enumerate(core_values[: len(self.cpu_graphs)]):
                self.cpu_graphs[i].push_value(usage)
        else:
            for i, usage in enumerate(cpu_usages[: len(self.cpu_graphs)]):
                self.cpu_graphs[i].push_value(usage)
        if self.memory_graph is not None:
            self.memory_graph.push_value(memory_usage)

    def _set_refresh_combo_from_interval(self, interval):
        best_index = 0
        best_diff = float("inf")
        for i in range(self.refresh_speed_combo.count()):
            value = self.refresh_speed_combo.itemData(i)
            if value is None:
                continue
            diff = abs(float(value) - float(interval))
            if diff < best_diff:
                best_diff = diff
                best_index = i
        self.refresh_speed_combo.setCurrentIndex(best_index)

    def build_dashboard_stylesheet(self):
        accent = self.accent_color
        if self.theme_mode == "light":
            root_bg = "#ffffff"
            sidebar_gradient = "qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #f2f5fb, stop:1 #e6ebf5)"
            sidebar_border = "#d6dde9"
            text = "#1f2937"
            button_bg = "#f8fafc"
            button_border = "#cbd5e1"
            button_hover = "#eef2f7"
            card_bg = "#f8fafc"
            card_border = "#dbe3ef"
            title_text = "#334155"
            detail_text = "#475569"
        else:
            root_bg = "#151515"
            sidebar_gradient = "qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #202020, stop:1 #161616)"
            sidebar_border = "#343434"
            text = "#e5e7eb"
            button_bg = "#2a2a2a"
            button_border = "#404040"
            button_hover = "#363636"
            card_bg = "#1f1f1f"
            card_border = "#3a3a3a"
            title_text = "#e5e7eb"
            detail_text = "#cbd5e1"
        hover_text = text

        return f"""
            #appRoot {{ background: {root_bg}; }}
            #appRoot QWidget {{ color: {text}; background: transparent; }}
            #appRoot QScrollArea, #appRoot QScrollArea > QWidget > QWidget {{ background: transparent; border: none; }}
            #appRoot QPushButton {{ background: {button_bg}; border: 1px solid {button_border}; color: {text}; border-radius: 10px; padding: 8px 12px; min-height: 18px; }}
            #appRoot QPushButton:hover {{ background: {button_hover}; border: 1px solid {button_border}; color: {hover_text}; }}
            #appRoot QPushButton:pressed {{ border: 1px solid {accent}; }}
            #sidebar {{ background: {sidebar_gradient}; border-radius: 18px; border: 1px solid {sidebar_border}; }}
            #sidebarTitle {{ font-size: 20px; font-weight: 800; color: {title_text}; padding: 4px 6px; }}
            #sidebarSubtitle {{ font-size: 11px; color: {detail_text}; padding: 0 6px 10px 6px; }}
            #navButton {{ color: {text}; font-size: 14px; font-weight: 600; text-align: left; padding: 10px 14px; border-radius: 10px; border: 1px solid {button_border}; min-height: 20px; }}
            #navButton:hover {{ background: {button_hover}; border: 1px solid {button_border}; color: {hover_text}; }}
            #navButton:checked {{ background: {accent}; color: #ffffff; border-color: {accent}; }}
            #navButton:checked:hover {{ background: {accent}; color: #ffffff; border-color: {accent}; }}
            #metricCard, #panelCard, #processCard, #processCardChild, #sensorCard, #driveCard {{ background: {card_bg}; border: 1px solid {card_border}; border-radius: 14px; }}
            #processCardChild {{ margin-left: 26px; border-left: 3px solid {accent}; }}
            #metricCardTitle {{ color: {detail_text}; font-size: 13px; font-weight: 600; }}
            #metricCardValue {{ font-size: 30px; font-weight: 700; }}
            #panelTitle {{ font-size: 18px; font-weight: 700; color: {title_text}; }}
            #processTitle {{ font-size: 14px; font-weight: 700; color: {title_text}; }}
            #processDetail {{ color: {detail_text}; font-size: 12px; }}
            #sensorValue {{ font-size: 14px; font-weight: 600; color: {title_text}; }}
            #overviewStatus {{ font-size: 12px; color: {detail_text}; padding-top: 6px; }}
            #overviewProgress {{ height: 6px; border-radius: 3px; }}
            #overviewProgress::chunk {{ background: {accent}; border-radius: 3px; }}
            #expandButton {{ min-width: 24px; max-width: 24px; padding: 2px; border-radius: 6px; }}
            #processStateRunning {{ color: #166534; background: #dcfce7; border-radius: 9px; padding: 3px 8px; font-weight: 700; }}
            #processStateFrozen {{ color: #92400e; background: #ffedd5; border-radius: 9px; padding: 3px 8px; font-weight: 700; }}
            #appRoot RGraph {{ background-color: {root_bg}; color: {text}; border: 1px solid {button_border}; border-radius: 10px; }}
            #appRoot QComboBox {{
                background: {button_bg};
                border: 1px solid {button_border};
                border-radius: 10px;
                padding: 8px 12px;
                min-height: 20px;
                color: {text};
            }}
            #appRoot QComboBox:hover {{ border: 1px solid {accent}; }}
            #appRoot QComboBox::drop-down {{ border: none; width: 28px; }}
            #appRoot QComboBox QAbstractItemView {{
                background: {card_bg};
                color: {text};
                selection-background-color: {accent};
                selection-color: #ffffff;
                border: 1px solid {button_border};
                outline: 0;
                padding: 4px;
            }}
            #appRoot QScrollBar:vertical {{ background: transparent; width: 12px; margin: 4px 2px 4px 2px; border: none; }}
            #appRoot QScrollBar::handle:vertical {{ background: {button_border}; border-radius: 6px; min-height: 28px; }}
            #appRoot QScrollBar::handle:vertical:hover {{ background: {accent}; }}
            #appRoot QScrollBar::add-line:vertical, #appRoot QScrollBar::sub-line:vertical {{ height: 0px; border: none; background: transparent; }}
            #appRoot QScrollBar::add-page:vertical, #appRoot QScrollBar::sub-page:vertical {{ background: transparent; }}
            #appRoot QScrollBar:horizontal {{ background: transparent; height: 12px; margin: 2px 4px 2px 4px; border: none; }}
            #appRoot QScrollBar::handle:horizontal {{ background: {button_border}; border-radius: 6px; min-width: 28px; }}
            #appRoot QScrollBar::handle:horizontal:hover {{ background: {accent}; }}
            #appRoot QScrollBar::add-line:horizontal, #appRoot QScrollBar::sub-line:horizontal {{ width: 0px; border: none; background: transparent; }}
            #appRoot QScrollBar::add-page:horizontal, #appRoot QScrollBar::sub-page:horizontal {{ background: transparent; }}
        """

    def apply_theme(self, mode):
        self.theme_mode = mode
        self.setStyleSheet(self.base_stylesheet + self.build_dashboard_stylesheet())
        self.cpu_card.set_color(self.accent_color)
        self.memory_card.set_color(self.accent_color)
        self.disk_card.set_color(self.accent_color)
        self.apply_graph_theme()
        self.prev_drive = None
        if self.latest_drive_data:
            self.update_drives(self.latest_drive_data)
        self.save_settings()

    def on_refresh_speed_changed(self):
        if not hasattr(self, "refresh_speed_combo") or self.refresh_speed_combo is None:
            return
        interval = self.refresh_speed_combo.currentData()
        if interval is None:
            return
        self.refresh_interval_s = float(interval)
        if hasattr(self, "fetcher") and self.fetcher is not None:
            self.fetcher.set_update_interval(self.refresh_interval_s)
        self.save_settings()

    def apply_graph_theme(self):
        if self.theme_mode == "light":
            bg = QColor("#ffffff")
            fg = QColor("#0f172a")
        else:
            bg = QColor("#000000")
            fg = QColor("#d1d5db")

        pool_graphs = list(self._cpu_graph_pool)
        if self._overall_cpu_graph is not None:
            pool_graphs.append(self._overall_cpu_graph)
        graphs = [
            *pool_graphs,
            self.memory_graph,
            self.sensor_gpu_temp_graph,
            self.sensor_gpu_power_graph,
        ]
        for graph in (g for g in graphs if g is not None):
            palette = graph.palette()
            palette.setColor(QPalette.Window, bg)
            palette.setColor(QPalette.Base, bg)
            palette.setColor(QPalette.WindowText, fg)
            palette.setColor(QPalette.Text, fg)
            graph.setAutoFillBackground(True)
            graph.setPalette(palette)
            graph.styling = graph.get_styling()
            graph.mark_styling_dirty()
        self._schedule_graph_refresh()

    def set_performance_mode(self, mode):
        if mode == self.performance_mode:
            return
        self.performance_mode = mode
        for key, button in self.performance_buttons.items():
            button.setChecked(key == mode)
        QTimer.singleShot(0, self._deferred_performance_mode_change)

    def _deferred_performance_mode_change(self):
        self.rebuild_performance_graphs()
        self._apply_pending_graph_data()
        self._schedule_graph_refresh(force=True)
        self.save_settings()

    def rebuild_performance_graphs(self):
        self._ensure_cpu_graph_pool()
        while self.cpu_graph_layout.count():
            item = self.cpu_graph_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
        for graph in self._cpu_graph_pool:
            graph.hide()
        if self._overall_cpu_graph is not None:
            self._overall_cpu_graph.hide()
            self._overall_cpu_graph.setParent(None)

        self.cpu_graphs = []
        for c in range(24):
            self.cpu_graph_layout.setColumnStretch(c, 0)
        for r in range(24):
            self.cpu_graph_layout.setRowStretch(r, 0)
            self.cpu_graph_layout.setRowMinimumHeight(r, 0)

        if self.performance_mode == "overall":
            graph = self._overall_cpu_graph
            graph.show()
            self.cpu_graphs.append(graph)
            self.cpu_graph_layout.addWidget(graph, 0, 0)
            self.cpu_graph_layout.setColumnStretch(0, 1)
            return

        if self.performance_mode == "cores":
            count = self._physical_cpu_count
            label_prefix = "Core"
        else:
            count = self._logical_cpu_count
            label_prefix = "Thread"

        grid_rows, grid_cols = optimal_grid(count)
        for i in range(count):
            graph = self._cpu_graph_pool[i]
            graph.set_label(f"{label_prefix} #{i}")
            graph.show()
            self.cpu_graphs.append(graph)
            self.cpu_graph_layout.addWidget(graph, i // grid_cols, i % grid_cols)
        for c in range(grid_cols):
            self.cpu_graph_layout.setColumnStretch(c, 1)
        for r in range(grid_rows):
            self.cpu_graph_layout.setRowMinimumHeight(r, self.graph_height)

    def _aggregate_core_usage(self, cpu_usages):
        physical_count = psutil.cpu_count(logical=False) or len(cpu_usages) or 1
        if not cpu_usages:
            return [0.0] * physical_count
        group_size = max(1, len(cpu_usages) // physical_count)
        values = []
        for i in range(physical_count):
            chunk = cpu_usages[i * group_size:(i + 1) * group_size]
            if not chunk:
                chunk = [cpu_usages[min(i, len(cpu_usages) - 1)]]
            values.append(sum(chunk) / len(chunk))
        return values

    def _extract_numeric_prefix(self, value, fallback=0.0):
        if not isinstance(value, str):
            return fallback
        try:
            return float(value.split()[0])
        except Exception:
            return fallback

    def pick_accent_color(self):
        color = QColorDialog.getColor(QColor(self.accent_color), self, "Select Accent Color")
        if color.isValid():
            self.accent_color = color.name()
            self.apply_theme(self.theme_mode)

    def update_stats(self, cpu_usage, memory_usage, disk_usage):
        self.cpu_card.set_value(f"{cpu_usage:.1f}%")
        self.memory_card.set_value(f"{memory_usage:.1f}%")
        self.disk_card.set_value(disk_usage)

    def update_process_table(self, process_data):
        self.latest_process_data = process_data
        if self.page_stack.currentIndex() != PAGE_PROCESSES:
            return
        current_ts = time.monotonic()
        structure_signature = tuple(
            sorted((p[0], p[1], p[2], p[3], p[4]) for p in process_data if p[2])
        )
        ui_signature = (
            structure_signature,
            tuple(sorted(self.frozen_pids)),
            tuple(sorted(self.collapsed_pids)),
        )

        throttle_s = 1.4
        if ui_signature == self.last_process_signature and (current_ts - self.last_process_render_ts) < throttle_s:
            return
        self.last_process_signature = ui_signature
        self.last_process_render_ts = current_ts
        callbacks = {
            "freeze": self.freeze_selected_processes,
            "unfreeze": self.unfreeze_selected_processes,
            "terminate": self.force_terminate_selected_processes,
        }
        pid_map, children, roots = self._build_process_hierarchy(process_data)
        if not self.initial_collapse_done:
            self.collapsed_pids.update(pid for pid, child_list in children.items() if child_list)
            self.initial_collapse_done = True
        visible_items = list(self._iter_visible_processes(pid_map, children, roots, limit=220))
        visible_order = [pid for pid, _depth in visible_items]

        stale_pids = [pid for pid in self.process_cards if pid not in pid_map]
        for pid in stale_pids:
            card = self.process_cards.pop(pid)
            card.setParent(None)
            card.deleteLater()
            self.selected_pids.discard(pid)

        for pid, depth in visible_items:
            parent_pid, program_name, threads, user, memory, cpu = pid_map[pid]
            process = [pid, parent_pid, program_name, threads, user, memory, cpu]
            has_children = len(children.get(pid, [])) > 0
            card = self.process_cards.get(pid)
            if card is None:
                card = ProcessCard(
                    process,
                    pid in self.frozen_pids,
                    callbacks,
                    depth=depth,
                    has_children=has_children,
                    collapsed=pid in self.collapsed_pids,
                    toggle_callback=self.toggle_process_children
                )
                card.checkbox.toggled.connect(lambda checked, process_id=pid: self.on_process_card_checked(process_id, checked))
                self.process_cards[pid] = card
            else:
                card.update_content(process, pid in self.frozen_pids, depth, has_children, pid in self.collapsed_pids)
            card.checkbox.blockSignals(True)
            card.checkbox.setChecked(pid in self.selected_pids)
            card.checkbox.blockSignals(False)

        if visible_order != self.visible_process_order:
            self._rebuild_process_layout(visible_order)
            self.visible_process_order = visible_order

        self.process_summary_label.setText(
            f"Showing {len(visible_order)} of {len(pid_map)} processes | "
            f"Frozen: {len(self.frozen_pids)} | Selected: {len(self.selected_pids)}"
        )

    def _build_process_hierarchy(self, process_data):
        pid_map = {}
        for process in process_data:
            process_id, parent_pid, program_name, threads, user, memory, cpu = process
            if not program_name:
                continue
            pid_map[process_id] = (parent_pid, program_name, threads, user, memory, cpu)

        children = {}
        roots = []
        for pid, (parent_pid, _program_name, _threads, _user, _memory, _cpu) in pid_map.items():
            if parent_pid in pid_map:
                children.setdefault(parent_pid, []).append(pid)
            else:
                roots.append(pid)

        def sort_key(pid):
            return pid_map[pid][1].lower()

        roots.sort(key=sort_key)
        for parent_pid in children:
            children[parent_pid].sort(key=sort_key)
        return pid_map, children, roots

    def _iter_visible_processes(self, pid_map, children, roots, limit):
        rendered = 0

        def walk(pid, depth):
            nonlocal rendered
            if rendered >= limit:
                return
            rendered += 1
            yield pid, depth
            if pid in self.collapsed_pids:
                return
            for child_pid in children.get(pid, []):
                if rendered >= limit:
                    return
                yield from walk(child_pid, depth + 1)

        for root_pid in roots:
            if rendered >= limit:
                break
            yield from walk(root_pid, 0)

    def _rebuild_process_layout(self, visible_order):
        while self.process_cards_layout.count():
            item = self.process_cards_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.setParent(None)
        for pid in visible_order:
            self.process_cards_layout.addWidget(self.process_cards[pid])
        self.process_cards_layout.addStretch()

    def get_selected_pids(self):
        return sorted(self.selected_pids)

    def on_process_card_checked(self, pid, checked):
        if checked:
            self.selected_pids.add(pid)
        else:
            self.selected_pids.discard(pid)

    def sync_selected_processes(self):
        self.selected_pids = set(self.get_selected_pids())

    def toggle_process_children(self, pid):
        if pid in self.collapsed_pids:
            self.collapsed_pids.discard(pid)
        else:
            self.collapsed_pids.add(pid)
        if self.latest_process_data:
            self.update_process_table(self.latest_process_data)

    def update_graphs(self, cpu_usages, memory_usage):
        self._pending_cpu_usages = list(cpu_usages) if cpu_usages else []
        self._pending_memory_usage = float(memory_usage)
        if self.page_stack.currentIndex() != PAGE_PERFORMANCE:
            return
        self._apply_pending_graph_data()
        self._schedule_graph_refresh()

    def update_sensors(
        self,
        gpu_temperature,
        gpu_power_usage,
        memory_frequency,
        memory_used,
        memory_available,
        gpu_ok
    ):
        self._pending_sensor_bundle = {
            "gpu_temperature": gpu_temperature,
            "gpu_power_usage": gpu_power_usage,
            "memory_frequency": memory_frequency,
            "memory_used": memory_used,
            "memory_available": memory_available,
            "gpu_ok": gpu_ok,
        }
        if self.page_stack.currentIndex() != PAGE_SENSORS:
            return
        self._render_sensors(**self._pending_sensor_bundle)

    def _render_sensors(
        self,
        gpu_temperature,
        gpu_power_usage,
        memory_frequency,
        memory_used,
        memory_available,
        gpu_ok,
    ):
        self.sensor_gpu_label.setText(f"GPU Temperature: {gpu_temperature}")
        self.sensor_gpu_power_usage_label.setText(f"GPU Power Usage: {gpu_power_usage}")
        self.sensor_memory_frequency_label.setText(f"Memory Frequency: {memory_frequency}")
        self.sensor_memory_used_label.setText(f"Memory Used: {memory_used}")
        self.sensor_memory_available_label.setText(f"Memory Available: {memory_available}")
        self.sensor_status_label.setText("Sensor Source: NVIDIA SMI")
        if self.sensor_gpu_temp_graph is not None:
            self.sensor_gpu_temp_graph.push_value(self._extract_numeric_prefix(gpu_temperature))
        if self.sensor_gpu_power_graph is not None:
            self.sensor_gpu_power_graph.push_value(self._extract_numeric_prefix(gpu_power_usage))
        self._schedule_graph_refresh()
        color = "#22c55e" if gpu_ok else "#f59e0b"
        self.sensor_status_label.setStyleSheet(f"font-size: 14px; font-weight: bold; color: {color}; padding-top: 8px;")

    def update_drives(self, drive_data):
        self.latest_drive_data = drive_data
        if self.page_stack.currentIndex() != PAGE_DRIVES:
            self.prev_drive = None
            return
        if drive_data == self.prev_drive:
            return
        self.prev_drive = drive_data
        disks = drive_data
        while self.disk_tab_layout.count():
            item = self.disk_tab_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.setParent(None)
        for disk in disks:
            usage_path = disk.mountpoint or disk.device
            try:
                disk_info = psutil.disk_usage(usage_path)
            except PermissionError:
                continue
            except OSError:
                continue
            disk_container = QVBoxLayout()
            disk_container.setAlignment(Qt.AlignTop | Qt.AlignLeft)
            total_disk = disk_info.total
            used_disk = disk_info.used
            used_percentage = used_disk / total_disk * 100
            used_percentage_100k = used_disk / total_disk * 100000

            def format_size(size):
                for unit in ['B', 'KB', 'MB', 'GB', 'TB', 'PB', 'EB', 'ZB', 'YB']:
                    if size < 1024:
                        return f"{size:.2f} {unit}"
                    size /= 1024
                return f"{size:.2f} YB"

            total_disk_display = format_size(total_disk)
            used_disk_display = format_size(used_disk)
            disk_display = f"{used_disk_display}/{total_disk_display} ({used_percentage:.1f}%)"
            title_color = "#1f2937" if self.theme_mode == "light" else "#e5e7eb"
            detail_color = "#475569" if self.theme_mode == "light" else "#d1d5db"
            progress_bg = "#e5e7eb" if self.theme_mode == "light" else "#2f2f2f"
            progress_border = "#cbd5e1" if self.theme_mode == "light" else "#474747"
            disk_label = QLabel(drive_card_title(disk))
            disk_label.setStyleSheet(f"font-size: 14px; font-weight: 700; color: {title_color};")
            disk_container.addWidget(disk_label)
            filled_disk = QProgressBar()
            filled_disk.setRange(0, 100000)
            filled_disk.setValue(round(used_percentage_100k))
            filled_disk.setStyleSheet(
                f"QProgressBar {{ background-color: {progress_bg}; border: 1px solid {progress_border}; border-radius: 6px; }}"
                f"QProgressBar::chunk {{ background-color: {self.accent_color}; border-radius: 6px; }}"
            )
            filled_disk.setTextVisible(False)
            disk_container.addWidget(filled_disk)
            disk_usage_label = QLabel(disk_display)
            disk_usage_label.setStyleSheet(f"font-size: 12px; color: {detail_color};")
            disk_container.addWidget(disk_usage_label)
            disk_widget = QWidget()
            disk_widget.setObjectName("driveCard")
            disk_widget.setLayout(disk_container)
            self.disk_tab_layout.addWidget(disk_widget)
        self.disk_tab_layout.addStretch()

    def force_terminate_selected_processes(self, pids=None):
        targets = pids if pids is not None else self.get_selected_pids()
        for pid in targets:
            try:
                process = psutil.Process(pid)
                process.terminate()
                self.frozen_pids.discard(pid)
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                pass

    def freeze_selected_processes(self, pids=None):
        targets = pids if pids is not None else self.get_selected_pids()
        for pid in targets:
            try:
                process = psutil.Process(pid)
                process.suspend()
                self.frozen_pids.add(pid)
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                pass

    def unfreeze_selected_processes(self, pids=None):
        targets = pids if pids is not None else self.get_selected_pids()
        for pid in targets:
            try:
                process = psutil.Process(pid)
                process.resume()
                self.frozen_pids.discard(pid)
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                pass

    def collapse_selected_processes(self):
        return

    def expand_selected_processes(self):
        return

    def toggle_always_on_top(self):
        self.set_always_on_top_state(not self.always_on_top)

    def set_always_on_top_state(self, enabled):
        self.always_on_top = bool(enabled)
        self.setWindowFlags(
            Qt.WindowStaysOnTopHint if self.always_on_top else Qt.Window
        )
        self.show()
        self.save_settings()

    def view_system_info(self):
        dialog = SystemInfoDialog(self)
        dialog.exec_()

    def _set_overview_status(self, text):
        if hasattr(self, "overview_status_label") and self.overview_status_label is not None:
            self.overview_status_label.setText(text)

    def _settings_path(self):
        return os.path.join(os.path.expanduser("~"), "systemon_settings.json")

    def load_settings(self):
        path = self._settings_path()
        if not os.path.exists(path):
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            self.theme_mode = data.get("theme_mode", self.theme_mode)
            self.accent_color = data.get("accent_color", self.accent_color)
            self.refresh_interval_s = float(data.get("refresh_interval_s", self.refresh_interval_s))
            self.performance_mode = data.get("performance_mode", self.performance_mode)
            self.last_page_index = int(data.get("last_page_index", self.last_page_index))
            self.always_on_top = bool(data.get("always_on_top", self.always_on_top))
        except Exception:
            pass

    def save_settings(self):
        if getattr(self, "_is_initializing", False):
            return
        data = {
            "theme_mode": self.theme_mode,
            "accent_color": self.accent_color,
            "refresh_interval_s": self.refresh_interval_s,
            "performance_mode": self.performance_mode,
            "last_page_index": self.last_page_index,
            "always_on_top": self.always_on_top,
        }
        try:
            with open(self._settings_path(), "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def closeEvent(self, event):
        self.save_settings()
        super().closeEvent(event)

    def _run_operation_with_progress(self, title, func):
        worker = BackgroundOperation(func)

        def finish(msg):
            if hasattr(self, "overview_progress") and self.overview_progress is not None:
                self.overview_progress.setVisible(False)
                self.overview_progress.setRange(0, 100)
            self._set_overview_status(msg)
            worker.deleteLater()

        self._set_overview_status(title)
        if hasattr(self, "overview_progress") and self.overview_progress is not None:
            self.overview_progress.setRange(0, 0)
            self.overview_progress.setVisible(True)

        worker.finished_message.connect(finish)
        worker.start()
        return worker

    def clear_ram_cache_with_progress(self):
        self._run_operation_with_progress("Clearing RAM cache…", self._clear_ram_cache_impl)

    def _clear_ram_cache_impl(self):
        if os.name != "nt":
            return "RAM cache: not supported on this OS."
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        psapi = ctypes.WinDLL("psapi", use_last_error=True)

        kernel32.GetCurrentProcess.restype = ctypes.c_void_p
        handle = kernel32.GetCurrentProcess()
        if not handle:
            return "RAM cache: failed to get process handle."

        psapi.EmptyWorkingSet.argtypes = [ctypes.c_void_p]
        psapi.EmptyWorkingSet.restype = ctypes.c_int
        ok = psapi.EmptyWorkingSet(handle)
        if ok:
            return "RAM cache cleared (working set trimmed)."

        kernel32.SetProcessWorkingSetSizeEx.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_size_t, ctypes.c_uint]
        kernel32.SetProcessWorkingSetSizeEx.restype = ctypes.c_int
        QUOTA_LIMITS_HARDWS_MIN_DISABLE = 0x00000002
        QUOTA_LIMITS_HARDWS_MAX_DISABLE = 0x00000004
        ok2 = kernel32.SetProcessWorkingSetSizeEx(
            handle,
            ctypes.c_size_t(-1).value,
            ctypes.c_size_t(-1).value,
            QUOTA_LIMITS_HARDWS_MIN_DISABLE | QUOTA_LIMITS_HARDWS_MAX_DISABLE
        )
        if ok2:
            return "RAM cache cleared (working set resized)."

        err = ctypes.get_last_error()
        return f"RAM cache: failed (winerror={err})."

    def clean_temp_folder_with_progress(self):
        self._run_operation_with_progress("Cleaning Temp folder…", self._clean_temp_folder_impl)

    def _clean_temp_folder_impl(self):
        temp_dir = tempfile.gettempdir()
        deleted_files = 0
        deleted_dirs = 0
        try:
            for name in os.listdir(temp_dir):
                path = os.path.join(temp_dir, name)
                try:
                    if os.path.isfile(path) or os.path.islink(path):
                        os.remove(path)
                        deleted_files += 1
                    elif os.path.isdir(path):
                        shutil.rmtree(path, ignore_errors=True)
                        deleted_dirs += 1
                except Exception:
                    continue
            return f"Temp cleaned: {deleted_files} files, {deleted_dirs} folders."
        except Exception as e:
            return f"Temp clean error: {e}"

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = SystemOn()
    window.show()
    sys.exit(app.exec_())
