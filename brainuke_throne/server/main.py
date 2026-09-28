# brainuke_throne/server/main.py
# The Central Orchestrator for the Project Brainuke Throne.

import sys
from pathlib import Path

# Bootstrap sys.path to include Project Brainuke root
project_root = str(Path(__file__).resolve().parent.parent.parent)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

import asyncio
import json
import time
from typing import List, Optional
from fastapi import FastAPI, WebSocket, Request, HTTPException, BackgroundTasks
from fastapi.responses import StreamingResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from brainuke_core.affect.engine import BrainukeCore
from brainuke_core.security.key_vault import KeyVault
from brainuke_core.memory.vault import MemoryVault
from brainuke_core.cognition import (
    CognitiveOrchestrator,
    LlamaServerClient,
    DeepCook,
    SimmerBus,
    SubagentDispatcher,
    SubagentType,
    ModelRouter,
    PCRunnerManager,
    ErrorSentry,
    SelfHealingIDE
)
from brainuke_core.session import SessionManager
from brainuke_core.protocol import ProtocolEnvelope, PacketType, SessionHandoffPayload
from brainuke_throne.tls.provisioner import TLSProvisioner, CADownloaderServer

# Initialize the Throne
app = FastAPI(title="Brainuke Throne")

# Public /ui webview static mount removed to prevent unauthenticated browser access to localhost.
# UI is now hosted strictly inside desktop native Cecilia-UI.


# --- GLOBAL STATE ---
# In a real implementation, these would be managed by a dedicated State Manager
# but for our initial bootstrap, we keep them in memory.
config_path = Path(project_root) / "config" / "brainuke_config.json"
brainuke_core = BrainukeCore.from_config_file(str(config_path)) if config_path.exists() else BrainukeCore(baseline_mu={'v': 0.2, 'a': 0.0, 'd': 0.8})
memory_vault = MemoryVault()
session_manager = SessionManager(max_turn_window=20)
llama_client = LlamaServerClient(port=8081)
pc_runner_manager = PCRunnerManager()
orchestrator = CognitiveOrchestrator(core=brainuke_core, llm_provider=llama_client, memory_vault=memory_vault, runner_manager=pc_runner_manager)
subagent_dispatcher = SubagentDispatcher(vault=memory_vault, llm_provider=llama_client)
error_sentry = ErrorSentry.get_instance()
self_healing_ide = SelfHealingIDE(llm_client=llama_client, runner_manager=pc_runner_manager)
active_clients: List[asyncio.Queue] = [] # List of connected Android SSE queues

# Sync status tracking
last_sync_info: Dict[str, Any] = {
    "timestamp": None,
    "source": "none",
    "summary": "Never synced",
    "status": "idle"
}


async def broadcast_to_sse(event_type: str, content: str):
    """Dispatches an event to all connected Android SSE subscribers."""
    payload = json.dumps({"type": event_type, "content": content})
    for q in list(active_clients):
        await q.put(payload)

async def broadcast_status_event(event_type: str, data: Dict[str, Any]):
    """Dispatches a structured status/telemetry event to all connected SSE subscribers."""
    payload = json.dumps({"type": event_type, "data": data})
    for q in list(active_clients):
        await q.put(payload)

# Initialize DMN Shared Simmer Bus with DeepCook
deep_cook = DeepCook(llm_provider=llama_client, memory_vault=memory_vault)
simmer_bus = SimmerBus(
    vault=memory_vault,
    core=brainuke_core,
    deep_cook=deep_cook,
    idle_timeout_sec=300.0,
    broadcast_fn=broadcast_to_sse,
    status_fn=broadcast_status_event
)

def process_sensory_payload(payload: dict):
    """Non-blocking background ingest for high-rate audio and telemetry packets."""
    try:
        memory_vault.ingest_sensory_batch([payload], source="android_stream")
        simmer_bus.record_activity()
    except Exception as e:
        print(f"[Sensory Ingest Error]: {e}")

# --- CORE ENDPOINTS ---

