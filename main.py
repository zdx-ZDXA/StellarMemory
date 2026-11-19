# -*- coding: utf-8 -*-
"""StellarMemory —— 星忆，记忆数据层 v1.0.1

**完全兼容 Astrbot_Amo_data 的表结构**，可直接复制数据库迁移。

迁移方法：
    cp ~/.astrbot/data/Astr_Amo_data/amo_data.db \
       ~/.astrbot/data/StellarMemory/stellar_memory.db

表结构对照（与 Astrbot_Amo_data/store_schema.py 一致）：
  memories   id / bot_id / uid / scope / group_id / kind / content /
             importance / hit_count / created_at / last_hit_at /
             idem_key / status / superseded_by
  profiles   bot_id / uid / name / alias / relation / remark / updated_at
  wardrobe   bot_id / id / name / slot / scenes / gender / note /
             enabled / created / updated_at
"""
from __future__ import annotations

import asyncio
import json
import os
import sqlite3
import time
from typing import Any, Dict, List, Optional

try:
    from astrbot.api import logger
    from astrbot.api.star import Context, Star
except ImportError:
    raise

PLUGIN_VERSION = "1.0.1"

# 与 Astrbot_Amo_data 完全一致的表结构
_DDL = """
CREATE TABLE IF NOT EXISTS profiles (
    bot_id TEXT NOT NULL,
    uid TEXT NOT NULL,
    name TEXT DEFAULT '',
    alias TEXT DEFAULT '',
    relation TEXT DEFAULT '',
    remark TEXT DEFAULT '',
    updated_at INTEGER NOT NULL,
    PRIMARY KEY (bot_id, uid)
);

CREATE TABLE IF NOT EXISTS memories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    bot_id TEXT NOT NULL,
    uid TEXT NOT NULL,
    scope TEXT NOT NULL DEFAULT 'private',
    group_id TEXT DEFAULT '',
    kind TEXT DEFAULT 'fact',
    content TEXT NOT NULL,
    importance REAL DEFAULT 0.5,
    hit_count INTEGER DEFAULT 0,
    created_at INTEGER NOT NULL,
    last_hit_at INTEGER NOT NULL,
    idem_key TEXT DEFAULT '',
    status TEXT DEFAULT 'active',
    superseded_by INTEGER DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_mem_uid
    ON memories(bot_id, uid, scope, group_id, status);
CREATE INDEX IF NOT EXISTS idx_mem_time
    ON memories(bot_id, uid, created_at);

CREATE TABLE IF NOT EXISTS wardrobe (
    bot_id TEXT NOT NULL DEFAULT '',
    id TEXT NOT NULL,
    name TEXT NOT NULL DEFAULT '',
    slot TEXT NOT NULL DEFAULT '',
    scenes TEXT NOT NULL DEFAULT '[]',
    gender TEXT NOT NULL DEFAULT '通用',
    note TEXT NOT NULL DEFAULT '',
    enabled INTEGER NOT NULL DEFAULT 1,
    created REAL NOT NULL DEFAULT 0,
    updated_at INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (bot_id, id)
);
CREATE INDEX IF NOT EXISTS idx_wardrobe_bot ON wardrobe(bot_id, enabled);
"""


