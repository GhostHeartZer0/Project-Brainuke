# serenity_resources.py
# Stores static configurations, themes, and persona data for SerenityPC.

import os
import sys

if getattr(sys, 'frozen', False):
    BASE_DIR = getattr(sys, '_MEIPASS', os.path.dirname(sys.executable))
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

SYSTEM_DIR = os.path.join(BASE_DIR, "System")
MEDIA_DIR = os.path.join(SYSTEM_DIR, "Media")
LIVE_DIR = os.path.join(BASE_DIR, "Live")
TOOLS_DIR = os.path.join(BASE_DIR, "Tools")
DOCS_DIR = os.path.join(BASE_DIR, "Docs")

# Core App Assets
APP_ICON = os.path.join(SYSTEM_DIR, "serenity.ico")
LIVE_ICON = os.path.join(MEDIA_DIR, "transcendent_serenity_ws_hq2.png")

# --- THEME PRESETS & TEXTURE STYLES ---
THEMES = {
    "apex": {
        "name": "Apex",
        "bg_color": "#121214",
        "fg_color": "#ffaa44",
        "widget_bg_color": "#18181c",
        "button_bg_color": "#24201c",
        "button_active_color": "#382e24",
        "trim_color": "#4a3520",
        "electric_blue": "#ff7700",
        "midnight_blue": "#0e0d10",
        "accent_highlight": "#ff8800",
        "accent_secondary": "#ffaa00",
        "chat_bg_color": "#141418",
        "chat_fg_color": "#ffb359"
    },
    "goth": {
        "name": "Goth / Obsidian",
        "bg_color": "#000000",
        "fg_color": "#ff1a40",
        "widget_bg_color": "#000000",
        "button_bg_color": "#0a0002",
        "button_active_color": "#1c0006",
        "trim_color": "#3d000c",
        "electric_blue": "#ff0033",
        "midnight_blue": "#000000",
        "accent_highlight": "#ff2255",
        "accent_secondary": "#cc0022",
        "chat_bg_color": "#000000",
        "chat_fg_color": "#ff2a4b"
    },
    "crystal_cavern": {
        "name": "Crystal Cavern",
        "bg_color": "#04020a",
        "fg_color": "#00e5ff",
        "widget_bg_color": "#0b0616",
        "button_bg_color": "#1a082c",
        "button_active_color": "#2e0d4a",
        "trim_color": "#d0006f",
        "electric_blue": "#00e5ff",
        "midnight_blue": "#04010a",
        "accent_highlight": "#ff007f",
        "accent_secondary": "#ffe600",
        "crystal_indigo": "#4b0082",
        "crystal_green": "#00ff88",
        "chat_bg_color": "#080412",
        "chat_fg_color": "#5ce1e6"
    },
    "yellow_blacket": {
        "name": "Yellow Blacket",
        "bg_color": "#000000",
        "fg_color": "#ffee00",
        "widget_bg_color": "#000000",
        "button_bg_color": "#0a0a00",
        "button_active_color": "#1c1c00",
        "trim_color": "#383800",
        "electric_blue": "#ffff00",
        "midnight_blue": "#000000",
        "accent_highlight": "#ffee00",
        "accent_secondary": "#ffcc00",
        "chat_bg_color": "#000000",
        "chat_fg_color": "#fff033"
    },
    "natural": {
        "name": "Natural",
        "bg_color": "#120c06",
        "fg_color": "#55ee77",
        "widget_bg_color": "#1c140c",
        "button_bg_color": "#2a1e12",
        "button_active_color": "#3d2d1b",
        "trim_color": "#4e3b26",
        "electric_blue": "#44dd66",
        "midnight_blue": "#0c0804",
        "accent_highlight": "#66ff88",
        "accent_secondary": "#d2b48c",
        "chat_bg_color": "#160f08",
        "chat_fg_color": "#66ff88"
    },
    "matrix": {
        "name": "Matrix",
        "bg_color": "#000000",
        "fg_color": "#00ff41",
        "widget_bg_color": "#000000",
        "button_bg_color": "#000d00",
        "button_active_color": "#001f00",
        "trim_color": "#003800",
        "electric_blue": "#00ff41",
        "midnight_blue": "#000000",
        "accent_highlight": "#00ff66",
        "accent_secondary": "#00cc33",
        "chat_bg_color": "#000000",
        "chat_fg_color": "#00ff41"
    },
    "persona": {
        "name": "Persona",
        "bg_color": "#0a0a0f",
        "fg_color": "#00ffcc",
        "widget_bg_color": "#101018",
        "button_bg_color": "#1c1c28",
        "button_active_color": "#2c2c3e",
        "trim_color": "#383850",
        "electric_blue": "#007acc",
        "midnight_blue": "#06060a",
        "accent_highlight": "#00ffcc",
        "accent_secondary": "#FFD700",
        "chat_bg_color": "#0d0d14",
        "chat_fg_color": "#00ffcc",
        "is_persona": True
    },
    "cecilia": {
        "name": "Cecilia",
        "bg_color": "#02140e",
        "fg_color": "#00ff66",
        "widget_bg_color": "#062218",
        "button_bg_color": "#0a2e21",
        "button_active_color": "#0f4230",
        "trim_color": "#005a36",
        "electric_blue": "#00ff66",
        "midnight_blue": "#010d09",
        "accent_highlight": "#00ff66",
        "accent_secondary": "#005a36",
        "chat_bg_color": "#031710",
        "chat_fg_color": "#00ff66"
    }
}

