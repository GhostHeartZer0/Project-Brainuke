"""
brainuke_core/memory/vault.py
SQLite-backed Master Memory Vault for Project Brainuke Throne.
Stores historical telemetry pool, conversation transcripts, and distilled DMN insights.
"""

import sqlite3
import json
import time
import uuid
import re
from pathlib import Path
from typing import List, Dict, Any, Optional


class MemoryVault:
    def __init__(self, db_path: Optional[str] = None):
        if db_path is None:
            # Default to Project Brainuke root memory directory
            base_dir = Path(__file__).resolve().parent.parent.parent
            data_dir = base_dir / "data"
            data_dir.mkdir(parents=True, exist_ok=True)
            db_path = str(data_dir / "brainuke_master.db")

        self.db_path = db_path
        self._init_schema()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=10.0)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_schema(self):
        """Initializes relational tables for pool storage and distilled memories."""
        with self._get_connection() as conn:
            cursor = conn.cursor()

            # 1. Incoming sensory telemetry pool (from Android and local sensors)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS sensory_pool (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    source TEXT NOT NULL,
                    payload_type TEXT NOT NULL,
                    data_json TEXT NOT NULL,
                    timestamp INTEGER NOT NULL,
                    simmered INTEGER DEFAULT 0
                )
            """)
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_sensory_simmered ON sensory_pool(simmered)")

            # 2. Conversation & Interaction records
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS interaction_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_input TEXT NOT NULL,
                    thought_stream TEXT,
                    final_response TEXT,
                    affect_state TEXT,
                    timestamp INTEGER NOT NULL,
                    simmered INTEGER DEFAULT 0,
                    source_device TEXT DEFAULT 'pc',
                    influence_weight REAL DEFAULT 1.0
                )
            """)
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_interaction_simmered ON interaction_history(simmered)")
            cursor.execute("PRAGMA table_info(interaction_history)")
            ih_cols = [col[1] for col in cursor.fetchall()]
            if "source_device" not in ih_cols:
                cursor.execute("ALTER TABLE interaction_history ADD COLUMN source_device TEXT DEFAULT 'pc'")
            if "influence_weight" not in ih_cols:
                cursor.execute("ALTER TABLE interaction_history ADD COLUMN influence_weight REAL DEFAULT 1.0")
            if "raw_response" not in ih_cols:
                cursor.execute("ALTER TABLE interaction_history ADD COLUMN raw_response TEXT DEFAULT ''")
            if "turn_uuid" not in ih_cols:
                cursor.execute("ALTER TABLE interaction_history ADD COLUMN turn_uuid TEXT")
            cursor.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_interaction_turn_uuid ON interaction_history(turn_uuid) WHERE turn_uuid IS NOT NULL")

            # 3. Distilled DMN Insights & World Model Nodes
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS distilled_insights (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    insight TEXT NOT NULL,
                    emotional_shift TEXT,
                    world_delta TEXT,
                    concept_family TEXT DEFAULT 'general',
                    importance_weight REAL DEFAULT 1.0,
                    dominance_weight REAL DEFAULT 0.5,
                    timestamp INTEGER NOT NULL
                )
            """)
            # Schema migration check for existing tables
            cursor.execute("PRAGMA table_info(distilled_insights)")
            cols = [col[1] for col in cursor.fetchall()]
            if "concept_family" not in cols:
                cursor.execute("ALTER TABLE distilled_insights ADD COLUMN concept_family TEXT DEFAULT 'general'")
            if "importance_weight" not in cols:
                cursor.execute("ALTER TABLE distilled_insights ADD COLUMN importance_weight REAL DEFAULT 1.0")
            if "dominance_weight" not in cols:
                cursor.execute("ALTER TABLE distilled_insights ADD COLUMN dominance_weight REAL DEFAULT 0.5")

            cursor.execute("CREATE INDEX IF NOT EXISTS idx_insights_timestamp ON distilled_insights(timestamp)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_insights_concept ON distilled_insights(concept_family)")

            # 4. Contextual Sandbox: Quarantine for untrusted external inputs (Phase IV)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS quarantine_posts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    thread_id INTEGER,
                    author_id TEXT NOT NULL,
                    author_name TEXT NOT NULL,
                    author_type TEXT NOT NULL,
                    content TEXT NOT NULL,
                    intent_label TEXT DEFAULT 'pending',
                    risk_score REAL DEFAULT 0.0,
                    quarantined_at INTEGER NOT NULL,
                    status TEXT DEFAULT 'quarantined',
                    rejection_reason TEXT
                )
            """)
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_quarantine_status ON quarantine_posts(status)")

            # 5. Messageboard Threads & Admitted Posts (Phase IV Social Layer)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS messageboard_threads (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    concept_family TEXT DEFAULT 'general',
                    creator_id TEXT NOT NULL,
                    created_at INTEGER NOT NULL,
                    last_active_at INTEGER NOT NULL,
                    status TEXT DEFAULT 'active'
                )
            """)
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_thread_family ON messageboard_threads(concept_family)")

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS messageboard_posts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    thread_id INTEGER NOT NULL,
                    author_id TEXT NOT NULL,
                    author_name TEXT NOT NULL,
                    author_type TEXT NOT NULL,
                    content TEXT NOT NULL,
                    timestamp INTEGER NOT NULL,
                    FOREIGN KEY(thread_id) REFERENCES messageboard_threads(id)
                )
            """)
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_posts_thread ON messageboard_posts(thread_id)")

            cursor.execute("PRAGMA table_info(messageboard_posts)")
            mb_cols = [col[1] for col in cursor.fetchall()]
            if "simmered" not in mb_cols:
                cursor.execute("ALTER TABLE messageboard_posts ADD COLUMN simmered INTEGER DEFAULT 0")

            # 6. Agent Profiles (Phase IV Identity Layer)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS agent_profiles (
                    agent_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    temperament TEXT NOT NULL,
                    stance TEXT NOT NULL,
                    created_at INTEGER NOT NULL
                )
            """)

            # 7. Failed / Unfinished prompt buffer (Desktop & Core Backlog)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS failed_prompt_buffer (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    prompt_text TEXT NOT NULL,
                    target_mode TEXT DEFAULT 'pc',
                    failure_reason TEXT NOT NULL,
                    retry_count INTEGER DEFAULT 0,
                    timestamp INTEGER NOT NULL,
                    status TEXT DEFAULT 'pending'
                )
            """)
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_failed_prompt_status ON failed_prompt_buffer(status)")

            conn.commit()


    def ingest_sensory_batch(self, items: List[Dict[str, Any]], source: str = "android") -> int:
        """Batch inserts sensory records from Android Sync Push into the PC pool."""
        if not items:
            return 0

        with self._get_connection() as conn:
            cursor = conn.cursor()
            records = [
                (
                    source,
                    item.get("type", "telemetry"),
                    json.dumps(item),
                    item.get("timestamp", int(time.time() * 1000)),
                    0
                )
                for item in items
            ]
            cursor.executemany("""
                INSERT INTO sensory_pool (source, payload_type, data_json, timestamp, simmered)
                VALUES (?, ?, ?, ?, ?)
            """, records)
            conn.commit()
            return cursor.rowcount

    def ingest_interaction(
        self,
        user_input: str,
        thought_stream: str,
        final_response: str,
        affect_state: Optional[Dict[str, float]] = None,
        source_device: str = "pc",
        influence_weight: Optional[float] = None,
        raw_response: str = "",
        turn_uuid: Optional[str] = None
    ) -> int:
        """
        Records a single conversation turn.
        PC interactions default to weight 1.0 (master cognitive core).
        Android companion interactions default to weight 0.35 (tether).
        Supports idempotent ingestion via turn_uuid deduplication.
        """
        if influence_weight is None:
            influence_weight = 1.0 if source_device == "pc" else 0.35
        if not turn_uuid:
            turn_uuid = str(uuid.uuid4())

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR IGNORE INTO interaction_history (
                    user_input, thought_stream, final_response, affect_state,
                    timestamp, simmered, source_device, influence_weight, raw_response, turn_uuid
                )
                VALUES (?, ?, ?, ?, ?, 0, ?, ?, ?, ?)
            """, (
                user_input,
                thought_stream,
                final_response,
                json.dumps(affect_state or {}),
                int(time.time() * 1000),
                source_device,
                influence_weight,
                raw_response,
                turn_uuid
            ))
            conn.commit()
            if cursor.lastrowid:
                return cursor.lastrowid
            cursor.execute("SELECT id FROM interaction_history WHERE turn_uuid = ?", (turn_uuid,))
            row = cursor.fetchone()
            return row["id"] if row else 0

    def get_recent_interactions(self, limit: int = 10, source_device: Optional[str] = None) -> List[Dict[str, Any]]:
        """Retrieves most recent interaction records, optionally filtered by source_device."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            if source_device:
                cursor.execute("""
                    SELECT id, user_input, thought_stream, final_response, affect_state, timestamp,
                           source_device, influence_weight, raw_response, turn_uuid
                    FROM interaction_history
                    WHERE source_device = ?
                    ORDER BY timestamp DESC
                    LIMIT ?
                """, (source_device, limit))
            else:
                cursor.execute("""
                    SELECT id, user_input, thought_stream, final_response, affect_state, timestamp,
                           source_device, influence_weight, raw_response, turn_uuid
                    FROM interaction_history
                    ORDER BY timestamp DESC
                    LIMIT ?
                """, (limit,))
            return [dict(row) for row in cursor.fetchall()]

    def get_distilled_insights(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Retrieves distilled DMN insights ordered by timestamp DESC."""
        return self.get_recent_grounding(limit=limit)

    def get_random_interactions(self, limit: int = 5) -> List[Dict[str, Any]]:
        """Retrieves random historical sample of interaction records."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, user_input, thought_stream, final_response, affect_state, timestamp,
                       source_device, influence_weight, raw_response, turn_uuid
                FROM interaction_history
                ORDER BY RANDOM()
                LIMIT ?
            """, (limit,))
            return [dict(row) for row in cursor.fetchall()]

    def get_unsimmered_records(self, limit: int = 50) -> Dict[str, List[Dict[str, Any]]]:
        """Retrieves raw interactions and telemetry pending DMN reflection."""
        with self._get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute("""
                SELECT id, user_input, thought_stream, final_response, affect_state, timestamp,
                       source_device, influence_weight
                FROM interaction_history
                WHERE simmered = 0
                ORDER BY timestamp ASC
                LIMIT ?
            """, (limit,))
            interactions = [dict(row) for row in cursor.fetchall()]

            cursor.execute("""
                SELECT id, payload_type, data_json, timestamp
                FROM sensory_pool
                WHERE simmered = 0
                ORDER BY timestamp ASC
                LIMIT ?
            """, (limit,))
            sensory = [
                {
                    "id": row["id"],
                    "payload_type": row["payload_type"],
                    "data": json.loads(row["data_json"]),
                    "timestamp": row["timestamp"]
                }
                for row in cursor.fetchall()
            ]

            return {"interactions": interactions, "sensory": sensory}

    def mark_records_simmered(self, interaction_ids: List[int], sensory_ids: List[int]):
        """Marks consolidated items as simmered."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            if interaction_ids:
                q = f"UPDATE interaction_history SET simmered = 1 WHERE id IN ({','.join(['?']*len(interaction_ids))})"
                cursor.execute(q, interaction_ids)
            if sensory_ids:
                q = f"UPDATE sensory_pool SET simmered = 1 WHERE id IN ({','.join(['?']*len(sensory_ids))})"
                cursor.execute(q, sensory_ids)
            conn.commit()

    def archive_insight(
        self,
        insight: str,
        emotional_shift: Optional[Dict[str, Any]] = None,
        world_delta: Optional[Dict[str, Any]] = None,
        concept_family: str = "general",
        importance_weight: float = 1.0,
        dominance_weight: float = 0.5
    ) -> int:
        """Stores consolidated DMN insight into long-term memory."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO distilled_insights (
                    insight, emotional_shift, world_delta, concept_family,
                    importance_weight, dominance_weight, timestamp
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                insight,
                json.dumps(emotional_shift or {}),
                json.dumps(world_delta or {}),
                concept_family,
                importance_weight,
                dominance_weight,
                int(time.time() * 1000)
            ))
            conn.commit()
            return cursor.lastrowid

    def get_recent_grounding(self, limit: int = 5) -> List[Dict[str, Any]]:
        """Retrieves recent distilled worldview anchors for cognitive grounding."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, insight, emotional_shift, world_delta, concept_family,
                       importance_weight, dominance_weight, timestamp
                FROM distilled_insights
                ORDER BY timestamp DESC
                LIMIT ?
            """, (limit,))
            rows = cursor.fetchall()

            grounding = []
            for row in rows:
                grounding.append({
                    "id": row["id"],
                    "insight": row["insight"],
                    "emotional_shift": json.loads(row["emotional_shift"]),
                    "world_delta": json.loads(row["world_delta"]),
                    "concept_family": row["concept_family"] or "general",
                    "importance_weight": float(row["importance_weight"] or 1.0),
                    "dominance_weight": float(row["dominance_weight"] or 0.5),
                    "timestamp": row["timestamp"]
                })
            return grounding

    def search_memory(
        self,
        query: str,
        limit: int = 10,
        max_recent: int = 3
    ) -> Dict[str, Any]:
        """
        Cross-temporal keyword memory retrieval:
        1. Prioritizes distilled insights (simmered DMN thoughts) across all time.
        2. Retrieves latest conversational turns (guaranteeing recency buffer).
        3. Retrieves matching historical turns across all time.
        """
        raw_tokens = [
            t.lower().strip() for t in re.split(r"[\s,;.!?'\"()\[\]{}]+", query)
            if len(t.strip()) >= 3 and t.lower().strip() not in {
                "the", "and", "for", "with", "this", "that", "you", "are", "have", "from",
                "what", "when", "where", "how", "why", "will", "your", "about"
            }
        ]
        # Deduplicate and cap to top distinct keywords to prevent SQLite expression tree overflow
        tokens = list(dict.fromkeys(raw_tokens))[:12]

        with self._get_connection() as conn:
            cursor = conn.cursor()

            # Priority 1: Distilled DMN insights (Simmered Thoughts across all time)
            matched_insights = []
            if tokens:
                try:
                    conditions = " OR ".join(["insight LIKE ? OR concept_family LIKE ?" for _ in tokens])
                    params = []
                    for t in tokens:
                        p = f"%{t}%"
                        params.extend([p, p])

                    cursor.execute(f"""
                        SELECT id, insight, emotional_shift, world_delta, concept_family,
                               importance_weight, dominance_weight, timestamp
                        FROM distilled_insights
                        WHERE {conditions}
                        ORDER BY importance_weight DESC, timestamp DESC
                        LIMIT ?
                    """, (*params, limit))
                    for row in cursor.fetchall():
                        matched_insights.append({
                            "id": row["id"],
                            "insight": row["insight"],
                            "emotional_shift": json.loads(row["emotional_shift"]),
                            "world_delta": json.loads(row["world_delta"]),
                            "concept_family": row["concept_family"] or "general",
                            "importance_weight": float(row["importance_weight"] or 1.0),
                            "dominance_weight": float(row["dominance_weight"] or 0.5),
                            "timestamp": row["timestamp"],
                            "source": "simmered_insight"
                        })
                except Exception:
                    pass

            # Priority 2: Latest few prompts (immediate conversational continuity)
            cursor.execute("""
                SELECT id, user_input, thought_stream, final_response, affect_state,
                       timestamp, source_device, influence_weight, raw_response, simmered
                FROM interaction_history
                ORDER BY timestamp DESC
                LIMIT ?
            """, (max_recent,))
            recent_prompts = [dict(row) for row in cursor.fetchall()]
            recent_ids = {r["id"] for r in recent_prompts}

            # Priority 3: Historical interaction records across all time matching keywords
            historical_matches = []
            if tokens:
                try:
                    h_conditions = " OR ".join(["user_input LIKE ? OR final_response LIKE ?" for _ in tokens])
                    h_params = []
                    for t in tokens:
                        p = f"%{t}%"
                        h_params.extend([p, p])
                    cursor.execute(f"""
                        SELECT id, user_input, thought_stream, final_response, affect_state,
                               timestamp, source_device, influence_weight, raw_response, simmered
                        FROM interaction_history
                        WHERE ({h_conditions})
                        ORDER BY simmered DESC, influence_weight DESC, timestamp DESC
                        LIMIT ?
                    """, (*h_params, limit))
                    for row in cursor.fetchall():
                        if row["id"] not in recent_ids:
                            historical_matches.append(dict(row))
                except Exception:
                    pass

            return {
                "simmered_insights": matched_insights,
                "recent_prompts": recent_prompts,
                "historical_interactions": historical_matches
            }

    def get_grounding_for_prompt(self, user_input: str, limit: int = 6) -> List[Dict[str, Any]]:
        """
        Retrieves thematic grounding nodes prioritized for the active user prompt.
        Prioritizes simmered DMN insights matching keywords across all time,
        falling back to recent grounding nodes to maintain stability.
        """
        search_res = self.search_memory(user_input, limit=limit)
        simmered = search_res.get("simmered_insights", [])

        if len(simmered) >= limit:
            return simmered[:limit]

        recent = self.get_recent_grounding(limit=limit)
        existing_ids = {s["id"] for s in simmered}
        for r in recent:
            if r["id"] not in existing_ids:
                simmered.append(r)
                if len(simmered) >= limit:
                    break

        return simmered

    def get_delta_pack(
        self,
        since_timestamp: int = 0,
        since_insight_id: int = 0,
        since_turn_id: int = 0,
        include_pc_turns: bool = True
    ) -> Dict[str, Any]:
        """
        Extracts new memory insights and PC dialogue turns generated since last Android sync.
        Uses sequence IDs (since_insight_id, since_turn_id) with fallback to since_timestamp.
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            if since_insight_id > 0:
                cursor.execute("""
                    SELECT id, insight, emotional_shift, world_delta, concept_family,
                           importance_weight, dominance_weight, timestamp
                    FROM distilled_insights
                    WHERE id > ?
                    ORDER BY id ASC
                """, (since_insight_id,))
            else:
                cursor.execute("""
                    SELECT id, insight, emotional_shift, world_delta, concept_family,
                           importance_weight, dominance_weight, timestamp
                    FROM distilled_insights
                    WHERE timestamp > ?
                    ORDER BY id ASC
                """, (since_timestamp,))
            rows = cursor.fetchall()

            insights = []
            max_insight_id = since_insight_id
            for row in rows:
                if row["id"] > max_insight_id:
                    max_insight_id = row["id"]
                insights.append({
                    "id": row["id"],
                    "insight": row["insight"],
                    "emotional_shift": json.loads(row["emotional_shift"]),
                    "world_delta": json.loads(row["world_delta"]),
                    "concept_family": row["concept_family"] or "general",
                    "importance_weight": float(row["importance_weight"] or 1.0),
                    "dominance_weight": float(row["dominance_weight"] or 0.5),
                    "timestamp": row["timestamp"]
                })

            pc_turns = []
            max_turn_id = since_turn_id
            if include_pc_turns:
                if since_turn_id > 0:
                    cursor.execute("""
                        SELECT id, user_input, thought_stream, final_response, affect_state,
                               timestamp, source_device, influence_weight, raw_response, turn_uuid
                        FROM interaction_history
                        WHERE id > ? AND source_device = 'pc'
                        ORDER BY id ASC
                        LIMIT 100
                    """, (since_turn_id,))
                else:
                    cursor.execute("""
                        SELECT id, user_input, thought_stream, final_response, affect_state,
                               timestamp, source_device, influence_weight, raw_response, turn_uuid
                        FROM interaction_history
                        WHERE timestamp > ? AND source_device = 'pc'
                        ORDER BY id ASC
                        LIMIT 100
                    """, (since_timestamp,))
                turn_rows = cursor.fetchall()
                for tr in turn_rows:
                    if tr["id"] > max_turn_id:
                        max_turn_id = tr["id"]
                    pc_turns.append({
                        "id": tr["id"],
                        "turn_uuid": tr["turn_uuid"] or f"turn_pc_{tr['id']}",
                        "user_input": tr["user_input"],
                        "thought_stream": tr["thought_stream"] or "",
                        "final_response": tr["final_response"] or "",
                        "raw_response": tr["raw_response"] or "",
                        "affect_state": json.loads(tr["affect_state"] or "{}"),
                        "timestamp": tr["timestamp"],
                        "source_device": tr["source_device"]
                    })

            return {
                "insights": insights,
                "pc_turns": pc_turns,
                "max_insight_id": max_insight_id,
                "max_turn_id": max_turn_id
            }

    # --- PHASE IV: CONTEXTUAL SANDBOX & QUARANTINE ---

    def quarantine_post(
        self,
        thread_id: Optional[int],
        author_id: str,
        author_name: str,
        author_type: str,
        content: str,
        intent_label: str = "pending",
        risk_score: float = 0.0
    ) -> int:
        """Stores untrusted inbound messageboard post into Quarantine Sandbox."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO quarantine_posts (
                    thread_id, author_id, author_name, author_type, content,
                    intent_label, risk_score, quarantined_at, status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'quarantined')
            """, (
                thread_id, author_id, author_name, author_type, content,
                intent_label, risk_score, int(time.time() * 1000)
            ))
            conn.commit()
            return cursor.lastrowid

    def get_quarantined_posts(self, status: str = "quarantined") -> List[Dict[str, Any]]:
        """Retrieves items in the sandbox awaiting moderation or cognitive evaluation."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, thread_id, author_id, author_name, author_type,
                       content, intent_label, risk_score, quarantined_at, status, rejection_reason
                FROM quarantine_posts
                WHERE status = ?
                ORDER BY quarantined_at ASC
            """, (status,))
            return [dict(r) for r in cursor.fetchall()]

    def resolve_quarantine_post(self, post_id: int, action: str, reason: str = "") -> Optional[int]:
        """
        Processes a quarantined post.
        If action == 'admit', moves post into active messageboard_posts table.
        If action == 'reject', updates status to 'rejected' with reason.
        """
        now = int(time.time() * 1000)
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM quarantine_posts WHERE id = ?", (post_id,))
            row = cursor.fetchone()
            if not row:
                return None

            if action == "admit":
                thread_id = row["thread_id"] or 1
                cursor.execute("""
                    INSERT INTO messageboard_posts (
                        thread_id, author_id, author_name, author_type, content, timestamp
                    ) VALUES (?, ?, ?, ?, ?, ?)
                """, (
                    thread_id, row["author_id"], row["author_name"],
                    row["author_type"], row["content"], now
                ))
                new_post_id = cursor.lastrowid

                # Update thread last active
                cursor.execute("UPDATE messageboard_threads SET last_active_at = ? WHERE id = ?", (now, thread_id))
                cursor.execute("UPDATE quarantine_posts SET status = 'admitted' WHERE id = ?", (post_id,))
                conn.commit()
                return new_post_id
            else:
                cursor.execute("""
                    UPDATE quarantine_posts SET status = 'rejected', rejection_reason = ? WHERE id = ?
                """, (reason, post_id))
                conn.commit()
                return None

    # --- PHASE IV: SOCIAL LAYER & AGENT PROFILES ---

    def create_thread(self, title: str, concept_family: str, creator_id: str) -> int:
        """Initializes a discussion thread under a concept family."""
        now = int(time.time() * 1000)
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO messageboard_threads (
                    title, concept_family, creator_id, created_at, last_active_at, status
                ) VALUES (?, ?, ?, ?, ?, 'active')
            """, (title, concept_family, creator_id, now, now))
            conn.commit()
            return cursor.lastrowid

    def get_threads(self, concept_family: Optional[str] = None) -> List[Dict[str, Any]]:
        """Lists active threads, optionally filtered by concept family."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            if concept_family:
                cursor.execute("""
                    SELECT t.*, COUNT(p.id) as post_count
                    FROM messageboard_threads t
                    LEFT JOIN messageboard_posts p ON t.id = p.thread_id
                    WHERE t.concept_family = ? AND t.status != 'archived'
                    GROUP BY t.id
                    ORDER BY t.last_active_at DESC
                """, (concept_family,))
            else:
                cursor.execute("""
                    SELECT t.*, COUNT(p.id) as post_count
                    FROM messageboard_threads t
                    LEFT JOIN messageboard_posts p ON t.id = p.thread_id
                    WHERE t.status != 'archived'
                    GROUP BY t.id
                    ORDER BY t.last_active_at DESC
                """)
            return [dict(r) for r in cursor.fetchall()]

    def get_thread_posts(self, thread_id: int) -> List[Dict[str, Any]]:
        """Retrieves verified posts for a discussion thread."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM messageboard_posts
                WHERE thread_id = ?
                ORDER BY timestamp ASC
            """, (thread_id,))
            return [dict(r) for r in cursor.fetchall()]

    def get_unsimmered_admitted_posts(self, limit: int = 25) -> List[Dict[str, Any]]:
        """Retrieves verified messageboard posts that have not yet been absorbed into DMN reflections."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT p.id, p.thread_id, p.author_name, p.author_type, p.content, p.timestamp, t.concept_family, t.title as thread_title
                FROM messageboard_posts p
                JOIN messageboard_threads t ON p.thread_id = t.id
                WHERE p.simmered = 0
                ORDER BY p.timestamp ASC
                LIMIT ?
            """, (limit,))
            return [dict(r) for r in cursor.fetchall()]

    def mark_posts_simmered(self, post_ids: List[int]):
        """Marks admitted messageboard posts as incorporated into DMN world model."""
        if not post_ids:
            return
        with self._get_connection() as conn:
            cursor = conn.cursor()
            placeholders = ",".join("?" for _ in post_ids)
            cursor.execute(f"UPDATE messageboard_posts SET simmered = 1 WHERE id IN ({placeholders})", post_ids)
            conn.commit()

    def get_concept_family_summary(self) -> List[Dict[str, Any]]:
        """Summarizes discussion distribution and emerging concept families."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT t.concept_family, COUNT(DISTINCT t.id) as thread_count, COUNT(p.id) as post_count
                FROM messageboard_threads t
                LEFT JOIN messageboard_posts p ON t.id = p.thread_id
                WHERE t.status != 'archived'
                GROUP BY t.concept_family
                ORDER BY post_count DESC, thread_count DESC
            """)
            return [dict(r) for r in cursor.fetchall()]

    @staticmethod
    def suggest_concept_family(text: str) -> str:
        """Categorizes discussion text into emerging concept taxonomy."""
        lowered = text.lower()
        if any(w in lowered for w in ["camera", "audio", "sensor", "vision", "vad", "perception", "gps", "location"]):
            return "sensory_grounding"
        if any(w in lowered for w in ["model", "runner", "llama", "latency", "offload", "gpu", "inference", "throughput"]):
            return "architecture"
        if any(w in lowered for w in ["emotion", "mood", "affect", "valence", "arousal", "dominance", "temperament", "identity"]):
            return "affect_and_identity"
        if any(w in lowered for w in ["security", "jailbreak", "adversarial", "firewall", "quarantine", "sandbox", "guardrail"]):
            return "security_guardrails"
        if any(w in lowered for w in ["reasoning", "thought", "dmn", "simmer", "deepcook", "cognition", "memory", "decay"]):
            return "cognition_and_dmn"
        return "general"

    def register_agent_profile(self, agent_id: str, name: str, temperament: str, stance: str):
        """Maintains agent identity registry for debate and autonomous social interaction."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO agent_profiles (
                    agent_id, name, temperament, stance, created_at
                ) VALUES (?, ?, ?, ?, ?)
            """, (agent_id, name, temperament, stance, int(time.time() * 1000)))
            conn.commit()

    def get_agent_profiles(self) -> List[Dict[str, Any]]:
        """Returns all registered agent identities."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM agent_profiles ORDER BY name ASC")
            return [dict(r) for r in cursor.fetchall()]

    # --- PHASE IV: RETENTION POLICY & DYNAMIC AFFECT GROUNDING ---

    def apply_memory_decay(self, decay_rate: float = 0.05, age_ms_threshold: int = 7 * 86400 * 1000) -> int:
        """Applies memory decay curve: older insights gradually lose importance unless reinforced."""
        cutoff = int(time.time() * 1000) - age_ms_threshold
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE distilled_insights
                SET importance_weight = MAX(0.1, ROUND(importance_weight * (1.0 - ?), 3))
                WHERE timestamp < ? AND importance_weight > 0.1
            """, (decay_rate, cutoff))
            conn.commit()
            return cursor.rowcount

    def get_dynamic_affect_grounding(self, recent_count: int = 3, sample_count: int = 3) -> Dict[str, Any]:
        """
        Weighted reading of prior conversations & insights:
        Combines recent turns with random historical samples to evolve dynamic mood and temperament.
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            # 1. Recent turns
            cursor.execute("""
                SELECT user_input, final_response, affect_state, timestamp
                FROM interaction_history
                ORDER BY timestamp DESC
                LIMIT ?
            """, (recent_count,))
            recent = [dict(r) for r in cursor.fetchall()]

            # 2. Random sample from historical pool
            cursor.execute("""
                SELECT user_input, final_response, affect_state, timestamp
                FROM interaction_history
                WHERE id NOT IN (
                    SELECT id FROM interaction_history ORDER BY timestamp DESC LIMIT ?
                )
                ORDER BY RANDOM()
                LIMIT ?
            """, (recent_count, sample_count))
            samples = [dict(r) for r in cursor.fetchall()]

            return {
                "recent_interactions": recent,
                "historical_samples": samples
            }

    # --- FAILED / UNFINISHED PROMPT BUFFER ---
    def buffer_failed_prompt(self, prompt_text: str, failure_reason: str = "model_offline", target_mode: str = "pc") -> int:
        """Buffers an unfinished prompt into SQLite queue."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO failed_prompt_buffer (prompt_text, target_mode, failure_reason, retry_count, timestamp, status)
                VALUES (?, ?, ?, 0, ?, 'pending')
            """, (prompt_text, target_mode, failure_reason, int(time.time() * 1000)))
            conn.commit()
            return cursor.lastrowid

    def get_pending_failed_prompts(self, target_mode: Optional[str] = None) -> List[Dict[str, Any]]:
        """Returns all pending unfinished prompts ordered by timestamp ASC."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            if target_mode:
                cursor.execute("""
                    SELECT id, prompt_text, target_mode, failure_reason, retry_count, timestamp, status
                    FROM failed_prompt_buffer
                    WHERE status = 'pending' AND target_mode = ?
                    ORDER BY timestamp ASC
                """, (target_mode,))
            else:
                cursor.execute("""
                    SELECT id, prompt_text, target_mode, failure_reason, retry_count, timestamp, status
                    FROM failed_prompt_buffer
                    WHERE status = 'pending'
                    ORDER BY timestamp ASC
                """)
            return [dict(row) for row in cursor.fetchall()]

    def mark_prompt_status(self, prompt_id: int, status: str = "flushed") -> bool:
        """Updates status of a buffered prompt ('flushed', 'discarded', 'pending')."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE failed_prompt_buffer
                SET status = ?
                WHERE id = ?
            """, (status, prompt_id))
            conn.commit()
            return cursor.rowcount > 0

    def get_pending_count(self, target_mode: Optional[str] = None) -> int:
        """Returns count of pending prompts in the buffer."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            if target_mode:
                cursor.execute("SELECT COUNT(*) FROM failed_prompt_buffer WHERE status = 'pending' AND target_mode = ?", (target_mode,))
            else:
                cursor.execute("SELECT COUNT(*) FROM failed_prompt_buffer WHERE status = 'pending'")
            row = cursor.fetchone()
            return row[0] if row else 0