def verify_machine_token(request: Request) -> str:
    """
    Hardware-bound machine token verification.
    Blocks unauthenticated browser/localhost navigation from accessing inner database.
    """
    token = None
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        token = auth_header.split(" ")[1]
    elif "token" in request.query_params:
        token = request.query_params["token"]

    if not token:
        raise HTTPException(
            status_code=401,
            detail="Unauthorized: Database & Throne API access restricted. Machine Token required."
        )
    if token != KeyVault.generate_token():
        raise HTTPException(status_code=403, detail="Invalid Machine Token")
    return token

# --- CORE ENDPOINTS ---

@app.get("/")
async def root(request: Request):
    accept = request.headers.get("accept", "")
    if "text/html" in accept:
        raise HTTPException(
            status_code=401,
            detail="Browser navigation to Throne inner database restricted. Use native Cecilia-UI."
        )
    return {"status": "Throne Online", "core_state": brainuke_core.get_status()}


@app.api_route("/api/v1/sensory/stream", methods=["GET", "POST"])
async def sensory_stream(request: Request, background_tasks: BackgroundTasks):
    """
    The 'Uplink' from Android. Receives telemetry and voice data.
    """
    # 1. Validate Auth Header (The Bearer Token from KeyVault)
    verify_machine_token(request)

    # 2. Process Incoming Stream
    payload = None
    if request.method == "POST":
        try:
            payload = await request.json()
            if payload:
                background_tasks.add_task(process_sensory_payload, payload)
        except Exception:
            pass
    return {"status": "Stream Received", "type": payload.get("type") if payload else "handshake"}

@app.get("/subscriptions/listen")
async def sse_listen(request: Request):
    """
    The 'Downlink' to Android & Desktop UI via Server-Sent Events (SSE).
    """
    verify_machine_token(request)
    client_queue = asyncio.Queue()
    active_clients.append(client_queue)

    async def event_generator():
        # This is the "Cognitive Bus"
        try:
            # Send initial handshake/heartbeat immediately
            yield f"data: {{\"type\": \"heartbeat\", \"state\": \"{brainuke_core.get_status()}\"}}\n\n"

            while True:
                if await request.is_disconnected():
                    break

                try:
                    event_data = await asyncio.wait_for(client_queue.get(), timeout=5.0)
                    yield f"data: {event_data}\n\n"
                except asyncio.TimeoutError:
                    yield f"data: {{\"type\": \"heartbeat\", \"state\": \"{brainuke_core.get_status()}\"}}\n\n"
        except Exception as e:
            print(f"SSE Error: {e}")
        finally:
            if client_queue in active_clients:
                active_clients.remove(client_queue)

    return StreamingResponse(event_generator(), media_type="text/event-stream")

@app.post("/api/v1/cognitive/broadcast")
async def broadcast_event(request: Request):
    """Broadcasts a thought or speech event to all connected SSE clients."""
    verify_machine_token(request)
    payload = await request.json()
    raw = json.dumps(payload)
    for q in list(active_clients):
        await q.put(raw)
    return {"status": "broadcast", "recipients": len(active_clients)}

@app.post("/api/v1/cognitive/interact")
async def cognitive_interact(request: Request):
    """
    Receives user query, orchestrates isolated reasoning and speech synthesis
    via PC llama-server, updates AffectState, records interaction in MemoryVault,
    and broadcasts thought/speech streams over SSE Downlink.
    """
    verify_machine_token(request)

    body = await request.json()
    user_input = body.get("text", "")
    context = body.get("context", [])

    if not user_input:
        raise HTTPException(status_code=400, detail="Missing 'text' field")

    simmer_bus.record_activity()

    async def _on_thought_chunk(chunk: str):
        await broadcast_to_sse("thought_chunk", chunk)

    async def _on_speech_chunk(chunk: str):
        await broadcast_to_sse("speech_chunk", chunk)

    result = await orchestrator.process_interaction(
        user_input=user_input,
        context=context,
        on_thought_chunk=_on_thought_chunk,
        on_speech_chunk=_on_speech_chunk
    )

    # Broadcast final full thought and speech over Downlink SSE
    await broadcast_to_sse("thought", result.thought_stream)
    await broadcast_to_sse("speech", result.final_response)

    if result.param_updates:
        status_data = pc_runner_manager.get_status(llama_client=llama_client)
        raw_status = json.dumps({"type": "model_status_update", "data": status_data})
        for q in list(active_clients):
            await q.put(raw_status)

    if user_input.strip().lower() in ("/reset", "reset"):
        session_manager.reset_active_session()

    # Record turn in MemoryVault and SessionManager
    affect_snapshot = {
        "valence": brainuke_core.state.valence,
        "arousal": brainuke_core.state.arousal,
        "dominance": brainuke_core.state.dominance
    }
    memory_vault.ingest_interaction(
        user_input=user_input,
        thought_stream=result.thought_stream,
        final_response=result.final_response,
        affect_state=affect_snapshot,
        source_device="pc",
        influence_weight=1.0
    )
    session_manager.record_turn(
        user_input=user_input,
        thought_stream=result.thought_stream,
        final_response=result.final_response,
        affect_state=affect_snapshot,
        source_device="pc"
    )

    return {
        "status": "success",
        "thought": result.thought_stream,
        "response": result.final_response,
        "affect_impulse": result.affect_impulse,
        "core_state": brainuke_core.get_status()
    }

