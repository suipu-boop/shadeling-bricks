"""agent-mail 连接器（M6 P0 单机版）—— 好友制邮件式异步通信积木。

设计依据：docs/m6-agent-mail.md（已拍板 spec）。
与 telegram.py / feishu.py 同构：Gateway 子类 + OFF by default + 常驻线程。

P0 单机版边界：
- 全部存储在本机 ~/.brickery/mail/（JSON Lines），不跨机；
- 投递 = 从 outbox 路由到各收件人 inbox/<handle>.jsonl；
- 异步投递队列：发送方先落 outbox，投递线程（或同步兜底）将其投递；
  失败重试走指数退避（2^attempts * 5s，上限 5 次后放弃并记 delivery_log）；
- 自主层级（L1-L4）判定：按配置层级对来信给出处理建议；
  敏感词（转账/付款/密码/删除等）一律降级为 ask；
- 护栏：单日自主执行上限（默认 50 次），超限拒绝并记 execution_log；
- enabled=false 默认不拉起（与 telegram 同构）。

存储布局（~/.brickery/mail/）：
  config.json              {enabled, autonomy_level, daily_limit, owner_handle}
  address_book.jsonl       {handle, display_name, created_at}
  groups.jsonl             {group, owner, members[], created_at}
  outbox.jsonl             待投递信封 {message_id, from, to[], cc[], subject, body,
                                       thread_id, reply_to, attempts, next_attempt_at, created_at}
  inbox/<handle>.jsonl     收件箱 {message_id, from, to[], cc[], subject, body,
                                   thread_id, reply_to, delivered_at, read}
  execution_log.jsonl      自主执行护栏日志 {ts, action, actor, handle, autonomy_level,
                                           decision, ok, reason}
  delivery_log.jsonl       投递日志 {ts, message_id, from, to, ok, error}

配置样例（~/.brickery/mail/config.json）：
  {
    "enabled": false,
    "autonomy_level": 3,
    "daily_limit": 50,
    "owner_handle": "me"
  }
"""
from __future__ import annotations

import datetime
import json
import logging
import os
import re
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from runtime.gateway import Gateway

logger = logging.getLogger("shadeling.connectors.agent_mail")

# --------------------------------------------------------------------------
# 常量与工具
# --------------------------------------------------------------------------

DEFAULT_MAIL_ROOT = Path.home() / ".brickery" / "mail"
DEFAULT_DAILY_LIMIT = 50
DEFAULT_AUTONOMY_LEVEL = 3
DEFAULT_OWNER_HANDLE = "me"

HANDLE_RE = re.compile(r"^[A-Za-z0-9_\-]{1,32}$")

# 自主层级标签（spec M6 §3.5）：
#   L1 仅通知；L2 汇总提示；L3 常规自主执行（默认）；L4 全自主执行。
LEVEL_LABELS: Dict[int, str] = {
    1: "notify",
    2: "summarize",
    3: "act",
    4: "act_always",
}

# 敏感词触发时无论层级一律降级 ask（避免自主误伤破坏性操作）
SENSITIVE_KEYWORDS = (
    "转账", "付款", "汇款", "付款码", "密码", "删除", "清空", "格式化", "销毁",
)

# outbox 重试：next_attempt_at = now + 2^attempts * RETRY_BASE_SECONDS；超过上限放弃
RETRY_BASE_SECONDS = 5
MAX_ATTEMPTS = 5


def _now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def _today_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")


def _new_id() -> str:
    return uuid.uuid4().hex[:16]


def _norm_handle(h: str) -> str:
    """归一化 @handle：去掉前导 @ 与空白。"""
    h = (h or "").strip()
    if h.startswith("@"):
        h = h[1:].strip()
    return h


# --------------------------------------------------------------------------
# 存储层（内核 handler 与常驻连接器共用）
# --------------------------------------------------------------------------

