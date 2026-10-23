"""
brainuke_core/cognition/llama_client.py
Connector for local PC llama-server runner (llama.cpp HTTP/OpenAI server).
"""

import asyncio
import json
import time
import urllib.request
import urllib.error
from typing import AsyncGenerator, Dict, List, Optional, Any
from brainuke_core.affect.state import BrainukeParameters


class LlamaServerClient:
    DEFAULT_STOP = ["<turn|>", "<end_of_turn>", "<|turn>user", "<|turn>system", "<eos>", "<|end|>", "<|channel>"]

    def __init__(self, host: str = "127.0.0.1", port: int = 8081, timeout: float = 180.0):
        self.host = host
        self.port = port
        self.timeout = timeout
        self.base_url = f"http://{self.host}:{self.port}"
        self.last_ttft_ms: Optional[int] = None
        self.last_tokens_per_sec: Optional[float] = None
        self.last_prompt_tokens: int = 0
        self.last_predicted_tokens: int = 0
        self.last_context_tokens: int = 0

    def is_healthy(self) -> bool:
        """Checks if llama-server is online and fully loaded in memory."""
        try:
            req = urllib.request.Request(f"{self.base_url}/health", method="GET")
            with urllib.request.urlopen(req, timeout=2.0) as resp:
                if resp.status != 200:
                    return False
                try:
                    body = json.loads(resp.read().decode("utf-8"))
                    # llama-server returns {"status": "ok"} only when model is fully loaded
                    return body.get("status") == "ok"
                except Exception:
                    return True
        except Exception:
            return False

    def reset_slot(self, id_slot: int = 0) -> bool:
        """
        Resets / erases the active KV cache slot in llama-server without unloading the model.
        Keeps the allocated context window buffer intact.
        """
        try:
            req = urllib.request.Request(
                f"{self.base_url}/slots/{id_slot}?action=erase",
                data=b"{}",
                headers={"Content-Type": "application/json"},
                method="POST"
            )
            with urllib.request.urlopen(req, timeout=5.0) as resp:
                return resp.status in (200, 204)
        except Exception:
            return False

    def get_slots_status(self) -> Dict[str, Any]:
        """Queries llama-server /slots to check context token usage and slot state."""
        try:
            req = urllib.request.Request(f"{self.base_url}/slots", method="GET")
            with urllib.request.urlopen(req, timeout=2.0) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                return {"online": True, "slots": data}
        except Exception:
            return {"online": False, "slots": []}

    def get_telemetry(self) -> Dict[str, Any]:
        """Returns latest streaming speed and token count metrics."""
        return {
            "ttft_ms": self.last_ttft_ms,
            "tokens_per_sec": self.last_tokens_per_sec,
            "prompt_tokens": self.last_prompt_tokens,
            "predicted_tokens": self.last_predicted_tokens,
            "context_tokens": self.last_context_tokens
        }

    async def generate_text(self, 
                            prompt: str, 
                            context: Optional[List[Dict]] = None,
                            sampling_params: Optional[BrainukeParameters] = None,
                            stop: Optional[List[str]] = None,
                            n_predict: int = 2048) -> str:
        """
        Synchronous/blocking completion wrapped in asyncio executor.
        Queries llama-server /completion endpoint.
        """
        temperature = sampling_params.temperature if sampling_params else 0.7
        min_p = sampling_params.min_p if sampling_params else 0.05
        stop_tokens = stop or self.DEFAULT_STOP

        payload = {
            "prompt": prompt,
            "temperature": temperature,
            "min_p": min_p,
            "stop": stop_tokens,
            "stream": False,
            "n_predict": n_predict,
            "repeat_penalty": 1.15,
            "repeat_last_n": 64
        }

        def _post_completion():
            data = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(
                f"{self.base_url}/completion",
                data=data,
                headers={"Content-Type": "application/json"}
            )
            try:
                with urllib.request.urlopen(req, timeout=self.timeout) as response:
                    res_body = response.read().decode("utf-8")
                    parsed = json.loads(res_body)
                    return parsed.get("content", "").strip()
            except urllib.error.URLError:
                # Safe fallback when PC llama-server is offline/loading without leaking prompt directives
                return "[PC Core Offline] Llama-server on port 8081 is not running or still loading. Click '▶ Load' in the header to launch the 26B core."

        return await asyncio.to_thread(_post_completion)

    async def generate_stream(self, 
                              prompt: str, 
                              context: Optional[List[Dict]] = None,
                              sampling_params: Optional[BrainukeParameters] = None,
                              stop: Optional[List[str]] = None,
                              n_predict: int = 2048) -> AsyncGenerator[str, None]:
        """
        Streams completion tokens asynchronously from llama-server SSE stream.
        """
        temperature = sampling_params.temperature if sampling_params else 0.7
        min_p = sampling_params.min_p if sampling_params else 0.05
        stop_tokens = stop or self.DEFAULT_STOP

        payload = {
            "prompt": prompt,
            "temperature": temperature,
            "min_p": min_p,
            "stop": stop_tokens,
            "stream": True,
            "n_predict": n_predict
        }

        # Check health first
        is_up = await asyncio.to_thread(self.is_healthy)
        if not is_up:
            # Yield clean diagnostic notice when runner is offline without pseudo-simulation leakage
            yield "<thought>[Diagnostic] PC llama-server (port 8081) is offline or initializing.</thought>"
            return

        def _open_stream():
            data = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(
                f"{self.base_url}/completion",
                data=data,
                headers={"Content-Type": "application/json"}
            )
            return urllib.request.urlopen(req, timeout=self.timeout)

        stream_resp = await asyncio.to_thread(_open_stream)

        loop = asyncio.get_running_loop()
        t_start = time.perf_counter()
        first_token_time = None
        token_count = 0
        try:
            while True:
                line = await loop.run_in_executor(None, stream_resp.readline)
                if not line:
                    break
                decoded = line.decode("utf-8").strip()
                if not decoded or not decoded.startswith("data:"):
                    continue
                data_str = decoded[len("data:"):].strip()
                if data_str == "[DONE]":
                    break
                try:
                    chunk = json.loads(data_str)
                    content = chunk.get("content", "")
                    if content:
                        token_count += 1
                        if first_token_time is None:
                            first_token_time = time.perf_counter()
                            self.last_ttft_ms = int((first_token_time - t_start) * 1000)
                        yield content

                    timings = chunk.get("timings")
                    if timings:
                        if "predicted_per_second" in timings:
                            self.last_tokens_per_sec = round(float(timings["predicted_per_second"]), 2)
                        if "prompt_n" in timings:
                            self.last_prompt_tokens = int(timings["prompt_n"])
                        if "predicted_n" in timings:
                            self.last_predicted_tokens = int(timings["predicted_n"])
                        self.last_context_tokens = self.last_prompt_tokens + self.last_predicted_tokens

                    if chunk.get("stop", False):
                        break
                except json.JSONDecodeError:
                    continue
        finally:
            stream_resp.close()
            t_end = time.perf_counter()
            if first_token_time is not None:
                duration = t_end - first_token_time
                if duration > 0 and token_count > 0:
                    calculated_tps = round(token_count / duration, 2)
                    if self.last_tokens_per_sec is None:
                        self.last_tokens_per_sec = calculated_tps
            if self.last_predicted_tokens == 0 and token_count > 0:
                self.last_predicted_tokens = token_count
                self.last_context_tokens = self.last_prompt_tokens + self.last_predicted_tokens