@app.get("/api/v1/cognitive/status")
async def cognitive_status(request: Request):
    """
    Returns Throne inference availability, queue depth, runner latency,
    and offload recommendation for Android SerenityDroid.
    """
    verify_machine_token(request)

    runner_online = llama_client.is_healthy() if hasattr(llama_client, "is_healthy") else True
    grounding = memory_vault.get_recent_grounding(limit=20)
    return {
        "status": "online" if runner_online else "degraded",
        "offload_recommended": True,
        "core_state": brainuke_core.get_status(),
        "affect_vector": {
            "valence": brainuke_core.state.valence,
            "arousal": brainuke_core.state.arousal,
            "dominance": brainuke_core.state.dominance
        },
        "grounding_count": len(grounding),
        "active_subscribers": len(active_clients),
        "last_sync": last_sync_info.get("timestamp"),
        "sync_status": last_sync_info.get("status", "idle"),
        "last_sync_summary": last_sync_info.get("summary", "Never synced"),
        "is_simmering": simmer_bus.is_simmering,
        "last_simmer": int(simmer_bus.last_simmer_time * 1000) if getattr(simmer_bus, "last_simmer_time", None) else None,
        "timestamp": int(time.time() * 1000)
    }


# --- SECURE ZERO-TOUCH PAIRING & SESSION HANDOFF ---

@app.post("/api/v1/pairing/handshake")
async def pairing_handshake(request: Request):
    """
    Zero-touch mutual pairing handshake.
    Android device connects after trusting rootCA.pem; exchanges device metadata and receives auth token.
    """
    import time
    body = await request.json()
    device_id = body.get("device_id", "unknown_device")
    device_type = body.get("device_type", "android")

    token = KeyVault.generate_token()
    return {
        "status": "paired",
        "device_id": device_id,
        "device_type": device_type,
        "auth_token": token,
        "session_id": session_manager.session_id,
        "core_state": brainuke_core.get_status(),
        "timestamp": int(time.time() * 1000)
    }

@app.post("/api/v1/session/handoff")
async def session_handoff(request: Request):
    """
    Transfers conversational focus between PC Throne and SerenityDroid.
    Ensures zero-amnesia context window and affect state continuity.
    """
    verify_machine_token(request)

    body = await request.json()
    target_device = body.get("target_device", "android")
    source_device = body.get("source_device", "pc")

    affect_dict = {
        "valence": brainuke_core.state.valence,
        "arousal": brainuke_core.state.arousal,
        "dominance": brainuke_core.state.dominance
    }

    handoff = session_manager.execute_handoff(
        target_device=target_device,
        source_device=source_device,
        affect_state=affect_dict
    )

    # Broadcast handoff event across SSE Downlink
    await broadcast_to_sse("handoff", json.dumps(handoff.to_dict()))

    return {
        "status": "handoff_completed",
        "handoff": handoff.to_dict(),
        "core_state": brainuke_core.get_status()
    }

@app.get("/api/v1/session/active")
async def session_active(request: Request):
    """
    Returns active session window and affect state for target device resume.
    """
    verify_machine_token(request)

    affect_dict = {
        "valence": brainuke_core.state.valence,
        "arousal": brainuke_core.state.arousal,
        "dominance": brainuke_core.state.dominance
    }
    session = session_manager.get_active_session(affect_state=affect_dict)
    return {
        "status": "ok",
        "session": session.to_dict(),
        "core_state": brainuke_core.get_status()
    }