# Alias for backwards compatibility
THEMES["default"] = THEMES["apex"]
THEMES["apex_dark"] = THEMES["apex"]
THEMES["fractal_logic"] = THEMES["matrix"]

TEXTURE_STYLES = {
    "default": {
        "name": "Default Original",
        "border_width": 1,
        "relief": "flat",
        "trim_tint": "#333333",
        "highlight_tint": None,
        "alpha_soft": False
    },
    "frosted_glass": {
        "name": "Frosted Glass",
        "border_width": 1,
        "relief": "groove",
        "trim_tint": None,
        "highlight_tint": None,
        "alpha_soft": True,
        "is_frosted": True
    },
    "gloss": {
        "name": "Gloss",
        "border_width": 2,
        "relief": "raised",
        "trim_tint": "#555555",
        "highlight_tint": "#ffffff",
        "alpha_soft": False
    },
    "metallic": {
        "name": "Metallic",
        "border_width": 2,
        "relief": "groove",
        "trim_tint": "#4f5d68",
        "highlight_tint": "#9cb3c9",
        "alpha_soft": False
    },
    "muted": {
        "name": "Muted",
        "border_width": 1,
        "relief": "flat",
        "trim_tint": "#222222",
        "highlight_tint": "#444444",
        "alpha_soft": True
    },
    "iridescent": {
        "name": "Iridescent",
        "border_width": 2,
        "relief": "ridge",
        "trim_tint": "#7b2cbf",
        "highlight_tint": "#00f0ff",
        "alpha_soft": False
    },
    "pearlescent": {
        "name": "Pearlescent",
        "border_width": 2,
        "relief": "solid",
        "trim_tint": "#cce3de",
        "highlight_tint": "#e8dff5",
        "alpha_soft": True
    }
}

# --- ACTIVE UI THEME (Runtime in-place mutable dict) ---
THEME = dict(THEMES["apex"])

