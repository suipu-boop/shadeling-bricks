"""Telegram 连接器（TelegramConnector）—— Telegram 官方 Bot ↔ 本地 Shadeling 的文本桥。

设计要点（与飞书连接器同构，见 docs/connectors_feishu_design.md）：
- 用 Telegram 官方 Bot API（getUpdates 长轮询 + sendMessage），纯标准库 urllib 实现，
  免公网 IP、免费、无第三方依赖、无合规风险。个人微信无官方 API，故不做。
- 连接器是 IpcServer 的 127.0.0.1 客户端，复用与 Swift UI 相同的 IPC 契约。
- 记忆/会话落在 ~/.brickery，与桌面 UI 共享同一库。
- 白名单：仅响应 allowed_user_ids 中的 Telegram user_id（或 userId+@ 前缀）。
- 凭据存 ~/.brickery/config/telegram.json，不进 git、不进记忆库。
- OFF by default。

配置样例（~/.brickery/config/telegram.json）：
  {
    "enabled": true,
    "bot_token": "123456:AA...",   // 由 @BotFather 创建 bot 获得
    "allowed_user_ids": [],         // 空 + auto_bind_owner=true = 首个向 bot 说话的人自动成为所有者
    "auto_bind_owner": true,
    "session_prefix": "telegram_",
    "api_base": "https://api.telegram.org"   // 默认官方端点；可改镜像
  }
"""
from __future__ import annotations

import json
import logging
import socket
import threading
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, List, Optional

from ..gateway import Gateway
from ..ipc import DEFAULT_PORT
from ..paths import get_config_dir

logger = logging.getLogger("shadeling.connectors.telegram")


# --------------------------------------------------------------------------
# 1. IPC 客户端（127.0.0.1，与 Swift UI 同契约）
# --------------------------------------------------------------------------
class IpcClient:
    """最小 IPC 客户端：连本机 IpcServer，发 JSON 行请求，读回 JSON 行响应。

    协议（与 runtime/ipc.py:_dispatch 一致）：
      请求 {"req_id":N, "method":"chat", "params":{...}}
      响应 {"req_id":N, "ok":true, "data":{...}} | {"req_id":N,"ok":false,"error":"..."}
    """

    def __init__(self, host: str = "127.0.0.1", port: int = DEFAULT_PORT, timeout: float = 60.0):
        self.host = host
        self.port = port
        self.timeout = timeout
        self._req_id = 0
        self._lock = threading.Lock()

    def _next_id(self) -> int:
        with self._lock:
            self._req_id += 1
            return self._req_id

    def request(self, method: str, params: Optional[dict] = None, timeout: Optional[float] = None) -> dict:
        """发送一次 IPC 请求，返回 handler 的 data dict；失败抛 RuntimeError。"""
        timeout = timeout or self.timeout
        req = {"req_id": self._next_id(), "method": method, "params": params or {}}
        payload = (json.dumps(req, ensure_ascii=False) + "\n").encode("utf-8")
        try:
            with socket.create_connection((self.host, self.port), timeout=timeout) as sock:
                sock.sendall(payload)
                buf = b""
                while b"\n" not in buf:
                    chunk = sock.recv(4096)
                    if not chunk:
                        break
                    buf += chunk
                line = buf.split(b"\n", 1)[0]
                resp = json.loads(line.decode("utf-8"))
        except Exception as e:  # noqa: BLE001
            raise RuntimeError(f"IPC 调用 {method} 失败：{e}") from e
        if not resp.get("ok"):
            raise RuntimeError(resp.get("error", f"IPC {method} 返回错误"))
        return resp.get("data", {})

    def chat(self, message: str, session_id: Optional[str] = None, project: str = "") -> dict:
        return self.request("chat", {"message": message, "session_id": session_id, "project": project})

    def chat_cancel(self) -> dict:
        return self.request("chat_cancel", {})