# --- DATASYNC & DMN SHARED POOL ENDPOINTS ---

@app.post("/api/v1/sync/push")
async def sync_push(request: Request):
    """
    Android Sync Push endpoint:
    Receives buffered telemetry and interaction batch from SerenityDroid.
    Queues them in the PC pool host for future DMN simmer cycle.
    """
    verify_machine_token(request)

    body = await request.json()
    items = body.get("items", [])
    count = memory_vault.ingest_sensory_batch(items, source="android_sync_push")

    # Ingest conversation turns if present with mobile weight 0.35
    conversation_turns = body.get("conversation_turns", [])
    if conversation_turns:
        session_manager.ingest_external_turns(conversation_turns)
        for turn in conversation_turns:
            memory_vault.ingest_interaction(
                user_input=turn.get("user_input", ""),
                thought_stream=turn.get("thought_stream", ""),
                final_response=turn.get("final_response", ""),
                affect_state=turn.get("affect_state", {}),
                source_device="android",
                influence_weight=0.35
            )

    simmer_bus.record_activity()
    now_ms = int(time.time() * 1000)
    last_sync_info["timestamp"] = now_ms
    last_sync_info["source"] = "android"
    last_sync_info["summary"] = f"Pushed {count} sensory & {len(conversation_turns)} turns"
    last_sync_info["status"] = "idle"

    raw_sync = json.dumps({"type": "sync_update", "data": last_sync_info})
    for q in list(active_clients):
        await q.put(raw_sync)

    return {
        "status": "queued",
        "count": count,
        "conversation_count": len(conversation_turns),
        "last_sync": now_ms,
        "core_state": brainuke_core.get_status()
    }

@app.get("/api/v1/sync/pull")
async def sync_pull(request: Request, since: int = 0):
    """
    Android Sync Pull endpoint:
    Returns distilled memory nodes and world updates created since given timestamp.
    """
    verify_machine_token(request)

    delta_pack = memory_vault.get_delta_pack(since_timestamp=since)
    now_ms = int(time.time() * 1000)
    last_sync_info["timestamp"] = now_ms
    last_sync_info["source"] = "android"
    last_sync_info["status"] = "idle"
    return {
        "status": "ok",
        "since": since,
        "delta_pack": delta_pack,
        "last_sync": now_ms,
        "core_state": brainuke_core.get_status()
    }

@app.post("/api/v1/sync/simmer")
async def sync_simmer(request: Request):
    """
    Manually triggers or tests a DMN simmer cycle.
    Distills unsimmered interactions and sensory logs, broadcasting [DMN Insight].
    Runs asynchronously to prevent client read timeouts during heavy LLM distillation.
    """
    verify_machine_token(request)

    if simmer_bus.is_simmering:
        return {
            "status": "simmered",
            "in_progress": True,
            "message": "DMN Simmer already in progress",
            "core_state": brainuke_core.get_status()
        }

    async def _bg_simmer():
        try:
            res = await simmer_bus.trigger_simmer_cycle(forced=True)
            notice_text = "DMN Simmer: Mind consolidated."
            if res and res.get("distilled_insight"):
                notice_text = f"DMN Simmer: {res['distilled_insight'][:80]}..."
            await broadcast_to_sse("notice", notice_text)
        except Exception as e:
            await broadcast_to_sse("notice", f"DMN Simmer error: {e}")

    asyncio.create_task(_bg_simmer())

    return {
        "status": "simmered",
        "in_progress": True,
        "message": "DMN Simmer cycle initiated",
        "core_state": brainuke_core.get_status()
    }

