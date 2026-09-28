// brainuke_throne/ui_desktop/app.js
// Project Brainuke - Real-time Cognitive Stage & Organic Neural Feedback

(function () {
  const token = "a47a07dde6f972119b03f1c85c7c353c"; // Standard Machine Token from KeyVault
  let isThinking = false;
  let currentThoughtStream = "";
  let currentModelTurnElem = null;

  // DOM Elements
  const messageStream = document.getElementById("message-stream");
  const userInput = document.getElementById("user-input");
  const btnSend = document.getElementById("btn-send");
  const btnSimmer = document.getElementById("btn-force-simmer");
  const btnSnapPerception = document.getElementById("btn-snap-perception");
  const btnClearChat = document.getElementById("btn-clear-chat");
  const appContainer = document.getElementById("app-container");
  const textMood = document.getElementById("text-mood");
  const textConnection = document.getElementById("text-connection");
  const meterValence = document.getElementById("meter-valence");
  const meterArousal = document.getElementById("meter-arousal");
  const meterDominance = document.getElementById("meter-dominance");
  const valValence = document.getElementById("val-valence");
  const valArousal = document.getElementById("val-arousal");
  const valDominance = document.getElementById("val-dominance");
  const statusSimmer = document.getElementById("status-simmer");
  const statusGrounding = document.getElementById("status-grounding");

  // --- 1. ORGANIC 'SMOKY GREEN' NEURAL MARGIN SHADER ---
  const canvas = document.getElementById("canvas-neural-left");
  const ctx = canvas.getContext("2d");
  let width, height;
  let time = 0;

  function resizeCanvas() {
    width = canvas.width = canvas.parentElement.clientWidth;
    height = canvas.height = canvas.parentElement.clientHeight;
  }
  window.addEventListener("resize", resizeCanvas);
  resizeCanvas();

  function renderNeuralMargin() {
    time += isThinking ? 0.04 : 0.012;
    ctx.clearRect(0, 0, width, height);

    // Multi-layer sine-wave fluid rendering
    const layers = [
      { color: "rgba(16, 185, 129, 0.15)", freq: 0.015, speed: 1.0, amp: 22 },
      { color: "rgba(5, 150, 105, 0.25)",  freq: 0.022, speed: 1.5, amp: 16 },
      { color: "rgba(52, 211, 153, 0.40)", freq: 0.035, speed: 2.2, amp: isThinking ? 26 : 10 }
    ];

    layers.forEach(layer => {
      ctx.beginPath();
      ctx.moveTo(0, 0);

      for (let y = 0; y <= height; y += 4) {
        const xOffset = Math.sin(y * layer.freq + time * layer.speed) * layer.amp
                      + Math.cos(y * 0.008 - time * 0.5) * (layer.amp * 0.5);
        ctx.lineTo(width * 0.5 + xOffset, y);
      }

      ctx.strokeStyle = layer.color;
      ctx.lineWidth = isThinking ? 3.5 : 2.0;
      ctx.stroke();
    });

    // Faint fluid particle motes during thinking
    if (isThinking) {
      for (let i = 0; i < 3; i++) {
        const py = (Math.sin(time * 2 + i * 3) * 0.5 + 0.5) * height;
        const px = width * 0.5 + Math.cos(time * 3 + i) * 20;
        ctx.beginPath();
        ctx.arc(px, py, 2.5, 0, Math.PI * 2);
        ctx.fillStyle = "rgba(110, 231, 183, 0.8)";
        ctx.shadowColor = "#34D399";
        ctx.shadowBlur = 10;
        ctx.fill();
        ctx.shadowBlur = 0;
      }
    }

    requestAnimationFrame(renderNeuralMargin);
  }
  renderNeuralMargin();

  function setThinkingState(active) {
    isThinking = active;
    if (active) {
      appContainer.classList.add("active-cognition");
    } else {
      appContainer.classList.remove("active-cognition");
    }
  }

  // --- 2. MESSAGE UI & THOUGHT ISOLATION ---
  function appendUserMessage(text) {
    const turn = document.createElement("article");
    turn.className = "message-turn user";
    turn.innerHTML = `<div class="bubble">${escapeHtml(text)}</div>`;
    messageStream.appendChild(turn);
    messageStream.scrollTop = messageStream.scrollHeight;
  }

  function createModelTurn(thought = "", speech = "") {
    const turn = document.createElement("article");
    turn.className = "message-turn model";
    turn.innerHTML = `
      <div class="bubble">
        <div class="model-header">⚡ Cecilia &bull; Core Persona</div>
        <details class="thought-drawer" ${thought ? "" : "style='display:none;'"}>
          <summary class="thought-summary">
            <span>⚡ Internal Reasoning (Hidden Subtext)</span>
          </summary>
          <pre class="thought-content">${escapeHtml(thought)}</pre>
        </details>
        <div class="speech-content">${escapeHtml(speech)}</div>
      </div>
    `;
    messageStream.appendChild(turn);
    messageStream.scrollTop = messageStream.scrollHeight;
    return turn;
  }

  function escapeHtml(str) {
    return str.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
  }

  // --- 3. COGNITIVE INTERACTION ---
  async function sendMessage() {
    const text = userInput.value.trim();
    if (!text || isThinking) return;

    userInput.value = "";
    appendUserMessage(text);
    setThinkingState(true);

    currentModelTurnElem = createModelTurn("Reasoning in shadows...", "...");
    const thoughtBox = currentModelTurnElem.querySelector(".thought-content");
    const drawer = currentModelTurnElem.querySelector(".thought-drawer");
    const speechBox = currentModelTurnElem.querySelector(".speech-content");
    drawer.style.display = "block";

    try {
      const response = await fetch("/api/v1/cognitive/interact", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "Authorization": `Bearer ${token}`
        },
        body: JSON.stringify({ text, context: [] })
      });

      if (!response.ok) {
        throw new Error(`Throne HTTP ${response.status}`);
      }

      const data = await response.json();
      thoughtBox.textContent = data.thought || "(Reasoning complete)";
      speechBox.textContent = data.response || "(Silence)";

      // Update affect
      updateStatusHUD();
    } catch (err) {
      speechBox.textContent = `[Cognitive Interruption]: ${err.message}`;
    } finally {
      setThinkingState(false);
      currentModelTurnElem = null;
      messageStream.scrollTop = messageStream.scrollHeight;
    }
  }

  btnSend.addEventListener("click", sendMessage);
  userInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  });

  // --- 4. SSE REAL-TIME DOWNLINK ---
  function connectSSE() {
    const eventSource = new EventSource("/subscriptions/listen");

    eventSource.onopen = () => {
      textConnection.textContent = "Downlink: Connected";
      textConnection.style.color = "#34D399";
    };

    eventSource.onmessage = (event) => {
      try {
        const payload = JSON.parse(event.data);
        if (payload.type === "thought" && currentModelTurnElem) {
          const tb = currentModelTurnElem.querySelector(".thought-content");
          tb.textContent += payload.content;
        } else if (payload.type === "speech" && currentModelTurnElem) {
          const sb = currentModelTurnElem.querySelector(".speech-content");
          sb.textContent = payload.content;
        } else if (payload.type === "dmn_insight") {
          statusSimmer.textContent = "Simmered Insight Broadcasted";
          setTimeout(() => statusSimmer.textContent = "Idle", 6000);
        }
      } catch (e) {
        // Heartbeat or raw string
      }
    };

    eventSource.onerror = () => {
      textConnection.textContent = "Downlink: Reconnecting...";
      textConnection.style.color = "#F87171";
    };
  }
  connectSSE();

  // --- 5. AFFECT & TELEMETRY HUD POLLING ---
  async function updateStatusHUD() {
    try {
      const res = await fetch("/api/v1/cognitive/status", {
        headers: { "Authorization": `Bearer ${token}` }
      });
      if (!res.ok) return;
      const data = await res.json();

      if (data.affect_vector) {
        const v = data.affect_vector.valence;
        const a = data.affect_vector.arousal;
        const d = data.affect_vector.dominance;

        valValence.textContent = v.toFixed(2);
        valArousal.textContent = a.toFixed(2);
        valDominance.textContent = d.toFixed(2);

        meterValence.style.width = `${Math.min(100, Math.max(0, (v + 1) * 50))}%`;
        meterArousal.style.width = `${Math.min(100, Math.max(0, (a + 1) * 50))}%`;
        meterDominance.style.width = `${Math.min(100, Math.max(0, (d + 1) * 50))}%`;
      }

      if (data.core_state) {
        textMood.textContent = `Mood: ${data.core_state}`;
      }

      if (data.grounding_count !== undefined) {
        statusGrounding.textContent = `${data.grounding_count} nodes`;
      }
    } catch (e) {
      // offline or poll error
    }

    // Update quarantine count
    try {
      const qRes = await fetch("/api/v1/messageboard/quarantine", {
        headers: { "Authorization": `Bearer ${token}` }
      });
      if (qRes.ok) {
        const qData = await qRes.json();
        const count = qData.quarantined_posts ? qData.quarantined_posts.length : 0;
        const statusQuarantine = document.getElementById("status-quarantine");
        if (statusQuarantine) {
          statusQuarantine.textContent = `${count} flagged`;
          statusQuarantine.style.color = count > 0 ? "#F87171" : "#A7F3D0";
        }
      }
    } catch (_) {}

    // Update subagent tasks count
    try {
      const sRes = await fetch("/api/v1/subagents/tasks?status=running");
      if (sRes.ok) {
        const sData = await sRes.json();
        const activeCount = sData.count || 0;
        const statusSubagents = document.getElementById("status-subagents");
        if (statusSubagents) {
          statusSubagents.textContent = `${activeCount} active`;
        }
      }
    } catch (_) {}
  }
  setInterval(updateStatusHUD, 4000);
  updateStatusHUD();

  // --- 6. MESSAGEBOARD & CONTEXTUAL SANDBOX ---
  const threadList = document.getElementById("thread-list");
  const btnNewThread = document.getElementById("btn-new-thread");
  const threadModal = document.getElementById("thread-modal");
  const modalThreadTitle = document.getElementById("modal-thread-title");
  const modalClose = document.getElementById("modal-close");
  const modalPosts = document.getElementById("modal-posts");
  const modalReplyInput = document.getElementById("modal-reply-input");
  const modalReplyBtn = document.getElementById("modal-reply-btn");
  let activeThreadId = null;

  async function loadThreads() {
    if (!threadList) return;
    try {
      const res = await fetch("/api/v1/messageboard/threads");
      if (!res.ok) return;
      const data = await res.json();
      if (!data.threads || data.threads.length === 0) {
        threadList.innerHTML = `<div style="font-size:0.75rem; color:var(--text-muted); padding:8px;">No active threads. Create one above!</div>`;
        return;
      }
      threadList.innerHTML = "";
      data.threads.forEach(t => {
        const item = document.createElement("div");
        item.className = "thread-item";
        item.innerHTML = `
          <div class="thread-tag">#${escapeHtml(t.concept_family || "general")}</div>
          <div style="font-weight:600; margin-top:3px;">${escapeHtml(t.title)}</div>
          <div style="font-size:0.75rem; color:var(--text-muted); margin-top:2px;">${escapeHtml(t.creator_id || "agent")} &bull; ${t.post_count || 0} posts</div>
        `;
        item.addEventListener("click", () => openThread(t));
        threadList.appendChild(item);
      });
    } catch (e) {
      // offline
    }
  }

  async function openThread(thread) {
    activeThreadId = thread.id;
    modalThreadTitle.textContent = `#${thread.concept_family || "general"} - ${thread.title}`;
    modalPosts.innerHTML = `<div style="font-size:0.8rem; color:var(--text-muted);">Loading posts...</div>`;
    threadModal.classList.remove("hidden");
    await loadThreadPosts(thread.id);
  }

  async function loadThreadPosts(threadId) {
    try {
      const res = await fetch(`/api/v1/messageboard/threads/${threadId}/posts`);
      if (!res.ok) return;
      const data = await res.json();
      if (!data.posts || data.posts.length === 0) {
        modalPosts.innerHTML = `<div style="font-size:0.8rem; color:var(--text-muted);">No posts in this thread yet. Be the first to reply!</div>`;
        return;
      }
      modalPosts.innerHTML = "";
      data.posts.forEach(p => {
        const postElem = document.createElement("div");
        postElem.className = "modal-post-item";
        postElem.innerHTML = `
          <div class="modal-post-author">${escapeHtml(p.author_name || p.author_id)} (${escapeHtml(p.author_type || "human")})</div>
          <div style="color:var(--text-main); font-size:0.88rem;">${escapeHtml(p.content)}</div>
        `;
        modalPosts.appendChild(postElem);
      });
      modalPosts.scrollTop = modalPosts.scrollHeight;
    } catch (e) {
      modalPosts.innerHTML = `<div style="font-size:0.8rem; color:#F87171;">Failed to load posts.</div>`;
    }
  }

  if (modalClose) {
    modalClose.addEventListener("click", () => {
      threadModal.classList.add("hidden");
      activeThreadId = null;
    });
  }

  if (modalReplyBtn) {
    modalReplyBtn.addEventListener("click", async () => {
      if (!activeThreadId) return;
      const content = modalReplyInput.value.trim();
      if (!content) return;

      modalReplyBtn.disabled = true;
      try {
        const res = await fetch(`/api/v1/messageboard/threads/${activeThreadId}/posts`, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "Authorization": `Bearer ${token}`
          },
          body: JSON.stringify({
            content: content,
            author_id: "human_user",
            author_name: "User",
            author_type: "human"
          })
        });
        const data = await res.json();
        modalReplyInput.value = "";
        if (data.status === "quarantined") {
          alert(`⚠️ Notice: Post held in Contextual Sandbox quarantine!\nReason: ${data.intent} (Risk Score: ${data.risk_score.toFixed(2)})`);
        }
        await loadThreadPosts(activeThreadId);
        loadThreads();
        updateStatusHUD();
      } catch (err) {
        alert("Failed to submit post: " + err.message);
      } finally {
        modalReplyBtn.disabled = false;
      }
    });
  }

  if (btnNewThread) {
    btnNewThread.addEventListener("click", async () => {
      const title = prompt("Enter new thread title:");
      if (!title || !title.trim()) return;

      try {
        const res = await fetch("/api/v1/messageboard/threads", {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "Authorization": `Bearer ${token}`
          },
          body: JSON.stringify({
            title: title.trim(),
            creator_id: "human_user"
          })
        });
        if (res.ok) {
          loadThreads();
        } else {
          alert("Failed to create thread.");
        }
      } catch (err) {
        alert("Thread creation failed: " + err.message);
      }
    });
  }

  loadThreads();

  // --- 7. ACTION CONTROLS ---
  btnSimmer.addEventListener("click", async () => {
    btnSimmer.textContent = "Simmering...";
    try {
      const res = await fetch("/api/v1/sync/simmer", {
        method: "POST",
        headers: { "Authorization": `Bearer ${token}` }
      });
      const data = await res.json();
      statusSimmer.textContent = "Simmer Completed";
      setTimeout(() => statusSimmer.textContent = "Idle", 4000);
      updateStatusHUD();
      loadThreads();
    } catch (err) {
      alert("Simmer failed: " + err.message);
    } finally {
      btnSimmer.textContent = "⚡ Simmer DMN";
    }
  });

  btnSnapPerception.addEventListener("click", async () => {
    const observation = prompt("Enter perceptual/environmental observation or paste sensor description:", "Desk setup: dual monitors, low lighting, focused programming session.");
    if (!observation) return;

    try {
      const res = await fetch("/api/v1/sensory/stream", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "Authorization": `Bearer ${token}`
        },
        body: JSON.stringify({
          type: "perceptual_frame",
          observation: observation,
          timestamp: Date.now()
        })
      });
      alert("Perception successfully injected into Throne sensory pool!");
    } catch (err) {
      alert("Sensory inject failed: " + err.message);
    }
  });

  btnClearChat.addEventListener("click", () => {
    messageStream.innerHTML = "";
    createModelTurn("Cognitive nexus active.", "Chat history cleared from active view. Memory Vault remains intact.");
  });

})();
