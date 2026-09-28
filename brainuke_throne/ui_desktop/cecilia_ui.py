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
import ssl
import time
import queue
import threading
import subprocess
import urllib.request
import urllib.error
import tkinter as tk
from tkinter import ttk, messagebox

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
            try:
                flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
                subprocess.Popen(
                    [sys.executable, server_main],
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

                if thought:
                    self.hist_text.insert(tk.END, "▶ Internal Thought Stream:\n", "hist_thought_hdr")
                    self.hist_text.insert(tk.END, f"{thought}\n\n", "hist_thought_body")

                if speech:
                    author_label = "⚡ Cecilia (PC Core Master):" if src == "pc" else "📱 Cecilia (Mobile Companion):"
                    self.hist_text.insert(tk.END, f"{author_label}\n", "hist_speech_hdr")
                    self.hist_text.insert(tk.END, f"{speech}\n\n", "hist_speech_body")

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

        btn_clear = tk.Button(actions_row, text="🧹 Clear View", command=self._on_clear_chat, bg=THEME["btn_sec_bg"], fg=THEME["text_muted"], font=("Segoe UI", 8), padx=12, pady=4, relief=tk.FLAT)
        btn_clear.pack(side=tk.RIGHT)

        # Input Row
        input_row = tk.Frame(composer_container, bg=THEME["bg_card"], highlightthickness=1, highlightbackground=THEME["border_card"])
        input_row.pack(side=tk.TOP, fill=tk.X)

        self.entry_input = tk.Entry(input_row, bg=THEME["bg_input"], fg=THEME["text_main"], insertbackground=THEME["accent_mint"], font=("Segoe UI", 10), relief=tk.FLAT)
        self.entry_input.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=12, pady=10)
        self.entry_input.bind("<Return>", lambda e: self._on_send())

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
    def _append_message(self, author: str, thought: str = "", speech: str = "", is_model: bool = False):
        self.chat_text.config(state=tk.NORMAL)

        if not is_model:
            # User Message
            self.chat_text.insert(tk.END, f"👤 {author}\n", "user_header")
            self.chat_text.insert(tk.END, f"{speech.strip()}\n\n", "user_body")
        else:
            # Model Turn with Strict Reasoning Isolation
            self.chat_text.insert(tk.END, f"{author}\n", "model_header")

            # Thought Drawer (Always inside a collapsible dropdown drawer)
            cleaned_thought = thought.strip() if thought else ""
            if cleaned_thought:
                drawer_frame = tk.Frame(self.chat_text, bg=THEME["bg_card"], padx=2, pady=2)

                content_box = tk.Frame(drawer_frame, bg=THEME["thought_bg"], highlightthickness=1, highlightbackground=THEME["border_card"], padx=10, pady=8)
                lbl_content = tk.Label(
                    content_box,
                    text=cleaned_thought,
                    font=("Consolas", 9, "italic"),
                    fg=THEME["accent_thought"],
                    bg=THEME["thought_bg"],
                    justify=tk.LEFT,
                    wraplength=660,
                    anchor="w"
                )
                lbl_content.pack(fill=tk.X, expand=True)

                is_open = [False]
                def _make_toggle(b, box, st):
                    def _toggle():
                        if st[0]:
                            box.pack_forget()
                            b.config(text="▶ Internal Reasoning (click to expand)")
                            st[0] = False
                        else:
                            box.pack(fill=tk.X, expand=True, pady=(4, 2))
                            b.config(text="▼ Internal Reasoning (click to collapse)")
                            st[0] = True
                        self.chat_text.see(tk.END)
                    return _toggle

                btn_toggle = tk.Button(
                    drawer_frame,
                    text="▶ Internal Reasoning (click to expand)",
                    font=("Segoe UI", 8, "bold"),
                    fg=THEME["accent_thought"],
                    bg=THEME["bg_card_subtle"],
                    activebackground=THEME["bg_card"],
                    activeforeground=THEME["accent_mint"],
                    relief=tk.FLAT,
                    padx=8,
                    pady=2,
                    cursor="hand2"
                )
                btn_toggle.config(command=_make_toggle(btn_toggle, content_box, is_open))
                btn_toggle.pack(anchor="w")

                self.chat_text.window_create(tk.END, window=drawer_frame)
                self.chat_text.insert(tk.END, "\n")

            # Spoken Text
            if speech:
                self.chat_text.insert(tk.END, f"{speech.strip()}\n\n", "model_speech")

        self.chat_text.insert(tk.END, "\n", "spacer")
        self.chat_text.config(state=tk.DISABLED)
        self.chat_text.see(tk.END)

    def _init_streaming_turn(self):
        """Initializes a live streaming turn with active reasoning drawer and speech insertion mark."""
        if self.is_streaming:
            return
        self.is_streaming = True
        self.streaming_thought_text = ""
        self.streaming_speech_started = False

        self.chat_text.config(state=tk.NORMAL)
        self.chat_text.insert(tk.END, "⚡ Cecilia • Core Persona\n", "model_header")

        # Collapsible Thought Drawer
        self.streaming_drawer_frame = tk.Frame(self.chat_text, bg=THEME["bg_card"], padx=2, pady=2)
        self.streaming_content_box = tk.Frame(
            self.streaming_drawer_frame,
            bg=THEME["thought_bg"],
            highlightthickness=1,
            highlightbackground=THEME["border_card"],
            padx=10,
            pady=8
        )
        self.streaming_thought_lbl = tk.Label(
            self.streaming_content_box,
            text="Reflecting in the shadows...",
            font=("Consolas", 9, "italic"),
            fg=THEME["accent_thought"],
            bg=THEME["thought_bg"],
            justify=tk.LEFT,
            wraplength=660,
            anchor="w"
        )
        self.streaming_thought_lbl.pack(fill=tk.X, expand=True)

        is_open = [False]
        def _make_toggle(b, box, st):
            def _toggle():
                if st[0]:
                    box.pack_forget()
                    b.config(text="▶ Internal Reasoning (click to expand)")
                    st[0] = False
                else:
                    box.pack(fill=tk.X, expand=True, pady=(4, 2))
                    b.config(text="▼ Internal Reasoning (click to collapse)")
                    st[0] = True
                self.chat_text.see(tk.END)
            return _toggle

        btn_toggle = tk.Button(
            self.streaming_drawer_frame,
            text="▶ Internal Reasoning (click to expand)",
            font=("Segoe UI", 8, "bold"),
            fg=THEME["accent_thought"],
            bg=THEME["bg_card_subtle"],
            activebackground=THEME["bg_card"],
            activeforeground=THEME["accent_mint"],
            relief=tk.FLAT,
            padx=8,
            pady=2,
            cursor="hand2"
        )
        btn_toggle.config(command=_make_toggle(btn_toggle, self.streaming_content_box, is_open))
        btn_toggle.pack(anchor="w")

        self.chat_text.window_create(tk.END, window=self.streaming_drawer_frame)
        self.chat_text.insert(tk.END, "\n")
        self.chat_text.mark_set("speech_stream_insert", tk.END)
        self.chat_text.mark_gravity("speech_stream_insert", tk.RIGHT)
        self.chat_text.config(state=tk.DISABLED)
        self.chat_text.see(tk.END)

    def _append_thought_chunk(self, chunk: str):
        """Streams a token chunk into the active reasoning drawer."""
        if not self.is_streaming:
            self._init_streaming_turn()
        self.streaming_thought_text += chunk
        if self.streaming_thought_lbl:
            self.streaming_thought_lbl.config(text=self.streaming_thought_text.strip())

    def _append_speech_chunk(self, chunk: str):
        """Streams a spoken token chunk live into the active chat speech block."""
        if not self.is_streaming:
            self._init_streaming_turn()

        # Guard: If chunk contains reasoning/deconstruction markers, divert to thought drawer
        deconstruct_markers = (
            "[DECONSTRUCTION", "[MOTIVE", "[SUBTEXT", "[STRATEGIC IMPLICATIONS",
            "[REASONING ENGINE", "[ANALYSIS_START", "<|thought|>", "<thought>", "<think>"
        )
        upper_chunk = chunk.upper()
        if getattr(self, "_in_deconstruct_stream", False) or any(m in upper_chunk for m in deconstruct_markers):
            self._in_deconstruct_stream = True
            # Divert to reasoning drawer
            self._append_thought_chunk(chunk)
            if any(m in upper_chunk for m in ("</|THOUGHT|>", "</THOUGHT>", "</THINK>", "[ANALYSIS_END]")):
                self._in_deconstruct_stream = False
            return

        self.streaming_speech_started = True
        self.chat_text.config(state=tk.NORMAL)
        self.chat_text.insert("speech_stream_insert", chunk, "model_speech")
        self.chat_text.config(state=tk.DISABLED)
        self.chat_text.see(tk.END)

    def _finalize_streaming_turn(self, final_thought: str = "", final_speech: str = ""):
        """Finalizes the live stream turn when interact completion is returned."""
        from brainuke_core.cognition.thought_isolation import ThoughtIsolation
        clean_thought, clean_speech = ThoughtIsolation().isolate(final_thought, final_speech)

        if not self.is_streaming:
            self._append_message(
                author="⚡ Cecilia • Core Persona",
                thought=clean_thought,
                speech=clean_speech,
                is_model=True
            )
            return

        if not self.streaming_speech_started and clean_speech:
            self.chat_text.config(state=tk.NORMAL)
            self.chat_text.insert("speech_stream_insert", clean_speech.strip(), "model_speech")
            self.chat_text.config(state=tk.DISABLED)

        if clean_thought and self.streaming_thought_lbl:
            self.streaming_thought_lbl.config(text=clean_thought.strip())

        self.chat_text.config(state=tk.NORMAL)
        self.chat_text.insert(tk.END, "\n\n", "spacer")
        self.chat_text.config(state=tk.DISABLED)
        self.chat_text.see(tk.END)

        self.is_streaming = False
        self.streaming_thought_lbl = None
        self.streaming_thought_text = ""
        self.streaming_speech_started = False
        self._in_deconstruct_stream = False

    # --- ACTIONS & LOGIC ---
    def _on_send(self):
        text = self.entry_input.get().strip()
        if not text:
            return
        self.entry_input.delete(0, tk.END)

        # Append user turn
        self._append_message("Human User", speech=text, is_model=False)

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
            with urllib.request.urlopen(req, context=self.ssl_context, timeout=120) as resp:
                result = json.loads(resp.read().decode())
                self.event_queue.put(("interact_result", result))
        except urllib.error.HTTPError as e:
            self.event_queue.put(("interact_error", f"HTTP {e.code}: {e.reason}"))
        except Exception as e:
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
                    self._finalize_streaming_turn(
                        final_thought=data.get("thought", ""),
                        final_speech=data.get("response", "")
                    )
                    if getattr(self, "active_tab", "") == "history":
                        self._fetch_history_async()
                elif event_type == "history_data":
                    self._render_history_feed(data)
                elif event_type == "thought_chunk":
                    self._append_thought_chunk(data)
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
        elif ev_type == "speech_chunk":
            self.event_queue.put(("speech_chunk", content))
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

    def _update_model_telemetry(self, data: dict):
        self.model_status_data = data
        is_online = data.get("online", False)
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

        path_label = tk.Label(
            card_model,
            text=f"Active Path: {self.model_status_data.get('active_path', 'unknown')}",
            font=("Segoe UI", 8),
            fg=THEME["text_muted"],
            bg=THEME["bg_card"],
            wraplength=480,
            justify=tk.LEFT
        )
        path_label.pack(anchor="w", padx=16, pady=(4, 10))

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
                # 1. Select model
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
        self.root.after(4000, self._refresh_status_loop)

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

        diag_btn_row = tk.Frame(card_errors, bg=THEME["bg_card"])
        diag_btn_row.pack(fill=tk.X, padx=12, pady=(0, 8))

        # Staged Patch Card
        patch_box_frame = tk.Frame(container, bg=THEME["bg_card"], highlightthickness=1, highlightbackground=THEME["border_card"])
        patch_box_frame.pack(fill=tk.X, pady=(0, 6))

        lbl_patch_header = tk.Label(patch_box_frame, text="STAGED CODE PATCH PREVIEW", font=(FONT_FAMILY, 8, "bold"), fg=THEME["accent_mint"], bg=THEME["bg_card"])
        lbl_patch_header.pack(anchor="w", padx=12, pady=(6, 2))

        patch_text = tk.Text(patch_box_frame, height=4, bg=THEME["thought_bg"], fg=THEME["accent_thought"], font=("Consolas", 8), relief=tk.FLAT, padx=8, pady=4)
        patch_text.pack(fill=tk.X, padx=12, pady=4)

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
        self.sse_active = False
        self.root.destroy()


def main():
    root = tk.Tk()
    app = CeciliaThroneDesktopApp(root)
    root.protocol("WM_DELETE_WINDOW", app.close)
    root.mainloop()


if __name__ == "__main__":
    main()