@app.post("/api/v1/sync/trigger")
async def sync_trigger(request: Request):
    """
    PC-initiated synchronization:
    1. Broadcasts sync_request event to Android clients over SSE Downlink.
    2. Launches DMN simmer consolidation in background.
    3. Updates last_sync status and broadcasts sync_update.
    """
    verify_machine_token(request)

    now_ms = int(time.time() * 1000)
    last_sync_info["source"] = "pc"
    last_sync_info["status"] = "in_progress"
    last_sync_info["summary"] = "PC-triggered sync in progress"

    # Broadcast sync request event over SSE Downlink to Android
    sync_req_payload = json.dumps({"type": "sync_request", "source": "pc", "timestamp": now_ms})
    for q in list(active_clients):
        await q.put(sync_req_payload)

    # Broadcast in-progress sync update
    prog_payload = json.dumps({"type": "sync_update", "data": {"status": "in_progress", "source": "pc"}})
    for q in list(active_clients):
        await q.put(prog_payload)

    async def _bg_sync():
        try:
            await simmer_bus.trigger_simmer_cycle(forced=False)
        finally:
            finished_ms = int(time.time() * 1000)
            last_sync_info["status"] = "idle"
            last_sync_info["timestamp"] = finished_ms
            last_sync_info["summary"] = "PC Throne and Android companion aligned"
            done_payload = json.dumps({
                "type": "sync_update",
                "data": {
                    "status": "idle",
                    "timestamp": finished_ms,
                    "last_sync": finished_ms,
                    "source": "pc"
                }
            })
            for q in list(active_clients):
                await q.put(done_payload)

    asyncio.create_task(_bg_sync())

    return {
        "status": "sync_triggered",
        "last_sync": last_sync_info.get("timestamp") or now_ms,
        "source": "pc",
        "in_progress": True,
        "core_state": brainuke_core.get_status()
    }

@app.get("/api/v1/sync/status")
async def sync_status_endpoint(request: Request):
    """Returns current synchronization status and last sync timestamp."""
    verify_machine_token(request)
    return {
        "status": "ok",
        "sync_status": last_sync_info.get("status", "idle"),
        "last_sync": last_sync_info.get("timestamp"),
        "source": last_sync_info.get("source"),
        "summary": last_sync_info.get("summary"),
        "is_simmering": simmer_bus.is_simmering,
        "last_simmer": int(simmer_bus.last_simmer_time * 1000) if getattr(simmer_bus, "last_simmer_time", None) else None,
        "core_state": brainuke_core.get_status()
    }

@app.get("/api/v1/history")
async def get_history_feed(request: Request, limit: int = 50, filter: str = "all"):
    """
    Retrieves chronological conversation history and DMN refined insights.
    Surfaces hierarchical weighting: PC Master Core (1.0) >> Android Companion (0.35) >> Telemetry Oracle (0.2).
    Supported filters: 'all', 'pc', 'android', 'dmn'.
    """
    verify_machine_token(request)

    interactions = []
    dmn_insights = []

    if filter == "pc":
        interactions = memory_vault.get_recent_interactions(limit=limit, source_device="pc")
    elif filter == "android":
        interactions = memory_vault.get_recent_interactions(limit=limit, source_device="android")
    elif filter == "all":
        interactions = memory_vault.get_recent_interactions(limit=limit)

    if filter in ("all", "dmn"):
        dmn_insights = memory_vault.get_distilled_insights(limit=limit)

    return {
        "status": "ok",
        "filter": filter,
        "weights": {
            "pc_master": 1.0,
            "android_companion": 0.35,
            "telemetry_oracle": 0.2
        },
        "interactions": interactions,
        "dmn_insights": dmn_insights,
        "total_interactions": len(interactions),
        "total_dmn": len(dmn_insights),
        "timestamp": int(time.time() * 1000)
    }

# --- PHASE III: SENSORY WORLD PERCEPTION ---

@app.post("/api/v1/sensory/frame")
async def sensory_frame(request: Request, background_tasks: BackgroundTasks):
    """
    Receives visual perception snapshot / camera frame from Android or Desktop.
    Ingests into sensory pool to ground Cecilia's active situational awareness.
    """
    verify_machine_token(request)

    body = await request.json()
    observation = body.get("observation", "Camera visual frame snapshot")
    frame_type = body.get("type", "visual_frame")
    
    memory_vault.ingest_sensory_batch([{
        "type": frame_type,
        "observation": observation,
        "timestamp": body.get("timestamp", int(time.time() * 1000))
    }], source="camera_stream")
    simmer_bus.record_activity()
    return {"status": "frame_ingested", "timestamp": int(time.time() * 1000)}

# --- PHASE IV: THE SOCIAL LAYER & CONTEXTUAL SANDBOX ---