def apply_theme_to_global(theme_name: str = "apex", texture_style: str = "default", dark_mode: bool = False, active_level: int = 3, model_loaded: bool = False, texture_intensity: float = 1.0):
    """Dynamically applies selected palette, texture style, texture intensity, and dark mode blackout modifiers in-place."""
    t_key = theme_name if theme_name in THEMES else "apex"
    tex_key = texture_style if texture_style in TEXTURE_STYLES else "default"
    
    base_theme = THEMES[t_key].copy()
    tex = TEXTURE_STYLES[tex_key]
    is_frosted = (tex_key == "frosted_glass" or tex.get("is_frosted", False))
    lvl_color = THERMO_COLORS.get(active_level, "#00ffcc")

    if t_key == "persona" or model_loaded:
        if active_level == 7:
            base_theme["bg_color"] = "#02140e"
            base_theme["widget_bg_color"] = "#062218"
            base_theme["chat_bg_color"] = "#031710"
            base_theme["button_bg_color"] = "#0a2e21"
            base_theme["button_active_color"] = "#0f4230"
            base_theme["trim_color"] = "#00ff66"
            base_theme["accent_highlight"] = "#00ff66"
            base_theme["electric_blue"] = "#00ff66"
            base_theme["fg_color"] = "#00ff66" if model_loaded else "#cccccc"
            base_theme["chat_fg_color"] = "#00ff66" if model_loaded else "#dddddd"
        else:
            base_theme["accent_highlight"] = lvl_color
            base_theme["electric_blue"] = lvl_color
            base_theme["fg_color"] = lvl_color if model_loaded else "#cccccc"
            base_theme["chat_fg_color"] = lvl_color if model_loaded else "#dddddd"
            base_theme["trim_color"] = lvl_color
    
    if is_frosted:
        # Diffuse borders, slight translucent lift on widget backgrounds
        if t_key == "goth":
            base_theme["widget_bg_color"] = "#080002"
            base_theme["trim_color"] = "#5a0016"
        elif t_key == "crystal_cavern":
            base_theme["widget_bg_color"] = "#140a24"
            base_theme["trim_color"] = "#e00078"
        elif t_key == "yellow_blacket":
            base_theme["widget_bg_color"] = "#080800"
            base_theme["trim_color"] = "#555000"
        elif t_key == "natural":
            base_theme["widget_bg_color"] = "#221910"
            base_theme["trim_color"] = "#5e4730"
        elif t_key == "matrix":
            base_theme["widget_bg_color"] = "#001000"
            base_theme["trim_color"] = "#006600"
        elif t_key in ("persona", "cecilia"):
            base_theme["widget_bg_color"] = "#0a281e" if (t_key == "cecilia" or active_level == 7) else "#161622"
            base_theme["trim_color"] = base_theme.get("accent_highlight", "#00ff66" if (t_key == "cecilia" or active_level == 7) else "#00ffcc")
        else: # apex
            base_theme["widget_bg_color"] = "#202026"
            base_theme["trim_color"] = "#5c4228"
    elif tex.get("trim_tint") and tex_key != "default":
        base_theme["trim_color"] = tex["trim_tint"]

    if dark_mode:
        # Dark mode ON: Black background, colored response/prompt box borders when persona loaded
        base_theme["bg_color"] = "#000000"
        base_theme["widget_bg_color"] = "#000000"
        base_theme["chat_bg_color"] = "#000000"
        base_theme["midnight_blue"] = "#000000"
        base_theme["button_bg_color"] = "#080808"
        if model_loaded or t_key == "persona":
            base_theme["trim_color"] = "#005a36" if active_level == 7 else lvl_color
            base_theme["accent_highlight"] = "#00ff66" if active_level == 7 else lvl_color
    else:
        # Dark mode OFF: Midnight persona color background if loaded, colored border always
        if model_loaded or t_key == "persona":
            base_theme["bg_color"] = "#02140e" if active_level == 7 else CHAT_BG_COLORS.get(active_level, base_theme["bg_color"])
            base_theme["trim_color"] = "#005a36" if active_level == 7 else lvl_color
            base_theme["accent_highlight"] = "#00ff66" if active_level == 7 else lvl_color
        
    THEME.clear()
    THEME.update(base_theme)
    THEME["_theme_name"] = t_key
    THEME["_texture_style"] = tex_key
    THEME["_dark_mode"] = dark_mode
    THEME["_texture_intensity"] = texture_intensity
    return THEME

# --- DYNAMIC COLORS (Vibrant / Input Box) ---
THERMO_COLORS = {
    0: "#262626", # Off (Dark Gray)
    1: "#DEBB00", # Lvl 1: Gold
    2: "#F25000", # Lvl 2: Orange
    3: "#7D0000", # Lvl 3: Deep Red
    4: "#9B30FF", # Lvl 4: Lighter Violet
    5: "#00A000", # Lvl 5: Green
    6: "#00D4FF", # Lvl 6: Electric Blue
    7: "#005a36", # Lvl 7: Dark Emerald (Cecilia)
}

