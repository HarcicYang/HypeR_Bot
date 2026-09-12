"""把 OneBot 消息与通知事件格式化为 Agent 可读文本。"""

import json
from typing import Any


def _user(user_id: Any) -> str:
    return f"用户 {user_id}" if user_id is not None else "未知用户"


def _operator(operator_id: Any) -> str:
    return f"，操作者：{operator_id}" if operator_id is not None else ""


def _file_name(file: Any) -> str:
    if isinstance(file, dict):
        for key in ("name", "file_name", "file", "id"):
            value = file.get(key)
            if value not in (None, ""):
                return str(value)
    return "未知文件"


def _message_text(message: list[Any]) -> str:
    parts: list[str] = []
    for segment in message:
        if not isinstance(segment, dict):
            continue
        segment_type = segment.get("type")
        if segment_type == "text":
            parts.append(str((segment.get("data") or {}).get("text", "")))
        else:
            parts.append(f"[{segment_type}]")
    return "".join(parts)


def _notice_text(event: dict[str, Any]) -> str:
    notice_type = event.get("notice_type")
    sub_type = event.get("sub_type")
    user_id = event.get("user_id")
    operator_id = event.get("operator_id")
    target_id = event.get("target_id")

    match notice_type:
        case "group_upload":
            return f"{_user(user_id)} 上传了群文件「{_file_name(event.get('file'))}」"
        case "group_admin":
            action = "被设置" if sub_type == "set" else "被取消"
            return f"{_user(user_id)} {action}群管理员{_operator(operator_id)}"
        case "group_decrease":
            action = {
                "leave": "退出了群聊",
                "kick": "被移出群聊",
                "kick_me": "机器人被移出群聊",
            }.get(str(sub_type), "离开了群聊")
            return f"{_user(user_id)} {action}{_operator(operator_id)}"
        case "group_increase":
            action = "被邀请加入群聊" if sub_type == "invite" else "加入了群聊"
            return f"{_user(user_id)} {action}{_operator(operator_id)}"
        case "group_ban":
            if sub_type == "lift_ban":
                return f"{_user(user_id)} 被解除禁言{_operator(operator_id)}"
            return f"{_user(user_id)} 被禁言 {event.get('duration', 0)} 秒{_operator(operator_id)}"
        case "group_whole_mute":
            action = "开启" if sub_type == "mute" else "关闭"
            return f"群全员禁言已{action}{_operator(operator_id)}"
        case "group_name_change":
            return f"群名称变更为「{event.get('new_group_name', '')}」{_operator(operator_id)}"
        case "group_recall":
            return f"{_user(operator_id)} 撤回了{_user(user_id)} 的消息 {event.get('message_id', '')}".rstrip()
        case "friend_upload":
            return f"{_user(user_id)} 上传了文件「{_file_name(event.get('file'))}」"
        case "friend_recall":
            return f"{_user(user_id)} 撤回了一条消息 {event.get('message_id', '')}".rstrip()
        case "friend_add":
            return f"{_user(user_id)} 已添加机器人为好友"
        case "notify":
            match sub_type:
                case "poke":
                    return f"{_user(user_id)} 戳了{_user(target_id)}"
                case "lucky_king":
                    return f"{_user(user_id)} 成为运气王"
                case "honor":
                    return f"{_user(user_id)} 获得群荣誉「{event.get('honor_type', '')}」"
                case _:
                    return f"{_user(user_id)} 触发了通知「{sub_type or 'unknown'}」"
        case "essence":
            action = "设为" if sub_type == "add" else "移除"
            return (
                f"{_user(operator_id)} 将{_user(event.get('sender_id'))} 的消息 "
                f"{event.get('message_id', '')} {action}精华"
            ).rstrip()
        case "reaction":
            action = "添加" if sub_type == "add" else "移除"
            return (
                f"{_user(operator_id)} 对消息 {event.get('message_id', '')} {action}了"
                f"表情 {event.get('code', '')}（当前 {event.get('count', 0)}）"
            )
        case "bot_online":
            return f"Bot 已重新连接：{event.get('reason', '')}"
        case _:
            return ""


def _request_text(event: dict[str, Any]) -> str:
    request_type = event.get("request_type")
    comment = str(event.get("comment") or "").strip()
    suffix = f"：{comment}" if comment else ""
    if request_type == "friend":
        return f"{_user(event.get('user_id'))} 请求添加好友{suffix}"
    if request_type == "group":
        return f"群 {event.get('group_id')} 收到加入邀请/申请{suffix}"
    return ""


def event_text(event: dict[str, Any]) -> str:
    """返回适合时间线、摘要与 RAG 的单行事件文本。"""
    message = event.get("message")
    if isinstance(message, list):
        return _message_text(message)

    post_type = event.get("post_type")
    if post_type == "notice":
        text = _notice_text(event)
        if text:
            return text
    elif post_type == "request":
        text = _request_text(event)
        if text:
            return text

    for key in ("raw_message", "summary", "comment"):
        value = event.get(key)
        if value not in (None, ""):
            return str(value)

    label = ".".join(str(part) for part in (post_type, event.get("sub_type")) if part)
    payload = json.dumps(event, ensure_ascii=False, separators=(",", ":"))
    return f"[{label or 'event'}] {payload}"


def event_actor_id(event: dict[str, Any]) -> Any:
    """返回时间线展示用的主要行为人。"""
    operator_id = event.get("operator_id")
    if operator_id is not None:
        return operator_id
    user_id = event.get("user_id")
    if user_id is not None:
        return user_id
    return event.get("self_id")