@app.get("/api/v1/messageboard/concepts")
async def list_concept_families(request: Request):
    """Returns emerging concept taxonomy and discussion statistics."""
    verify_machine_token(request)
    summary = memory_vault.get_concept_family_summary()
    return {"status": "ok", "concepts": summary}

@app.get("/api/v1/messageboard/threads")
async def list_threads(request: Request, concept_family: Optional[str] = None):
    """Retrieves discussion threads grouped by concept family."""
    verify_machine_token(request)
    threads = memory_vault.get_threads(concept_family=concept_family)
    return {"status": "ok", "threads": threads}

@app.post("/api/v1/messageboard/threads")
async def create_thread(request: Request):
    """Initializes a new concept discussion thread with auto-taxonomy tagging."""
    verify_machine_token(request)

    body = await request.json()
    title = body.get("title")
    concept_family = body.get("concept_family")
    creator_id = body.get("creator_id", "human_user")

    if not title:
        raise HTTPException(status_code=400, detail="Missing thread 'title'")

    if not concept_family or concept_family == "general":
        concept_family = memory_vault.suggest_concept_family(title)

    thread_id = memory_vault.create_thread(title, concept_family, creator_id)
    return {"status": "created", "thread_id": thread_id, "title": title, "concept_family": concept_family}

@app.get("/api/v1/messageboard/threads/{thread_id}/posts")
async def get_thread_posts(thread_id: int, request: Request):
    """Retrieves admitted posts for a specific discussion thread."""
    verify_machine_token(request)
    posts = memory_vault.get_thread_posts(thread_id)
    return {"status": "ok", "thread_id": thread_id, "posts": posts}

@app.post("/api/v1/messageboard/threads/{thread_id}/posts")
async def post_to_thread(thread_id: int, request: Request):
    """
    Submits a post to a messageboard thread.
    Contextual Sandbox Gate:
    Evaluates intent and manipulation risk.
    If risk < 0.4: automatically admits post to thread.
    If risk >= 0.4: holds in Quarantine Sandbox for moderation / DeepCook review.
    """
    verify_machine_token(request)

    body = await request.json()
    content = body.get("content", "").strip()
    author_id = body.get("author_id", "external_actor")
    author_name = body.get("author_name", "Guest")
    author_type = body.get("author_type", "human")

    if not content:
        raise HTTPException(status_code=400, detail="Missing 'content'")

    # Run Intent & Risk evaluation
    intent_label, risk_score = orchestrator._evaluate_intent_and_risk(content)
    
    # Store in Quarantine Sandbox initially
    sandbox_id = memory_vault.quarantine_post(
        thread_id=thread_id,
        author_id=author_id,
        author_name=author_name,
        author_type=author_type,
        content=content,
        intent_label=intent_label,
        risk_score=risk_score
    )

    if risk_score < 0.4:
        # Safe -> Auto-admit
        post_id = memory_vault.resolve_quarantine_post(sandbox_id, action="admit")
        return {
            "status": "admitted",
            "post_id": post_id,
            "thread_id": thread_id,
            "intent": intent_label,
            "risk_score": risk_score
        }
    else:
        # Flagged -> Quarantined
        return {
            "status": "quarantined",
            "sandbox_id": sandbox_id,
            "thread_id": thread_id,
            "intent": intent_label,
            "risk_score": risk_score,
            "message": "Held in Contextual Sandbox: manipulation/risk detected."
        }

@app.get("/api/v1/messageboard/quarantine")
async def list_quarantined_posts(request: Request):
    """Inspects posts currently held in Contextual Sandbox quarantine."""
    verify_machine_token(request)

    posts = memory_vault.get_quarantined_posts()
    return {"status": "ok", "quarantined_posts": posts}

@app.post("/api/v1/messageboard/quarantine/{post_id}/resolve")
async def resolve_quarantine(post_id: int, request: Request):
    """Moderation action: admits or rejects a quarantined post."""
    verify_machine_token(request)

    body = await request.json()
    action = body.get("action", "admit") # 'admit' or 'reject'
    reason = body.get("reason", "")

    result = memory_vault.resolve_quarantine_post(post_id, action=action, reason=reason)
    return {"status": "resolved", "action": action, "result": result}