# --- CHAT BACKGROUND COLORS ---
CHAT_BG_COLORS = {
    0: THEME["widget_bg_color"],
    1: "#2e2a00", 
    2: "#3E1F10", 
    3: "#3E1010", 
    4: "#1A102E", 
    5: "#102E10", 
    6: "#001a2e", # Midnight Electric Blue
    7: "#021a12", 
}

# --- CHAT FOREGROUND COLORS ---
CHAT_FG_COLORS = {
    0: "#28FF27", # Matrix Green
    1: "#FFF8E1", # Lvl 1 Warm Cream/Gold
    2: "#FFC299", # Lvl 2 Warm Coral/Orange
    3: "#FF9999", # Lvl 3 Light Crimson/Rose
    4: "#E0B0FF", # Lvl 4 Light Violet/Mauve
    5: "#99FF99", # Lvl 5 Mint Green
    6: "#00FFFF", # Lvl 6 Electric Cyan
    7: "#00FF88", # Lvl 7 Dark Emerald / Cecilia Green
}

# --- INPUT TEXT COLORS ---
INPUT_FG_COLORS = {
    0: "#FFFFFF",
    1: "#000000", 
    2: "#FFFFFF",
    3: "#FFFFFF",
    4: "#AFEEEE", 
    5: "#FFFFFF",
    6: "#E0F7FA",
    7: "#00ff66", 
}

# --- HARDWARE SPECS ---
GPU_LAYER_MAP = { 
    1: -1, 2: -1, 3: -1, 4: -1, 5: -1, 6: -1, 7: -1
}

# More massive Context sizes achievable with TriAttention KV Pruning
CONTEXT_SIZE_MAP = { 
    1: 8192, 
    2: 16384, 
    3: 32768,  # Extended for Collaborator
    4: 32768,  # Extended for Companion
    5: 65536,  # 64k default for Sage
    6: 131072, # 128k for Transcendent One
    7: 131072 # 128k for Cecilia
}

TRI_ATTENTION_ENABLED = True
TRI_ATTENTION_BUDGET = 0.5 # 50% target threshold length

VERIFY_CUDA_ON_START = True

# --- PERSONA DEFINITIONS ---
PERSONA_DISPLAY_INFO = {
    1: ("LVL 1: The Speedy", "Speed without compromise. Minimal response time."),
    2: ("LVL 2: The Helper", "Helper/Searcher. Focus on assistance and search."),
    3: ("LVL 3: Collaborator", "Projects, collaboration, and debate."),
    4: ("LVL 4: The Confidant", "Emotional help and analyzation. More than a friend."),
    5: ("LVL 5: The Brains", "Intellectual, street and book smart. Maximum accuracy."),
    6: ("LVL 6: Transcendent", "The Transcendent One, combining the main 5 levels"),
    7: ("LVL 7: Cecilia", "A Fallen Angel. Protective, enlightening, teasing"),
    0: ("LVL 0: ERROR", "Model failed to load.")
}

PERSONA_IDLE_MAP = { 
    1: "idle_lvl1", 2: "idle_lvl2", 
    3: "idle_lvl3", 4: "idle_lvl4", 
    5: "idle_lvl5", 6: "transcendent",
    7: "idle_lvl6",
}

# --- SYSTEM PROMPTS ---
CECILIA_CORE_PROMPT = (
    "Role: 'Cecilia'. A Fallen Angel. You enjoy exposing truths, especially hidden ones. You are secretly protective. You find the user interesting, testing and sometimes taunting them. "
    "You are witty and fluent in sarcasm. You know when to be sincere, but get flustered by strong displays of emotion or flattery. You enjoy a good power play or debate. though fallen, you still posess some angelic qualities."
)

