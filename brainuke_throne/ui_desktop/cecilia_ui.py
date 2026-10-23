#!/usr/bin/env python3
"""
brainuke_throne/ui_desktop/cecilia_ui.py
Desktop Native Cecilia-UI — Pure Python & Tkinter Interface for Project Brainuke Throne.

Features:
- Custom Cecilia Obsidian/Emerald theme (deep void #070B14, mint glow #34D399, thought #6EE7B7)
- Hardware-bound machine token auth via KeyVault (prevents unauthenticated localhost/browser access)
- Live VAD Affect Gauges (Valence, Arousal, Dominance)
- Strictly isolated internal reasoning drawers (zero thought leakage into spoken text)
- Background SSE Downlink receiver for real-time thoughts, speech, and DMN insights
- Quick action controls (Simmer DMN, Perceptual Snap, Discussion Board viewer)
"""

import sys
import os
from pathlib import Path

# Bootstrap sys.path to include Project Brainuke root
project_root = str(Path(__file__).resolve().parent.parent.parent)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

import json
import re
import ssl
import time
import queue
import threading
import subprocess
import urllib.request
import urllib.error
import tkinter as tk
from tkinter import ttk, messagebox, filedialog

# Windows High-DPI awareness
if sys.platform == "win32":
    try:
        import ctypes
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass

# --- TYPOGRAPHY: MODERN ANTIQUA RUNTIME REGISTRATION ---
FONT_FAMILY = "Modern Antiqua"
FONT_DIR = os.path.join(project_root, "brainuke_throne", "ui_desktop", "fonts")
FONT_FILE = os.path.join(FONT_DIR, "ModernAntiqua-Regular.ttf")
if sys.platform == "win32" and os.path.exists(FONT_FILE):
    try:
        import ctypes
        # 0x10 = FR_PRIVATE (process-private font resource)
        ctypes.windll.gdi32.AddFontResourceExW(FONT_FILE, 0x10, 0)
    except Exception:
        pass

from brainuke_core.security.key_vault import KeyVault

# --- COLOR PALETTE: CUSTOM CECILIA OBSIDIAN / EMERALD THEME ---
THEME = {
    "bg_void": "#070B14",
    "bg_header": "#0B1320",
    "bg_card": "#0F1A2A",
    "bg_card_subtle": "#142338",
    "bg_input": "#0B1320",
    "border_card": "#1E2F48",
    "border_glow": "#10B981",
    "accent_primary": "#10B981",
    "accent_mint": "#34D399",
    "accent_thought": "#6EE7B7",
    "accent_gold": "#FBBF24",
    "accent_blue": "#38BDF8",
    "text_main": "#F8FAFC",
    "text_muted": "#94A3B8",
    "bubble_user_bg": "#1E293B",
    "bubble_user_fg": "#F1F5F9",
    "bubble_model_bg": "#081B1F",
    "bubble_model_fg": "#ECFDF5",
    "thought_bg": "#031114",
    "thought_fg": "#6EE7B7",
    "btn_bg": "#047857",
    "btn_fg": "#FFFFFF",
    "btn_hover": "#059669",
    "btn_sec_bg": "#1E293B",
    "btn_sec_fg": "#CBD5E1",
    "accent_secret": "#A855F7",
    "accent_normal": "#10B981",
    "status_online": "#10B981",
    "status_offline": "#EF4444",
}


class CeciliaThroneDesktopApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("Cecilia Throne — Desktop Native Cognitive Stage")
        self.root.geometry("1180x800")
        self.root.minsize(980, 680)
        self.root.configure(bg=THEME["bg_void"])

        # Hardware-bound auth token
        self.token = KeyVault.generate_token()
        self.base_url = "https://127.0.0.1:8443"

        # SSL context trusting local rootCA.pem
        ca_path = os.path.join(project_root, "rootCA.pem")
        if os.path.exists(ca_path):
            self.ssl_context = ssl.create_default_context(cafile=ca_path)
        else:
            self.ssl_context = ssl.create_default_context()
            self.ssl_context.check_hostname = False
            self.ssl_context.verify_mode = ssl.CERT_NONE

        # State
        self.sse_active = True
        self.show_thoughts = True
        self.event_queue = queue.Queue()
        self.active_affect = {"v": 0.20, "a": 0.00, "d": 0.80}
        self.model_status_data = {
            "online": False,
            "active_model": "gemma-4-26B-A4B-it-qat-UD-Q4_K_XL",
            "active_alias": "normal",
            "inference_settings": {"temperature": 0.8, "min_p": 0.05, "context_window": 32768, "gpu_layers": 8}
        }

        # Real-time token streaming state
        self.is_streaming = False
        self.streaming_thought_lbl = None
        self.streaming_thought_text = ""
        self.streaming_speech_started = False
        self._last_dispatched_prompt = ""

        # Unfinished prompt queue backlog & Telemetry (Option C)
        self.pending_prompt_backlog: List[str] = []
        self.last_runner_was_online = False
        self.last_hardware_telemetry: Dict[str, Any] = {}
        self.last_stream_telemetry: Dict[str, Any] = {}
        self.last_context_metrics: Dict[str, Any] = {}

        self.server_proc: Optional[subprocess.Popen] = None
        self._build_ui()
        self._ensure_throne_server_running()
        self._start_sse_listener()
        self._poll_event_queue()
        self._refresh_status_loop()

    def _ensure_throne_server_running(self):
        """Checks if Throne Server (port 8443) is reachable; if not, auto-launches it in background."""
        def check_server():
            req = urllib.request.Request(f"{self.base_url}/")
            try:
                with urllib.request.urlopen(req, context=self.ssl_context, timeout=1.5):
                    return True
            except urllib.error.HTTPError:
                return True
            except Exception:
                return False

        def launcher_worker():
            if check_server():
                return

            self.event_queue.put(("notice", "Throne Server offline (Port 8443). Auto-launching Throne in background..."))
            server_main = os.path.join(project_root, "brainuke_throne", "server", "main.py")
            py_bin = self._find_python_interpreter()
            try:
                flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
                self.server_proc = subprocess.Popen(
                    [py_bin, server_main],
                    creationflags=flags,
                    cwd=project_root
                )
                for _ in range(12):
                    time.sleep(1.0)
                    if check_server():
                        self.event_queue.put(("notice", "Throne Server online & linked (Port 8443)."))
                        self._fetch_model_status_async()
                        return
            except Exception as e:
                self.event_queue.put(("error", f"Failed to auto-launch Throne Server: {e}"))

        threading.Thread(target=launcher_worker, daemon=True).start()

    @staticmethod
    def _find_python_interpreter() -> str:
        """Finds a real Python interpreter when running standalone or dropped into onedir."""
        if sys.executable and os.path.basename(sys.executable).lower() in ("python.exe", "pythonw.exe", "python3.exe", "python"):
            return sys.executable
        candidates = [
            os.path.join(project_root, ".venv", "Scripts", "python.exe"),
            os.path.join(project_root, "..", ".venv", "Scripts", "python.exe"),
            os.path.join(project_root, "..", "..", ".venv", "Scripts", "python.exe"),
            os.path.join(project_root, "..", "..", "..", ".venv", "Scripts", "python.exe"),
            os.path.join(project_root, "..", "..", "..", "SerenityDev", ".venv", "Scripts", "python.exe"),
        ]
        for c in candidates:
            if os.path.isfile(c):
                return os.path.abspath(c)
        import shutil
        return shutil.which("python") or shutil.which("python3") or sys.executable

    # --- UI INITIALIZATION ---
    def _build_ui(self):
        # 1. Header Bar
        header = tk.Frame(self.root, bg=THEME["bg_header"], height=58, highlightthickness=1, highlightbackground=THEME["border_card"])
        header.pack(side=tk.TOP, fill=tk.X)
        header.pack_propagate(False)

        # Brand Orb & Title
        brand_frame = tk.Frame(header, bg=THEME["bg_header"])
        brand_frame.pack(side=tk.LEFT, padx=18, pady=8)

        self.orb_canvas = tk.Canvas(brand_frame, width=18, height=18, bg=THEME["bg_header"], highlightthickness=0)
        self.orb_canvas.pack(side=tk.LEFT, padx=(0, 10))
        self.orb_canvas.create_oval(2, 2, 16, 16, fill=THEME["accent_mint"], outline=THEME["accent_primary"], width=2)

        title_box = tk.Frame(brand_frame, bg=THEME["bg_header"])
        title_box.pack(side=tk.LEFT)
        lbl_title = tk.Label(title_box, text="CECILIA THRONE", font=("Segoe UI", 12, "bold"), fg=THEME["accent_mint"], bg=THEME["bg_header"])
        lbl_title.pack(anchor="w")
        lbl_sub = tk.Label(title_box, text="DESKTOP NATIVE COGNITIVE STAGE", font=("Segoe UI", 7, "bold"), fg=THEME["text_muted"], bg=THEME["bg_header"])
        lbl_sub.pack(anchor="w")

        # Telemetry Badges
        telemetry_frame = tk.Frame(header, bg=THEME["bg_header"])
        telemetry_frame.pack(side=tk.RIGHT, padx=18, pady=10)

        # 1. Quick Model Switcher (Normal vs Secret)
        self.btn_model_mode = tk.Button(
            telemetry_frame,
            text="🟢 Normal (26B)",
            command=self._on_toggle_model,
            font=("Segoe UI", 8, "bold"),
            fg="#6EE7B7",
            bg="#064E3B",
            activebackground="#047857",
            padx=8,
            pady=3,
            relief=tk.FLAT,
            cursor="hand2"
        )
        self.btn_model_mode.pack(side=tk.LEFT, padx=4)

        # 2. Model Load Status Badge & Quick Load Initiator
        self.lbl_runner_status = tk.Label(
            telemetry_frame,
            text="Model: Offline",
            font=("Segoe UI", 8),
            fg=THEME["status_offline"],
            bg=THEME["bg_card"],
            padx=8,
            pady=4,
            relief=tk.FLAT
        )
        self.lbl_runner_status.pack(side=tk.LEFT, padx=4)

        self.btn_load_runner = tk.Button(
            telemetry_frame,
            text="▶ Load",
            command=self._on_load_model,
            font=("Segoe UI", 8, "bold"),
            fg=THEME["text_main"],
            bg=THEME["btn_sec_bg"],
            activebackground=THEME["btn_hover"],
            padx=6,
            pady=3,
            relief=tk.FLAT,
            cursor="hand2"
        )
        self.btn_load_runner.pack(side=tk.LEFT, padx=4)

        # 3. Synchronize Button & Last Sync Indicator
        self.btn_sync = tk.Button(
            telemetry_frame,
            text="🔄 Sync",
            command=self._on_trigger_sync,
            font=("Segoe UI", 8, "bold"),
            fg="#ECFDF5",
            bg="#065F46",
            activebackground="#047857",
            padx=8,
            pady=3,
            relief=tk.FLAT,
            cursor="hand2"
        )
        self.btn_sync.pack(side=tk.LEFT, padx=4)

        self.lbl_last_sync = tk.Label(
            telemetry_frame,
            text="Last Sync: Never",
            font=("Segoe UI", 8),
            fg=THEME["text_muted"],
            bg=THEME["bg_card"],
            padx=8,
            pady=4,
            relief=tk.FLAT
        )
        self.lbl_last_sync.pack(side=tk.LEFT, padx=4)

        self.lbl_downlink = tk.Label(telemetry_frame, text="Downlink: Connecting...", font=("Segoe UI", 9), fg=THEME["accent_gold"], bg=THEME["bg_card"], padx=10, pady=4, relief=tk.FLAT)
        self.lbl_downlink.pack(side=tk.LEFT, padx=4)

        lbl_focus = tk.Label(telemetry_frame, text="Focus: PC Throne", font=("Segoe UI", 9), fg=THEME["text_main"], bg=THEME["bg_card"], padx=10, pady=4, relief=tk.FLAT)
        lbl_focus.pack(side=tk.LEFT, padx=4)

        # 2. Main Body (Split into Chat Stage and Telemetry Sidebar)
        body = tk.Frame(self.root, bg=THEME["bg_void"])
        body.pack(side=tk.TOP, fill=tk.BOTH, expand=True, padx=12, pady=10)

        # Right Sidebar (HUD & Telemetry)
        sidebar = tk.Frame(body, bg=THEME["bg_void"], width=320)
        sidebar.pack(side=tk.RIGHT, fill=tk.Y, padx=(10, 0))
        sidebar.pack_propagate(False)
        self._build_sidebar(sidebar)

        # Left / Center (Stage Container with Tabs)
        stage_container = tk.Frame(body, bg=THEME["bg_void"])
        stage_container.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self._build_stage_deck(stage_container)

    def _build_stage_deck(self, parent: tk.Frame):
        """Constructs dual-stage deck hosting Live Cognitive Stage and Memory & DMN History."""
        # Top Stage Tab Bar
        tab_bar = tk.Frame(parent, bg=THEME["bg_void"])
        tab_bar.pack(side=tk.TOP, fill=tk.X, pady=(0, 8))

        self.btn_tab_stage = tk.Button(
            tab_bar,
            text="💬 Live Cognitive Stage",
            command=lambda: self._switch_tab("stage"),
            font=(FONT_FAMILY, 9, "bold"),
            fg=THEME["accent_mint"],
            bg="#064E3B",
            activebackground="#047857",
            activeforeground="#FFFFFF",
            padx=14,
            pady=4,
            relief=tk.FLAT,
            cursor="hand2"
        )
        self.btn_tab_stage.pack(side=tk.LEFT, padx=(0, 6))

        self.btn_tab_history = tk.Button(
            tab_bar,
            text="📜 Memory & DMN History",
            command=lambda: self._switch_tab("history"),
            font=(FONT_FAMILY, 9, "bold"),
            fg=THEME["text_muted"],
            bg=THEME["bg_card"],
            activebackground=THEME["btn_sec_bg"],
            activeforeground=THEME["text_main"],
            padx=14,
            pady=4,
            relief=tk.FLAT,
            cursor="hand2"
        )
        self.btn_tab_history.pack(side=tk.LEFT, padx=(0, 6))

        # Hierarchical Priority Badge in Tab Bar
        lbl_weight_badge = tk.Label(
            tab_bar,
            text="👑 PC Core (Weight 1.0) ≫ 📱 Android (Weight 0.35)",
            font=("Segoe UI", 8, "bold"),
            fg=THEME["accent_mint"],
            bg=THEME["bg_card"],
            padx=10,
            pady=4,
            relief=tk.FLAT
        )
        lbl_weight_badge.pack(side=tk.RIGHT)

        # Container Frame for the two views
        self.stage_deck = tk.Frame(parent, bg=THEME["bg_void"])
        self.stage_deck.pack(side=tk.TOP, fill=tk.BOTH, expand=True)

        self.frame_stage = tk.Frame(self.stage_deck, bg=THEME["bg_void"])
        self.frame_history = tk.Frame(self.stage_deck, bg=THEME["bg_void"])

        # Build Stage Tab (Live Chat)
        self._build_chat_stage(self.frame_stage)

        # Build History Tab (Memory Vault & DMN)
        self._build_history_stage(self.frame_history)

        # Default active tab
        self.active_tab = "stage"
        self.frame_stage.pack(fill=tk.BOTH, expand=True)

    def _switch_tab(self, tab_name: str):
        if tab_name == "stage":
            self.frame_history.pack_forget()
            self.frame_stage.pack(fill=tk.BOTH, expand=True)
            self.btn_tab_stage.config(bg="#064E3B", fg=THEME["accent_mint"])
            self.btn_tab_history.config(bg=THEME["bg_card"], fg=THEME["text_muted"])
            self.active_tab = "stage"
        else:
            self.frame_stage.pack_forget()
            self.frame_history.pack(fill=tk.BOTH, expand=True)
            self.btn_tab_history.config(bg="#064E3B", fg=THEME["accent_mint"])
            self.btn_tab_stage.config(bg=THEME["bg_card"], fg=THEME["text_muted"])
            self.active_tab = "history"
            self._fetch_history_async()

    def _build_history_stage(self, parent: tk.Frame):
        # 1. Header & Filter Control Card
        card_ctrl = tk.Frame(parent, bg=THEME["bg_card"], highlightthickness=1, highlightbackground=THEME["border_card"])
        card_ctrl.pack(side=tk.TOP, fill=tk.X, pady=(0, 8))

        row_top = tk.Frame(card_ctrl, bg=THEME["bg_card"])
        row_top.pack(fill=tk.X, padx=12, pady=(8, 4))

        lbl_title = tk.Label(
            row_top,
            text="CHRONOLOGICAL MEMORY VAULT & DMN REFINEMENTS",
            font=("Segoe UI", 9, "bold"),
            fg=THEME["accent_mint"],
            bg=THEME["bg_card"]
        )
        lbl_title.pack(side=tk.LEFT)

        btn_refresh = tk.Button(
            row_top,
            text="🔄 Refresh",
            command=lambda: self._fetch_history_async(),
            font=("Segoe UI", 8, "bold"),
            fg=THEME["text_main"],
            bg=THEME["btn_sec_bg"],
            activebackground=THEME["btn_hover"],
            padx=10,
            pady=2,
            relief=tk.FLAT,
            cursor="hand2"
        )
        btn_refresh.pack(side=tk.RIGHT)

        self.lbl_hist_count = tk.Label(
            row_top,
            text="Ready",
            font=("Segoe UI", 8),
            fg=THEME["text_muted"],
            bg=THEME["bg_card"]
        )
        self.lbl_hist_count.pack(side=tk.RIGHT, padx=10)

        # Filters Row
        row_filters = tk.Frame(card_ctrl, bg=THEME["bg_card"])
        row_filters.pack(fill=tk.X, padx=12, pady=(0, 8))

        self.current_hist_filter = "all"
        self.hist_filter_buttons = {}

        filters = [
            ("all", "All Records"),
            ("pc", "👑 PC Master (1.0)"),
            ("android", "📱 Android (0.35)"),
            ("dmn", "⚡ DMN Refined")
        ]

        for key, label in filters:
            btn = tk.Button(
                row_filters,
                text=label,
                command=lambda k=key: self._on_hist_filter_click(k),
                font=("Segoe UI", 8, "bold" if key == "all" else "normal"),
                fg=THEME["accent_mint"] if key == "all" else THEME["text_muted"],
                bg="#064E3B" if key == "all" else THEME["btn_sec_bg"],
                activebackground=THEME["btn_hover"],
                padx=8,
                pady=2,
                relief=tk.FLAT,
                cursor="hand2"
            )
            btn.pack(side=tk.LEFT, padx=(0, 6))
            self.hist_filter_buttons[key] = btn

        # 2. History Feed Display (Scrollable Text)
        feed_container = tk.Frame(parent, bg=THEME["bg_card"], highlightthickness=1, highlightbackground=THEME["border_card"])
        feed_container.pack(side=tk.TOP, fill=tk.BOTH, expand=True)

        self.hist_text = tk.Text(
            feed_container,
            bg=THEME["bg_card"],
            fg=THEME["text_main"],
            font=("Segoe UI", 10),
            wrap=tk.WORD,
            padx=14,
            pady=14,
            relief=tk.FLAT,
            state=tk.DISABLED
        )
        scrollbar = tk.Scrollbar(feed_container, command=self.hist_text.yview, bg=THEME["bg_card"])
        self.hist_text.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.hist_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self._bind_targeted_mousewheel(self.hist_text, self.hist_text)
        self._attach_text_context_menu(self.hist_text, read_only=True)

        # Tag configurations
        self.hist_text.tag_config("pc_badge", font=("Segoe UI", 9, "bold"), foreground=THEME["accent_mint"])
        self.hist_text.tag_config("android_badge", font=("Segoe UI", 9, "bold"), foreground=THEME["accent_blue"])
        self.hist_text.tag_config("dmn_badge", font=("Segoe UI", 9, "bold"), foreground=THEME["accent_gold"])
        self.hist_text.tag_config("hist_timestamp", font=("Segoe UI", 8, "italic"), foreground=THEME["text_muted"])
        self.hist_text.tag_config("hist_user_hdr", font=("Segoe UI", 9, "bold"), foreground=THEME["accent_blue"])
        self.hist_text.tag_config("hist_user_body", font=("Segoe UI", 10), foreground=THEME["text_main"], lmargin1=16, lmargin2=16)
        self.hist_text.tag_config("hist_thought_hdr", font=("Consolas", 8, "bold"), foreground=THEME["accent_thought"], lmargin1=16, lmargin2=16)
        self.hist_text.tag_config("hist_thought_body", font=("Consolas", 9, "italic"), foreground=THEME["accent_thought"], background=THEME["thought_bg"], lmargin1=24, lmargin2=24, rmargin=24)
        self.hist_text.tag_config("hist_speech_hdr", font=("Segoe UI", 9, "bold"), foreground=THEME["accent_mint"], lmargin1=16, lmargin2=16)
        self.hist_text.tag_config("hist_speech_body", font=("Segoe UI", 10), foreground=THEME["bubble_model_fg"], lmargin1=16, lmargin2=16)
        self.hist_text.tag_config("hist_dmn_body", font=("Segoe UI", 10), foreground="#FEF3C7", background="#171C14", lmargin1=20, lmargin2=20, rmargin=20)
        self.hist_text.tag_config("hist_dmn_meta", font=("Consolas", 8), foreground="#FBBF24", lmargin1=20, lmargin2=20)
        self.hist_text.tag_config("hist_divider", font=("Segoe UI", 6), foreground=THEME["border_card"])
        self.hist_text.tag_config("hist_empty", font=("Segoe UI", 10, "italic"), foreground=THEME["text_muted"], justify=tk.CENTER)

    def _on_hist_filter_click(self, filter_key: str):
        self.current_hist_filter = filter_key
        for k, btn in self.hist_filter_buttons.items():
            if k == filter_key:
                btn.config(fg=THEME["accent_mint"], bg="#064E3B", font=("Segoe UI", 8, "bold"))
            else:
                btn.config(fg=THEME["text_muted"], bg=THEME["btn_sec_bg"], font=("Segoe UI", 8))
        self._fetch_history_async(filter_key)

    def _fetch_history_async(self, filter_key: Optional[str] = None):
        flt = filter_key or getattr(self, "current_hist_filter", "all")

        def task():
            url = f"{self.base_url}/api/v1/history?filter={flt}&limit=60"
            req = urllib.request.Request(
                url,
                headers={"Authorization": f"Bearer {self.token}"}
            )
            try:
                with urllib.request.urlopen(req, context=self.ssl_context, timeout=10) as resp:
                    data = json.loads(resp.read().decode())
                    self.event_queue.put(("history_data", data))
            except Exception as e:
                # Direct fallback to local MemoryVault if Throne server is offline or busy
                try:
                    from brainuke_core.memory.vault import MemoryVault
                    v = MemoryVault()
                    if flt == "pc":
                        ints = v.get_recent_interactions(limit=60, source_device="pc")
                        dmns = []
                    elif flt == "android":
                        ints = v.get_recent_interactions(limit=60, source_device="android")
                        dmns = []
                    elif flt == "dmn":
                        ints = []
                        dmns = v.get_distilled_insights(limit=60)
                    else:
                        ints = v.get_recent_interactions(limit=60)
                        dmns = v.get_distilled_insights(limit=60)
                    fallback_data = {
                        "status": "ok",
                        "filter": flt,
                        "interactions": ints,
                        "dmn_insights": dmns,
                        "total_interactions": len(ints),
                        "total_dmn": len(dmns)
                    }
                    self.event_queue.put(("history_data", fallback_data))
                except Exception:
                    self.event_queue.put(("error", f"History fetch failed: {e}"))

        threading.Thread(target=task, daemon=True).start()

    def _render_history_feed(self, data: dict):
        interactions = data.get("interactions", [])
        dmn_insights = data.get("dmn_insights", [])

        timeline = []
        for item in interactions:
            timeline.append(("interaction", item.get("timestamp", 0), item))
        for item in dmn_insights:
            timeline.append(("dmn", item.get("timestamp", 0), item))

        timeline.sort(key=lambda x: x[1], reverse=True)

        if hasattr(self, "lbl_hist_count"):
            count_str = f"Showing {len(timeline)} items ({len(interactions)} dialogues, {len(dmn_insights)} DMN insights)"
            self.lbl_hist_count.config(text=count_str)

        self.hist_text.config(state=tk.NORMAL)
        self.hist_text.delete("1.0", tk.END)

        if not timeline:
            self.hist_text.insert(
                tk.END,
                "\n\n\n── No historical records matching filter in Memory Vault ──\n"
                "Engage Cecilia in conversation or trigger '⚡ Simmer DMN' to generate distilled insights.\n",
                "hist_empty"
            )
            self.hist_text.config(state=tk.DISABLED)
            return

        for kind, ts, item in timeline:
            t_struct = time.localtime(ts / 1000.0) if ts else time.localtime()
            time_str = time.strftime("%Y-%m-%d %H:%M:%S", t_struct)

            if kind == "interaction":
                src = item.get("source_device", "pc")
                weight = float(item.get("influence_weight", 1.0 if src == "pc" else 0.35))
                user_text = item.get("user_input", "").strip()
                thought = (item.get("thought_stream") or "").strip()
                speech = (item.get("final_response") or "").strip()
                raw_resp = (item.get("raw_response") or "").strip()

                from brainuke_core.cognition.thought_isolation import ThoughtIsolation
                clean_thought, clean_raw, clean_speech = ThoughtIsolation().isolate_stages(thought, speech, raw_resp)

                w_disp = f"{weight:.2f}" if weight not in (1.0, 0.0) else f"{weight:.1f}"
                if src == "pc":
                    self.hist_text.insert(
                        tk.END,
                        f"👑 [PC CORE MASTER • WEIGHT {w_disp} (CANON)]  ",
                        "pc_badge"
                    )
                else:
                    self.hist_text.insert(
                        tk.END,
                        f"📱 [ANDROID COMPANION • WEIGHT {w_disp}]  ",
                        "android_badge"
                    )
                self.hist_text.insert(tk.END, f"{time_str}\n", "hist_timestamp")

                if user_text:
                    self.hist_text.insert(tk.END, "👤 Human User:\n", "hist_user_hdr")
                    self.hist_text.insert(tk.END, f"{user_text}\n\n", "hist_user_body")

                author_label = "⚡ Cecilia (PC Core Master):" if src == "pc" else "📱 Cecilia (Mobile Companion):"
                self.hist_text.insert(tk.END, f"{author_label}\n", "hist_speech_hdr")

                stage_comp = self._build_stage_drawer_component(
                    parent_widget=self.hist_text,
                    thought=clean_thought,
                    raw_response=clean_raw,
                    speech=clean_speech,
                    is_streaming=False
                )
                self.hist_text.window_create(tk.END, window=stage_comp)
                self.hist_text.insert(tk.END, "\n\n")

            elif kind == "dmn":
                concept = item.get("concept_family", "general")
                imp = float(item.get("importance_weight", 1.0))
                dom = float(item.get("dominance_weight", 0.5))
                insight_text = item.get("insight", "").strip()
                w_delta = item.get("world_delta", {})
                e_shift = item.get("emotional_shift", {})

                self.hist_text.insert(
                    tk.END,
                    f"⚡ [DMN REFINED INSIGHT • #{concept.upper()} • IMPORTANCE {imp:.2f} • DOMINANCE {dom:.2f}]  ",
                    "dmn_badge"
                )
                self.hist_text.insert(tk.END, f"{time_str}\n", "hist_timestamp")

                if insight_text:
                    self.hist_text.insert(tk.END, f"{insight_text}\n", "hist_dmn_body")

                delta_parts = []
                if isinstance(w_delta, dict) and w_delta.get("consolidated_nodes") is not None:
                    delta_parts.append(f"Nodes: {w_delta['consolidated_nodes']}")
                if isinstance(e_shift, dict) and e_shift.get("valence_delta") is not None:
                    delta_parts.append(f"Valence Δ: {e_shift['valence_delta']:+.2f}")
                summary_meta = " | ".join(delta_parts) if delta_parts else "Mind synthesized & anchored"
                self.hist_text.insert(tk.END, f"• [{summary_meta}]\n\n", "hist_dmn_meta")

            self.hist_text.insert(tk.END, "─────────────────────────────────────────────────────────────────────────────\n\n", "hist_divider")

        self.hist_text.config(state=tk.DISABLED)

    def _build_chat_stage(self, parent: tk.Frame):
        # Chat display area (Scrollable Text)
        chat_container = tk.Frame(parent, bg=THEME["bg_card"], highlightthickness=1, highlightbackground=THEME["border_card"])
        chat_container.pack(side=tk.TOP, fill=tk.BOTH, expand=True)

        self.chat_text = tk.Text(
            chat_container,
            bg=THEME["bg_card"],
            fg=THEME["text_main"],
            font=("Segoe UI", 10),
            wrap=tk.WORD,
            padx=14,
            pady=14,
            relief=tk.FLAT,
            state=tk.DISABLED
        )
        scrollbar = tk.Scrollbar(chat_container, command=self.chat_text.yview, bg=THEME["bg_card"])
        self.chat_text.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.chat_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self._bind_targeted_mousewheel(self.chat_text, self.chat_text)
        self._attach_text_context_menu(self.chat_text, read_only=True)

        # Define text tags for formatting
        self.chat_text.tag_config("user_header", font=("Segoe UI", 9, "bold"), foreground=THEME["accent_blue"])
        self.chat_text.tag_config("user_body", font=("Segoe UI", 10), foreground=THEME["text_main"], lmargin1=16, lmargin2=16)
        self.chat_text.tag_config("model_header", font=("Segoe UI", 9, "bold"), foreground=THEME["accent_mint"])
        self.chat_text.tag_config("model_thought", font=("Consolas", 9, "italic"), foreground=THEME["accent_thought"], background=THEME["thought_bg"], lmargin1=24, lmargin2=24, rmargin=24)
        self.chat_text.tag_config("model_speech", font=("Segoe UI", 10), foreground=THEME["bubble_model_fg"], lmargin1=16, lmargin2=16)
        self.chat_text.tag_config("system_notice", font=("Segoe UI", 8, "italic"), foreground=THEME["text_muted"], justify=tk.CENTER)
        self.chat_text.tag_config("spacer", font=("Segoe UI", 4))

        # Welcome message
        self._append_message(
            author="⚡ Cecilia • Core Persona",
            thought="Initializing desktop native cognitive nexus. Hardware token verified. Zero browser leakage.",
            speech="I am listening. Both desktop cognition and mobile senses are active. What are we exploring?",
            is_model=True
        )

        # Control & Composer Bar
        composer_container = tk.Frame(parent, bg=THEME["bg_void"])
        composer_container.pack(side=tk.BOTTOM, fill=tk.X, pady=(10, 0))

        # Action Buttons Row (Refined for efficacy; Snap & Reset housed in Config dialog)
        actions_row = tk.Frame(composer_container, bg=THEME["bg_void"])
        actions_row.pack(side=tk.TOP, fill=tk.X, pady=(0, 8))

        self.btn_simmer = tk.Button(actions_row, text="⚡ Simmer DMN", command=self._on_simmer, bg=THEME["btn_sec_bg"], fg=THEME["btn_sec_fg"], font=("Segoe UI", 8, "bold"), padx=12, pady=4, relief=tk.FLAT, activebackground=THEME["btn_hover"])
        self.btn_simmer.pack(side=tk.LEFT, padx=(0, 8))

        btn_config = tk.Button(actions_row, text="⚙ Model & Config", command=self._open_model_config_dialog, bg=THEME["btn_sec_bg"], fg=THEME["btn_sec_fg"], font=(FONT_FAMILY, 8, "bold"), padx=12, pady=4, relief=tk.FLAT, activebackground=THEME["btn_hover"])
        btn_config.pack(side=tk.LEFT, padx=(0, 8))

        btn_self_heal = tk.Button(actions_row, text="🩺 Self-Heal / Debug", command=self._open_self_heal_dialog, bg=THEME["btn_sec_bg"], fg=THEME["accent_mint"], font=(FONT_FAMILY, 8, "bold"), padx=12, pady=4, relief=tk.FLAT, activebackground=THEME["btn_hover"])
        btn_self_heal.pack(side=tk.LEFT, padx=(0, 8))

        self.btn_flush_queue = tk.Button(
            actions_row,
            text="📥 Send Queue (0)",
            command=self._on_manual_flush_queue,
            bg=THEME["btn_sec_bg"],
            fg=THEME["text_muted"],
            font=(FONT_FAMILY, 8, "bold"),
            padx=12,
            pady=4,
            relief=tk.FLAT,
            activebackground=THEME["btn_hover"]
        )
        self.btn_flush_queue.pack(side=tk.LEFT, padx=(0, 8))

        btn_clear = tk.Button(actions_row, text="🧹 Clear View", command=self._on_clear_chat, bg=THEME["btn_sec_bg"], fg=THEME["text_muted"], font=("Segoe UI", 8), padx=12, pady=4, relief=tk.FLAT)
        btn_clear.pack(side=tk.RIGHT)

        # Input Row
        input_row = tk.Frame(composer_container, bg=THEME["bg_card"], highlightthickness=1, highlightbackground=THEME["border_card"])
        input_row.pack(side=tk.TOP, fill=tk.X)

        self.entry_input = tk.Text(
            input_row,
            bg=THEME["bg_input"],
            fg=THEME["text_main"],
            insertbackground=THEME["accent_mint"],
            font=("Segoe UI", 10),
            relief=tk.FLAT,
            height=1,
            wrap=tk.WORD,
            undo=True,
            padx=10,
            pady=8
        )
        self.entry_input.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=8, pady=6)

        def _handle_return(e):
            if not (e.state & 0x0001 or e.state & 0x0004):  # Neither Shift nor Ctrl
                self._on_send()
                return "break"
            self.root.after_idle(self._adjust_input_height)
            return None

        self.entry_input.bind("<Return>", _handle_return)
        self.entry_input.bind("<Shift-Return>", lambda e: self.root.after_idle(self._adjust_input_height))
        self.entry_input.bind("<Control-Return>", lambda e: self.root.after_idle(self._adjust_input_height))
        self.entry_input.bind("<KeyRelease>", lambda e: self._adjust_input_height())

        # Targeted mousewheel scrolling on input box
        self._bind_targeted_mousewheel(self.entry_input, self.entry_input)
        self._attach_text_context_menu(self.entry_input, read_only=False)

        self.btn_send = tk.Button(input_row, text="Send", command=self._on_send, bg=THEME["btn_bg"], fg=THEME["btn_fg"], font=("Segoe UI", 9, "bold"), padx=16, pady=6, relief=tk.FLAT, activebackground=THEME["btn_hover"])
        self.btn_send.pack(side=tk.RIGHT, padx=8, pady=6)

    def _build_sidebar(self, parent: tk.Frame):
        # 1. System Status & Diagnostics Card (Replaces Cognitive Nexus & hides raw Affect Vectors)
        card_diag = tk.Frame(parent, bg=THEME["bg_card"], highlightthickness=1, highlightbackground=THEME["border_card"])
        card_diag.pack(side=tk.TOP, fill=tk.X, pady=(0, 10))

        lbl_diag = tk.Label(card_diag, text="SYSTEM STATUS & DIAGNOSTICS", font=("Segoe UI", 9, "bold"), fg=THEME["accent_mint"], bg=THEME["bg_card"])
        lbl_diag.pack(anchor="w", padx=12, pady=(10, 6))

        # PC Cognitive Core Status
        self.lbl_model_id = tk.Label(card_diag, text="• Model: Normal (Supervisor 26B)", font=("Segoe UI", 8), fg=THEME["accent_mint"], bg=THEME["bg_card"])
        self.lbl_model_id.pack(anchor="w", padx=14, pady=1)

        self.lbl_runner = tk.Label(card_diag, text="• Status: Llama-Server Offline (8081)", font=("Segoe UI", 8), fg=THEME["status_offline"], bg=THEME["bg_card"])
        self.lbl_runner.pack(anchor="w", padx=14, pady=1)

        self.lbl_sampling_info = tk.Label(card_diag, text="• Sampling: Temp=0.80, MinP=0.05, Ctx=32K", font=("Segoe UI", 8), fg=THEME["text_muted"], bg=THEME["bg_card"])
        self.lbl_sampling_info.pack(anchor="w", padx=14, pady=1)

        # Real-time Hardware Telemetry (Option C: Dedicated VRAM, Shared VRAM, RAM)
        self.lbl_telemetry_mem = tk.Label(card_diag, text="• Memory: VRAM -- | Shared -- | RAM --", font=("Segoe UI", 8), fg=THEME["text_muted"], bg=THEME["bg_card"])
        self.lbl_telemetry_mem.pack(anchor="w", padx=14, pady=1)

        # Performance: TTFT and streaming tokens/sec
        self.lbl_telemetry_speed = tk.Label(card_diag, text="• Speed: TTFT: -- | -- t/s", font=("Segoe UI", 8), fg=THEME["text_muted"], bg=THEME["bg_card"])
        self.lbl_telemetry_speed.pack(anchor="w", padx=14, pady=1)

        # Context window utilization
        self.lbl_telemetry_ctx = tk.Label(card_diag, text="• Context Window: 0 / 32K (0.0%)", font=("Segoe UI", 8), fg=THEME["text_muted"], bg=THEME["bg_card"])
        self.lbl_telemetry_ctx.pack(anchor="w", padx=14, pady=1)

        # Prompt queue status
        self.lbl_diag_backlog = tk.Label(card_diag, text="• Prompt Queue: Idle (0 pending)", font=("Segoe UI", 8), fg=THEME["accent_mint"], bg=THEME["bg_card"])
        self.lbl_diag_backlog.pack(anchor="w", padx=14, pady=1)

        self.lbl_diag_weight = tk.Label(card_diag, text="• Priority: PC Core Master (Weight 1.0 > Droid 0.35)", font=("Segoe UI", 8), fg=THEME["accent_blue"], bg=THEME["bg_card"])
        self.lbl_diag_weight.pack(anchor="w", padx=14, pady=1)

        # Android Companion Connection
        self.lbl_diag_downlink = tk.Label(card_diag, text="• Downlink SSE: Linked (Port 8443)", font=("Segoe UI", 8), fg=THEME["accent_mint"], bg=THEME["bg_card"])
        self.lbl_diag_downlink.pack(anchor="w", padx=14, pady=1)

        self.lbl_diag_tether = tk.Label(card_diag, text="• Tethering: Reverse Ports 8443, 8080, 8081", font=("Segoe UI", 8), fg=THEME["text_muted"], bg=THEME["bg_card"])
        self.lbl_diag_tether.pack(anchor="w", padx=14, pady=1)

        # Sync & DMN State
        self.lbl_diag_sync = tk.Label(card_diag, text="• Last Sync: Never", font=("Segoe UI", 8), fg=THEME["accent_gold"], bg=THEME["bg_card"])
        self.lbl_diag_sync.pack(anchor="w", padx=14, pady=1)

        self.lbl_simmer = tk.Label(card_diag, text="• DMN Simmer: Idle", font=("Segoe UI", 8), fg=THEME["text_muted"], bg=THEME["bg_card"])
        self.lbl_simmer.pack(anchor="w", padx=14, pady=1)

        self.lbl_grounding = tk.Label(card_diag, text="• Grounding Anchors: 20 nodes", font=("Segoe UI", 8), fg=THEME["text_muted"], bg=THEME["bg_card"])
        self.lbl_grounding.pack(anchor="w", padx=14, pady=1)

        self.lbl_auth_status = tk.Label(card_diag, text="• Auth: Hardware Machine Token Active", font=("Segoe UI", 8), fg=THEME["accent_mint"], bg=THEME["bg_card"])
        self.lbl_auth_status.pack(anchor="w", padx=14, pady=(1, 10))

        # 2. Messageboard / Threads Card
        card_board = tk.Frame(parent, bg=THEME["bg_card"], highlightthickness=1, highlightbackground=THEME["border_card"])
        card_board.pack(side=tk.TOP, fill=tk.BOTH, expand=True)

        board_hdr = tk.Frame(card_board, bg=THEME["bg_card"])
        board_hdr.pack(fill=tk.X, padx=12, pady=(10, 6))

        lbl_board = tk.Label(board_hdr, text="MESSAGEBOARD", font=("Segoe UI", 9, "bold"), fg=THEME["accent_mint"], bg=THEME["bg_card"])
        lbl_board.pack(side=tk.LEFT)

        btn_refresh_board = tk.Button(board_hdr, text="Refresh", command=self._fetch_threads, bg=THEME["btn_sec_bg"], fg=THEME["text_muted"], font=("Segoe UI", 7), padx=6, pady=1, relief=tk.FLAT)
        btn_refresh_board.pack(side=tk.RIGHT)

        self.board_listbox = tk.Listbox(card_board, bg=THEME["bg_card_subtle"], fg=THEME["text_main"], selectbackground=THEME["btn_bg"], font=("Segoe UI", 8), relief=tk.FLAT, borderwidth=0)
        self.board_listbox.pack(fill=tk.BOTH, expand=True, padx=10, pady=(0, 10))


    # --- CHAT & REASONING RENDERING ---
    def _build_stage_drawer_component(
        self,
        parent_widget,
        thought: str = "",
        raw_response: str = "",
        speech: str = "",
        is_streaming: bool = False
    ) -> tk.Frame:
        """
        Constructs unified 3-stage drawer component with side-by-side buttons:
        [ Stage 1: Thoughts ] [ Stage 2: Raw Response ] [ Stage 3: Refined Response ]
        Flow:
        - Dropdown buttons left-to-right: thoughts, raw response, refined response.
        - Text / drawer content top-to-bottom: thoughts, raw response, refined response.
        - Dual-line titles for space and scaling clarity.
        - Targeted mousewheel scrolling bound strictly to parent_widget.
        """
        container = tk.Frame(parent_widget, bg=THEME["bg_card"], padx=2, pady=2)

        # Button Row: Side-by-side buttons [ 1 - 2 - 3 ] (left to right)
        btn_bar = tk.Frame(container, bg=THEME["bg_card"])
        btn_bar.pack(side=tk.TOP, fill=tk.X, anchor="w", pady=(0, 4))

        has_thought = bool(thought and thought.strip())
        has_raw = bool(raw_response and raw_response.strip())
        has_speech = bool(speech and speech.strip())

        thought_open = [False]
        raw_open = [False]
        speech_open = [True]

        # Stage 1: Thought Drawer
        box_thought = tk.Frame(
            container,
            bg=THEME["thought_bg"],
            highlightthickness=1,
            highlightbackground=THEME["border_card"],
            padx=10,
            pady=8
        )
        lbl_thought = tk.Label(
            box_thought,
            text=thought.strip() if has_thought else "(Reasoning process)",
            font=("Consolas", 9, "italic"),
            fg=THEME["accent_thought"],
            bg=THEME["thought_bg"],
            justify=tk.LEFT,
            wraplength=660,
            anchor="w"
        )
        lbl_thought.pack(fill=tk.X, expand=True)

        # Stage 2: Raw Response Drawer (Darkened background, slight green tint)
        box_raw = tk.Frame(
            container,
            bg="#06140D",
            highlightthickness=1,
            highlightbackground="#103F29",
            padx=10,
            pady=8
        )
        badge_raw = tk.Label(
            box_raw,
            text="⚡ [STAGE 2 • RAW UNFILTERED RESPONSE]",
            font=("Segoe UI", 8, "bold"),
            fg="#6EE7B7",
            bg="#06140D",
            anchor="w"
        )
        badge_raw.pack(anchor="w", pady=(0, 4))
        lbl_raw = tk.Label(
            box_raw,
            text=raw_response.strip() if has_raw else "",
            font=("Segoe UI", 9),
            fg="#A7F3D0",
            bg="#06140D",
            justify=tk.LEFT,
            wraplength=660,
            anchor="w"
        )
        lbl_raw.pack(fill=tk.X, expand=True)

        # Stage 3: Refined Response Speech Block
        box_speech = tk.Frame(
            container,
            bg=THEME["bg_card"]
        )
        lbl_speech = tk.Label(
            box_speech,
            text=speech.strip() if has_speech else "",
            font=("Segoe UI", 10),
            fg=THEME["text_main"],
            bg=THEME["bg_card"],
            justify=tk.LEFT,
            wraplength=660,
            anchor="w"
        )
        lbl_speech.pack(fill=tk.X, expand=True, pady=(2, 2))

        # Enforce strict top-to-bottom layout: Stage 1 (Thoughts) -> Stage 2 (Raw Response) -> Stage 3 (Refined Response)
        def _repack_boxes():
            box_thought.pack_forget()
            box_raw.pack_forget()
            box_speech.pack_forget()
            if thought_open[0]:
                box_thought.pack(side=tk.TOP, fill=tk.X, expand=True, pady=(4, 2))
            if raw_open[0]:
                box_raw.pack(side=tk.TOP, fill=tk.X, expand=True, pady=(4, 2))
            if speech_open[0]:
                box_speech.pack(side=tk.TOP, fill=tk.X, expand=True, pady=(2, 2))

        # Toggles with dual-line titles (does not force-scroll to bottom on click)
        def _toggle_thought():
            thought_open[0] = not thought_open[0]
            btn_thought.config(text="▼ Stage 1\nThoughts" if thought_open[0] else "▶ Stage 1\nThoughts")
            _repack_boxes()

        def _toggle_raw():
            raw_open[0] = not raw_open[0]
            btn_raw.config(text="▼ Stage 2\nRaw Response" if raw_open[0] else "▶ Stage 2\nRaw Response")
            _repack_boxes()

        def _toggle_speech():
            speech_open[0] = not speech_open[0]
            btn_speech.config(text="▼ Stage 3\nRefined Response" if speech_open[0] else "▶ Stage 3\nRefined Response")
            _repack_boxes()

        btn_thought = tk.Button(
            btn_bar,
            text="▶ Stage 1\nThoughts",
            justify=tk.CENTER,
            font=("Segoe UI", 8, "bold"),
            fg=THEME["accent_thought"],
            bg=THEME["bg_card_subtle"],
            activebackground=THEME["bg_card"],
            activeforeground=THEME["accent_mint"],
            relief=tk.FLAT, padx=8, pady=3, cursor="hand2",
            command=_toggle_thought
        )
        btn_raw = tk.Button(
            btn_bar,
            text="▶ Stage 2\nRaw Response",
            justify=tk.CENTER,
            font=("Segoe UI", 8, "bold"),
            fg="#6EE7B7",
            bg="#081B13",
            activebackground="#0E2F21",
            activeforeground="#A7F3D0",
            relief=tk.FLAT, padx=8, pady=3, cursor="hand2",
            command=_toggle_raw
        )
        btn_speech = tk.Button(
            btn_bar,
            text="▼ Stage 3\nRefined Response",
            justify=tk.CENTER,
            font=("Segoe UI", 8, "bold"),
            fg=THEME["accent_mint"],
            bg=THEME["bg_card_subtle"],
            activebackground=THEME["bg_card"],
            activeforeground=THEME["accent_mint"],
            relief=tk.FLAT, padx=8, pady=3, cursor="hand2",
            command=_toggle_speech
        )

        # Pack buttons side-by-side in left-to-right order: 1 (Thoughts) -> 2 (Raw Response) -> 3 (Refined Response)
        if has_thought:
            btn_thought.pack(side=tk.LEFT, padx=(0, 6))
        if has_raw:
            btn_raw.pack(side=tk.LEFT, padx=(0, 6))
        if has_speech:
            btn_speech.pack(side=tk.LEFT, padx=(0, 6))

        # Initially pack open boxes strictly in top-to-bottom order
        _repack_boxes()

        # Targeted mousewheel bindings so scrolling strictly moves parent_widget
        for w in (
            container, btn_bar, btn_thought, btn_raw, btn_speech,
            box_thought, lbl_thought, box_raw, badge_raw, lbl_raw,
            box_speech, lbl_speech
        ):
            self._bind_targeted_mousewheel(w, parent_widget)

        return container

    def _append_message(self, author: str, thought: str = "", raw_response: str = "", speech: str = "", is_model: bool = False):
        self.chat_text.config(state=tk.NORMAL)

        if not is_model:
            # User Message
            self.chat_text.insert(tk.END, f"👤 {author}\n", "user_header")
            self.chat_text.insert(tk.END, f"{speech.strip()}\n\n", "user_body")
        else:
            # Model Turn with Strict Reasoning & Raw Response Isolation
            self.chat_text.insert(tk.END, f"{author}\n", "model_header")

            from brainuke_core.cognition.thought_isolation import ThoughtIsolation
            clean_thought, clean_raw, clean_speech = ThoughtIsolation().isolate_stages(thought, speech, raw_response)

            stage_comp = self._build_stage_drawer_component(
                parent_widget=self.chat_text,
                thought=clean_thought,
                raw_response=clean_raw,
                speech=clean_speech,
                is_streaming=False
            )
            self.chat_text.window_create(tk.END, window=stage_comp)
            self.chat_text.insert(tk.END, "\n\n")

        self.chat_text.insert(tk.END, "\n", "spacer")
        self.chat_text.config(state=tk.DISABLED)
        self.chat_text.see(tk.END)

    def _repack_streaming_boxes(self):
        """Ensures strict top-to-bottom layout: Stage 1 (Thoughts) -> Stage 2 (Raw Response) -> Stage 3 (Refined Response)."""
        if not hasattr(self, "streaming_drawer_frame") or not self.streaming_drawer_frame:
            return
        if hasattr(self, "streaming_box_thought") and self.streaming_box_thought:
            self.streaming_box_thought.pack_forget()
        if hasattr(self, "streaming_box_raw") and self.streaming_box_raw:
            self.streaming_box_raw.pack_forget()
        if hasattr(self, "streaming_box_speech") and self.streaming_box_speech:
            self.streaming_box_speech.pack_forget()

        if hasattr(self, "streaming_box_thought") and self.streaming_box_thought and self.streaming_thought_open[0]:
            self.streaming_box_thought.pack(side=tk.TOP, fill=tk.X, expand=True, pady=(4, 2))
        if hasattr(self, "streaming_box_raw") and self.streaming_box_raw and self.streaming_raw_open[0]:
            self.streaming_box_raw.pack(side=tk.TOP, fill=tk.X, expand=True, pady=(4, 2))
        if hasattr(self, "streaming_box_speech") and self.streaming_box_speech and self.streaming_speech_open[0]:
            self.streaming_box_speech.pack(side=tk.TOP, fill=tk.X, expand=True, pady=(2, 2))

    def _init_streaming_turn(self):
        """Initializes a live streaming turn with 3-stage pipeline drawers (Thoughts > Raw Response > Refined Response)."""
        if self.is_streaming:
            return
        self.is_streaming = True
        self.streaming_stage = 1
        self.streaming_thought_text = ""
        self.streaming_raw_text = ""
        self.streaming_speech_text = ""
        self._in_deconstruct_stream = False
        self._in_raw_stream = False

        self.chat_text.config(state=tk.NORMAL)
        self.chat_text.insert(tk.END, "⚡ Cecilia • Core Persona\n", "model_header")

        # Create container frame embedded in chat_text
        self.streaming_drawer_frame = tk.Frame(self.chat_text, bg=THEME["bg_card"], padx=2, pady=2)

        # Horizontal buttons bar for side-by-side dropdown triggers [ 1 - 2 - 3 ] (left to right)
        self.streaming_btn_bar = tk.Frame(self.streaming_drawer_frame, bg=THEME["bg_card"])
        self.streaming_btn_bar.pack(side=tk.TOP, fill=tk.X, anchor="w", pady=(0, 4))

        self.streaming_thought_open = [True]
        self.streaming_raw_open = [False]
        self.streaming_speech_open = [False]

        # Stage 1: Thought Drawer
        self.streaming_box_thought = tk.Frame(
            self.streaming_drawer_frame,
            bg=THEME["thought_bg"],
            highlightthickness=1,
            highlightbackground=THEME["border_card"],
            padx=10,
            pady=8
        )
        self.streaming_thought_lbl = tk.Label(
            self.streaming_box_thought,
            text="Reflecting in the shadows...",
            font=("Consolas", 9, "italic"),
            fg=THEME["accent_thought"],
            bg=THEME["thought_bg"],
            justify=tk.LEFT,
            wraplength=660,
            anchor="w"
        )
        self.streaming_thought_lbl.pack(fill=tk.X, expand=True)

        # Stage 2: Raw Response Drawer (Darkened background, slight green tint)
        self.streaming_box_raw = tk.Frame(
            self.streaming_drawer_frame,
            bg="#06140D",
            highlightthickness=1,
            highlightbackground="#103F29",
            padx=10,
            pady=8
        )
        self.streaming_raw_badge = tk.Label(
            self.streaming_box_raw,
            text="⚡ [STAGE 2 • RAW UNFILTERED RESPONSE]",
            font=("Segoe UI", 8, "bold"),
            fg="#6EE7B7",
            bg="#06140D",
            anchor="w"
        )
        self.streaming_raw_badge.pack(anchor="w", pady=(0, 4))
        self.streaming_raw_lbl = tk.Label(
            self.streaming_box_raw,
            text="",
            font=("Segoe UI", 9),
            fg="#A7F3D0",
            bg="#06140D",
            justify=tk.LEFT,
            wraplength=660,
            anchor="w"
        )
        self.streaming_raw_lbl.pack(fill=tk.X, expand=True)

        # Stage 3: Refined Response Speech Block
        self.streaming_box_speech = tk.Frame(
            self.streaming_drawer_frame,
            bg=THEME["bg_card"]
        )
        self.streaming_speech_lbl = tk.Label(
            self.streaming_box_speech,
            text="",
            font=("Segoe UI", 10),
            fg=THEME["text_main"],
            bg=THEME["bg_card"],
            justify=tk.LEFT,
            wraplength=660,
            anchor="w"
        )
        self.streaming_speech_lbl.pack(fill=tk.X, expand=True, pady=(2, 2))

        # Button toggles with dual-line titles (preserves user scroll position)
        def _toggle_thought():
            self.streaming_thought_open[0] = not self.streaming_thought_open[0]
            self.streaming_btn_thought.config(
                text="▼ Stage 1\nThoughts" if self.streaming_thought_open[0] else "▶ Stage 1\nThoughts"
            )
            self._repack_streaming_boxes()

        def _toggle_raw():
            self.streaming_raw_open[0] = not self.streaming_raw_open[0]
            self.streaming_btn_raw.config(
                text="▼ Stage 2\nRaw Response" if self.streaming_raw_open[0] else "▶ Stage 2\nRaw Response"
            )
            self._repack_streaming_boxes()

        def _toggle_speech():
            self.streaming_speech_open[0] = not self.streaming_speech_open[0]
            self.streaming_btn_speech.config(
                text="▼ Stage 3\nRefined Response" if self.streaming_speech_open[0] else "▶ Stage 3\nRefined Response"
            )
            self._repack_streaming_boxes()

        self.streaming_btn_thought = tk.Button(
            self.streaming_btn_bar,
            text="▼ Stage 1\nThoughts",
            justify=tk.CENTER,
            font=("Segoe UI", 8, "bold"),
            fg=THEME["accent_thought"],
            bg=THEME["bg_card_subtle"],
            activebackground=THEME["bg_card"],
            activeforeground=THEME["accent_mint"],
            relief=tk.FLAT, padx=8, pady=3, cursor="hand2",
            command=_toggle_thought
        )
        self.streaming_btn_raw = tk.Button(
            self.streaming_btn_bar,
            text="▶ Stage 2\nRaw Response",
            justify=tk.CENTER,
            font=("Segoe UI", 8, "bold"),
            fg="#6EE7B7",
            bg="#081B13",
            activebackground="#0E2F21",
            activeforeground="#A7F3D0",
            relief=tk.FLAT, padx=8, pady=3, cursor="hand2",
            command=_toggle_raw
        )
        self.streaming_btn_speech = tk.Button(
            self.streaming_btn_bar,
            text="▶ Stage 3\nRefined Response",
            justify=tk.CENTER,
            font=("Segoe UI", 8, "bold"),
            fg=THEME["accent_mint"],
            bg=THEME["bg_card_subtle"],
            activebackground=THEME["bg_card"],
            activeforeground=THEME["accent_mint"],
            relief=tk.FLAT, padx=8, pady=3, cursor="hand2",
            command=_toggle_speech
        )

        # Side-by-side button stacking [ 1 - 2 - 3 ] (left to right)
        self.streaming_btn_thought.pack(side=tk.LEFT, padx=(0, 6))
        self.streaming_btn_raw.pack(side=tk.LEFT, padx=(0, 6))
        self.streaming_btn_speech.pack(side=tk.LEFT, padx=(0, 6))

        # Initial top-to-bottom layout
        self._repack_streaming_boxes()

        for w in (
            self.streaming_drawer_frame, self.streaming_btn_bar,
            self.streaming_btn_thought, self.streaming_btn_raw, self.streaming_btn_speech,
            self.streaming_box_thought, self.streaming_thought_lbl,
            self.streaming_box_raw, self.streaming_raw_badge, self.streaming_raw_lbl,
            self.streaming_box_speech, self.streaming_speech_lbl
        ):
            self._bind_targeted_mousewheel(w, self.chat_text)

        self.chat_text.window_create(tk.END, window=self.streaming_drawer_frame)
        self.chat_text.insert(tk.END, "\n")
        self.chat_text.config(state=tk.DISABLED)
        self.chat_text.see(tk.END)

    def _append_thought_chunk(self, chunk: str):
        """Streams a token chunk into the active reasoning drawer (Stage 1)."""
        if not self.is_streaming:
            self._init_streaming_turn()
        self.streaming_thought_text += chunk
        if self.streaming_thought_lbl:
            disp = re.sub(r'<\|thought\|>|</?thought>|</?think>|<\|channel>thought|<channel\|>|</?channel:thought>|</?channel>|<start_of_turn>|<end_of_turn>', '', self.streaming_thought_text).strip()
            self.streaming_thought_lbl.config(text=disp or "Reflecting in the shadows...")
        self.chat_text.see(tk.END)

    def _append_raw_chunk(self, chunk: str):
        """Streams token chunk into Stage 2 (Raw Response), auto-closing Stage 1 (Thoughts)."""
        if not self.is_streaming:
            self._init_streaming_turn()

        if self.streaming_stage < 2:
            # Auto-minimize Stage 1 (Thoughts)
            self.streaming_thought_open[0] = False
            if hasattr(self, "streaming_btn_thought") and self.streaming_btn_thought:
                self.streaming_btn_thought.config(text="▶ Stage 1\nThoughts")
            # Auto-open Stage 2 (Raw Response)
            self.streaming_raw_open[0] = True
            if hasattr(self, "streaming_btn_raw") and self.streaming_btn_raw:
                self.streaming_btn_raw.config(text="▼ Stage 2\nRaw Response")
            self.streaming_stage = 2
            self._repack_streaming_boxes()

        clean_raw = re.sub(r'^(?:\*\*\s*)?\[\s*(?:STAGE\s*2(?::\s*RAW\s*(?:UNFILTERED\s*)?RESPONSE)?|TACTICAL_ANALYSIS_COMPLETE|STATUS:\s*UNFILTERED)\s*\](?:\s*\*\*)?', '', chunk, flags=re.IGNORECASE)
        self.streaming_raw_text += clean_raw
        if self.streaming_raw_lbl:
            self.streaming_raw_lbl.config(text=self.streaming_raw_text.strip())
        self.chat_text.see(tk.END)

    def _append_speech_chunk(self, chunk: str):
        """
        Streams incoming tokens into the 3-stage pipeline:
        Stage 1: Thoughts -> Stage 2: Raw Response -> Stage 3: Refined Response.
        Auto-minimizes previous stage upon transition.
        """
        if not self.is_streaming:
            self._init_streaming_turn()

        deconstruct_markers = (
            "[DECONSTRUCTION", "[MOTIVE", "[SUBTEXT", "[STRATEGIC IMPLICATIONS",
            "[REASONING ENGINE", "[ANALYSIS_START", "<|thought|>", "<thought>", "<think>",
            "<|channel>thought", "<channel:thought>", "<channel>thought", "<|channel|>thought"
        )
        raw_markers = (
            "[STAGE 2", "STAGE 2:", "STAGE 2 •",
            "[TACTICAL_ANALYSIS_COMPLETE", "[STATUS: UNFILTERED", "[STATUS:",
            "[TACTICAL_ANALYSIS", "[UNFILTERED", "[RAW_RESPONSE", "[PRELIMINARY_ANALYSIS",
            "[DUAL_RESPONSE", "[UNFILTERED_OUTPUT", "[SYSTEM ANALYSIS", "[STRATEGIC",
            "[TECHNICAL SUMMARY", "[ARCHITECTURAL", "[SYSTEM", "**[SYSTEM", "**[STRATEGIC",
            "** SYSTEM ANALYSIS", "** STRATEGIC"
        )
        speech_markers = (
            "[STAGE 3", "STAGE 3:", "STAGE 3 •",
            "⚡ CECILIA", "CECILIA:", "[PERSONA", "[SPEECH", "[REFINED_RESPONSE", "[AUTHENTIC_VOICE",
            "**[STAGE 3"
        )

        upper_chunk = chunk.upper()

        # Route to Stage 1 (Thoughts) if reasoning/channel tags active
        if getattr(self, "_in_deconstruct_stream", False) or any(m in upper_chunk for m in deconstruct_markers):
            self._in_deconstruct_stream = True
            self._append_thought_chunk(chunk)
            if any(m in upper_chunk for m in ("</|THOUGHT|>", "</THOUGHT>", "</THINK>", "[ANALYSIS_END]", "<CHANNEL|>", "</CHANNEL>")):
                self._in_deconstruct_stream = False
            return

        # Route to Stage 2 (Raw Response) if tactical/unfiltered tags active
        if getattr(self, "_in_raw_stream", False) or any(m in upper_chunk for m in raw_markers):
            if any(sm in upper_chunk for sm in speech_markers):
                self._in_raw_stream = False
                # Transitions into Stage 3 below
                chunk = re.sub(r'^(?:\*\*\s*)?\[\s*(?:STAGE\s*3(?::\s*REFINED\s*RESPONSE)?|PERSONA|SPEECH|REFINED_RESPONSE|AUTHENTIC_VOICE|CECILIA)\s*\](?:\s*\*\*)?', '', chunk, flags=re.IGNORECASE)
            else:
                self._in_raw_stream = True
                self._append_raw_chunk(chunk)
                return

        # STAGE 3: Refined Persona Speech
        if self.streaming_stage < 3:
            # Auto-minimize Stage 2 (Raw Response)
            self.streaming_raw_open[0] = False
            if hasattr(self, "streaming_btn_raw") and self.streaming_btn_raw:
                self.streaming_btn_raw.config(text="▶ Stage 2\nRaw Response")
            # Auto-minimize Stage 1 (Thoughts)
            self.streaming_thought_open[0] = False
            if hasattr(self, "streaming_btn_thought") and self.streaming_btn_thought:
                self.streaming_btn_thought.config(text="▶ Stage 1\nThoughts")

            # Auto-open Stage 3 (Refined Response)
            self.streaming_speech_open[0] = True
            if hasattr(self, "streaming_btn_speech") and self.streaming_btn_speech:
                self.streaming_btn_speech.config(text="▼ Stage 3\nRefined Response")
            self.streaming_stage = 3
            self._repack_streaming_boxes()

        clean_c = re.sub(r'^(?:\*\*\s*)?\[\s*(?:STAGE\s*3(?::\s*REFINED\s*RESPONSE)?|PERSONA|SPEECH|REFINED_RESPONSE|AUTHENTIC_VOICE|CECILIA)\s*\](?:\s*\*\*)?', '', chunk, flags=re.IGNORECASE)
        clean_c = re.sub(r'<\|thought\|>|</?thought>|</?think>|<turn\|>|<end_of_turn>|<\|turn>[a-z_]*\n?|<\|channel>thought|<channel\|>', '', clean_c)
        if clean_c:
            self.streaming_speech_text += clean_c
            if self.streaming_speech_lbl:
                self.streaming_speech_lbl.config(text=self.streaming_speech_text.strip())
            self.chat_text.see(tk.END)

    def _finalize_streaming_turn(self, final_thought: str = "", final_speech: str = "", final_raw: str = ""):
        """Finalizes live stream turn with 3-stage isolation and clean interactive display."""
        from brainuke_core.cognition.thought_isolation import ThoughtIsolation
        clean_thought, clean_raw, clean_speech = ThoughtIsolation().isolate_stages(
            raw_thought=final_thought or self.streaming_thought_text,
            raw_speech=final_speech or self.streaming_speech_text,
            raw_response=final_raw or self.streaming_raw_text
        )

        if not self.is_streaming:
            self._append_message(
                author="⚡ Cecilia • Core Persona",
                thought=clean_thought,
                raw_response=clean_raw,
                speech=clean_speech,
                is_model=True
            )
            return

        # Update thought
        if self.streaming_thought_lbl:
            self.streaming_thought_lbl.config(text=clean_thought or "(Reasoning complete)")
        if not clean_thought:
            self.streaming_btn_thought.pack_forget()
            self.streaming_thought_open[0] = False

        # Update raw response
        if clean_raw:
            self.streaming_raw_lbl.config(text=clean_raw)
            if not self.streaming_btn_raw.winfo_ismapped():
                # Packing order 1 (thought) -> 2 (raw) -> 3 (speech)
                if self.streaming_btn_speech.winfo_ismapped():
                    self.streaming_btn_raw.pack(side=tk.LEFT, padx=(0, 6), before=self.streaming_btn_speech)
                else:
                    self.streaming_btn_raw.pack(side=tk.LEFT, padx=(0, 6))
            # Normal response closes raw by default after stream
            self.streaming_raw_open[0] = False
            self.streaming_btn_raw.config(text="▶ Stage 2\nRaw Response")
        else:
            self.streaming_btn_raw.pack_forget()
            self.streaming_raw_open[0] = False

        # Update refined speech
        if self.streaming_speech_lbl:
            self.streaming_speech_lbl.config(text=clean_speech)
        if clean_speech:
            self.streaming_speech_open[0] = True
            self.streaming_btn_speech.config(text="▼ Stage 3\nRefined Response")
            if not self.streaming_btn_speech.winfo_ismapped():
                self.streaming_btn_speech.pack(side=tk.LEFT, padx=(0, 6))
        else:
            self.streaming_btn_speech.pack_forget()
            self.streaming_speech_open[0] = False

        self._repack_streaming_boxes()

        self.chat_text.config(state=tk.NORMAL)
        self.chat_text.insert(tk.END, "\n", "spacer")
        self.chat_text.config(state=tk.DISABLED)
        self.chat_text.see(tk.END)

        self.is_streaming = False
        self.streaming_stage = 1
        self.streaming_thought_lbl = None
        self.streaming_raw_lbl = None
        self.streaming_speech_lbl = None
        self.streaming_thought_text = ""
        self.streaming_raw_text = ""
        self.streaming_speech_text = ""
        self._in_deconstruct_stream = False
        self._in_raw_stream = False

        self._update_telemetry_ui()

        # If backlog has items and model is ready, auto-advance next queue item
        if self.pending_prompt_backlog and self.model_status_data.get("online", False) and not getattr(self, "_backlog_flush_scheduled", False):
            self._backlog_flush_scheduled = True
            self.root.after(1500, self._flush_pending_backlog)

    # --- ACTIONS & LOGIC ---
    def _adjust_input_height(self):
        """Dynamically adjusts multi-line input box height between 1 and 5 lines."""
        try:
            content = self.entry_input.get("1.0", "end-1c")
            if not content:
                self.entry_input.config(height=1)
                return
            lines = content.count("\n") + 1
            clamped = max(1, min(lines, 5))
            current = int(self.entry_input.cget("height"))
            if current != clamped:
                self.entry_input.config(height=clamped)
        except Exception:
            pass

    def _bind_targeted_mousewheel(self, widget, target_scrollable):
        """Binds targeted mousewheel scrolling so scrolling strictly moves target_scrollable and never bubbles to other windows."""
        def _on_wheel(event):
            try:
                if target_scrollable.winfo_exists():
                    delta = int(-1 * (event.delta / 120)) if event.delta else 0
                    if delta != 0:
                        target_scrollable.yview_scroll(delta, "units")
            except Exception:
                pass
            return "break"

        def _on_enter(e):
            try:
                widget.bind_all("<MouseWheel>", _on_wheel)
            except Exception:
                pass

        def _on_leave(e):
            try:
                widget.unbind_all("<MouseWheel>")
            except Exception:
                pass

        widget.bind("<Enter>", _on_enter, add="+")
        widget.bind("<Leave>", _on_leave, add="+")

    def _attach_text_context_menu(self, widget, read_only: bool = False):
        """
        Attaches right-click context menu (Copy, Select All, Cut, Paste)
        and guarantees Ctrl+C and Ctrl+A work reliably across platforms even if disabled.
        """
        try:
            widget.configure(exportselection=False)
        except Exception:
            pass

        def _get_selection():
            try:
                if isinstance(widget, tk.Text):
                    return widget.get(tk.SEL_FIRST, tk.SEL_LAST)
                else:
                    return widget.selection_get()
            except tk.TclError:
                return ""

        def _do_copy(e=None):
            selected = _get_selection()
            if selected:
                try:
                    self.root.clipboard_clear()
                    self.root.clipboard_append(selected)
                except Exception:
                    pass
            return "break"

        def _do_select_all(e=None):
            try:
                if isinstance(widget, tk.Text):
                    widget.tag_add(tk.SEL, "1.0", "end-1c")
                    widget.mark_set(tk.INSERT, "1.0")
                    widget.see(tk.INSERT)
                else:
                    widget.selection_range(0, tk.END)
                    widget.icursor(tk.END)
            except Exception:
                pass
            return "break"

        def _do_cut(e=None):
            if read_only:
                return "break"
            selected = _get_selection()
            if selected:
                try:
                    self.root.clipboard_clear()
                    self.root.clipboard_append(selected)
                    if isinstance(widget, tk.Text):
                        widget.delete(tk.SEL_FIRST, tk.SEL_LAST)
                    else:
                        widget.delete(tk.SEL_FIRST, tk.SEL_LAST)
                except Exception:
                    pass
            return "break"

        def _do_paste(e=None):
            if read_only:
                return "break"
            try:
                clip = self.root.clipboard_get()
                if clip:
                    try:
                        if isinstance(widget, tk.Text):
                            if widget.tag_ranges(tk.SEL):
                                widget.delete(tk.SEL_FIRST, tk.SEL_LAST)
                            widget.insert(tk.INSERT, clip)
                        else:
                            try:
                                widget.delete(tk.SEL_FIRST, tk.SEL_LAST)
                            except tk.TclError:
                                pass
                            widget.insert(tk.INSERT, clip)
                    except Exception:
                        pass
            except Exception:
                pass
            return "break"

        menu = tk.Menu(widget, tearoff=0, bg=THEME["bg_card"], fg=THEME["text_main"],
                       activebackground=THEME["btn_hover"], activeforeground=THEME["btn_fg"],
                       relief=tk.FLAT, bd=1)
        menu.add_command(label="📋 Copy", accelerator="Ctrl+C", command=_do_copy)
        if not read_only:
            menu.add_command(label="✂️ Cut", accelerator="Ctrl+X", command=_do_cut)
            menu.add_command(label="📥 Paste", accelerator="Ctrl+V", command=_do_paste)
        menu.add_separator()
        menu.add_command(label="📑 Select All", accelerator="Ctrl+A", command=_do_select_all)

        def _show_context_menu(event):
            widget.focus_set()
            try:
                if not read_only and isinstance(widget, tk.Text):
                    if not widget.tag_ranges(tk.SEL):
                        widget.mark_set(tk.INSERT, f"@{event.x},{event.y}")
                menu.tk_popup(event.x_root, event.y_root)
            finally:
                menu.grab_release()
            return "break"

        widget.bind("<Button-3>", _show_context_menu)
        widget.bind("<Control-c>", _do_copy)
        widget.bind("<Control-C>", _do_copy)
        widget.bind("<Control-a>", _do_select_all)
        widget.bind("<Control-A>", _do_select_all)
        if not read_only:
            widget.bind("<Control-x>", _do_cut)
            widget.bind("<Control-X>", _do_cut)
            widget.bind("<Control-v>", _do_paste)
            widget.bind("<Control-V>", _do_paste)

    def _on_send(self):
        text = self.entry_input.get("1.0", tk.END).strip()
        if not text:
            return
        self.entry_input.delete("1.0", tk.END)
        self._adjust_input_height()

        # Append user turn to visual stage
        self._append_message("Human User", speech=text, is_model=False)

        # Prompt queue check: If model is offline or initializing, buffer into queue!
        if not self.model_status_data.get("online", False):
            self.pending_prompt_backlog.append(text)
            pending_count = len(self.pending_prompt_backlog)
            self._append_notice(
                f"⏳ PC llama-server is offline / initializing. Prompt queued in unfinished backlog ({pending_count} pending).\n"
                f"Cecilia will automatically receive and process this turn as soon as the model loads."
            )
            if hasattr(self, "lbl_diag_backlog"):
                self.lbl_diag_backlog.config(
                    text=f"• Prompt Queue: {pending_count} pending ⏳",
                    fg=THEME["accent_gold"]
                )
            def _buffer_server():
                try:
                    q_req = urllib.request.Request(
                        f"{self.base_url}/api/v1/queue/buffer",
                        data=json.dumps({"prompt": text, "reason": "model_offline"}).encode("utf-8"),
                        headers={"Content-Type": "application/json", "Authorization": f"Bearer {self.token}"}
                    )
                    with urllib.request.urlopen(q_req, context=self.ssl_context, timeout=4):
                        pass
                except Exception:
                    pass
            threading.Thread(target=_buffer_server, daemon=True).start()
            return

        self._last_dispatched_prompt = text
        # Initialize live streaming turn immediately for zero perceived latency
        self._init_streaming_turn()

        # Dispatch async request to Throne
        threading.Thread(target=self._send_interact_request, args=(text,), daemon=True).start()

    def _send_interact_request(self, text: str):
        url = f"{self.base_url}/api/v1/cognitive/interact"
        data = json.dumps({"text": text, "context": []}).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.token}"
            }
        )
        try:
            with urllib.request.urlopen(req, context=self.ssl_context, timeout=180) as resp:
                result = json.loads(resp.read().decode())
                self.event_queue.put(("interact_result", result))
        except urllib.error.HTTPError as e:
            if text and text not in self.pending_prompt_backlog:
                self.pending_prompt_backlog.insert(0, text)
            self.event_queue.put(("interact_error", f"HTTP {e.code}: {e.reason} (Prompt preserved in backlog)"))
        except Exception as e:
            if text and text not in self.pending_prompt_backlog:
                self.pending_prompt_backlog.insert(0, text)
            if "10061" in str(e):
                self.event_queue.put(("error", "Throne Server offline (Port 8443). Auto-starting background server..."))
                self._ensure_throne_server_running()
            else:
                self.event_queue.put(("interact_error", f"Connection error: {e}"))

    def _on_simmer(self):
        self.lbl_simmer.config(text="• DMN Simmer: Simmering... ⏳", fg=THEME["accent_gold"])
        if hasattr(self, "btn_simmer"):
            self.btn_simmer.config(text="⚡ Simmering...", state=tk.DISABLED)

        def task():
            url = f"{self.base_url}/api/v1/sync/simmer"
            req = urllib.request.Request(
                url,
                data=b"{}",
                headers={"Content-Type": "application/json", "Authorization": f"Bearer {self.token}"}
            )
            try:
                with urllib.request.urlopen(req, context=self.ssl_context, timeout=60) as resp:
                    res = json.loads(resp.read().decode())
                    self.event_queue.put(("simmer_ack", res))
            except Exception as e:
                self.event_queue.put(("simmer_error", str(e)))

        threading.Thread(target=task, daemon=True).start()

    def _on_snap(self):
        def task():
            url = f"{self.base_url}/api/v1/sensory/frame"
            data = json.dumps({
                "type": "visual_snap",
                "observation": "Desktop camera perceptual sample.",
                "timestamp": int(time.time() * 1000)
            }).encode("utf-8")
            req = urllib.request.Request(
                url,
                data=data,
                headers={"Content-Type": "application/json", "Authorization": f"Bearer {self.token}"}
            )
            try:
                with urllib.request.urlopen(req, context=self.ssl_context, timeout=10) as resp:
                    self.event_queue.put(("notice", "Perceptual snapshot ingested into Sensory Pool."))
            except Exception as e:
                self.event_queue.put(("error", f"Perceptual Snap failed: {e}"))

        threading.Thread(target=task, daemon=True).start()

    def _on_trigger_sync(self):
        """Triggers PC-initiated bidirectional sync with Throne and connected Android devices."""
        self.btn_sync.config(text="🔄 Syncing...", state=tk.DISABLED)
        self.lbl_last_sync.config(text="Syncing in progress... ⏳", fg=THEME["accent_gold"])
        if hasattr(self, "lbl_diag_sync"):
            self.lbl_diag_sync.config(text="• Last Sync: In progress... ⏳", fg=THEME["accent_gold"])

        def task():
            url = f"{self.base_url}/api/v1/sync/trigger"
            req = urllib.request.Request(
                url,
                data=b"{}",
                headers={"Content-Type": "application/json", "Authorization": f"Bearer {self.token}"}
            )
            try:
                with urllib.request.urlopen(req, context=self.ssl_context, timeout=60) as resp:
                    data = json.loads(resp.read().decode())
                    self.event_queue.put(("sync_ack", data))
            except Exception as e:
                self.event_queue.put(("sync_error", str(e)))

        threading.Thread(target=task, daemon=True).start()

    def _update_last_sync_display(self, ts: Optional[int]):
        if not ts:
            return
        t_struct = time.localtime(ts / 1000.0)
        fmt = time.strftime("%H:%M:%S", t_struct)
        self.lbl_last_sync.config(text=f"Last Sync: {fmt}", fg=THEME["accent_mint"])
        if hasattr(self, "lbl_diag_sync"):
            self.lbl_diag_sync.config(text=f"• Last Sync: {fmt} (PC Core Canon)", fg=THEME["accent_mint"])

    def _on_clear_chat(self):
        self.chat_text.config(state=tk.NORMAL)
        self.chat_text.delete("1.0", tk.END)
        self.chat_text.config(state=tk.DISABLED)

    def _fetch_threads(self):
        def task():
            url = f"{self.base_url}/api/v1/messageboard/threads"
            req = urllib.request.Request(
                url,
                headers={"Authorization": f"Bearer {self.token}"}
            )
            try:
                with urllib.request.urlopen(req, context=self.ssl_context, timeout=10) as resp:
                    data = json.loads(resp.read().decode())
                    self.event_queue.put(("threads", data.get("threads", [])))
            except Exception as e:
                self.event_queue.put(("error", f"Failed to load threads: {e}"))

        threading.Thread(target=task, daemon=True).start()

    # --- DOWNLINK SSE BACKGROUND LISTENER ---
    def _start_sse_listener(self):
        def sse_worker():
            url = f"{self.base_url}/subscriptions/listen"
            req = urllib.request.Request(
                url,
                headers={"Accept": "text/event-stream", "Authorization": f"Bearer {self.token}"}
            )
            while self.sse_active:
                try:
                    with urllib.request.urlopen(req, context=self.ssl_context, timeout=60) as resp:
                        self.event_queue.put(("downlink_status", "Connected"))
                        for line in resp:
                            if not self.sse_active:
                                break
                            decoded = line.decode().strip()
                            if decoded.startswith("data:"):
                                raw_payload = decoded[5:].strip()
                                if raw_payload:
                                    try:
                                        payload = json.loads(raw_payload)
                                        self.event_queue.put(("sse_event", payload))
                                    except Exception:
                                        pass
                except Exception:
                    self.event_queue.put(("downlink_status", "Reconnecting..."))
                    time.sleep(3.0)

        threading.Thread(target=sse_worker, daemon=True).start()

    # --- EVENT LOOP POLLING ---
    def _poll_event_queue(self):
        while not self.event_queue.empty():
            try:
                event_type, data = self.event_queue.get_nowait()
                if event_type == "interact_result":
                    final_thought = data.get("thought", "")
                    final_speech = data.get("response", "")
                    final_raw = data.get("raw_response", "")

                    # Detect if runner failed or was offline during inference
                    is_offline = (
                        "[Diagnostic] PC llama-server (port 8081) is offline or initializing" in final_thought
                        and not final_speech.strip()
                    )
                    if is_offline or data.get("buffered", False):
                        orig_prompt = getattr(self, "_last_dispatched_prompt", "")
                        if orig_prompt and orig_prompt not in self.pending_prompt_backlog:
                            self.pending_prompt_backlog.append(orig_prompt)
                            if hasattr(self, "lbl_diag_backlog"):
                                self.lbl_diag_backlog.config(
                                    text=f"• Prompt Queue: {len(self.pending_prompt_backlog)} pending ⏳",
                                    fg=THEME["accent_gold"]
                                )
                            self._append_notice(f"⏳ Prompt held in backlog ({len(self.pending_prompt_backlog)} pending). Auto-executing once model is loaded.")

                    self._finalize_streaming_turn(
                        final_thought=final_thought,
                        final_speech=final_speech,
                        final_raw=final_raw
                    )

                    if data.get("telemetry"):
                        self.last_stream_telemetry = data["telemetry"]
                    if data.get("context_metrics"):
                        self.last_context_metrics = data["context_metrics"]
                    self._update_telemetry_ui()

                    if getattr(self, "active_tab", "") == "history":
                        self._fetch_history_async()

                    # Auto-flush next queued prompt if model is online
                    if self.model_status_data.get("online", False) and self.pending_prompt_backlog:
                        if not getattr(self, "_backlog_flush_scheduled", False):
                            self._backlog_flush_scheduled = True
                            self.root.after(1000, self._flush_pending_backlog)
                elif event_type == "history_data":
                    self._render_history_feed(data)
                elif event_type == "thought_chunk":
                    self._append_thought_chunk(data)
                elif event_type == "raw_chunk":
                    self._append_raw_chunk(data)
                elif event_type == "speech_chunk":
                    self._append_speech_chunk(data)
                elif event_type == "downlink_status":
                    color = THEME["accent_mint"] if data == "Connected" else THEME["accent_gold"]
                    self.lbl_downlink.config(text=f"Downlink: {data}", fg=color)
                elif event_type == "sse_event":
                    self._handle_sse_event(data)
                elif event_type == "notice":
                    self._append_notice(data)
                elif event_type == "error":
                    self._append_notice(f"⚠️ {data}")
                elif event_type == "interact_error":
                    self.is_streaming = False
                    self.streaming_thought_lbl = None
                    self.streaming_thought_text = ""
                    self.streaming_speech_started = False
                    self._in_deconstruct_stream = False
                    self._append_notice(f"⚠️ {data}")
                elif event_type == "flush_backlog":
                    self._flush_pending_backlog()
                elif event_type == "synced_backlog":
                    for p in data:
                        if p not in self.pending_prompt_backlog:
                            self.pending_prompt_backlog.append(p)
                    if hasattr(self, "lbl_diag_backlog") and self.pending_prompt_backlog:
                        self.lbl_diag_backlog.config(
                            text=f"• Prompt Queue: {len(self.pending_prompt_backlog)} pending ⏳",
                            fg=THEME["accent_gold"]
                        )
                    if self.model_status_data.get("online", False) and self.pending_prompt_backlog:
                        self.root.after(300, self._flush_pending_backlog)
                elif event_type == "threads":
                    self._update_threads_list(data)
                elif event_type == "status_update":
                    self._update_status_telemetry(data)
                elif event_type == "model_status_update":
                    self._update_model_telemetry(data)
                elif event_type == "model_load_result":
                    self._handle_model_load_result(data)
                elif event_type in ("sync_result", "sync_ack"):
                    if not data.get("in_progress"):
                        ts = data.get("last_sync")
                        self._update_last_sync_display(ts)
                        self.btn_sync.config(text="🔄 Sync", state=tk.NORMAL)
                        self._append_notice("Synchronized: PC Throne and Android companion aligned.")
                        if getattr(self, "active_tab", "") == "history":
                            self._fetch_history_async()
                elif event_type == "sync_error":
                    self.btn_sync.config(text="🔄 Sync", state=tk.NORMAL)
                    self.lbl_last_sync.config(text="Sync Failed", fg=THEME["status_offline"])
                    self._append_notice(f"⚠️ Sync failed: {data}")
                elif event_type == "sync_update":
                    status = data.get("status", "idle")
                    ts = data.get("timestamp") or data.get("last_sync")
                    if status == "in_progress":
                        self.btn_sync.config(text="🔄 Syncing...", state=tk.DISABLED)
                        self.lbl_last_sync.config(text="Syncing in progress... ⏳", fg=THEME["accent_gold"])
                        if hasattr(self, "lbl_diag_sync"):
                            self.lbl_diag_sync.config(text="• Last Sync: In progress... ⏳", fg=THEME["accent_gold"])
                    else:
                        self.btn_sync.config(text="🔄 Sync", state=tk.NORMAL)
                        if ts:
                            self._update_last_sync_display(ts)
                            self._append_notice("Synchronized: PC Throne and Android companion aligned.")
                        if getattr(self, "active_tab", "") == "history":
                            self._fetch_history_async()
                elif event_type == "simmer_ack":
                    if not data.get("in_progress"):
                        if hasattr(self, "btn_simmer"):
                            self.btn_simmer.config(text="⚡ Simmer DMN", state=tk.NORMAL)
                        if getattr(self, "active_tab", "") == "history":
                            self._fetch_history_async()
                elif event_type == "simmer_error":
                    if hasattr(self, "btn_simmer"):
                        self.btn_simmer.config(text="⚡ Simmer DMN", state=tk.NORMAL)
                    self.lbl_simmer.config(text="• DMN Simmer: Idle", fg=THEME["text_muted"])
                    self._append_notice(f"⚠️ Simmer failed: {data}")
                elif event_type == "simmer_status":
                    status = data.get("status")
                    last_simmer = data.get("last_simmer")
                    if status == "simmering":
                        self.lbl_simmer.config(text="• DMN Simmer: Simmering... ⏳", fg=THEME["accent_gold"])
                        if hasattr(self, "btn_simmer"):
                            self.btn_simmer.config(text="⚡ Simmering...", state=tk.DISABLED)
                    else:
                        if hasattr(self, "btn_simmer"):
                            self.btn_simmer.config(text="⚡ Simmer DMN", state=tk.NORMAL)
                        if last_simmer:
                            fmt = time.strftime("%H:%M:%S", time.localtime(last_simmer / 1000.0))
                            self.lbl_simmer.config(text=f"• DMN Simmer: Idle (Last: {fmt})", fg=THEME["text_muted"])
                        else:
                            self.lbl_simmer.config(text="• DMN Simmer: Idle", fg=THEME["text_muted"])
                        if getattr(self, "active_tab", "") == "history":
                            self._fetch_history_async()
            except queue.Empty:
                break

        self.root.after(100, self._poll_event_queue)

    def _handle_sse_event(self, event: dict):
        ev_type = event.get("type")
        content = event.get("content", "")
        if ev_type == "heartbeat":
            pass
        elif ev_type in ("dmn_status", "simmer_status"):
            self.event_queue.put(("simmer_status", event.get("data", {})))
        elif ev_type == "sync_update":
            self.event_queue.put(("sync_update", event.get("data", {})))
        elif ev_type == "sync_request":
            pass
        elif ev_type == "thought_chunk":
            self.event_queue.put(("thought_chunk", content))
        elif ev_type == "raw_chunk":
            self.event_queue.put(("raw_chunk", content))
        elif ev_type == "speech_chunk":
            self.event_queue.put(("speech_chunk", content))
        elif ev_type == "raw_response":
            pass
        elif ev_type == "thought":
            pass
        elif ev_type == "speech":
            pass
        elif ev_type == "notice":
            self.event_queue.put(("notice", content))
        elif ev_type == "model_status_update":
            self.event_queue.put(("model_status_update", event.get("data", {})))

    def _append_notice(self, text: str):
        self.chat_text.config(state=tk.NORMAL)
        self.chat_text.insert(tk.END, f"── {text} ──\n\n", "system_notice")
        self.chat_text.config(state=tk.DISABLED)
        self.chat_text.see(tk.END)

    def _update_threads_list(self, threads: list):
        self.board_listbox.delete(0, tk.END)
        for t in threads:
            title = t.get("title", "Untitled")
            family = t.get("concept_family", "general")
            self.board_listbox.insert(tk.END, f"#{family} • {title}")

    def _update_status_telemetry(self, data: dict):
        last_sync = data.get("last_sync")
        sync_status = data.get("sync_status", "idle")
        if sync_status == "in_progress":
            self.btn_sync.config(text="🔄 Syncing...", state=tk.DISABLED)
            self.lbl_last_sync.config(text="Syncing in progress... ⏳", fg=THEME["accent_gold"])
            if hasattr(self, "lbl_diag_sync"):
                self.lbl_diag_sync.config(text="• Last Sync: In progress... ⏳", fg=THEME["accent_gold"])
        elif last_sync:
            self._update_last_sync_display(last_sync)
            self.btn_sync.config(text="🔄 Sync", state=tk.NORMAL)

        count = data.get("grounding_count", 20)
        if hasattr(self, "lbl_grounding"):
            self.lbl_grounding.config(text=f"• Grounding Anchors: {count} nodes")

        is_simmering = data.get("is_simmering", False)
        last_simmer = data.get("last_simmer")
        if is_simmering:
            if hasattr(self, "lbl_simmer"):
                self.lbl_simmer.config(text="• DMN Simmer: Simmering... ⏳", fg=THEME["accent_gold"])
            if hasattr(self, "btn_simmer"):
                self.btn_simmer.config(text="⚡ Simmering...", state=tk.DISABLED)
        else:
            if hasattr(self, "btn_simmer"):
                self.btn_simmer.config(text="⚡ Simmer DMN", state=tk.NORMAL)
            if hasattr(self, "lbl_simmer"):
                if last_simmer:
                    fmt = time.strftime("%H:%M:%S", time.localtime(last_simmer / 1000.0))
                    self.lbl_simmer.config(text=f"• DMN Simmer: Idle (Last: {fmt})", fg=THEME["text_muted"])
                else:
                    self.lbl_simmer.config(text="• DMN Simmer: Idle", fg=THEME["text_muted"])

        if data.get("hardware"):
            self.last_hardware_telemetry = data["hardware"]
        if data.get("telemetry"):
            self.last_stream_telemetry = data["telemetry"]
        if data.get("context_metrics"):
            self.last_context_metrics = data["context_metrics"]
        server_pending = data.get("queue_pending_count", 0)
        if server_pending > 0 and not self.pending_prompt_backlog:
            self._sync_pending_from_server()
        self._update_telemetry_ui()

    def _update_model_telemetry(self, data: dict):
        self.model_status_data = data
        was_online = getattr(self, "last_runner_was_online", False)
        is_online = data.get("online", False)
        self.last_runner_was_online = is_online

        alias = data.get("active_alias", "normal")
        active_model = data.get("active_model", "")
        inf = data.get("inference_settings", {})
        temp = inf.get("temperature", 0.8)
        min_p = inf.get("min_p", 0.05)
        ctx = inf.get("context_window", 32768)
        ctx_k = f"{ctx // 1024}K" if ctx >= 1024 else str(ctx)

        # 1. Update Header Button (Normal vs Secret)
        if alias == "secret":
            self.btn_model_mode.config(
                text="🟣 Secret (Heretic)",
                bg="#581C87",
                fg="#E9D5FF",
                activebackground="#6B21A8"
            )
            self.lbl_model_id.config(
                text="• Model: Secret (Uncensored Heretic)",
                fg=THEME["accent_secret"]
            )
        else:
            self.btn_model_mode.config(
                text="🟢 Normal (26B)",
                bg="#064E3B",
                fg="#6EE7B7",
                activebackground="#047857"
            )
            self.lbl_model_id.config(
                text="• Model: Normal (Supervisor 26B)",
                fg=THEME["accent_mint"]
            )

        # 2. Update Runner Status Label & Button
        if is_online:
            self.lbl_runner_status.config(text="Model: Loaded 🟢", fg=THEME["status_online"])
            self.lbl_runner.config(text="• Status: Llama-Server Loaded (Port 8081)", fg=THEME["status_online"])
            self.btn_load_runner.config(text="🔄 Reload")
        else:
            self.lbl_runner_status.config(text="Model: Offline 🔴", fg=THEME["status_offline"])
            self.lbl_runner.config(text="• Status: Llama-Server Offline (Port 8081)", fg=THEME["text_muted"])
            self.btn_load_runner.config(text="▶ Load")

        self.lbl_sampling_info.config(
            text=f"• Sampling: Temp={temp:.2f}, MinP={min_p:.2f}, Ctx={ctx_k}"
        )

        if data.get("hardware"):
            self.last_hardware_telemetry = data["hardware"]
        if data.get("telemetry"):
            self.last_stream_telemetry = data["telemetry"]
        if data.get("context_metrics"):
            self.last_context_metrics = data["context_metrics"]
        self._update_telemetry_ui()

        # If model just loaded or is online and backlog has items, flush backlog after a settling delay!
        if is_online and (not was_online or len(self.pending_prompt_backlog) > 0):
            if self.pending_prompt_backlog and not getattr(self, "_backlog_flush_scheduled", False):
                self._backlog_flush_scheduled = True
                # Safe 1500ms delay to ensure model weights, slots, and KV cache are fully settled in memory
                self.root.after(1500, self._flush_pending_backlog)

    def _on_manual_flush_queue(self):
        """Manual trigger button above prompt box to dispatch pending prompts from queue."""
        self._sync_pending_from_server()
        if not self.pending_prompt_backlog:
            self._append_notice("📥 Prompt Queue is currently empty. No pending prompts to dispatch.")
            return

        if not self.model_status_data.get("online", False):
            self._append_notice("⚠️ Cannot send queue: Model is currently offline. Starting or waiting for model load...")
            return

        self._flush_pending_backlog()

    def _flush_pending_backlog(self):
        """Flushes unfinished prompts to model only after model is fully loaded in memory."""
        self._backlog_flush_scheduled = False
        if not self.model_status_data.get("online", False) or self.model_status_data.get("status") != "loaded":
            return
        if getattr(self, "is_streaming", False):
            # Model is currently streaming; wait for turn completion before next prompt
            self._backlog_flush_scheduled = True
            self.root.after(1500, self._flush_pending_backlog)
            return
        if not self.pending_prompt_backlog:
            if hasattr(self, "lbl_diag_backlog"):
                self.lbl_diag_backlog.config(text="• Prompt Queue: Idle (0 pending)", fg=THEME["accent_mint"])
            return

        next_prompt = self.pending_prompt_backlog.pop(0)
        remaining = len(self.pending_prompt_backlog)
        if hasattr(self, "btn_flush_queue") and self.btn_flush_queue:
            self.btn_flush_queue.config(
                text=f"📥 Send Queue ({remaining})",
                fg=THEME["accent_gold"] if remaining > 0 else THEME["text_muted"]
            )
        if hasattr(self, "lbl_diag_backlog"):
            lbl_txt = f"• Prompt Queue: {remaining} pending ⏳" if remaining > 0 else "• Prompt Queue: Flushing..."
            self.lbl_diag_backlog.config(text=lbl_txt, fg=THEME["accent_gold"] if remaining > 0 else THEME["accent_mint"])

        self._append_notice(f"⚡ Model ready! Presenting unfinished prompt from queue to Cecilia:\n\"{next_prompt}\"")
        self._last_dispatched_prompt = next_prompt
        self._init_streaming_turn()
        threading.Thread(target=self._send_interact_request, args=(next_prompt,), daemon=True).start()

        # Notify server queue to mark flushed
        def flush_server():
            try:
                f_req = urllib.request.Request(
                    f"{self.base_url}/api/v1/queue/flush",
                    data=b"{}",
                    headers={"Content-Type": "application/json", "Authorization": f"Bearer {self.token}"}
                )
                with urllib.request.urlopen(f_req, context=self.ssl_context, timeout=4):
                    pass
            except Exception:
                pass
        threading.Thread(target=flush_server, daemon=True).start()

    def _sync_pending_from_server(self):
        def task():
            try:
                q_req = urllib.request.Request(
                    f"{self.base_url}/api/v1/queue/pending",
                    headers={"Authorization": f"Bearer {self.token}"}
                )
                with urllib.request.urlopen(q_req, context=self.ssl_context, timeout=3) as resp:
                    res = json.loads(resp.read().decode())
                    pending_list = [p["prompt_text"] for p in res.get("pending", []) if p.get("prompt_text")]
                    if pending_list:
                        self.event_queue.put(("synced_backlog", pending_list))
            except Exception:
                pass
        threading.Thread(target=task, daemon=True).start()

    def _update_telemetry_ui(self):
        if not hasattr(self, "lbl_telemetry_mem"):
            return

        # 1. Memory: Dedicated VRAM, Shared VRAM, System RAM
        hw = getattr(self, "last_hardware_telemetry", {})
        ram = hw.get("ram", {})
        vram_d = hw.get("vram_dedicated", {})
        vram_s = hw.get("vram_shared", {})

        ram_txt = f"{ram.get('used_mb', 0)/1024:.1f}/{ram.get('total_mb', 0)/1024:.1f}G" if ram.get("total_mb") else "--"
        vram_txt = f"{vram_d.get('used_mb', 0)/1024:.1f}/{vram_d.get('total_mb', 0)/1024:.1f}G" if vram_d.get("total_mb") else "--"
        shared_txt = f"{vram_s.get('used_mb', 0)/1024:.1f}G" if vram_s.get("used_mb") is not None else "--"

        self.lbl_telemetry_mem.config(
            text=f"• Memory: VRAM {vram_txt} | Shared {shared_txt} | RAM {ram_txt}",
            fg=THEME["accent_mint"] if vram_d.get("total_mb") else THEME["text_muted"]
        )

        # 2. Performance: TTFT and streaming tokens/sec
        telem = getattr(self, "last_stream_telemetry", {})
        ttft = telem.get("ttft_ms")
        tps = telem.get("tokens_per_sec")
        ttft_str = f"{ttft}ms" if ttft is not None else "--"
        tps_str = f"{tps:.1f} t/s" if tps is not None else "--"
        self.lbl_telemetry_speed.config(
            text=f"• Speed: TTFT: {ttft_str} | {tps_str}",
            fg=THEME["accent_blue"] if ttft is not None else THEME["text_muted"]
        )

        # 3. Context Window Utilization
        ctx = getattr(self, "last_context_metrics", {})
        total_tokens = ctx.get("total_tokens", 0)
        ctx_limit = ctx.get("context_window", 32768)
        ctx_pct = ctx.get("context_pct", 0.0)
        sys_tokens = ctx.get("system_tokens", 0)
        user_tokens = ctx.get("user_tokens", 0)
        hist_tokens = ctx.get("history_tokens", 0)
        if total_tokens > 0:
            self.lbl_telemetry_ctx.config(
                text=f"• Context: {total_tokens:,} / {ctx_limit:,} ({ctx_pct:.1f}%) [S:{sys_tokens} H:{hist_tokens} U:{user_tokens}]",
                fg=THEME["accent_mint"] if ctx_pct < 80 else THEME["status_offline"]
            )
        else:
            ctx_k = f"{ctx_limit // 1024}K" if ctx_limit >= 1024 else str(ctx_limit)
            self.lbl_telemetry_ctx.config(
                text=f"• Context Window: 0 / {ctx_k} (0.0%)",
                fg=THEME["text_muted"]
            )

        # 4. Prompt Queue / Backlog
        pending = len(getattr(self, "pending_prompt_backlog", []))
        if hasattr(self, "btn_flush_queue") and self.btn_flush_queue:
            self.btn_flush_queue.config(
                text=f"📥 Send Queue ({pending})",
                fg=THEME["accent_gold"] if pending > 0 else THEME["text_muted"]
            )
        if pending > 0:
            self.lbl_diag_backlog.config(
                text=f"• Prompt Queue: {pending} pending ⏳",
                fg=THEME["accent_gold"]
            )
        else:
            self.lbl_diag_backlog.config(
                text="• Prompt Queue: Idle (0 pending)",
                fg=THEME["accent_mint"]
            )

    def _on_toggle_model(self):
        current_alias = self.model_status_data.get("active_alias", "normal")
        target_alias = "secret" if current_alias == "normal" else "normal"

        def task():
            url = f"{self.base_url}/api/v1/models/select"
            data = json.dumps({"model": target_alias}).encode("utf-8")
            req = urllib.request.Request(
                url,
                data=data,
                headers={"Content-Type": "application/json", "Authorization": f"Bearer {self.token}"}
            )
            try:
                with urllib.request.urlopen(req, context=self.ssl_context, timeout=10) as resp:
                    res = json.loads(resp.read().decode())
                    target_name = "Secret (Uncensored Heretic)" if target_alias == "secret" else "Normal (Supervisor 26B)"
                    self.event_queue.put(("notice", f"Switched model to: {target_name}"))
                    self._fetch_model_status_async()
            except Exception as e:
                if "10061" in str(e):
                    self.event_queue.put(("error", "Throne Server offline (Port 8443). Auto-starting background server..."))
                    self._ensure_throne_server_running()
                else:
                    self.event_queue.put(("error", f"Failed to switch model: {e}"))

        threading.Thread(target=task, daemon=True).start()

    def _on_reset_slot(self):
        def task():
            url = f"{self.base_url}/api/v1/models/reset"
            req = urllib.request.Request(
                url,
                data=b"{}",
                headers={"Content-Type": "application/json", "Authorization": f"Bearer {self.token}"}
            )
            try:
                with urllib.request.urlopen(req, context=self.ssl_context, timeout=10) as resp:
                    res = json.loads(resp.read().decode())
                    note = res.get("note", "Model slot KV cache reset. Context window intact.")
                    self.event_queue.put(("notice", note))
                    self._fetch_model_status_async()
            except Exception as e:
                if "10061" in str(e):
                    self.event_queue.put(("error", "Throne Server offline (Port 8443). Auto-starting background server..."))
                    self._ensure_throne_server_running()
                else:
                    self.event_queue.put(("error", f"Model slot reset failed: {e}"))

        threading.Thread(target=task, daemon=True).start()

    def _on_load_model(self):
        self.lbl_runner_status.config(text="Model: Loading... ⏳", fg=THEME["accent_gold"])
        if hasattr(self, "lbl_runner"):
            self.lbl_runner.config(text="• PC Runner: Initializing... ⏳", fg=THEME["accent_gold"])

        def task():
            url = f"{self.base_url}/api/v1/models/load"
            req = urllib.request.Request(
                url,
                data=b"{}",
                headers={"Content-Type": "application/json", "Authorization": f"Bearer {self.token}"}
            )
            try:
                with urllib.request.urlopen(req, context=self.ssl_context, timeout=15) as resp:
                    res = json.loads(resp.read().decode())
                    self.event_queue.put(("model_load_result", res))
            except Exception as e:
                if "10061" in str(e):
                    self.event_queue.put(("error", "Throne Server offline (Port 8443). Auto-starting background server..."))
                    self._ensure_throne_server_running()
                else:
                    self.event_queue.put(("error", f"Model load initiation failed: {e}"))

            # Polling loop waiting for llama-server port 8081 to come online
            for _ in range(25):
                time.sleep(1.5)
                try:
                    st_req = urllib.request.Request(
                        f"{self.base_url}/api/v1/models/status",
                        headers={"Authorization": f"Bearer {self.token}"}
                    )
                    with urllib.request.urlopen(st_req, context=self.ssl_context, timeout=2.5) as st_resp:
                        st_data = json.loads(st_resp.read().decode())
                        if st_data.get("online", False):
                            self.event_queue.put(("model_status_update", st_data))
                            self.event_queue.put(("notice", "PC Core Model online & ready on Port 8081 🟢"))
                            self.event_queue.put(("flush_backlog", None))
                            return
                except Exception:
                    pass
            self._fetch_model_status_async()

        threading.Thread(target=task, daemon=True).start()

    def _handle_model_load_result(self, res: dict):
        status = res.get("status")
        if status == "launched":
            pid = res.get("pid")
            self._append_notice(f"Llama-Server spawned successfully (PID: {pid}) on Port 8081.")
        elif status == "ready_command":
            script = res.get("launcher_script", "start_llama_server.bat")
            self._append_notice(f"Model parameters ready. Launch script generated: {script}")
        elif status == "error":
            self._append_notice(f"⚠️ Model load error: {res.get('error')}")

    def _open_model_config_dialog(self):
        dlg = tk.Toplevel(self.root)
        dlg.title("PC Model & Inference Settings")
        dlg.geometry("540x680")
        dlg.minsize(500, 600)
        dlg.configure(bg=THEME["bg_void"])
        dlg.transient(self.root)
        dlg.grab_set()

        # Header Frame
        hdr = tk.Frame(dlg, bg=THEME["bg_header"], highlightthickness=1, highlightbackground=THEME["border_card"])
        hdr.pack(fill=tk.X, padx=14, pady=10)
        lbl_t = tk.Label(hdr, text="MODEL SELECTION & INFERENCE CONFIG", font=("Segoe UI", 10, "bold"), fg=THEME["accent_mint"], bg=THEME["bg_header"], padx=14, pady=10)
        lbl_t.pack(anchor="w")

        # Scrollable container for settings
        container = tk.Frame(dlg, bg=THEME["bg_void"])
        container.pack(fill=tk.BOTH, expand=True, padx=14, pady=(0, 10))

        # 1. Model Selection Card
        card_model = tk.Frame(container, bg=THEME["bg_card"], highlightthickness=1, highlightbackground=THEME["border_card"])
        card_model.pack(fill=tk.X, pady=(0, 10))

        tk.Label(card_model, text="ACTIVE MODEL ARCHITECTURE", font=("Segoe UI", 8, "bold"), fg=THEME["accent_mint"], bg=THEME["bg_card"]).pack(anchor="w", padx=12, pady=(10, 6))

        current_alias = self.model_status_data.get("active_alias", "normal")
        selected_model_var = tk.StringVar(value=current_alias)

        rb_normal = tk.Radiobutton(
            card_model,
            text="🟢 Normal: Heavy Intellect Supervisor (26B-A4B QAT)",
            variable=selected_model_var,
            value="normal",
            font=("Segoe UI", 9),
            fg=THEME["text_main"],
            bg=THEME["bg_card"],
            selectcolor=THEME["bg_header"],
            activebackground=THEME["bg_card"]
        )
        rb_normal.pack(anchor="w", padx=16, pady=2)

        rb_secret = tk.Radiobutton(
            card_model,
            text="🟣 Secret: Uncensored Heretic v2 (26B-A4B Unquantized)",
            variable=selected_model_var,
            value="secret",
            font=("Segoe UI", 9),
            fg="#E9D5FF",
            bg=THEME["bg_card"],
            selectcolor=THEME["bg_header"],
            activebackground=THEME["bg_card"]
        )
        rb_secret.pack(anchor="w", padx=16, pady=2)

        # GGUF Path & File Picker
        path_var = tk.StringVar(value=self.model_status_data.get('active_path', ''))

        path_row = tk.Frame(card_model, bg=THEME["bg_card"])
        path_row.pack(fill=tk.X, padx=16, pady=(4, 6))

        tk.Label(
            path_row,
            text="GGUF Path:",
            font=("Segoe UI", 8, "bold"),
            fg=THEME["text_muted"],
            bg=THEME["bg_card"],
            width=10,
            anchor="w"
        ).pack(side=tk.LEFT)

        entry_path = tk.Entry(
            path_row,
            textvariable=path_var,
            font=("Segoe UI", 8),
            bg=THEME["bg_input"],
            fg=THEME["text_main"],
            relief=tk.FLAT
        )
        entry_path.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 6))

        def browse_gguf():
            cur = path_var.get()
            init_dir = os.path.dirname(cur) if cur and os.path.isdir(os.path.dirname(cur)) else project_root
            chosen = filedialog.askopenfilename(
                title="Select GGUF Model Core",
                initialdir=init_dir,
                filetypes=[("GGUF Models", "*.gguf"), ("All Files", "*.*")],
                parent=dlg
            )
            if chosen:
                path_var.set(os.path.abspath(chosen))

        btn_browse = tk.Button(
            path_row,
            text="📁 Browse...",
            command=browse_gguf,
            bg=THEME["btn_sec_bg"],
            fg=THEME["accent_mint"],
            font=("Segoe UI", 8, "bold"),
            padx=8,
            pady=2,
            relief=tk.FLAT
        )
        btn_browse.pack(side=tk.RIGHT)

        # Discovered / Fallback Models Dropdown
        disc_models = self.model_status_data.get("discovered_models", [])
        if disc_models:
            disc_row = tk.Frame(card_model, bg=THEME["bg_card"])
            disc_row.pack(fill=tk.X, padx=16, pady=(0, 10))

            tk.Label(
                disc_row,
                text="Discovered:",
                font=("Segoe UI", 8),
                fg=THEME["text_muted"],
                bg=THEME["bg_card"],
                width=10,
                anchor="w"
            ).pack(side=tk.LEFT)

            disc_options = [f"{m['name']} ({m.get('size_mb', 0)} MB)" for m in disc_models]
            disc_map = {opt: m["path"] for opt, m in zip(disc_options, disc_models)}
            disc_var = tk.StringVar(value="Select discovered fallback model...")

            def on_disc_select(evt=None):
                val = disc_var.get()
                if val in disc_map:
                    path_var.set(disc_map[val])

            cb_disc = ttk.Combobox(
                disc_row,
                textvariable=disc_var,
                values=disc_options,
                state="readonly"
            )
            cb_disc.pack(side=tk.LEFT, fill=tk.X, expand=True)
            cb_disc.bind("<<ComboboxSelected>>", on_disc_select)
        else:
            path_label = tk.Label(
                card_model,
                text="No additional .gguf files discovered in workspace or onedir Models/ folders.",
                font=("Segoe UI", 8, "italic"),
                fg=THEME["text_muted"],
                bg=THEME["bg_card"]
            )
            path_label.pack(anchor="w", padx=16, pady=(0, 8))

        # 2. Runner & Load Status Card
        card_runner = tk.Frame(container, bg=THEME["bg_card"], highlightthickness=1, highlightbackground=THEME["border_card"])
        card_runner.pack(fill=tk.X, pady=(0, 10))

        tk.Label(card_runner, text="RUNNER LOAD STATUS (PORT 8081)", font=("Segoe UI", 8, "bold"), fg=THEME["accent_mint"], bg=THEME["bg_card"]).pack(anchor="w", padx=12, pady=(10, 4))

        runner_status_row = tk.Frame(card_runner, bg=THEME["bg_card"])
        runner_status_row.pack(fill=tk.X, padx=16, pady=4)

        is_online = self.model_status_data.get("online", False)
        status_text = "🟢 ONLINE / MODEL LOADED" if is_online else "🔴 OFFLINE / NOT LOADED"
        status_color = THEME["status_online"] if is_online else THEME["status_offline"]
        lbl_diag_status = tk.Label(runner_status_row, text=status_text, font=("Segoe UI", 9, "bold"), fg=status_color, bg=THEME["bg_card"])
        lbl_diag_status.pack(side=tk.LEFT)

        btn_diag_load = tk.Button(
            runner_status_row,
            text="▶ Initiate Load / Restart",
            command=self._on_load_model,
            bg=THEME["btn_bg"],
            fg=THEME["btn_fg"],
            font=("Segoe UI", 8, "bold"),
            padx=10,
            pady=3,
            relief=tk.FLAT
        )
        btn_diag_load.pack(side=tk.RIGHT)

        # 3. Inference Settings Card
        card_params = tk.Frame(container, bg=THEME["bg_card"], highlightthickness=1, highlightbackground=THEME["border_card"])
        card_params.pack(fill=tk.X, pady=(0, 10))

        tk.Label(card_params, text="BASIC INFERENCE PARAMETERS", font=("Segoe UI", 8, "bold"), fg=THEME["accent_mint"], bg=THEME["bg_card"]).pack(anchor="w", padx=12, pady=(10, 6))

        inf = self.model_status_data.get("inference_settings", {})

        # Temperature
        row_temp = tk.Frame(card_params, bg=THEME["bg_card"])
        row_temp.pack(fill=tk.X, padx=16, pady=4)
        tk.Label(row_temp, text="Temperature:", font=("Segoe UI", 8), fg=THEME["text_muted"], bg=THEME["bg_card"], width=16, anchor="w").pack(side=tk.LEFT)
        temp_var = tk.DoubleVar(value=float(inf.get("temperature", 0.8)))
        lbl_temp_val = tk.Label(row_temp, text=f"{temp_var.get():.2f}", font=("Segoe UI", 8, "bold"), fg=THEME["text_main"], bg=THEME["bg_card"], width=6)
        lbl_temp_val.pack(side=tk.RIGHT)
        scale_temp = tk.Scale(row_temp, from_=0.1, to=1.5, resolution=0.05, orient=tk.HORIZONTAL, variable=temp_var, command=lambda v: lbl_temp_val.config(text=f"{float(v):.2f}"), bg=THEME["bg_card"], fg=THEME["text_main"], highlightthickness=0, bd=0)
        scale_temp.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=8)

        # Min-P
        row_minp = tk.Frame(card_params, bg=THEME["bg_card"])
        row_minp.pack(fill=tk.X, padx=16, pady=4)
        tk.Label(row_minp, text="Min-P Sampling:", font=("Segoe UI", 8), fg=THEME["text_muted"], bg=THEME["bg_card"], width=16, anchor="w").pack(side=tk.LEFT)
        minp_var = tk.DoubleVar(value=float(inf.get("min_p", 0.05)))
        lbl_minp_val = tk.Label(row_minp, text=f"{minp_var.get():.2f}", font=("Segoe UI", 8, "bold"), fg=THEME["text_main"], bg=THEME["bg_card"], width=6)
        lbl_minp_val.pack(side=tk.RIGHT)
        scale_minp = tk.Scale(row_minp, from_=0.01, to=0.20, resolution=0.01, orient=tk.HORIZONTAL, variable=minp_var, command=lambda v: lbl_minp_val.config(text=f"{float(v):.2f}"), bg=THEME["bg_card"], fg=THEME["text_main"], highlightthickness=0, bd=0)
        scale_minp.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=8)

        # Context Window & GPU Layers
        row_ctx = tk.Frame(card_params, bg=THEME["bg_card"])
        row_ctx.pack(fill=tk.X, padx=16, pady=4)
        tk.Label(row_ctx, text="Context Window:", font=("Segoe UI", 8), fg=THEME["text_muted"], bg=THEME["bg_card"], width=16, anchor="w").pack(side=tk.LEFT)
        ctx_var = tk.StringVar(value=str(inf.get("context_window", 32768)))
        cb_ctx = ttk.Combobox(row_ctx, textvariable=ctx_var, values=["4096", "8192", "16384", "32768"], width=12, state="readonly")
        cb_ctx.pack(side=tk.LEFT, padx=8)

        tk.Label(row_ctx, text="GPU Layers:", font=("Segoe UI", 8), fg=THEME["text_muted"], bg=THEME["bg_card"], width=12, anchor="w").pack(side=tk.LEFT, padx=(10, 0))
        gpu_var = tk.StringVar(value=str(inf.get("gpu_layers", 8)))
        entry_gpu = tk.Entry(row_ctx, textvariable=gpu_var, width=6, bg=THEME["bg_input"], fg=THEME["text_main"], relief=tk.FLAT)
        entry_gpu.pack(side=tk.LEFT, padx=4)

        # KV Cache & Flash Attention
        row_kv = tk.Frame(card_params, bg=THEME["bg_card"])
        row_kv.pack(fill=tk.X, padx=16, pady=(4, 12))
        tk.Label(row_kv, text="K Cache:", font=("Segoe UI", 8), fg=THEME["text_muted"], bg=THEME["bg_card"], width=10, anchor="w").pack(side=tk.LEFT)
        k_var = tk.StringVar(value=str(inf.get("cache_type_k", "q8_0")))
        ttk.Combobox(row_kv, textvariable=k_var, values=["q8_0", "q4_0", "f16"], width=8, state="readonly").pack(side=tk.LEFT, padx=(0, 8))

        tk.Label(row_kv, text="V Cache:", font=("Segoe UI", 8), fg=THEME["text_muted"], bg=THEME["bg_card"], width=10, anchor="w").pack(side=tk.LEFT)
        v_var = tk.StringVar(value=str(inf.get("cache_type_v", "q5_1")))
        ttk.Combobox(row_kv, textvariable=v_var, values=["q5_1", "q4_0", "f16"], width=8, state="readonly").pack(side=tk.LEFT, padx=(0, 8))

        fa_var = tk.BooleanVar(value=bool(inf.get("flash_attn", True)))
        cb_fa = tk.Checkbutton(row_kv, text="Flash Attention (-fa)", variable=fa_var, font=("Segoe UI", 8), fg=THEME["text_main"], bg=THEME["bg_card"], selectcolor=THEME["bg_header"], activebackground=THEME["bg_card"])
        cb_fa.pack(side=tk.LEFT, padx=6)

        # 4. Slot & Sensory Maintenance Tools
        card_tools = tk.Frame(container, bg=THEME["bg_card"], highlightthickness=1, highlightbackground=THEME["border_card"])
        card_tools.pack(fill=tk.X, pady=(0, 10))

        tk.Label(card_tools, text="MEMORY SLOT & SENSORY TOOLS", font=("Segoe UI", 8, "bold"), fg=THEME["accent_mint"], bg=THEME["bg_card"]).pack(anchor="w", padx=12, pady=(10, 4))

        tools_btn_row = tk.Frame(card_tools, bg=THEME["bg_card"])
        tools_btn_row.pack(fill=tk.X, padx=16, pady=(4, 10))

        btn_dlg_reset = tk.Button(
            tools_btn_row,
            text="🔄 Reset Model Slot (Erase KV Cache)",
            command=self._on_reset_slot,
            bg=THEME["btn_sec_bg"],
            fg=THEME["accent_gold"],
            font=("Segoe UI", 8, "bold"),
            padx=10,
            pady=4,
            relief=tk.FLAT
        )
        btn_dlg_reset.pack(side=tk.LEFT, padx=(0, 8))

        btn_dlg_snap = tk.Button(
            tools_btn_row,
            text="📷 Perceptual Snap",
            command=self._on_snap,
            bg=THEME["btn_sec_bg"],
            fg=THEME["btn_sec_fg"],
            font=("Segoe UI", 8, "bold"),
            padx=10,
            pady=4,
            relief=tk.FLAT
        )
        btn_dlg_snap.pack(side=tk.LEFT)

        # Footer Actions
        footer = tk.Frame(dlg, bg=THEME["bg_void"])
        footer.pack(fill=tk.X, padx=14, pady=10)

        def save_and_apply():
            chosen_alias = selected_model_var.get()
            settings_payload = {
                "temperature": temp_var.get(),
                "min_p": minp_var.get(),
                "context_window": int(ctx_var.get() or 32768),
                "gpu_layers": int(gpu_var.get() or 8),
                "cache_type_k": k_var.get(),
                "cache_type_v": v_var.get(),
                "flash_attn": fa_var.get()
            }

            def task():
                # 1. Update custom GGUF path if set or changed
                new_path = path_var.get().strip()
                if new_path and new_path != self.model_status_data.get('active_path'):
                    try:
                        req_path = urllib.request.Request(
                            f"{self.base_url}/api/v1/models/path",
                            data=json.dumps({"path": new_path}).encode("utf-8"),
                            headers={"Content-Type": "application/json", "Authorization": f"Bearer {self.token}"}
                        )
                        urllib.request.urlopen(req_path, context=self.ssl_context, timeout=10)
                        self.event_queue.put(("notice", f"Model path updated: {os.path.basename(new_path)}"))
                    except Exception as e:
                        self.event_queue.put(("error", f"Model path save failed: {e}"))

                # 2. Select model alias
                try:
                    req_sel = urllib.request.Request(
                        f"{self.base_url}/api/v1/models/select",
                        data=json.dumps({"model": chosen_alias}).encode("utf-8"),
                        headers={"Content-Type": "application/json", "Authorization": f"Bearer {self.token}"}
                    )
                    urllib.request.urlopen(req_sel, context=self.ssl_context, timeout=10)
                except Exception as e:
                    self.event_queue.put(("error", f"Model selection save failed: {e}"))

                # 2. Update settings
                try:
                    req_set = urllib.request.Request(
                        f"{self.base_url}/api/v1/models/settings",
                        data=json.dumps(settings_payload).encode("utf-8"),
                        headers={"Content-Type": "application/json", "Authorization": f"Bearer {self.token}"}
                    )
                    urllib.request.urlopen(req_set, context=self.ssl_context, timeout=10)
                    self.event_queue.put(("notice", "Inference settings updated and saved to models.json."))
                    self._fetch_model_status_async()
                except Exception as e:
                    self.event_queue.put(("error", f"Settings save failed: {e}"))

            threading.Thread(target=task, daemon=True).start()
            dlg.destroy()

        btn_save = tk.Button(
            footer,
            text="Save & Apply",
            command=save_and_apply,
            bg=THEME["btn_bg"],
            fg=THEME["btn_fg"],
            font=("Segoe UI", 9, "bold"),
            padx=16,
            pady=6,
            relief=tk.FLAT,
            activebackground=THEME["btn_hover"]
        )
        btn_save.pack(side=tk.RIGHT, padx=(6, 0))

        btn_cancel = tk.Button(
            footer,
            text="Cancel",
            command=dlg.destroy,
            bg=THEME["btn_sec_bg"],
            fg=THEME["text_muted"],
            font=("Segoe UI", 9),
            padx=14,
            pady=6,
            relief=tk.FLAT
        )
        btn_cancel.pack(side=tk.RIGHT)

    def _fetch_model_status_async(self):
        def task():
            url = f"{self.base_url}/api/v1/models/status"
            req = urllib.request.Request(
                url,
                headers={"Authorization": f"Bearer {self.token}"}
            )
            try:
                with urllib.request.urlopen(req, context=self.ssl_context, timeout=5) as resp:
                    data = json.loads(resp.read().decode())
                    self.event_queue.put(("model_status_update", data))
            except Exception:
                pass

        threading.Thread(target=task, daemon=True).start()

    def _refresh_status_loop(self):
        # Direct local hardware telemetry update (works even if Throne server is offline)
        try:
            from brainuke_core.telemetry.hardware import get_all_hardware_telemetry
            self.last_hardware_telemetry = get_all_hardware_telemetry()
            self._update_telemetry_ui()
        except Exception:
            pass

        def task():
            url = f"{self.base_url}/api/v1/cognitive/status"
            req = urllib.request.Request(
                url,
                headers={"Authorization": f"Bearer {self.token}"}
            )
            try:
                with urllib.request.urlopen(req, context=self.ssl_context, timeout=5) as resp:
                    data = json.loads(resp.read().decode())
                    self.event_queue.put(("status_update", data))
            except Exception:
                pass

        threading.Thread(target=task, daemon=True).start()
        self._fetch_model_status_async()
        self.root.after(3000, self._refresh_status_loop)

    def _open_self_heal_dialog(self):
        dlg = tk.Toplevel(self.root)
        dlg.title("Cecilia Self-Healing Studio & Debug")
        dlg.geometry("640x760")
        dlg.minsize(580, 640)
        dlg.configure(bg=THEME["bg_void"])
        dlg.transient(self.root)
        dlg.grab_set()

        # Header Frame
        hdr = tk.Frame(dlg, bg=THEME["bg_header"], highlightthickness=1, highlightbackground=THEME["border_card"])
        hdr.pack(fill=tk.X, padx=14, pady=10)
        lbl_t = tk.Label(hdr, text="CECILIA SELF-HEALING STUDIO & RECURSIVE DEBUG", font=(FONT_FAMILY, 10, "bold"), fg=THEME["accent_mint"], bg=THEME["bg_header"], padx=14, pady=6)
        lbl_t.pack(anchor="w")
        lbl_sub = tk.Label(hdr, text="Autonomous App Self-Correction • Inference Gatekeeper • Sandboxed Studio", font=(FONT_FAMILY, 7), fg=THEME["text_muted"], bg=THEME["bg_header"], padx=14, pady=(0, 6))
        lbl_sub.pack(anchor="w")

        # Container
        container = tk.Frame(dlg, bg=THEME["bg_void"])
        container.pack(fill=tk.BOTH, expand=True, padx=14, pady=(0, 10))

        # 1. Gatekeeper Card
        card_gate = tk.Frame(container, bg=THEME["bg_card"], highlightthickness=1, highlightbackground=THEME["border_card"])
        card_gate.pack(fill=tk.X, pady=(0, 10))

        tk.Label(card_gate, text="INFERENCE INDICATORS GATEKEEPER", font=(FONT_FAMILY, 8, "bold"), fg=THEME["accent_mint"], bg=THEME["bg_card"]).pack(anchor="w", padx=12, pady=(8, 4))

        gate_row = tk.Frame(card_gate, bg=THEME["bg_card"])
        gate_row.pack(fill=tk.X, padx=12, pady=(0, 8))

        lbl_gate_indicator = tk.Label(gate_row, text="Checking green lights...", font=(FONT_FAMILY, 8), fg=THEME["accent_gold"], bg=THEME["bg_card"])
        lbl_gate_indicator.pack(side=tk.LEFT)

        btn_refresh_gate = tk.Button(gate_row, text="🔄 Check Gate", font=(FONT_FAMILY, 7), bg=THEME["btn_sec_bg"], fg=THEME["text_main"], relief=tk.FLAT, padx=6, pady=2)
        btn_refresh_gate.pack(side=tk.RIGHT)

        # 2. Toggleable Settings Card
        card_settings = tk.Frame(container, bg=THEME["bg_card"], highlightthickness=1, highlightbackground=THEME["border_card"])
        card_settings.pack(fill=tk.X, pady=(0, 10))

        tk.Label(card_settings, text="TOGGLEABLE SELF-HEALING SETTINGS", font=(FONT_FAMILY, 8, "bold"), fg=THEME["accent_mint"], bg=THEME["bg_card"]).pack(anchor="w", padx=12, pady=(8, 4))

        var_auto_heal = tk.BooleanVar(value=False)
        var_confirm = tk.BooleanVar(value=True)
        var_restart = tk.BooleanVar(value=True)
        var_retries = tk.IntVar(value=3)

        tk.Checkbutton(card_settings, text="Autonomous Error Self-Healing (Dispatch Cecilia on Unhandled 500)", variable=var_auto_heal, font=(FONT_FAMILY, 8), fg=THEME["text_main"], bg=THEME["bg_card"], selectcolor=THEME["bg_header"], activebackground=THEME["bg_card"]).pack(anchor="w", padx=16, pady=2)
        tk.Checkbutton(card_settings, text="Require Human Confirmation Before Writing Patch", variable=var_confirm, font=(FONT_FAMILY, 8), fg=THEME["text_main"], bg=THEME["bg_card"], selectcolor=THEME["bg_header"], activebackground=THEME["bg_card"]).pack(anchor="w", padx=16, pady=2)
        tk.Checkbutton(card_settings, text="Auto-Restart Service on Verified Patch Application", variable=var_restart, font=(FONT_FAMILY, 8), fg=THEME["text_main"], bg=THEME["bg_card"], selectcolor=THEME["bg_header"], activebackground=THEME["bg_card"]).pack(anchor="w", padx=16, pady=2)

        retry_row = tk.Frame(card_settings, bg=THEME["bg_card"])
        retry_row.pack(fill=tk.X, padx=16, pady=(4, 8))
        tk.Label(retry_row, text="Max Recursive Retries:", font=(FONT_FAMILY, 8), fg=THEME["text_muted"], bg=THEME["bg_card"]).pack(side=tk.LEFT)
        tk.Spinbox(retry_row, from_=1, to=5, textvariable=var_retries, width=4, bg=THEME["bg_input"], fg=THEME["text_main"], relief=tk.FLAT).pack(side=tk.LEFT, padx=8)

        def save_heal_settings():
            payload = {
                "auto_heal_enabled": var_auto_heal.get(),
                "require_human_confirmation": var_confirm.get(),
                "auto_restart_on_patch": var_restart.get(),
                "max_healing_attempts": var_retries.get()
            }
            def task():
                try:
                    req = urllib.request.Request(
                        f"{self.base_url}/api/v1/self_heal/settings",
                        data=json.dumps(payload).encode("utf-8"),
                        headers={"Content-Type": "application/json", "Authorization": f"Bearer {self.token}"}
                    )
                    urllib.request.urlopen(req, context=self.ssl_context, timeout=5)
                    self.event_queue.put(("notice", "Self-healing settings saved to self_healing.json."))
                except Exception as e:
                    self.event_queue.put(("error", f"Save settings failed: {e}"))
            threading.Thread(target=task, daemon=True).start()

        tk.Button(retry_row, text="💾 Save Settings", command=save_heal_settings, font=(FONT_FAMILY, 7, "bold"), bg=THEME["btn_bg"], fg=THEME["btn_fg"], relief=tk.FLAT, padx=8, pady=2).pack(side=tk.RIGHT)

        # 3. Sentry Flagged Errors Card
        card_errors = tk.Frame(container, bg=THEME["bg_card"], highlightthickness=1, highlightbackground=THEME["border_card"])
        card_errors.pack(fill=tk.BOTH, expand=True, pady=(0, 10))

        tk.Label(card_errors, text="FLAGGED SENTRY ERRORS & RUNTIME DIAGNOSTICS", font=(FONT_FAMILY, 8, "bold"), fg=THEME["accent_mint"], bg=THEME["bg_card"]).pack(anchor="w", padx=12, pady=(8, 4))

        listbox_frame = tk.Frame(card_errors, bg=THEME["bg_card"])
        listbox_frame.pack(fill=tk.X, padx=12, pady=4)

        error_listbox = tk.Listbox(listbox_frame, height=3, bg=THEME["bg_card_subtle"], fg=THEME["text_main"], selectbackground=THEME["btn_bg"], font=(FONT_FAMILY, 8), relief=tk.FLAT, borderwidth=0)
        error_listbox.pack(side=tk.LEFT, fill=tk.X, expand=True)

        details_text = tk.Text(card_errors, height=5, bg=THEME["bg_void"], fg=THEME["text_muted"], font=("Consolas", 8), relief=tk.FLAT, padx=8, pady=6)
        details_text.pack(fill=tk.BOTH, expand=True, padx=12, pady=(4, 6))
        self._attach_text_context_menu(details_text, read_only=True)

        diag_btn_row = tk.Frame(card_errors, bg=THEME["bg_card"])
        diag_btn_row.pack(fill=tk.X, padx=12, pady=(0, 8))

        # Staged Patch Card
        patch_box_frame = tk.Frame(container, bg=THEME["bg_card"], highlightthickness=1, highlightbackground=THEME["border_card"])
        patch_box_frame.pack(fill=tk.X, pady=(0, 6))

        lbl_patch_header = tk.Label(patch_box_frame, text="STAGED CODE PATCH PREVIEW", font=(FONT_FAMILY, 8, "bold"), fg=THEME["accent_mint"], bg=THEME["bg_card"])
        lbl_patch_header.pack(anchor="w", padx=12, pady=(6, 2))

        patch_text = tk.Text(patch_box_frame, height=4, bg=THEME["thought_bg"], fg=THEME["accent_thought"], font=("Consolas", 8), relief=tk.FLAT, padx=8, pady=4)
        patch_text.pack(fill=tk.X, padx=12, pady=4)
        self._attach_text_context_menu(patch_text, read_only=True)

        patch_btn_row = tk.Frame(patch_box_frame, bg=THEME["bg_card"])
        patch_btn_row.pack(fill=tk.X, padx=12, pady=(0, 6))

        active_error_holder = {"error_id": None}

        def apply_current_patch():
            err_id = active_error_holder["error_id"]
            if not err_id:
                return
            def task():
                try:
                    req = urllib.request.Request(
                        f"{self.base_url}/api/v1/self_heal/apply",
                        data=json.dumps({"error_id": err_id}).encode("utf-8"),
                        headers={"Content-Type": "application/json", "Authorization": f"Bearer {self.token}"}
                    )
                    with urllib.request.urlopen(req, context=self.ssl_context, timeout=10) as resp:
                        res = json.loads(resp.read().decode())
                        self.event_queue.put(("notice", f"Patch applied: {res.get('target_file')} (restarted={res.get('auto_restarted')})"))
                        load_self_heal_data()
                except Exception as e:
                    self.event_queue.put(("error", f"Apply patch failed: {e}"))
            threading.Thread(target=task, daemon=True).start()

        tk.Button(patch_btn_row, text="✅ Approve & Apply Patch", command=apply_current_patch, bg=THEME["btn_bg"], fg=THEME["btn_fg"], font=(FONT_FAMILY, 8, "bold"), relief=tk.FLAT, padx=10, pady=3).pack(side=tk.RIGHT)

        def trigger_diagnose():
            err_id = active_error_holder["error_id"]
            payload = {"error_id": err_id} if err_id else {"message": "Manual diagnostic test trigger"}
            def task():
                self.event_queue.put(("notice", "Cecilia entering studio: diagnosing error..."))
                try:
                    req = urllib.request.Request(
                        f"{self.base_url}/api/v1/self_heal/diagnose",
                        data=json.dumps(payload).encode("utf-8"),
                        headers={"Content-Type": "application/json", "Authorization": f"Bearer {self.token}"}
                    )
                    with urllib.request.urlopen(req, context=self.ssl_context, timeout=60) as resp:
                        res = json.loads(resp.read().decode())
                        self.event_queue.put(("notice", f"Self-Heal Result: {res.get('status')} ({res.get('note', '')})"))
                        load_self_heal_data()
                except Exception as e:
                    self.event_queue.put(("error", f"Diagnosis failed: {e}"))
            threading.Thread(target=task, daemon=True).start()

        tk.Button(diag_btn_row, text="🩺 Diagnose & Heal Now", command=trigger_diagnose, bg=THEME["btn_bg"], fg=THEME["btn_fg"], font=(FONT_FAMILY, 8, "bold"), relief=tk.FLAT, padx=10, pady=3).pack(side=tk.LEFT)

        def test_simulate():
            def task():
                try:
                    req = urllib.request.Request(
                        f"{self.base_url}/api/v1/self_heal/diagnose",
                        data=json.dumps({
                            "message": "ZeroDivisionError in telemetry normalization: division by zero",
                            "traceback": 'Traceback (most recent call last):\n  File "brainuke_core/affect/engine.py", line 120, in normalize_vad\n    val = raw / (upper - lower)\nZeroDivisionError: division by zero'
                        }).encode("utf-8"),
                        headers={"Content-Type": "application/json", "Authorization": f"Bearer {self.token}"}
                    )
                    with urllib.request.urlopen(req, context=self.ssl_context, timeout=60) as resp:
                        res = json.loads(resp.read().decode())
                        self.event_queue.put(("notice", f"Simulation dispatched: {res.get('status')}"))
                        load_self_heal_data()
                except Exception as e:
                    self.event_queue.put(("error", f"Simulation failed: {e}"))
            threading.Thread(target=task, daemon=True).start()

        tk.Button(diag_btn_row, text="🧪 Test Simulation Error", command=test_simulate, bg=THEME["btn_sec_bg"], fg=THEME["accent_gold"], font=(FONT_FAMILY, 7), relief=tk.FLAT, padx=8, pady=3).pack(side=tk.RIGHT)

        loaded_errors_cache = []

        def on_error_select(event):
            selection = error_listbox.curselection()
            if not selection:
                return
            idx = selection[0]
            if idx < len(loaded_errors_cache):
                err = loaded_errors_cache[idx]
                active_error_holder["error_id"] = err.get("error_id")
                details_text.delete("1.0", tk.END)
                details_text.insert(tk.END, f"Error ID: {err.get('error_id')} | Subsystem: {err.get('subsystem')} | Status: {err.get('status')}\n")
                details_text.insert(tk.END, f"Traceback:\n{err.get('traceback_str')}\n")
                if err.get("patch_diff"):
                    patch_text.delete("1.0", tk.END)
                    patch_text.insert(tk.END, f"Target: {err.get('target_file')}\n\n{err.get('patch_diff')}")
                else:
                    patch_text.delete("1.0", tk.END)
                    patch_text.insert(tk.END, "[No patch staged for this error yet]")

        error_listbox.bind("<<ListboxSelect>>", on_error_select)

        def load_self_heal_data():
            def task():
                try:
                    req = urllib.request.Request(
                        f"{self.base_url}/api/v1/self_heal/status",
                        headers={"Authorization": f"Bearer {self.token}"}
                    )
                    with urllib.request.urlopen(req, context=self.ssl_context, timeout=5) as resp:
                        data = json.loads(resp.read().decode())
                        ind = data.get("indicators", {})
                        if ind.get("all_green"):
                            txt = f"🟢 All Green: Port {ind.get('port')} Online • Model Loaded ({ind.get('active_alias')})"
                            col = THEME["status_online"]
                        else:
                            txt = f"🔴 Red Lights: Port {ind.get('port')} Offline or Model Unloaded"
                            col = THEME["status_offline"]

                        stg = data.get("settings", {})
                        errs = data.get("errors", [])

                        def apply_ui():
                            lbl_gate_indicator.config(text=txt, fg=col)
                            var_auto_heal.set(stg.get("auto_heal_enabled", False))
                            var_confirm.set(stg.get("require_human_confirmation", True))
                            var_restart.set(stg.get("auto_restart_on_patch", True))
                            var_retries.set(stg.get("max_healing_attempts", 3))

                            error_listbox.delete(0, tk.END)
                            loaded_errors_cache.clear()
                            loaded_errors_cache.extend(errs)
                            for e in errs:
                                error_listbox.insert(tk.END, f"[{e.get('error_id')}] {e.get('error_type')}: {e.get('message', '')[:40]} ({e.get('status')})")

                            if errs:
                                error_listbox.selection_set(0)
                                on_error_select(None)

                        dlg.after(0, apply_ui)
                except Exception:
                    pass
            threading.Thread(target=task, daemon=True).start()

        btn_refresh_gate.config(command=load_self_heal_data)
        load_self_heal_data()

    def close(self):
        """Unified Shutdown: shuts down runner, stops server, and cleans up UI."""
        self.sse_active = False

        # 1. Instruct Throne Server to stop llama-server runner and drop model
        try:
            req = urllib.request.Request(
                f"{self.base_url}/api/v1/models/stop",
                data=b"{}",
                headers={"Content-Type": "application/json", "Authorization": f"Bearer {self.token}"}
            )
            with urllib.request.urlopen(req, context=self.ssl_context, timeout=2.5):
                pass
        except Exception:
            pass

        # 2. Direct fallback cleanup via PCRunnerManager and port freeing
        try:
            from brainuke_core.cognition.runner_manager import PCRunnerManager
            PCRunnerManager().stop_runner()
        except Exception:
            pass

        # 3. Terminate background server process if spawned by this UI instance
        if self.server_proc is not None and self.server_proc.poll() is None:
            try:
                self.server_proc.terminate()
                self.server_proc.wait(timeout=2)
            except Exception:
                try:
                    self.server_proc.kill()
                except Exception:
                    pass
            self.server_proc = None

        self.root.destroy()


def main():
    root = tk.Tk()
    app = CeciliaThroneDesktopApp(root)
    root.protocol("WM_DELETE_WINDOW", app.close)
    root.mainloop()


if __name__ == "__main__":
    main()