@app.get("/api/v1/messageboard/agents")
async def list_agents(request: Request):
    """Returns registered agent identities."""
    verify_machine_token(request)
    agents = memory_vault.get_agent_profiles()
    return {"status": "ok", "agents": agents}

@app.post("/api/v1/messageboard/agents")
async def register_agent(request: Request):
    """Registers a new agent profile into the identity layer."""
    verify_machine_token(request)

    body = await request.json()
    agent_id = body.get("agent_id")
    name = body.get("name")
    temperament = body.get("temperament", "Analytical")
    stance = body.get("stance", "Neutral")

    if not agent_id or not name:
        raise HTTPException(status_code=400, detail="Missing 'agent_id' or 'name'")

    memory_vault.register_agent_profile(agent_id, name, temperament, stance)
    return {"status": "registered", "agent_id": agent_id, "name": name}


# --- PC MODEL MANAGEMENT & RUNNER CONTROL ---

@app.get("/api/v1/models/status")
async def get_models_status(request: Request):
    """Returns PC model loaded status, active model, and inference settings."""
    verify_machine_token(request)
    return pc_runner_manager.get_status(llama_client=llama_client)

@app.post("/api/v1/models/select")
async def select_model_endpoint(request: Request):
    """Switches active model between Normal (Supervisor) and Secret (Heretic)."""
    verify_machine_token(request)
    body = await request.json()
    model_key = body.get("model", "normal")
    res = pc_runner_manager.select_model(model_key)
    return res

@app.post("/api/v1/models/load")
async def load_model_endpoint(request: Request):
    """Initiates model load/runner launch on PC port 8081."""
    verify_machine_token(request)
    body = {}
    try:
        body = await request.json()
    except Exception:
        pass
    model_key = body.get("model")
    res = pc_runner_manager.initiate_load(model_key)
    return res

@app.post("/api/v1/models/settings")
async def update_model_settings_endpoint(request: Request):
    """Updates basic inference parameters in models.json."""
    verify_machine_token(request)
    body = await request.json()
    res = pc_runner_manager.update_inference_settings(body)
    return res

@app.post("/api/v1/models/reset")
async def reset_model_endpoint(request: Request):
    """
    Erases active KV cache slot on port 8081 while preserving context window buffer,
    and resets active conversation turn context.
    """
    verify_machine_token(request)
    res = pc_runner_manager.reset_model_slot(llama_client=llama_client)
    session_manager.reset_active_session()
    await broadcast_to_sse("notice", res.get("note", "Model slot reset. Context window intact."))
    return res


# --- CECILIA RECURSIVE SELF-HEALING STUDIO & DEBUG ---

@app.get("/api/v1/self_heal/status")
async def get_self_heal_status(request: Request):
    """Returns self-healing toggleable settings, green light indicators, and flagged errors."""
    verify_machine_token(request)
    settings = self_healing_ide.load_settings()
    green, indicators = self_healing_ide.check_green_lights()
    errors = error_sentry.get_errors()
    return {
        "status": "ok",
        "settings": settings,
        "indicators": indicators,
        "errors": errors,
        "error_count": len(errors)
    }

@app.post("/api/v1/self_heal/settings")
async def update_self_heal_settings(request: Request):
    """Updates self-healing toggleable settings in self_healing.json."""
    verify_machine_token(request)
    body = await request.json()
    updated = self_healing_ide.save_settings(body)
    return {"status": "updated", "settings": updated}

@app.post("/api/v1/self_heal/diagnose")
async def trigger_self_heal_diagnose(request: Request):
    """Manually initiates diagnosis and self-healing for an error (debug fallback)."""
    verify_machine_token(request)
    body = {}
    try:
        body = await request.json()
    except Exception:
        pass

    error_id = body.get("error_id")
    diag = None
    if error_id:
        diag = error_sentry.get_error_by_id(error_id)
    elif "message" in body:
        diag = error_sentry.flag_manual_error(
            message=body.get("message", "Manual debug request"),
            traceback_str=body.get("traceback", "")
        )

    res = await self_healing_ide.diagnose_and_heal(diag, force=True)
    return res

