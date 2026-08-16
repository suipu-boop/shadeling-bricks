"""飞书连接器（FeishuConnector）—— 手机飞书 ↔ 本地 Shadeling 的文本桥。

设计要点（详见 docs/connectors_feishu_design.md）：
- 飞书事件订阅走 WebSocket 长连接模式（bot 出站建连，免公网 IP）。
- 连接器是 IpcServer 的 127.0.0.1 客户端，复用与 Swift UI 相同的 IPC 契约。
- 记忆/会话落在 ~/.brickery，与桌面 UI 共享同一库。
- 白名单：仅响应 allowed_user_ids 中的飞书 user_id。
- 凭据存 ~/.brickery/config/feishu.json，不进 git、不进记忆库。
- OFF by default。

依赖：飞书长连接需要 `lark-oapi` 库（官方 SDK，pip install lark-oapi）。
REST 调用用标准库 urllib。旧版手写 websocket 端点（portal 404）已废弃。
"""
from __future__ import annotations

import json
import logging
import socket
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, List, Optional

from ..gateway import Gateway
from ..ipc import DEFAULT_PORT
from ..paths import get_config_dir

logger = logging.getLogger("shadeling.connectors.feishu")


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
class FeishuConfig:
    enabled: bool = False
    app_id: str = ""
    app_secret: str = ""
    allowed_user_ids: List[str] = field(default_factory=list)
    event_mode: str = "websocket"
    base_url: str = "https://open.feishu.cn"
    session_prefix: str = "feishu_"
    ws_url: str = ""  # 保留字段（兼容旧配置）；SDK 模式不再使用
    # 极简引导：用户只填 app_id/app_secret，第一个对自己 bot 说话的飞书账号自动成为授权用户。
    auto_bind_owner: bool = True
    # 事件订阅安全参数（SDK EventDispatcherHandler.builder 需要；未设置为空串即可）
    verification_token: str = ""
    encrypt_key: str = ""

    @classmethod
    def load(cls, path: Path) -> "FeishuConfig":
        p = Path(path)
        if not p.exists():
            # 默认 OFF：无配置文件即不启用
            return cls()
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as e:
            logger.warning("飞书配置读取失败，连接器不启用：%s", e)
            return cls()
        return cls(
            enabled=bool(data.get("enabled", False)),
            app_id=data.get("app_id", ""),
            app_secret=data.get("app_secret", ""),
            allowed_user_ids=list(data.get("allowed_user_ids", [])),
            event_mode=data.get("event_mode", "websocket"),
            base_url=data.get("base_url", "https://open.feishu.cn"),
            session_prefix=data.get("session_prefix", "feishu_"),
            ws_url=data.get("ws_url", ""),
            auto_bind_owner=bool(data.get("auto_bind_owner", True)),
            verification_token=data.get("verification_token", ""),
            encrypt_key=data.get("encrypt_key", ""),
        )