# --------------------------------------------------------------------------
# 2. 配置
# --------------------------------------------------------------------------
@dataclass
class TelegramConfig:
    enabled: bool = False
    bot_token: str = ""
    allowed_user_ids: List[str] = field(default_factory=list)
    session_prefix: str = "telegram_"
    api_base: str = "https://api.telegram.org"
    # 极简引导：第一个向 bot 说话的 Telegram 账号自动成为授权用户。
    auto_bind_owner: bool = True
    # 长轮询超时（秒）。Telegram 建议 30–50；越大越省请求，但轮询中断延后越久。
    long_poll_timeout: int = 30

    @classmethod
    def load(cls, path: Path) -> "TelegramConfig":
        p = Path(path)
        if not p.exists():
            # 默认 OFF：无配置文件即不启用
            return cls()
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as e:
            logger.warning("Telegram 配置读取失败，连接器不启用：%s", e)
            return cls()
        return cls(
            enabled=bool(data.get("enabled", False)),
            bot_token=data.get("bot_token", ""),
            allowed_user_ids=list(data.get("allowed_user_ids", [])),
            session_prefix=data.get("session_prefix", "telegram_"),
            api_base=data.get("api_base", "https://api.telegram.org"),
            auto_bind_owner=bool(data.get("auto_bind_owner", True)),
            long_poll_timeout=int(data.get("long_poll_timeout", 30)),
        )


# --------------------------------------------------------------------------
# 3. Telegram 传输层（真实协议隔离；endpoint 可配置）
# --------------------------------------------------------------------------
class TelegramTransport:
    """封装 Telegram Bot API：getUpdates 长轮询 + sendMessage。

    所有 endpoint 集中在此，便于按官方文档校正。
    单测用 mock（send_hook / fake updates），不依赖真实 Telegram。
    """

    def __init__(self, config: TelegramConfig,
                 send_hook: Optional[Callable[[dict, str], None]] = None):
        self.config = config
        self._send_hook = send_hook
        self._stop = threading.Event()
        self._offset: Optional[int] = None  # 已确认处理的最大 update_id

    # --- HTTP 请求封装（纯 stdlib urllib）---
    def _get(self, method: str, params: Optional[dict] = None) -> dict:
        url = f"{self.config.api_base}/bot{self.config.bot_token}/{method}"
        if params:
            qs = "&".join(f"{k}={urllib.parse.quote(str(v))}" for k, v in params.items())
            url = f"{url}?{qs}"
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        if not data.get("ok"):
            raise RuntimeError(f"Telegram {method} 返回错误：{data}")
        return data.get("result", [])

    # --- 长轮询拉取更新 ---
    def run_loop(self, on_update: Callable[[dict], None], stop_event: threading.Event) -> None:
        """持续 getUpdates 长轮询，把每条 update 交给 on_update。可被 stop_event 中断。"""
        import urllib.parse
        self._stop = stop_event
        while not stop_event.is_set():
            params = {
                "timeout": self.config.long_poll_timeout,
                "offset": self._offset + 1 if self._offset is not None else None,
            }
            # 过滤掉 None（首轮 offset 为空即为全新拉取）
            params = {k: v for k, v in params.items() if v is not None}
            try:
                updates = self._get("getUpdates", params)
            except (urllib.error.URLError, urllib.error.HTTPError, OSError, RuntimeError) as e:
                if stop_event.is_set():
                    break
                logger.warning("[telegram] getUpdates 异常，退避重连：%s", e)
                stop_event.wait(5)
                continue
            for upd in updates:  # type: ignore[union-attr]
                self._offset = max(self._offset or 0, upd.get("update_id", 0))
                on_update(upd)

    def stop(self) -> None:
        self._stop.set()

    # --- 发送消息回应用户 ---
    def send_message(self, chat_id: str, text: str) -> None:
        if self._send_hook is not None:
            # 注入的回发（单测用）
            self._send_hook({"chat_id": chat_id}, text)
            return
        import urllib.parse
        params = {"chat_id": chat_id, "text": text}
        self._get("sendMessage", params)