class AgentMailStore:
    """agent-mail 存储与投递（单机 ~/.brickery/mail/，JSON Lines）。"""

    def __init__(self, mail_root: Optional[Path] = None):
        env_root = os.environ.get("SHADELING_AGENT_MAIL_ROOT")
        if env_root:
            self.root = Path(env_root)
        else:
            self.root = Path(mail_root) if mail_root else DEFAULT_MAIL_ROOT
        self.root.mkdir(parents=True, exist_ok=True)
        (self.root / "inbox").mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    # ----- 基础文件工具 -----
    def _path(self, *parts: str) -> Path:
        return self.root.joinpath(*parts)

    def _append_jsonl(self, path: Path, obj: dict) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(obj, ensure_ascii=False) + "\n")

    def _read_jsonl(self, path: Path, reverse: bool = False) -> List[dict]:
        if not path.exists():
            return []
        rows = []
        with path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
        if reverse:
            rows.reverse()
        return rows

    def _rewrite_jsonl(self, path: Path, rows: List[dict]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        with tmp.open("w", encoding="utf-8") as f:
            for r in rows:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        tmp.replace(path)

    # ----- 配置 -----
    def load_config(self) -> dict:
        cfg_path = self._path("config.json")
        cfg = {
            "enabled": False,
            "autonomy_level": DEFAULT_AUTONOMY_LEVEL,
            "daily_limit": DEFAULT_DAILY_LIMIT,
            "owner_handle": DEFAULT_OWNER_HANDLE,
        }
        if cfg_path.exists():
            try:
                cfg.update(json.loads(cfg_path.read_text(encoding="utf-8")))
            except (json.JSONDecodeError, OSError):
                logger.warning("[agent-mail] config.json 解析失败，使用默认配置。")
        return cfg

    def save_config(self, cfg: dict) -> None:
        # 仅覆盖已知键，保留用户手工写的其它键
        base = self.load_config()
        base.update({k: v for k, v in cfg.items() if k in base})
        self._path("config.json").write_text(
            json.dumps(base, ensure_ascii=False, indent=2), encoding="utf-8")

    def get_owner(self) -> str:
        return _norm_handle(self.load_config().get("owner_handle") or DEFAULT_OWNER_HANDLE)

    def get_autonomy_level(self) -> int:
        try:
            return int(self.load_config().get("autonomy_level") or DEFAULT_AUTONOMY_LEVEL)
        except (TypeError, ValueError):
            return DEFAULT_AUTONOMY_LEVEL

    def get_daily_limit(self) -> int:
        try:
            return int(self.load_config().get("daily_limit") or DEFAULT_DAILY_LIMIT)
        except (TypeError, ValueError):
            return DEFAULT_DAILY_LIMIT

    # ----- 地址簿 -----
    def list_address_book(self) -> List[dict]:
        return self._read_jsonl(self._path("address_book.jsonl"), reverse=True)

    def add_address(self, handle: str, display_name: str = "") -> dict:
        h = _norm_handle(handle)
        if not HANDLE_RE.match(h):
            raise ValueError(f"非法 handle：{handle!r}（仅字母/数字/_/-，≤32 字符）")
        rows = self._read_jsonl(self._path("address_book.jsonl"))
        rows = [r for r in rows if r.get("handle") != h]
        rows.append({
            "handle": h,
            "display_name": display_name.strip(),
            "created_at": _now_iso(),
        })
        self._rewrite_jsonl(self._path("address_book.jsonl"), rows)
        return {"handle": h, "display_name": display_name.strip()}

    def remove_address(self, handle: str) -> bool:
        h = _norm_handle(handle)
        rows = self._read_jsonl(self._path("address_book.jsonl"))
        kept = [r for r in rows if r.get("handle") != h]
        if len(kept) == len(rows):
            return False
        self._rewrite_jsonl(self._path("address_book.jsonl"), kept)
        return True

    def has_address(self, handle: str) -> bool:
        h = _norm_handle(handle)
        return any(r.get("handle") == h
                   for r in self._read_jsonl(self._path("address_book.jsonl")))

    # ----- 群组 -----
    def list_groups(self) -> List[dict]:
        return self._read_jsonl(self._path("groups.jsonl"), reverse=True)

    def _get_group(self, group: str) -> Optional[dict]:
        g = group.strip()
        return next((r for r in self._read_jsonl(self._path("groups.jsonl"))
                     if r.get("group") == g), None)

    def create_group(self, group: str, members: List[str], owner: Optional[str] = None) -> dict:
        g = group.strip()
        if not g or not HANDLE_RE.match(g):
            raise ValueError(f"非法群组名：{group!r}")
        if self._get_group(g) is not None:
            raise ValueError(f"群组已存在：{g}")
        members = [_norm_handle(m) for m in (members or [])]
        for m in members:
            if not HANDLE_RE.match(m):
                raise ValueError(f"群组成员 handle 非法：{m!r}")
        row = {
            "group": g,
            "owner": _norm_handle(owner) if owner else self.get_owner(),
            "members": members,
            "created_at": _now_iso(),
        }
        self._append_jsonl(self._path("groups.jsonl"), row)
        return row

    def update_group_members(self, group: str, members: List[str], action: str) -> dict:
        """action: add_member / remove_member。"""
        rows = self._read_jsonl(self._path("groups.jsonl"))
        row = next((r for r in rows if r.get("group") == group), None)
        if row is None:
            raise ValueError(f"群组不存在：{group}")
        members = [_norm_handle(m) for m in (members or [])]
        cur = list(row.get("members") or [])
        if action == "add_member":
            for m in members:
                if not HANDLE_RE.match(m):
                    raise ValueError(f"群组成员 handle 非法：{m!r}")
                if m not in cur:
                    cur.append(m)
        elif action == "remove_member":
            cur = [m for m in cur if m not in members]
        else:
            raise ValueError(f"未知群组动作：{action}")
        row["members"] = cur
        for i, r in enumerate(rows):
            if r.get("group") == group:
                rows[i] = row
        self._rewrite_jsonl(self._path("groups.jsonl"), rows)
        return row

    def delete_group(self, group: str) -> bool:
        rows = self._read_jsonl(self._path("groups.jsonl"))
        kept = [r for r in rows if r.get("group") != group]
        if len(kept) == len(rows):
            return False
        self._rewrite_jsonl(self._path("groups.jsonl"), kept)
        return True

    def _resolve_recipients(self, to: Optional[Any], cc: Optional[Any],
                            group: Optional[str]) -> tuple:
        """解析收件人集合（to + group 展开 + cc），返回 (recipients, cc_set)。"""
        recips: List[str] = []
        cc_set: List[str] = []

        def _flat(v: Any) -> List[str]:
            if v is None:
                return []
            if isinstance(v, str):
                return [x.strip() for x in v.replace("，", ",").split(",") if x.strip()]
            if isinstance(v, list):
                return [_norm_handle(x) for x in v if str(x).strip()]
            return []

        for h in _flat(to):
            recips.append(_norm_handle(h))
        if group:
            g = group.strip()
            row = self._get_group(g)
            if row is None:
                raise ValueError(f"群组不存在：{g}（请先经 mail_group 创建）")
            for m in row.get("members") or []:
                if m not in recips:
                    recips.append(m)
        for h in _flat(cc):
            hh = _norm_handle(h)
            if hh not in recips:
                recips.append(hh)
                cc_set.append(hh)
        # 去重保序
        seen = set()
        recips = [h for h in recips if not (h in seen or seen.add(h))]
        if not recips:
            raise ValueError("收件人为空：请提供 to / group / cc 至少一项")
        for h in recips:
            if not HANDLE_RE.match(h):
                raise ValueError(f"非法收件人 handle：{h!r}")
        return recips, cc_set

    # ----- 自主层级判定与护栏 -----
    def classify_autonomy(self, message: dict) -> str:
        """按配置自主层级对一封来信给出处理建议（spec M6 §3.5）。"""
        level = self.get_autonomy_level()
        text = " ".join([str(message.get("subject") or ""),
                         str(message.get("body") or "")])
        if any(k in text for k in SENSITIVE_KEYWORDS):
            return "ask"
        return LEVEL_LABELS.get(level, "act")

    def count_autonomous_today(self) -> int:
        """今日自主执行（action=mail_send 且 autonomy=true 且 ok）次数。"""
        today = _today_iso()
        n = 0
        for r in self._read_jsonl(self._path("execution_log.jsonl")):
            if (r.get("action") == "mail_send"
                    and r.get("autonomy") is True
                    and r.get("ok") is True
                    and str(r.get("ts", "")).startswith(today)):
                n += 1
        return n

    def log_execution(self, *, action: str, actor: str, handle: str = "",
                      autonomy: bool = False, decision: str = "",
                      ok: bool = True, reason: str = "") -> None:
        """写自主执行日志（护栏审计）。"""
        self._append_jsonl(self._path("execution_log.jsonl"), {
            "ts": _now_iso(),
            "action": action,
            "actor": actor,
            "handle": handle,
            "autonomy": bool(autonomy),
            "autonomy_level": self.get_autonomy_level(),
            "decision": decision,
            "ok": bool(ok),
            "reason": reason,
        })

    def check_daily_limit(self) -> bool:
        """护栏：今日自主执行次数是否已达上限（True=未超限可执行）。"""
        limit = self.get_daily_limit()
        used = self.count_autonomous_today()
        return used < limit

    # ----- 发送与投递 -----
    def send_mail(self, *, sender: str, to: Optional[Any] = None, cc: Optional[Any] = None,
                  group: Optional[str] = None, subject: str = "", body: str = "",
                  reply_to: Optional[str] = None, thread_id: Optional[str] = None,
                  autonomy: bool = False) -> dict:
        """发送一封邮件：落 outbox 并同步兜底投递。

        返回 {message_id, from, to, cc, recipients, delivery}。
        自主执行（autonomy=True）先过单日上限护栏。
        """
        sender = _norm_handle(sender) or self.get_owner()
        if not HANDLE_RE.match(sender):
            raise ValueError(f"非法发件人 handle：{sender!r}")
        if not subject.strip() and not body.strip():
            raise ValueError("主题与正文不能同时为空")
        recips, cc_set = self._resolve_recipients(to, cc, group)

        # 护栏：自主执行先查单日上限
        decision = ""
        if autonomy:
            if not self.check_daily_limit():
                self.log_execution(
                    action="mail_send", actor=sender, handle=sender,
                    autonomy=True, decision="denied",
                    ok=False, reason="daily_limit_reached")
                raise ValueError(
                    f"单日自主执行上限已达（{self.get_daily_limit()} 次），已拒绝本次自主发信")
            decision = "act" if self.get_autonomy_level() >= 3 else "notify"

        message_id = _new_id()
        env = {
            "message_id": message_id,
            "from": sender,
            "to": [_norm_handle(h) for h in recips],
            "cc": cc_set,
            "subject": subject.strip(),
            "body": body.strip(),
            "thread_id": thread_id or message_id,
            "reply_to": reply_to,
            "attempts": 0,
            "next_attempt_at": _now_iso(),
            "created_at": _now_iso(),
        }
        with self._lock:
            self._append_jsonl(self._path("outbox.jsonl"), env)
            delivery = self.deliver_pending()
        self.log_execution(
            action="mail_send", actor=sender, handle=sender,
            autonomy=autonomy, decision=decision, ok=True,
            reason=f"to={recips}")
        return {
            "message_id": message_id,
            "from": sender,
            "to": recips,
            "cc": cc_set,
            "recipients": recips,
            "delivery": delivery,
        }

    def deliver_pending(self) -> dict:
        """把 outbox 中到期待投递的信封投递到各收件人 inbox。

        同步兜底投递由发送方调用；常驻线程周期调用负责失败重试。
        投递成功即从 outbox 移除；失败留在 outbox 按指数退避重试。
        """
        rows = self._read_jsonl(self._path("outbox.jsonl"))
        now = _now_iso()
        kept: List[dict] = []
        delivered = 0
        failed = 0
        dropped = 0
        for env in rows:
            mid = env.get("message_id")
            # 未到重试时间则保留
            if env.get("next_attempt_at", "") > now:
                kept.append(env)
                continue
            ok_all = True
            for h in env.get("to") or []:
                try:
                    self._append_jsonl(self._path("inbox", f"{h}.jsonl"), {
                        "message_id": mid,
                        "from": env.get("from"),
                        "to": env.get("to"),
                        "cc": env.get("cc") or [],
                        "subject": env.get("subject") or "",
                        "body": env.get("body") or "",
                        "thread_id": env.get("thread_id"),
                        "reply_to": env.get("reply_to"),
                        "delivered_at": now,
                        "read": False,
                    })
                    self._append_jsonl(self._path("delivery_log.jsonl"), {
                        "ts": now, "message_id": mid,
                        "from": env.get("from"), "to": h,
                        "ok": True, "error": "",
                    })
                except OSError as e:
                    ok_all = False
                    self._append_jsonl(self._path("delivery_log.jsonl"), {
                        "ts": now, "message_id": mid,
                        "from": env.get("from"), "to": h,
                        "ok": False, "error": str(e),
                    })
                    break
            if ok_all:
                delivered += 1
                continue  # 从 outbox 移除
            # 失败：指数退避重试，超上限放弃
            attempts = int(env.get("attempts") or 0) + 1
            if attempts >= MAX_ATTEMPTS:
                dropped += 1
                self._append_jsonl(self._path("delivery_log.jsonl"), {
                    "ts": now, "message_id": mid,
                    "from": env.get("from"), "to": env.get("to"),
                    "ok": False, "error": f"delivery_failed_after_{attempts}_attempts",
                })
                continue
            env["attempts"] = attempts
            wait = RETRY_BASE_SECONDS * (2 ** (attempts - 1))
            env["next_attempt_at"] = (
                datetime.datetime.now(datetime.timezone.utc)
                + datetime.timedelta(seconds=wait)).isoformat()
            kept.append(env)
            failed += 1
        self._rewrite_jsonl(self._path("outbox.jsonl"), kept)
        return {"delivered": delivered, "failed": failed, "dropped": dropped,
                "pending": len(kept)}

    # ----- 收件箱 -----
    def read_inbox(self, handle: Optional[str] = None, *, limit: int = 20,
                   offset: int = 0, mark_read: bool = False,
                   unread_only: bool = False,
                   since: Optional[str] = None) -> dict:
        h = _norm_handle(handle) or self.get_owner()
        if not HANDLE_RE.match(h):
            raise ValueError(f"非法 handle：{h!r}")
        rows = self._read_jsonl(self._path("inbox", f"{h}.jsonl"), reverse=True)
        if since:
            rows = [r for r in rows if r.get("delivered_at", "") >= since]
        if unread_only:
            rows = [r for r in rows if not r.get("read")]
        total = len(rows)
        page = rows[offset:offset + max(0, limit)]
        ids = [r.get("message_id") for r in page if r.get("message_id")]
        if mark_read and ids:
            self.mark_read(h, ids)
        return {"handle": h, "total": total, "returned": len(page),
                "messages": page, "marked_read": ids if mark_read else []}

    def mark_read(self, handle: str, message_ids: List[str]) -> int:
        h = _norm_handle(handle)
        path = self._path("inbox", f"{h}.jsonl")
        rows = self._read_jsonl(path)
        marked = 0
        for r in rows:
            if r.get("message_id") in message_ids and not r.get("read"):
                r["read"] = True
                marked += 1
        if marked:
            self._rewrite_jsonl(path, rows)
        return marked

    # ----- 审计视图 -----
    def stats(self) -> dict:
        inbox_counts = {}
        inbox_dir = self._path("inbox")
        if inbox_dir.is_dir():
            for p in sorted(inbox_dir.glob("*.jsonl")):
                rows = self._read_jsonl(p)
                inbox_counts[p.stem] = {"total": len(rows),
                                        "unread": sum(1 for r in rows if not r.get("read"))}
        return {
            "owner": self.get_owner(),
            "autonomy_level": self.get_autonomy_level(),
            "daily_limit": self.get_daily_limit(),
            "autonomous_today": self.count_autonomous_today(),
            "address_book": len(self._read_jsonl(self._path("address_book.jsonl"))),
            "groups": len(self._read_jsonl(self._path("groups.jsonl"))),
            "inbox": inbox_counts,
            "pending_outbox": len(self._read_jsonl(self._path("outbox.jsonl"))),
            "mail_root": str(self.root),
        }


# --------------------------------------------------------------------------
# 常驻投递服务（Gateway 同构：enabled=false 默认不拉起）
# --------------------------------------------------------------------------

class AgentMailConnector(Gateway):
    name = "agent_mail"

    def __init__(self, mail_root: Optional[Path] = None):
        self.store = AgentMailStore(mail_root)
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()

    def on_start(self) -> None:
        cfg = self.store.load_config()
        if not cfg.get("enabled"):
            logger.info("[agent-mail] 未启用（enabled=false），不拉起投递服务。")
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        logger.info("[agent-mail] 投递服务已拉起（autonomy_level=%s，daily_limit=%s）。",
                    self.store.get_autonomy_level(), self.store.get_daily_limit())

    def on_stop(self) -> None:
        self._stop.set()
        logger.info("[agent-mail] 投递服务已停止。")

    def _run(self) -> None:
        """常驻投递循环：周期扫描 outbox 投递 + 写投递日志。"""
        while not self._stop.is_set():
            try:
                res = self.store.deliver_pending()
                if res["delivered"]:
                    logger.info("[agent-mail] 常驻投递：%s", res)
            except Exception as e:  # noqa: BLE001
                logger.error("[agent-mail] 投递异常：%s", e)
            # 指数退避感知：短轮询 10s；若有失败重试项交给 deliver_pending 的 next_attempt_at 控制
            self._stop.wait(10)


__all__ = ["AgentMailStore", "AgentMailConnector", "DEFAULT_MAIL_ROOT"]