# --------------------------------------------------------------------------
# 3. 飞书传输层（真实协议隔离；endpoint 可配置、标注待真机验证）
# --------------------------------------------------------------------------
class FeishuTransport:
    """封装飞书 REST + WS 长连接。

    所有飞书 endpoint 集中在此，便于随朴按官方文档校正。
    单测用 mock（send_hook / fake 帧），不依赖真实飞书。
    """

    def __init__(self, config: FeishuConfig,
                 send_hook: Optional[Callable[[dict, str], None]] = None):
        self.config = config
        self._token: Optional[str] = None
        self._ws = None
        self._lark_client = None
        self._thread: Optional[threading.Thread] = None
        self._send_hook = send_hook
        self._stop = threading.Event()

    # --- 鉴权（飞书标准内部鉴权路径；以官方文档为准）---
    def get_tenant_access_token(self) -> str:
        import urllib.request
        url = f"{self.config.base_url}/open-apis/auth/v3/tenant_access_token/internal"
        body = json.dumps({"app_id": self.config.app_id,
                           "app_secret": self.config.app_secret}).encode("utf-8")
        req = urllib.request.Request(url, data=body,
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        token = data.get("tenant_access_token")
        if not token:
            raise RuntimeError(f"获取 tenant_access_token 失败：{data}")
        self._token = token
        return token

    # --- WS 长连接（飞书官方 lark-oapi SDK 封装）---
    # 飞书长连接是 SDK 内提供的能力（官方文档），ws 地址由 lark.ws.Client 内部
    # 拉取并建立，无公开 REST 端点可手写。因此这里不再手写 portal 端点（曾 404），
    # 改用官方 SDK。依赖 lark-oapi（build_app.sh 已装）。
    def run_loop(self, on_event: Callable[[dict], None], stop_event: threading.Event) -> None:
        """用官方 lark-oapi SDK 建立长连接，持续接收事件并交给 on_event。

        事件回调会把 SDK 对象转成 dict 帧再喂给 on_event（外部行为与旧版一致）。
        可被 stop_event 中断（通过 stop()）。缺 lark-oapi 时抛 ImportError 由调用方退避。
        """
        import lark_oapi as lark  # 需 pip install lark-oapi

        def _on_p2(data):  # P2ImMessageReceiveV1 对象
            frame = _sdk_event_to_frame(data)
            if frame is not None:
                on_event(frame)

        handler = (
            lark.EventDispatcherHandler.builder(self.config.verification_token, self.config.encrypt_key)
            .register_p2_im_message_receive_v1(_on_p2)
            .build()
        )
        self._stop = stop_event
        # SDK start() 阻塞；放在独立线程跑，便于 stop_event 控制退出。
        self._lark_client = lark.ws.Client(
            self.config.app_id, self.config.app_secret, event_handler=handler,
            log_level=lark.LogLevel.INFO)
        # 用本地 stop_event 绑定：SDK 无阻塞内中断，靠 stop() 主动 close。
        self._thread = threading.Thread(target=self._lark_client.start, daemon=True)
        self._thread.start()
        # 阻塞在当前连接生命周期：SDK 连接断开本身会抛并结束 start()。
        self._thread.join()
        logger.info("[feishu] 长连接已结束（stop_event=%s）", stop_event.is_set())

    def stop(self) -> None:
        self._stop.set()
        try:
            if self._lark_client is not None:
                self._lark_client.stop()
        except Exception:  # noqa: BLE001
            pass

    # --- 发送消息回应用户（飞书标准路径；以官方文档为准）---
    def send_text(self, receive_id: str, text: str) -> None:
        if self._send_hook is not None:
            # 注入的回发（单测用）
            self._send_hook({"chat_id": receive_id}, text)
            return
        import urllib.request
        url = f"{self.config.base_url}/open-apis/im/v1/messages?receive_id_type=open_id"
        body = json.dumps({
            "receive_id": receive_id,
            "msg_type": "text",
            "content": json.dumps({"text": text}),
        }).encode("utf-8")
        req = urllib.request.Request(
            url, data=body,
            headers={"Authorization": f"Bearer {self._token}",
                     "Content-Type": "application/json"},
            method="POST")
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        if data.get("code") not in (0, None):
            logger.warning("飞书发送消息返回非 0：%s", data)


# --------------------------------------------------------------------------
# 4. 连接器主体
# --------------------------------------------------------------------------
class FeishuConnector(Gateway):
    name = "feishu"

    def __init__(self, config_path: Optional[Path] = None,
                 ipc_client: Optional[IpcClient] = None,
                 transport: Optional[FeishuTransport] = None,
                 ipc_port: int = DEFAULT_PORT):
        self.config_path = Path(config_path) if config_path else (get_config_dir() / "feishu.json")
        self.config = FeishuConfig.load(self.config_path)
        self._ipc = ipc_client or IpcClient(port=ipc_port)
        self._transport = transport
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()

    def on_start(self) -> None:
        if not self.config.enabled:
            logger.info("[feishu] 未启用（enabled=false 或无配置），不拉起连接器。")
            return
        if not self.config.app_id or not self.config.app_secret:
            logger.warning("[feishu] 缺少 app_id/app_secret，不拉起连接器。")
            return
        if not self.config.allowed_user_ids and not self.config.auto_bind_owner:
            logger.warning("[feishu] allowed_user_ids 为空且未开启 auto_bind_owner，不拉起连接器。")
            return
        mode = ("首次绑定模式（第一个发消息的飞书账号自动成为授权用户）"
                if not self.config.allowed_user_ids
                else f"白名单 {len(self.config.allowed_user_ids)} 人")
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        logger.info("[feishu] 连接器已拉起（%s）。", mode)

    def on_stop(self) -> None:
        self._stop.set()
        if self._transport is not None:
            try:
                self._transport.stop()
            except Exception:  # noqa: BLE001
                pass
        logger.info("[feishu] 连接器已停止。")

    def _persist_config(self) -> None:
        """把当前配置（主要是自动绑定的 allowed_user_ids）写回 feishu.json。

        仅覆盖已知字段，保留用户在配置文件里手工写的其它键。
        """
        data = {
            "enabled": self.config.enabled,
            "app_id": self.config.app_id,
            "app_secret": self.config.app_secret,
            "allowed_user_ids": self.config.allowed_user_ids,
            "event_mode": self.config.event_mode,
            "base_url": self.config.base_url,
            "session_prefix": self.config.session_prefix,
            "ws_url": self.config.ws_url,
            "auto_bind_owner": self.config.auto_bind_owner,
            "verification_token": self.config.verification_token,
            "encrypt_key": self.config.encrypt_key,
        }
        try:
            self.config_path.write_text(
                json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        except OSError as e:
            logger.warning("[feishu] 持久化配置失败：%s", e)

    def _run(self) -> None:
        """持续运行 WS 事件循环，异常时指数退避重试，线程永不死。

        故障域隔离：飞书长连接的任何异常（网络抖动 / 404 / 鉴权失败 / 超时）
        只在本线程内退避重试，绝不抛到外层拖死核心后端进程。
        stop_event 被设置时优雅退出。
        """
        import time as _time
        attempt = 0
        max_backoff = 60.0
        while not self._stop.is_set():
            attempt += 1
            try:
                transport = self._transport or FeishuTransport(self.config)
                logger.info("[feishu] 第 %d 次尝试建立长连接（官方 SDK）", attempt)
                transport.run_loop(on_event=self._handle_event, stop_event=self._stop)
            except Exception as e:  # noqa: BLE001
                if self._stop.is_set():
                    logger.info("[feishu] 连接器已收到停止信号，线程退出。")
                    return
                backoff = min(max_backoff, 2 ** min(attempt - 1, 6))
                logger.error("[feishu] 运行异常退出（第 %d 次）：%s；%d 秒后重试", attempt, e, backoff)
                # 逐秒 wait，确保 stop_event 能被及时响应，不用 sleep(backoff) 堵死
                for _ in range(int(backoff)):
                    if self._stop.is_set():
                        return
                    _time.sleep(1)

    # --- 事件处理（核心，纯逻辑，可单测）---
    def _handle_event(self, event: dict) -> None:
        msg = self._extract_message(event)
        if msg is None:
            return
        user_id = msg["user_id"]
        text = msg["text"]
        # 授权约束（白名单 / 首次绑定二选一）
        if user_id not in self.config.allowed_user_ids:
            if self.config.auto_bind_owner and not self.config.allowed_user_ids:
                # 极简引导：第一个对自己 bot 说话的飞书账号自动成为授权用户
                self.config.allowed_user_ids.append(user_id)
                self._persist_config()
                logger.info("[feishu] 首次绑定所有者 %s。", user_id)
            else:
                logger.info("[feishu] 忽略非白名单用户 %s 的消息。", user_id)
                return
        session_id = self.config.session_prefix + user_id
        # 取消指令
        if text.strip() == "/cancel":
            try:
                self._ipc.chat_cancel()
            except Exception as e:  # noqa: BLE001
                logger.warning("[feishu] 取消失败：%s", e)
            return
        # 主聊天
        try:
            data = self._ipc.chat(text, session_id=session_id)
        except Exception as e:  # noqa: BLE001
            logger.warning("[feishu] chat IPC 失败：%s", e)
            return
        reply = data.get("reply", "")
        if reply:
            self._send_reply(msg, reply)

    def _send_reply(self, msg: dict, reply: str) -> None:
        try:
            if self._transport is not None:
                self._transport.send_text(msg["chat_id"], reply)
            else:
                logger.info("[feishu] 回发（无 transport）：%s", reply[:50])
        except Exception as e:  # noqa: BLE001
            logger.warning("[feishu] 回发失败：%s", e)

    @staticmethod
    def _sdk_event_to_frame(data) -> Optional[dict]:
        """把 lark-oapi SDK 的 P2ImMessageReceiveV1 对象转成与旧版一致的 dict 帧。

        转换后 frame 结构与 hand-written WS 解析的一致（header/event.message...），
        让下游 _extract_message / _handle_event 零改动复用。非法输入返回 None。
        """
        try:
            ev = getattr(data, "event", None)
            if ev is None:
                return None
            msg = getattr(ev, "message", None)
            if msg is None:
                return None
            sender = getattr(ev, "sender", None)
            sender_id = getattr(sender, "sender_id", None) if sender is not None else None
            return {
                "header": {"event_type": "im.message.receive_v1"},
                "event": {
                    "message": {
                        "chat_id": getattr(msg, "chat_id", None) or "",
                        "content": getattr(msg, "content", None) or "{}",
                        "sender": {
                            "sender_id": {
                                "open_id": getattr(sender_id, "open_id", None) if sender_id else None,
                                "user_id": getattr(sender_id, "user_id", None) if sender_id else None,
                            }
                        },
                    }
                },
            }
        except Exception:  # noqa: BLE001
            return None

    @staticmethod
    def _extract_message(event) -> Optional[dict]:
        """从飞书事件提取 {user_id, text, chat_id}。

        兼容两种输入：
          - lark-oapi SDK 对象（P2ImMessageReceiveV1）→ 先转成 dict 帧
          - dict 帧（旧版手写 WS 解析 / 单测直接构造）
        飞书 im.message.receive_v1 事件结构（v2）：
          event.message.content 是「JSON 字符串」，需二次 parse 得 {"text": "..."}
          event.message.sender.sender_id.open_id / user_id 为发送者
          event.message.chat_id 为会话 id
        """
        try:
            if isinstance(event, dict):
                frame = event
            else:
                frame = FeishuConnector._sdk_event_to_frame(event)
                if frame is None:
                    return None
            header = frame.get("header") or {}
            if header.get("event_type") != "im.message.receive_v1":
                return None
            m = (frame.get("event") or {}).get("message") or {}
            if not m:
                return None
            content_raw = m.get("content", "{}")
            try:
                content = json.loads(content_raw) if isinstance(content_raw, str) else content_raw
            except (json.JSONDecodeError, TypeError):
                content = {}
            text = content.get("text", "")
            sender = (m.get("sender") or {}).get("sender_id") or {}
            user_id = sender.get("open_id") or sender.get("user_id") or ""
            chat_id = m.get("chat_id", "")
            if not user_id:
                return None
            return {"user_id": user_id, "text": text, "chat_id": chat_id}
        except Exception:  # noqa: BLE001
            return None


# --------------------------------------------------------------------------
# 5. 轻量主动推送器（任务完成通知；不拉 WS，只做 REST 发送）
# --------------------------------------------------------------------------
class FeishuNotifier:
    """单向通知：后台任务完成时推飞书，与 FeishuConnector 的双向桥解耦。

    - 复用 FeishuTransport 的 tenant_access_token 获取 + send_text（REST）。
    - 仅向已绑定的 allowed_user_ids 推送（首个向 bot 说话的账号经 auto_bind_owner
      自动入列；详见 FeishuConnector 授权逻辑）。
    - 未启用 / 缺凭证 / 未绑定接收者 → enabled()=False，notify 静默返回 False，不崩。
    - transport 可注入（单测用 send_hook 捕获），默认按 config 真实构造。
    """

    def __init__(self, config_path: Optional[Path] = None,
                 transport: Optional["FeishuTransport"] = None):
        self.config_path = Path(config_path) if config_path else (get_config_dir() / "feishu.json")
        self.config = FeishuConfig.load(self.config_path)
        self._transport = transport  # 测试可注入

    def enabled(self) -> bool:
        return bool(
            self.config.enabled
            and self.config.app_id
            and self.config.app_secret
            and self.config.allowed_user_ids
        )

    def _get_transport(self) -> "FeishuTransport":
        if self._transport is not None:
            return self._transport
        t = FeishuTransport(self.config)
        t.get_tenant_access_token()
        return t

    def notify(self, title: str, text: str) -> bool:
        """向所有已绑定接收者推送一条文本。成功返回 True，否则 False（不抛）。"""
        if not self.enabled():
            return False
        try:
            transport = self._get_transport()
            body = f"【{title}】\n{text}"
            for open_id in self.config.allowed_user_ids:
                transport.send_text(open_id, body)
            return True
        except Exception as e:  # noqa: BLE001
            logger.warning("[feishu] 任务完成通知发送失败：%s", e)
            return False