# --------------------------------------------------------------------------
# 4. 连接器主体
# --------------------------------------------------------------------------
class TelegramConnector(Gateway):
    name = "telegram"

    def __init__(self, config_path: Optional[Path] = None,
                 ipc_client: Optional[IpcClient] = None,
                 transport: Optional[TelegramTransport] = None,
                 ipc_port: int = DEFAULT_PORT):
        self.config_path = Path(config_path) if config_path else (get_config_dir() / "telegram.json")
        self.config = TelegramConfig.load(self.config_path)
        self._ipc = ipc_client or IpcClient(port=ipc_port)
        self._transport = transport
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()

    def on_start(self) -> None:
        if not self.config.enabled:
            logger.info("[telegram] 未启用（enabled=false 或无配置），不拉起连接器。")
            return
        if not self.config.bot_token:
            logger.warning("[telegram] 缺少 bot_token，不拉起连接器。")
            return
        if not self.config.allowed_user_ids and not self.config.auto_bind_owner:
            logger.warning("[telegram] allowed_user_ids 为空且未开启 auto_bind_owner，不拉起连接器。")
            return
        mode = ("首次绑定模式（第一个发消息的 Telegram 账号自动成为授权用户）"
                if not self.config.allowed_user_ids
                else f"白名单 {len(self.config.allowed_user_ids)} 人")
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        logger.info("[telegram] 连接器已拉起（%s）。", mode)

    def on_stop(self) -> None:
        self._stop.set()
        if self._transport is not None:
            try:
                self._transport.stop()
            except Exception:  # noqa: BLE001
                pass
        logger.info("[telegram] 连接器已停止。")

    def _persist_config(self) -> None:
        """把当前配置（主要是自动绑定的 allowed_user_ids）写回 telegram.json。

        仅覆盖已知字段，保留用户在配置文件里手工写的其它键。
        """
        data = {
            "enabled": self.config.enabled,
            "bot_token": self.config.bot_token,
            "allowed_user_ids": self.config.allowed_user_ids,
            "session_prefix": self.config.session_prefix,
            "api_base": self.config.api_base,
            "auto_bind_owner": self.config.auto_bind_owner,
            "long_poll_timeout": self.config.long_poll_timeout,
        }
        try:
            self.config_path.write_text(
                json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        except OSError as e:
            logger.warning("[telegram] 持久化配置失败：%s", e)

    def _run(self) -> None:
        transport = self._transport or TelegramTransport(self.config)
        try:
            transport.run_loop(on_update=self._handle_update, stop_event=self._stop)
        except Exception as e:  # noqa: BLE001
            logger.error("[telegram] 运行异常退出：%s", e)

    # --- 事件处理（核心，纯逻辑，可单测）---
    def _handle_update(self, update: dict) -> None:
        msg = self._extract_message(update)
        if msg is None:
            return
        user_id = msg["user_id"]
        text = msg["text"]
        chat_id = msg["chat_id"]
        # 授权约束（白名单 / 首次绑定二选一）
        if user_id not in self.config.allowed_user_ids:
            if self.config.auto_bind_owner and not self.config.allowed_user_ids:
                # 极简引导：第一个向 bot 说话的账号自动成为授权用户
                self.config.allowed_user_ids.append(user_id)
                self._persist_config()
                logger.info("[telegram] 首次绑定所有者 %s。", user_id)
            else:
                logger.info("[telegram] 忽略非白名单用户 %s 的消息。", user_id)
                return
        session_id = self.config.session_prefix + user_id
        # 取消指令
        if text.strip() == "/cancel":
            try:
                self._ipc.chat_cancel()
            except Exception as e:  # noqa: BLE001
                logger.warning("[telegram] 取消失败：%s", e)
            return
        # 主聊天
        try:
            data = self._ipc.chat(text, session_id=session_id)
        except Exception as e:  # noqa: BLE001
            logger.warning("[telegram] chat IPC 失败：%s", e)
            return
        reply = data.get("reply", "")
        if reply:
            self._send_reply(msg, reply)

    def _send_reply(self, msg: dict, reply: str) -> None:
        try:
            if self._transport is not None:
                self._transport.send_message(msg["chat_id"], reply)
            else:
                logger.info("[telegram] 回发（无 transport）：%s", reply[:50])
        except Exception as e:  # noqa: BLE001
            logger.warning("[telegram] 回发失败：%s", e)

    @staticmethod
    def _extract_message(update: dict) -> Optional[dict]:
        """从 Telegram getUpdates 的一条 update 提取 {user_id, text, chat_id}。

        结构（Telegram Bot API）：
          update.update_id  长轮询游标
          update.message.from.id / is_bot / first_name  发送者
          update.message.chat.id   会话 id
          update.message.text   文本内容
        仅处理消息、且非 bot 发送者。字段路径以官方文档为准。
        """
        try:
            message = update.get("message") or update.get("edited_message")
            if not message:
                return None
            sender = message.get("from") or {}
            if sender.get("is_bot"):
                return None
            user_id = str(sender.get("id", ""))
            chat_id = str((message.get("chat") or {}).get("id", ""))
            text = message.get("text", "")
            if not user_id or not text:
                return None
            return {"user_id": user_id, "text": text, "chat_id": chat_id}
        except Exception:  # noqa: BLE001
            return None