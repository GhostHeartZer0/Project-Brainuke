"""
Integration Test Suite: Project Brainuke Throne <-> SerenityDroid Extension
Verifies:
1. Port 8080 Discovery / Root CA download.
2. Port 8443 HTTPS mutual verification using custom Root CA (simulating Android X509TrustManager).
3. Machine-bound Token Auth (Bearer Token via KeyVault).
4. Sensory Uplink (POST Telemetry, Audio, Vision).
5. Cognitive Downlink (SSE Event Stream with Thought Isolation).
"""

import os
import sys
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import time
import json
import ssl
import threading
import urllib.request
import urllib.error
import uvicorn

from brainuke_core.security.key_vault import KeyVault
from brainuke_throne.tls.provisioner import TLSProvisioner, CADownloaderServer
from brainuke_throne.server.main import app, brainuke_core


class ServerThread(threading.Thread):
    def __init__(self, host="127.0.0.1", port=8443, ssl_cert="cert.pem", ssl_key="cert.key"):
        super().__init__(daemon=True)
        self.host = host
        self.port = port
        self.ssl_cert = ssl_cert
        self.ssl_key = ssl_key
        config = uvicorn.Config(
            app,
            host=self.host,
            port=self.port,
            ssl_certfile=self.ssl_cert,
            ssl_keyfile=self.ssl_key,
            log_level="warning"
        )
        self.server = uvicorn.Server(config)

    def run(self):
        self.server.run()

    def stop(self):
        self.server.should_exit = True