class StellarMemory(Star):
    def __init__(self, context: Context, config: Dict[str, Any] | None = None) -> None:
        super().__init__(context)
        cfg = config or {}
        db_path = str(cfg.get("db_path") or "")
        if not db_path:
            data_dir = os.path.join(
                os.path.expanduser("~"), ".astrbot", "data", "StellarMemory"
            )
            os.makedirs(data_dir, exist_ok=True)
            db_path = os.path.join(data_dir, "stellar_memory.db")
        self._db_path = db_path
        self._conn: Optional[sqlite3.Connection] = None
        self._lock = asyncio.Lock()
        self._recall_limit: int = max(1, min(50, int(cfg.get("recall_limit") or 6)))
        self._bot_id: str = str(cfg.get("bot_id") or "")
        logger.info(f"[StellarMemory] v{PLUGIN_VERSION} DB={db_path}")

    async def initialize(self) -> None:
        try:
            self._open()
            logger.info(f"[StellarMemory] 数据库已就绪（{self._db_path}）")
        except Exception as e:
            logger.error(f"[StellarMemory] 数据库初始化失败: {e}")

    async def terminate(self) -> None:
        if self._conn is not None:
            try:
                self._conn.close()
            except Exception:
                pass
            self._conn = None

    def _open(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = sqlite3.connect(self._db_path, check_same_thread=False)
            self._conn.row_factory = sqlite3.Row
            self._conn.executescript(_DDL)
            self._conn.commit()
        return self._conn

    def _bot(self, bot_id: str = "") -> str:
        return str(bot_id or self._bot_id or "")

    # ------------------------------------------------------------------
    # 记忆：recall / save（兼容 Amo_data 签名）
    # ------------------------------------------------------------------
    async def recall(
        self,
        bot_id: str,
        uid: str,
        query: str = "",
        limit: int = 6,
        scope: str = "",
        group_id: str = "",
    ) -> List[Dict]:
        """召回记忆。签名与 Astrbot_Amo_data.recall 一致。

        返回字段：content / kind / importance / created_at / id
        按「scope + group_id 隔离」，私聊读不到群聊。
        """
        if not uid:
            return []
        limit = max(1, min(limit or self._recall_limit, 50))
        bot = self._bot(bot_id)

        async with self._lock:
            try:
                db = self._open()
                params: List[Any] = [bot, str(uid)]
                where = "bot_id=? AND uid=? AND status='active'"
                if scope:
                    where += " AND scope=?"
                    params.append(str(scope))
                    if str(scope) == "group":
                        where += " AND group_id=?"
                        params.append(str(group_id or ""))
                    else:
                        # 私聊：只拿 private，且不串群
                        where += " AND (group_id='' OR group_id IS NULL)"
                rows = db.execute(
                    f"""
                    SELECT id, content, kind, importance, created_at, scope, group_id
                    FROM memories
                    WHERE {where}
                    ORDER BY importance DESC, created_at DESC
                    LIMIT ?
                    """,
                    (*params, limit),
                ).fetchall()
                if rows:
                    ids = [r["id"] for r in rows]
                    marks = ",".join("?" * len(ids))
                    db.execute(
                        f"UPDATE memories SET hit_count=hit_count+1, last_hit_at=? "
                        f"WHERE id IN ({marks})",
                        (int(time.time()), *ids),
                    )
                    db.commit()
                return [dict(r) for r in rows]
            except Exception as e:
                logger.debug(f"[StellarMemory] recall 失败: {e}")
                return []

    async def save(
        self,
        bot_id: str,
        uid: str,
        content: str,
        kind: str = "fact",
        importance: float = 0.5,
        scope: str = "private",
        group_id: str = "",
        idem_key: str = "",
    ) -> bool:
        """保存记忆。签名兼容 Amo_data。

        idem_key 非空时做去重：同 bot+uid+idem_key 只保留一条。
        """
        if not uid or not content:
            return False
        bot = self._bot(bot_id)
        content = str(content)[:2000]
        now = int(time.time())

        async with self._lock:
            try:
                db = self._open()
                if idem_key:
                    exist = db.execute(
                        "SELECT id FROM memories "
                        "WHERE bot_id=? AND uid=? AND idem_key=? AND status='active'",
                        (bot, str(uid), str(idem_key)),
                    ).fetchone()
                    if exist:
                        db.execute(
                            "UPDATE memories SET content=?, importance=?, last_hit_at=? "
                            "WHERE id=?",
                            (content, float(importance), now, exist["id"]),
                        )
                        db.commit()
                        return True
                db.execute(
                    """
                    INSERT INTO memories
                      (bot_id, uid, scope, group_id, kind, content,
                       importance, hit_count, created_at, last_hit_at,
                       idem_key, status, superseded_by)
                    VALUES (?,?,?,?,?,?,?,0,?,?,?,'active',0)
                    """,
                    (bot, str(uid), str(scope or "private"), str(group_id or ""),
                     str(kind or "fact"), content, float(importance),
                     now, now, str(idem_key or "")),
                )
                db.commit()
                return True
            except Exception as e:
                logger.debug(f"[StellarMemory] save 失败: {e}")
                return False

    # ------------------------------------------------------------------
    # 画像
    # ------------------------------------------------------------------
    async def profile_get(self, bot_id: str, uid: str) -> Dict:
        async with self._lock:
            try:
                row = self._open().execute(
                    "SELECT * FROM profiles WHERE bot_id=? AND uid=?",
                    (self._bot(bot_id), str(uid)),
                ).fetchone()
                return dict(row) if row else {}
            except Exception:
                return {}

    async def profile_save(self, bot_id: str, uid: str, **fields) -> bool:
        if not uid:
            return False
        bot = self._bot(bot_id)
        now = int(time.time())
        allowed = ("name", "alias", "relation", "remark")
        data = {k: str(v) for k, v in fields.items() if k in allowed}
        async with self._lock:
            try:
                db = self._open()
                if data:
                    cols = ", ".join(f"{k}=?" for k in data)
                    db.execute(
                        f"INSERT INTO profiles (bot_id, uid, updated_at) "
                        f"VALUES (?,?,?) "
                        f"ON CONFLICT(bot_id, uid) DO UPDATE SET {cols}, updated_at=?",
                        (bot, str(uid), now, *data.values(), now),
                    )
                else:
                    db.execute(
                        "INSERT OR IGNORE INTO profiles (bot_id, uid, updated_at) "
                        "VALUES (?,?,?)",
                        (bot, str(uid), now),
                    )
                db.commit()
                return True
            except Exception as e:
                logger.debug(f"[StellarMemory] profile_save 失败: {e}")
                return False

    # ------------------------------------------------------------------
    # 衣柜（兼容 Amo_data wardrobe 表）
    # ------------------------------------------------------------------
    async def wardrobe_list(self, bot_id: str = "") -> List[Dict]:
        async with self._lock:
            try:
                rows = self._open().execute(
                    "SELECT * FROM wardrobe WHERE bot_id=? AND enabled=1 "
                    "ORDER BY created ASC",
                    (self._bot(bot_id),),
                ).fetchall()
                out = []
                for r in rows:
                    item = dict(r)
                    try:
                        item["scenes"] = json.loads(item.get("scenes") or "[]")
                    except Exception:
                        item["scenes"] = []
                    out.append(item)
                return out
            except Exception as e:
                logger.debug(f"[StellarMemory] wardrobe_list 失败: {e}")
                return []

    async def wardrobe_save(self, item: Dict, bot_id: str = "") -> bool:
        if not item.get("id") or not item.get("name"):
            return False
        bot = self._bot(bot_id)
        now = int(time.time())
        async with self._lock:
            try:
                db = self._open()
                db.execute(
                    """
                    INSERT INTO wardrobe
                      (bot_id, id, name, slot, scenes, gender, note, enabled, created, updated_at)
                    VALUES (?,?,?,?,?,?,?,?,?,?)
                    ON CONFLICT(bot_id, id) DO UPDATE SET
                      name=excluded.name, slot=excluded.slot, scenes=excluded.scenes,
                      gender=excluded.gender, note=excluded.note,
                      enabled=excluded.enabled, updated_at=excluded.updated_at
                    """,
                    (bot, item["id"], item["name"],
                     item.get("slot", "dress"),
                     json.dumps(item.get("scenes") or [], ensure_ascii=False),
                     item.get("gender", "通用"),
                     item.get("note", ""),
                     int(item.get("enabled", 1)),
                     float(item.get("created") or time.time()),
                     now),
                )
                db.commit()
                return True
            except Exception as e:
                logger.debug(f"[StellarMemory] wardrobe_save 失败: {e}")
                return False

    async def wardrobe_delete(self, item_id: str, bot_id: str = "") -> bool:
        """软删除（enabled=0），与 Amo_data 一致。"""
        async with self._lock:
            try:
                db = self._open()
                db.execute(
                    "UPDATE wardrobe SET enabled=0, updated_at=? "
                    "WHERE bot_id=? AND id=?",
                    (int(time.time()), self._bot(bot_id), str(item_id)),
                )
                db.commit()
                return True
            except Exception as e:
                logger.debug(f"[StellarMemory] wardrobe_delete 失败: {e}")
                return False

    # ------------------------------------------------------------------
    # 迁移辅助
    # ------------------------------------------------------------------
    async def migrate_from(self, source_db: str, bot_id: str = "") -> Dict:
        """从 Amo_data 数据库复制 memories / profiles / wardrobe。

        用法：/stellar_migrate /path/to/amo_data.db
        """
        if not os.path.isfile(source_db):
            return {"ok": False, "msg": f"找不到文件：{source_db}"}
        stats = {"memories": 0, "profiles": 0, "wardrobe": 0}
        try:
            src = sqlite3.connect(source_db)
            src.row_factory = sqlite3.Row
        except Exception as e:
            return {"ok": False, "msg": f"打开源库失败：{e}"}

        async with self._lock:
            try:
                db = self._open()
                for table, cols in (
                    ("memories", ("bot_id", "uid", "scope", "group_id", "kind",
                                  "content", "importance", "hit_count", "created_at",
                                  "last_hit_at", "idem_key", "status", "superseded_by")),
                    ("profiles", ("bot_id", "uid", "name", "alias", "relation",
                                  "remark", "updated_at")),
                    ("wardrobe", ("bot_id", "id", "name", "slot", "scenes", "gender",
                                  "note", "enabled", "created", "updated_at")),
                ):
                    try:
                        rows = src.execute(f"SELECT * FROM {table}").fetchall()
                    except Exception:
                        continue
                    for row in rows:
                        data = {}
                        for c in cols:
                            try:
                                data[c] = row[c]
                            except Exception:
                                data[c] = None
                        # bot_id 归一
                        data["bot_id"] = self._bot(data.get("bot_id") or bot_id)
                        placeholders = ",".join("?" * len(cols))
                        colnames = ",".join(cols)
                        if table in ("memories", "wardrobe"):
                            # 跳过主键冲突（id 自增 / 复合主键）
                            if table == "memories":
                                data.pop("id", None)
                            db.execute(
                                f"INSERT OR IGNORE INTO {table} ({colnames}) "
                                f"VALUES ({placeholders})",
                                tuple(data[c] for c in cols),
                            )
                        else:
                            db.execute(
                                f"INSERT INTO {table} ({colnames}) "
                                f"VALUES ({placeholders}) "
                                f"ON CONFLICT(bot_id, uid) DO UPDATE SET "
                                f"name=excluded.name, alias=excluded.alias, "
                                f"relation=excluded.relation, remark=excluded.remark, "
                                f"updated_at=excluded.updated_at",
                                tuple(data[c] for c in cols),
                            )
                        stats[table] += 1
                src.close()
                db.commit()
                return {"ok": True, "stats": stats}
            except Exception as e:
                return {"ok": False, "msg": str(e), "stats": stats}