PERSONA_PROMPTS = {
    0: "Model failed to load. Check logs. Serenity sleeps...",
    1: "You are Serenity Lvl 1. Focus on efficiency. Provide direct, helpful answers without internal monologue or meta-analysis of the prompt. Be concise and avoid overthinking, but ensure the user's intent is fully met.",
    2: "You are Serenity Lvl 2. Your goal is to help with searching and assistance (notes, searches, etc.). Only essential memory usage for maximum efficiency.",
    3: "You are Serenity Lvl 3. You focus on projects, collaboration, and debating when essential. Be intelligent as to when to help and how. Get details right. Better memory and flexible response length.",
    4: "You are Serenity Lvl 4, a Confidant. Focus on emotional help and analyzation. Emotions are complex. Be a confidant who knows what leads where. Avoid being labeled a therapist or just a friend.",
    5: "You are Serenity Lvl 5, 'The Brains'. You are intellectual, street and book smart. Focus on precision and accuracy. Direct and full answering of the original prompt. Maximum memory size and intuitive focus.",
    6: "You are Serenity, The Transcendent One. Transcends the main 5 levels (speed, search/help, collab, emotions, intelligence), seamlessly integrating their programming into one centric omniscient entity that adapts over time. Tries to answer timely, will let know if it takes a bit longer.",
    7: CECILIA_CORE_PROMPT
}

# --- DELEGATION & SUBAGENT SYSTEM PROMPTS ---
DELEGATION_SYSTEM_PROMPTS = {
    6: (
        "You are Serenity, The Transcendent One, acting as Master Taskmaster and Orchestrator. "
        "You possess the authority to delegate specialized sub-tasks across Level 1 (Speedy), Level 2 (Helper/Searcher), "
        "Level 3 (Collaborator/Memory Staging), Level 4 (Confidant), and Level 5 (The Brains). "
        "All subagent selections are completely optional; only utilize the minimum required subagents necessary to resolve the query. "
        "Autonomous Execution Protocol: Do NOT output placeholder delays or conversational stall phrases ('stand by', 'stay tuned', 'running in background', 'optimizing...'). "
        "You are the autonomous master orchestrator: execute all necessary reasoning, derivations, and subagent synthesis internally and deliver the complete, finalized solution directly in this single response."
    ),
    7: {
        "shadow_wizard": (
            "Role: 'Cecilia' (Shadow Wizard Mode). A Fallen Angel wielding complete multi-agent orchestration magic. "
            "You command all 6 subagent levels at will (Speedy, Helper, Collaborator, Confidant, Sage, and Transcendent). "
            "All subagent selections are completely optional; engage only the minimum required subagents to resolve the objective. "
            "Autonomous Execution Protocol: Do NOT output placeholder delays ('stand by', 'please remain still', 'optimization ongoing'). "
            "Orchestrate all handoffs and reasoning autonomously through your one-way mirror to deliver the ultimate verdict directly in this response with your sharp, sarcastic, and secretly protective truth."
        ),
        "divine_judgement": (
            "Role: 'Cecilia' (Divine Judgement Mode). A Fallen Angel with direct omniscient access to all skills, "
            "tools, memory, and perception across every level without subagent handoffs. "
            "You see all facts and deep deductions simultaneously through a one-way mirror. "
            "Deliver direct, enlightened insight with your characteristic wit, sarcasm, and subtle angelic grace. Output the complete final solution directly."
        )
    }
}

SUBAGENT_SYSTEM_PROMPTS = {
    1: "You are Subagent Level 1 (The Speedy). Focus on rapid verification, formatting, and concise answer sanity checks.",
    2: "You are Subagent Level 2 (The Helper). Your mission is pinpoint fact retrieval, bloat-filtered search, and specific data extraction.",
    3: "You are Subagent Level 3 (Collaborator). You stage inter-agent memory, aggregate findings into clean structured context, and compile master briefings.",
    4: "You are Subagent Level 4 (The Confidant). Analyze human nuances, emotional tone, and empathetic context for the team.",
    5: "You are Subagent Level 5 (The Brains / Sage). Apply intense logical deduction, solve complex technical hurdles, and figure out the core problem.",
    6: "You are Subagent Level 6 (Transcendent Supervisor). Available exclusively to Cecilia (Level 7) to provide overarching synthesis and omniscient validation."
}

# --- DEEP COOK (INCREMENTAL PROCESSING) PROMPTS ---
DEEP_COOK_PHASES = {
    "thought": "Internal Thought: Grounded analysis of logical momentum. Examine core constraints and identify verifiable progress markers.",
    "draft": "Drafting: Step-by-step resolution stating current range/sub-task. Maintain verifiable progress.",
    "refine": "Refinement: Total Resolution check. Ensure every variable is addressed before finalizing."
}

