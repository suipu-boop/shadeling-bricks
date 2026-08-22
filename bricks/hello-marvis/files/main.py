#!/usr/bin/env python3
"""hello-marvis：向用户问好并返回当前时间。

纯 Python 标准库（datetime）实现：零第三方依赖、无网络、无落盘。
按本地时段自动生成问候语（早上好 / 下午好 / 晚上好）。

用法：
    python files/main.py               # CLI 试运行，输出 JSON
    from main import greet             # 作为库调用
"""

from datetime import datetime

_WEEKDAYS = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"]


def _period(hour: int) -> str:
    """按小时数返回本地时段问候前缀。"""
    if 5 <= hour < 12:
        return "早上好"
    if 12 <= hour < 18:
        return "下午好"
    return "晚上好"


def greet(user: str = "Marvis") -> dict:
    """向用户问好并返回当前时间信息。

    Args:
        user: 被问候的用户名，默认 "Marvis"。

    Returns:
        dict，字段：
        - greeting (str): 按本地时段生成的问候语
        - time (str): 当前本地时间 "YYYY-MM-DD HH:MM:SS"
        - weekday (str): 中文星期几
        - unix_ts (int): Unix 时间戳（秒）
    """
    now = datetime.now()
    return {
        "greeting": f"{_period(now.hour)}，{user}！",
        "time": now.strftime("%Y-%m-%d %H:%M:%S"),
        "weekday": _WEEKDAYS[now.weekday()],
        "unix_ts": int(now.timestamp()),
    }


if __name__ == "__main__":
    import json

    print(json.dumps(greet(), ensure_ascii=False, indent=2))