def run_integration_tests():
    print("[1/5] Provisioning TLS Certificates...")
    ca_cert, leaf_cert, leaf_key = TLSProvisioner.ensure_root_ca_and_cert(
        ca_cert_path="rootCA.pem",
        ca_key_path="rootCA.key",
        cert_path="cert.pem",
        key_path="cert.key"
    )
    assert os.path.exists(ca_cert), "rootCA.pem missing"
    assert os.path.exists(leaf_cert), "cert.pem missing"
    assert os.path.exists(leaf_key), "cert.key missing"
    print("  -> Root CA and Leaf Certs verified.")

    print("[2/5] Starting Discovery Server (Port 8080)...")
    ca_server = CADownloaderServer.start("rootCA.pem", port=8080)
    time.sleep(0.5)

    # Test downloading Root CA from Port 8080
    with urllib.request.urlopen("http://127.0.0.1:8080/rootCA.pem", timeout=5) as resp:
        assert resp.status == 200, f"Expected 200 from CA server, got {resp.status}"
        ca_bytes = resp.read()
        assert b"BEGIN CERTIFICATE" in ca_bytes, "Downloaded CA is not valid PEM"
    print("  -> Port 8080 Discovery Server serving Root CA verified.")

    print("[3/5] Starting Throne Server (Port 8443 HTTPS)...")
    server_thread = ServerThread(host="127.0.0.1", port=8443, ssl_cert=leaf_cert, ssl_key=leaf_key)
    server_thread.start()

    # Wait for server startup
    ssl_context = ssl.create_default_context(cafile=ca_cert)
    # Allow hostname 127.0.0.1 which is in SAN list
    connected = False
    for _ in range(25):
        try:
            req = urllib.request.Request("https://127.0.0.1:8443/")
            with urllib.request.urlopen(req, context=ssl_context, timeout=2) as resp:
                if resp.status == 200:
                    connected = True
                    break
        except Exception:
            time.sleep(0.2)
    assert connected, "Throne HTTPS server failed to respond on port 8443"
    print("  -> Throne HTTPS online and verified with custom Root CA context.")

    print("[4/5] Testing Sensory Uplink & Security (Port 8443)...")
    token = KeyVault.generate_token()

    # 4a. Auth rejection without token on API
    req_no_auth = urllib.request.Request("https://127.0.0.1:8443/api/v1/sensory/stream")
    try:
        urllib.request.urlopen(req_no_auth, context=ssl_context, timeout=3)
        assert False, "Should fail without auth"
    except urllib.error.HTTPError as e:
        assert e.code == 401, f"Expected 401, got {e.code}"
    print("  -> 401 Unauthorized check passed.")

    # 4a-1. Inner database rejection: raw browser navigation to localhost /
    req_browser_root = urllib.request.Request(
        "https://127.0.0.1:8443/",
        headers={"Accept": "text/html,application/xhtml+xml,application/xml;q=0.9"}
    )
    try:
        urllib.request.urlopen(req_browser_root, context=ssl_context, timeout=3)
        assert False, "Browser navigation to localhost root should be blocked"
    except urllib.error.HTTPError as e:
        assert e.code == 401, f"Expected 401 on browser localhost access, got {e.code}"
    print("  -> Raw browser localhost navigation blocked (401).")

    # 4a-2. Inner database rejection: unauthenticated messageboard threads access
    req_db_no_auth = urllib.request.Request("https://127.0.0.1:8443/api/v1/messageboard/threads")
    try:
        urllib.request.urlopen(req_db_no_auth, context=ssl_context, timeout=3)
        assert False, "Inner DB access should fail without machine token"
    except urllib.error.HTTPError as e:
        assert e.code == 401, f"Expected 401 for inner database, got {e.code}"
    print("  -> Inner database access blocked without machine token (401).")

    # 4a-3. Authenticated inner database access
    req_db_auth = urllib.request.Request(
        "https://127.0.0.1:8443/api/v1/messageboard/threads",
        headers={"Authorization": f"Bearer {token}"}
    )
    with urllib.request.urlopen(req_db_auth, context=ssl_context, timeout=3) as resp:
        assert resp.status == 200
        body = json.loads(resp.read().decode())
        assert body.get("status") == "ok"
    print("  -> Authenticated inner database access verified.")

    # 4b. Auth rejection with invalid token
    req_bad_auth = urllib.request.Request(
        "https://127.0.0.1:8443/api/v1/sensory/stream",
        headers={"Authorization": "Bearer invalid_token_12345"}
    )
    try:
        urllib.request.urlopen(req_bad_auth, context=ssl_context, timeout=3)
        assert False, "Should fail with bad token"
    except urllib.error.HTTPError as e:
        assert e.code == 403, f"Expected 403, got {e.code}"
    print("  -> 403 Forbidden check passed.")

    # 4c. Valid Auth Handshake (GET)
    req_auth = urllib.request.Request(
        "https://127.0.0.1:8443/api/v1/sensory/stream",
        headers={"Authorization": f"Bearer {token}"}
    )
    with urllib.request.urlopen(req_auth, context=ssl_context, timeout=3) as resp:
        assert resp.status == 200
        body = json.loads(resp.read().decode())
        assert body.get("status") == "Stream Received"
    print("  -> Valid Bearer Token handshake passed.")

    # 4d. POST Telemetry Payload
    telemetry_data = json.dumps({
        "type": "telemetry",
        "battery_pct": 82,
        "is_charging": True,
        "network_type": "WIFI",
        "light_lux": 240.5,
        "proximity_cm": 5.0
    }).encode("utf-8")
    req_telemetry = urllib.request.Request(
        "https://127.0.0.1:8443/api/v1/sensory/stream",
        data=telemetry_data,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req_telemetry, context=ssl_context, timeout=3) as resp:
        assert resp.status == 200
        body = json.loads(resp.read().decode())
        assert body.get("type") == "telemetry"
    print("  -> Uplink: Telemetry payload accepted.")

    # 4e. POST Audio Chunk Payload
    audio_data = json.dumps({
        "type": "audio_chunk",
        "pcm_base64": "AP8A/wD/AP8A/w==",
        "sample_rate": 16000,
        "channels": 1,
        "bit_depth": 16,
        "rms_energy": 412.0
    }).encode("utf-8")
    req_audio = urllib.request.Request(
        "https://127.0.0.1:8443/api/v1/sensory/stream",
        data=audio_data,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req_audio, context=ssl_context, timeout=3) as resp:
        assert resp.status == 200
        body = json.loads(resp.read().decode())
        assert body.get("type") == "audio_chunk"
    print("  -> Uplink: Audio chunk payload accepted.")

    print("[5/5] Testing Downlink SSE & Thought Isolation...")
    sse_events = []
    sse_active = True

    def sse_reader():
        req_sse = urllib.request.Request(
            "https://127.0.0.1:8443/subscriptions/listen",
            headers={"Accept": "text/event-stream", "Authorization": f"Bearer {token}"}
        )
        try:
            with urllib.request.urlopen(req_sse, context=ssl_context, timeout=10) as sse_resp:
                for line in sse_resp:
                    if not sse_active:
                        break
                    line_str = line.decode().strip()
                    if line_str.startswith("data:"):
                        raw_data = line_str[5:].strip()
                        if raw_data:
                            try:
                                sse_events.append(json.loads(raw_data))
                            except Exception:
                                pass
        except Exception:
            pass

    sse_thread = threading.Thread(target=sse_reader, daemon=True)
    sse_thread.start()

    # Wait for initial heartbeat
    time.sleep(1.0)
    assert len(sse_events) > 0, "No heartbeat received on SSE stream"
    assert sse_events[0].get("type") == "heartbeat"
    print("  -> Downlink SSE connected; heartbeat received.")

    # Trigger dummy ThoughtEvent from PC
    thought_payload = json.dumps({
        "type": "thought",
        "content": "Cecilia internal reasoning: isolating cognition from spoken voice."
    }).encode("utf-8")
    req_broadcast_thought = urllib.request.Request(
        "https://127.0.0.1:8443/api/v1/cognitive/broadcast",
        data=thought_payload,
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {token}"}
    )
    with urllib.request.urlopen(req_broadcast_thought, context=ssl_context, timeout=3) as resp:
        assert resp.status == 200

    # Trigger dummy SpeechEvent from PC
    speech_payload = json.dumps({
        "type": "speech",
        "content": "SerenityDroid telemetry acknowledged. Uplink active."
    }).encode("utf-8")
    req_broadcast_speech = urllib.request.Request(
        "https://127.0.0.1:8443/api/v1/cognitive/broadcast",
        data=speech_payload,
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {token}"}
    )
    with urllib.request.urlopen(req_broadcast_speech, context=ssl_context, timeout=3) as resp:
        assert resp.status == 200

    # Wait for events to arrive at SSE client
    time.sleep(1.0)

    types = [e.get("type") for e in sse_events]
    assert "thought" in types, "ThoughtEvent not received on SSE downlink"
    assert "speech" in types, "SpeechEvent not received on SSE downlink"

    # Verify content separation
    thought_event = next(e for e in sse_events if e.get("type") == "thought")
    speech_event = next(e for e in sse_events if e.get("type") == "speech")

    assert "isolating cognition" in thought_event["content"]
    assert "telemetry acknowledged" in speech_event["content"]
    assert thought_event["content"] != speech_event["content"]

    print(f"  -> Thought Event Received: {thought_event}")
    print(f"  -> Speech Event Received: {speech_event}")
    print("  -> Thought and Speech streams strictly isolated!")

    print("[6/6] Testing DMN Simmer Bus & Bidirectional DataSync...")
    # 6a. Push telemetry batch to PC Throne Memory Vault
    sync_push_data = json.dumps({
        "items": [
            {
                "type": "telemetry",
                "battery_pct": 79,
                "is_charging": False,
                "network_type": "WIFI",
                "light_lux": 150.0,
                "proximity_cm": 2.0,
                "timestamp": int(time.time() * 1000)
            }
        ]
    }).encode("utf-8")
    req_sync_push = urllib.request.Request(
        "https://127.0.0.1:8443/api/v1/sync/push",
        data=sync_push_data,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req_sync_push, context=ssl_context, timeout=3) as resp:
        assert resp.status == 200
        push_body = json.loads(resp.read().decode())
        assert push_body.get("status") == "queued"
        assert push_body.get("count") >= 1
    print("  -> DataSync: Push telemetry batch queued in Throne Memory Vault.")

    # 6b. Trigger Simmer Cycle on SimmerBus
    req_simmer = urllib.request.Request(
        "https://127.0.0.1:8443/api/v1/sync/simmer",
        data=b"{}",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req_simmer, context=ssl_context, timeout=3) as resp:
        assert resp.status == 200
        simmer_body = json.loads(resp.read().decode())
        assert simmer_body.get("status") == "simmered"
    print("  -> Simmer Bus: Consolidation cycle executed.")

    # 6c. Verify [DMN Insight] arrived via SSE downlink strictly on 'thought' channel
    time.sleep(1.0)
    sse_active = False

    dmn_insights = [
        e for e in sse_events
        if e.get("type") == "thought" and "[DMN Insight]" in e.get("content", "")
    ]
    assert len(dmn_insights) > 0, "DMN Insight not received on SSE thought stream"
    print(f"  -> DMN Insight Verified on SSE Downlink: {dmn_insights[0]['content']}")

    # 6d. Pull Delta Pack from Memory Vault
    req_sync_pull = urllib.request.Request(
        "https://127.0.0.1:8443/api/v1/sync/pull?since=0",
        headers={"Authorization": f"Bearer {token}"}
    )
    with urllib.request.urlopen(req_sync_pull, context=ssl_context, timeout=3) as resp:
        assert resp.status == 200
        pull_body = json.loads(resp.read().decode())
        assert pull_body.get("status") == "ok"
        assert len(pull_body.get("delta_pack", [])) > 0
    print(f"  -> DataSync: Pull verified ({len(pull_body['delta_pack'])} memory nodes retrieved).")

    # Stage 7: Test Cognitive Interact (PC LLM & Affect Engine)
    print("[7/7] Testing Cognitive Interact & Affect Loop...")
    interact_payload = json.dumps({"text": "System status check."}).encode()
    req_interact = urllib.request.Request(
        "https://127.0.0.1:8443/api/v1/cognitive/interact",
        data=interact_payload,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }
    )
    with urllib.request.urlopen(req_interact, context=ssl_context, timeout=5) as resp:
        assert resp.status == 200
        interact_body = json.loads(resp.read().decode())
        assert interact_body.get("status") == "success"
        assert "thought" in interact_body
        assert "response" in interact_body
        assert "core_state" in interact_body
    print(f"  -> Cognitive Interact verified: state={interact_body['core_state']}")

    # Stage 8: Secure Zero-Touch Pairing Handshake
    print("[8/9] Testing Secure Zero-Touch Pairing Handshake...")
    pairing_data = json.dumps({
        "device_id": "pixel_9_pro_field_unit",
        "device_type": "android"
    }).encode("utf-8")
    req_pairing = urllib.request.Request(
        "https://127.0.0.1:8443/api/v1/pairing/handshake",
        data=pairing_data,
        headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req_pairing, context=ssl_context, timeout=3) as resp:
        assert resp.status == 200
        pair_body = json.loads(resp.read().decode())
        assert pair_body.get("status") == "paired"
        assert pair_body.get("auth_token") is not None
        assert pair_body.get("session_id") is not None
        paired_token = pair_body.get("auth_token")
    print(f"  -> Pairing Handshake succeeded. Session ID={pair_body['session_id']}")

    # Stage 9: Cross-Platform Session Handoff & Zero-Amnesia Dialogue Continuity
    print("[9/9] Testing Cross-Platform Session Handoff & Zero-Amnesia Context...")
    # 9a. Execute handoff to Android
    handoff_data = json.dumps({
        "target_device": "android",
        "source_device": "pc"
    }).encode("utf-8")
    req_handoff = urllib.request.Request(
        "https://127.0.0.1:8443/api/v1/session/handoff",
        data=handoff_data,
        headers={"Authorization": f"Bearer {paired_token}", "Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req_handoff, context=ssl_context, timeout=3) as resp:
        assert resp.status == 200
        handoff_body = json.loads(resp.read().decode())
        assert handoff_body.get("status") == "handoff_completed"
        assert handoff_body["handoff"]["focus_device"] == "android"
        assert len(handoff_body["handoff"]["recent_turns"]) > 0

    # 9b. Retrieve active session snapshot
    req_active_session = urllib.request.Request(
        "https://127.0.0.1:8443/api/v1/session/active",
        headers={"Authorization": f"Bearer {paired_token}"}
    )
    with urllib.request.urlopen(req_active_session, context=ssl_context, timeout=3) as resp:
        assert resp.status == 200
        active_body = json.loads(resp.read().decode())
        assert active_body.get("status") == "ok"
        assert active_body["session"]["focus_device"] == "android"
        recent_turns = active_body["session"]["recent_turns"]
        assert len(recent_turns) > 0
        assert "System status check." in recent_turns[-1]["user_input"]
    print(f"  -> Session Handoff verified: {len(recent_turns)} turns transferred to Android focus.")

    # 9c. Sync external conversation turn from Android
    sync_turns_data = json.dumps({
        "items": [],
        "conversation_turns": [
            {
                "user_input": "Field check from Android",
                "thought_stream": "Sensory correlation active",
                "final_response": "Standing by on mobile.",
                "source_device": "android",
                "affect_state": {"valence": 0.25, "arousal": 0.05, "dominance": 0.85}
            }
        ]
    }).encode("utf-8")
    req_sync_turns = urllib.request.Request(
        "https://127.0.0.1:8443/api/v1/sync/push",
        data=sync_turns_data,
        headers={"Authorization": f"Bearer {paired_token}", "Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req_sync_turns, context=ssl_context, timeout=3) as resp:
        assert resp.status == 200
        push_turns_body = json.loads(resp.read().decode())
        assert push_turns_body.get("conversation_count") == 1
    print("  -> Sync Push with dialogue turns verified into Throne SessionManager.")

    # Stage 10: Cognitive Status Telemetry & Grounding
    print("[10/10] Testing Cognitive Status & Plan C Grounding Telemetry...")
    req_cog_status = urllib.request.Request(
        "https://127.0.0.1:8443/api/v1/cognitive/status",
        headers={"Authorization": f"Bearer {paired_token}"}
    )
    with urllib.request.urlopen(req_cog_status, context=ssl_context, timeout=3) as resp:
        assert resp.status == 200
        cog_body = json.loads(resp.read().decode())
        assert cog_body.get("offload_recommended") is True
        assert "affect_vector" in cog_body
        assert cog_body.get("grounding_count", 0) >= 1
    print(f"  -> Cognitive Status verified: offload_recommended=True, grounding={cog_body['grounding_count']}")

    print("\nALL INTEGRATION TESTS PASSED SUCCESSFULLY!")
    server_thread.stop()
    ca_server.shutdown()


if __name__ == "__main__":
    run_integration_tests()