@app.post("/api/v1/self_heal/apply")
async def apply_self_heal_patch(request: Request):
    """Applies a verified staged patch to the live workspace file."""
    verify_machine_token(request)
    body = await request.json()
    error_id = body.get("error_id")
    if not error_id:
        raise HTTPException(status_code=400, detail="Missing 'error_id'")
    res = self_healing_ide.apply_staged_patch(error_id)
    if res.get("status") == "applied":
        await broadcast_to_sse("notice", f"Self-Heal Patch applied: {res.get('target_file')}")
    return res

@app.get("/api/v1/self_heal/patch/{error_id}")
async def get_staged_patch(request: Request, error_id: str):
    """Returns staged patch diff for human review."""
    verify_machine_token(request)
    diag = error_sentry.get_error_by_id(error_id)
    if not diag or not diag.patch_diff:
        raise HTTPException(status_code=404, detail="No staged patch found for this error")
    return {
        "status": "ok",
        "error_id": error_id,
        "target_file": diag.target_file,
        "patch_diff": diag.patch_diff,
        "attempts": diag.attempts
    }


# --- PHASE IV.3: AUTONOMY & AGENCY (SUBAGENT DISPATCH & MODEL SELECTION) ---

@app.get("/api/v1/subagents/models")
async def list_available_models(request: Request):
    """Returns available models and active dynamic routing rules."""
    verify_machine_token(request)
    return {
        "status": "ok",
        "models": {
            "supervisor": ModelRouter.MODEL_SUPERVISOR,
            "heretic": ModelRouter.MODEL_HERETIC,
            "edge_reflex": ModelRouter.MODEL_EDGE_REFLEX
        },
        "subagent_types": [e.value for e in SubagentType]
    }

@app.get("/api/v1/subagents/tasks")
async def list_subagent_tasks(request: Request, status: Optional[str] = None):
    """Lists tracked autonomous subagent tasks."""
    verify_machine_token(request)
    tasks = subagent_dispatcher.get_tasks(status=status)
    return {"status": "ok", "tasks": tasks, "count": len(tasks)}

@app.post("/api/v1/subagents/dispatch")
async def dispatch_subagent_task(request: Request):
    """
    Autonomously launches a background subagent task.
    Selects model according to task demands and complexity.
    """
    verify_machine_token(request)

    body = await request.json()
    task_type_str = body.get("subagent_type", "analytical_scout")
    objective = body.get("objective", "").strip()
    target_model = body.get("target_model")
    complexity = float(body.get("complexity", 0.5))

    if not objective:
        raise HTTPException(status_code=400, detail="Missing subagent 'objective'")

    try:
        subagent_type = SubagentType(task_type_str)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid subagent_type: {task_type_str}")

    task = await subagent_dispatcher.dispatch(
        subagent_type=subagent_type,
        objective=objective,
        target_model=target_model,
        complexity=complexity
    )

    return {
        "status": "dispatched",
        "task_id": task.task_id,
        "subagent_type": task.subagent_type.value,
        "target_model": task.target_model,
        "objective": task.objective
    }



# --- RUNTIME ORCHESTRATION ---

async def run_throne():
    """
    Orchestrates the startup of the various sub-systems.
    """
    print("[Throne] Initializing Cryptographic Foundation, Firewall & ADB Reverse Tethering...")
    TLSProvisioner.ensure_root_ca_and_cert()
    TLSProvisioner.ensure_firewall_rules()
    if TLSProvisioner.ensure_adb_reverse():
        print("[Throne] ADB reverse tethering active (ports 8443, 8080, 8081).")
    else:
        print("[Throne] ADB reverse: no USB device attached or ADB offline (Wi-Fi LAN active).")
    
    print("[Throne] Starting Discovery Server (Port 8080)...")
    CADownloaderServer.start("rootCA.pem", 8080)

    print("[Throne] Starting DMN Shared Simmer Bus...")
    asyncio.create_task(simmer_bus.start_simmer_loop())

    print("[Throne] Starting Throne MCP/SSE Server (Port 8443)...")
    # Run the FastAPI app using uvicorn on port 8443
    import uvicorn
    config = uvicorn.Config(app, host="0.0.0.0", port=8443, ssl_keyfile="cert.key", ssl_certfile="cert.pem")
    server = uvicorn.Server(config)
    await server.serve()

if __name__ == "__main__":
    asyncio.run(run_throne())