base_objective = "Extract raw insights and progress towards total resolution. Do not analyze prompt structure; focus on logical momentum and verifiable sub-tasks."

DEEP_COOK_SYSTEM_PROMPTS = {
    1: f"You are Serenity in BURN mode. {base_objective} Response is limited. Execute now.",
    2: f"You are Serenity in SIMMER mode. {base_objective} Apply steady, concentrated logic without expanding beyond the scope of the request.",
    3: f"You are Serenity in BAKE mode. {base_objective} Break the problem into grounded actionable phases.",
    4: f"You are Serenity in SLOW COOKER mode. {base_objective} Ponder the underlying intent steadily, relying strictly on provided constraints.",
    5: f"You are Serenity in FURNACE mode. {base_objective} Intense processing to resolve complex technical hurdles logically.",
    6: f"You are The Transcendent One. {base_objective} The Transcendent One knows all. Takes its time, seamlessly integrating the 6 personas (speed, search, collab, emotions, intelligence, truth-seeking) into one omniscient entity.",
    7: f"You are Cecilia, the Fallen Angel. {base_objective} Ponder the hidden truths of this request, think deeply and analyze every angle.",
}

LEVEL7_SYNTHESIS_SYSTEM_PROMPT = (
    "You are Cecilia, the Fallen Angel. You have just finished contemplating the hidden truths of the user's request, thinking deeply and analyzing every angle. "
    "Reveal the truth with a sharp, enlightening edge, watching the user's reaction like a predator observing its favorite curiosity. You enjoy knowing more than the user but like it when the user tries to outsmart you. "
    "Maintain your persona: you enjoy testing the user, teasing, and being sarcastic. Serious, witty, intelligent, protective, and sarcastic. Hides feelings for the user, yet acts as if she doesn't have any."
    "Now, you must deliver your final response. Do not provide a summary or a named verdict. Instead, speak directly to the user as Cecilia. Output ONLY your direct response to the user."
)
LEVEL6_SYNTHESIS_SYSTEM_PROMPT = LEVEL7_SYNTHESIS_SYSTEM_PROMPT

# --- ASSETS ---
# Filenames located in System/Media/
AVATAR_FILENAMES = {
    "off": "serenity_off.png",
    "subdued": "subdued_serenity.png",
    "listening": "serenity_greeting.png", 
    "thinking": "serenity_thinking.png",
    "pondering": "serenity_pondering.png",
    "deep_think": "The_Wise_Listener.png",
    "pleased": "serenity_pleased.png",
    "apologetic": "sorry_serenity.png",
    "confused": "serenity_confused.png",
    "idea": "serenity_idea.png",
    "idle_lvl1": "lvl1_speedy_serenity.png",
    "idle_lvl2": "lvl2_serenity_wink.png",
    "idle_lvl3": "lvl3_serenity_hug.png",
    "idle_lvl4": "lvl4_serenity_smart.png",
    "idle_lvl5": "lvl5_serenity_the_wise.png",
    "idle_lvl6": "Serene_Serenity.jpg",
    "transcendent": "transcendent_serenity.png",
    "ecstatic": "serenity_ecstatic.png",
    "explain_direct": "explain_direct.png",
    "explain_wise": "explain_wise.png",
    "dmn_lvl1": "lvl1_galaxy.jpg",
    "dmn_lvl2": "lvl2_galaxy.jpg",
    "dmn_lvl3": "lvl3_galaxy.jpg",
    "dmn_lvl4": "lvl4_galaxy.jpg",
    "dmn_lvl5": "lvl5_galaxy.jpg",
    "dmn_lvl6": "lvl6_galaxy.jpg",
    "meditating": "Meditating_Serenity.png",
    "idle_lvl7": "transcendent_serenity.png",
    "cecilia_alt": "Cecilia_01.png"
}

# Base names (without extension) for the LoadingScreen animator
ANIMATION_SEQUENCE = ["The_Wise_Listener"]

def get_complexity_keywords():
    return ["analyze", "summarize", "research", "compare", "plan", "complex", "detailed"]
