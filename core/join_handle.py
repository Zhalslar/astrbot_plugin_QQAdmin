
from pathlib import Path
from typing import Dict, List
import json
import os

from aiocqhttp import CQHttp
from astrbot.api import logger
from astrbot.core.config.astrbot_config import AstrBotConfig
from astrbot.core.platform.sources.aiocqhttp.aiocqhttp_message_event import AiocqhttpMessageEvent
from ..utils import get_reply_message_str



class GroupJoinData:
    def __init__(self,path: str = "group_join_data.json"):
        self.path = path
        self.accept_keywords: Dict[str, List[str]] = {}
        self.reject_ids: Dict[str, List[str]] = {}
        self._load()

    def _load(self):
        if not os.path.exists(self.path):
            self._save()
            return
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                data = json.load(f)
            self.accept_keywords = data.get("accept_keywords", {})
            self.reject_ids = data.get("reject_ids", {})
        except Exception as e:
            print(f"加载 group_join_data 失败: {e}")
            self._save()

    def _save(self):
        data = {
            "accept_keywords": self.accept_keywords,
            "reject_ids": self.reject_ids,
        }
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def save(self):
        self._save()



class GroupJoinManager:
    def __init__(self, json_path: str):
        self.data = GroupJoinData(json_path)

    def should_reject(self, group_id: str, user_id: str) -> bool:
        return (
            group_id in self.data.reject_ids
            and user_id in self.data.reject_ids[group_id]
        )

    def should_approve(self, group_id: str, comment: str) -> bool:
        if group_id not in self.data.accept_keywords:
            return False
        return any(
            kw.lower() in comment.lower() for kw in self.data.accept_keywords[group_id]
        )

    def add_keyword(self, group_id: str, keywords: List[str]):
        self.data.accept_keywords.setdefault(group_id, []).extend(keywords)
        self.data.accept_keywords[group_id] = list(
            set(self.data.accept_keywords[group_id])
        )
        self.data.save()

    def remove_keyword(self, group_id: str, keywords: List[str]):
        if group_id in self.data.accept_keywords:
            for k in keywords:
                if k in self.data.accept_keywords[group_id]:
                    self.data.accept_keywords[group_id].remove(k)
            self.data.save()

    def get_keywords(self, group_id: str) -> List[str]:
        return self.data.accept_keywords.get(group_id, [])

    def add_reject_id(self, group_id: str, ids: List[str]):
        self.data.reject_ids.setdefault(group_id, []).extend(ids)
        self.data.reject_ids[group_id] = list(set(self.data.reject_ids[group_id]))
        self.data.save()

    def remove_reject_id(self, group_id: str, ids: List[str]):
        if group_id in self.data.reject_ids:
            for uid in ids:
                if uid in self.data.reject_ids[group_id]:
                    self.data.reject_ids[group_id].remove(uid)
            self.data.save()

    def get_reject_ids(self, group_id: str) -> List[str]:
        return self.data.reject_ids.get(group_id, [])

    def blacklist_on_leave(self, group_id: str, user_id: str) -> None:
        self.data.reject_ids.setdefault(group_id, []).append(user_id)
        self.data.save()


class JoinHandle:
    def __init__(self, config: AstrBotConfig, data_dir: Path, admins_id: List[str]):
        self.conf = config
        self.admins_id: list[str] = admins_id
        self.group_join_manager = GroupJoinManager(
            str(data_dir / "group_join_data.json")
        )

    async def _send_admin(self, client: CQHttp, message: str):
        """向bot管理员发送私聊消息"""
        for admin_id in self.admins_id:
            if admin_id.isdigit():
                try:
                    await client.send_private_msg(
                        user_id=int(admin_id), message=message
                    )
                except Exception as e:
                    logger.error(f"无法发送消息给bot管理员：{e}")

    async def add_accept_keyword(self, event: AiocqhttpMessageEvent):
        """添加自动批准进群的关键词"""
        if keywords := event.message_str.removeprefix("添加进群关键词").strip().split():
            self.group_join_manager.add_keyword(event.get_group_id(), keywords)
            await event.send(event.plain_result(f"新增进群关键词：{keywords}"))
        else:
            await event.send(event.plain_result("未输入任何关键词"))

    async def remove_accept_keyword(self, event: AiocqhttpMessageEvent):
        """删除自动批准进群的关键词"""
        if keywords := event.message_str.removeprefix("删除进群关键词").strip().split():
            self.group_join_manager.remove_keyword(event.get_group_id(), keywords)
            await event.send(event.plain_result(f"已删进群关键词：{keywords}"))
        else:
            await event.send(event.plain_result("未指定要删除的关键词"))

    async def view_accept_keywords(self, event: AiocqhttpMessageEvent):
        """查看自动批准进群的关键词"""
        keywords = self.group_join_manager.get_keywords(event.get_group_id())
        if not keywords:
            await event.send(event.plain_result("本群没有设置进群关键词"))
            return
        await event.send(event.plain_result(f"本群的进群关键词：{keywords}"))

    async def add_reject_ids(self, event: AiocqhttpMessageEvent):
        """添加指定ID到进群黑名单"""
        parts = event.message_str.strip().split(" ")
        if len(parts) < 2:
            await event.send(event.plain_result("请提供至少一个用户ID"))
            return
        reject_ids = list(set(parts[1:]))
        self.group_join_manager.add_reject_id(event.get_group_id(), reject_ids)
        await event.send(event.plain_result(f"进群黑名单新增ID：{reject_ids}"))

    async def remove_reject_ids(self, event: AiocqhttpMessageEvent):
        """从进群黑名单中删除指定ID"""
        parts = event.message_str.strip().split(" ")
        if len(parts) < 2:
            await event.send(event.plain_result("请提供至少一个用户ID。"))
            return
        ids = list(set(parts[1:]))
        self.group_join_manager.remove_reject_id(event.get_group_id(), ids)
        await event.send(event.plain_result(f"已从黑名单中删除：{ids}"))


    async def view_reject_ids(self, event: AiocqhttpMessageEvent):
        """查看进群黑名单"""
        ids = self.group_join_manager.get_reject_ids(event.get_group_id())
        if not ids:
            await event.send(event.plain_result("本群没有设置进群黑名单"))
            return
        await event.send(event.plain_result(f"本群的进群黑名单：{ids}"))

    async def agree_add_group(self, event: AiocqhttpMessageEvent, extra: str = ""):
        """批准进群申请"""
        reply = await self.approve(event=event, extra=extra, approve=True)
        if reply:
            await event.send(event.plain_result(reply))

    async def refuse_add_group(self, event: AiocqhttpMessageEvent, extra: str = ""):
        """驳回进群申请"""
        reply = await self.approve(event=event, extra=extra, approve=False)
        if reply:
            await event.send(event.plain_result(reply))


    async def event_monitoring(self, event: AiocqhttpMessageEvent):
        """监听进群/退群事件"""
        raw = getattr(event.message_obj, "raw_message", None)
        if not isinstance(raw, dict):
            return

        client = event.bot
        group_id: int = raw.get("group_id", 0)
        user_id: int = raw.get("user_id", 0)
        # 进群申请事件
        if (
            self.conf["enable_audit"]
            and raw.get("post_type") == "request"
            and raw.get("request_type") == "group"
            and raw.get("sub_type") == "add"
        ):
            comment = raw.get("comment")
            flag = raw.get("flag", "")
            nickname = (await client.get_stranger_info(user_id=user_id))[
                "nickname"
            ] or "未知昵称"
            reply = f"【进群申请】批准/驳回：\n昵称：{nickname}\nQQ：{user_id}\nflag：{flag}"
            if comment:
                reply += f"\n{comment}"
            if self.conf["admin_audit"]:
                await self._send_admin(client, reply)
            else:
                await event.send(event.plain_result(reply))

            if self.group_join_manager.should_reject(str(group_id), str(user_id)):
                await client.set_group_add_request(
                    flag=flag, sub_type="add", approve=False, reason="黑名单用户"
                )
                await event.send(event.plain_result("黑名单用户，已自动拒绝进群"))
            elif comment and self.group_join_manager.should_approve(
                str(group_id), comment
            ):
                await client.set_group_add_request(
                    flag=flag, sub_type="add", approve=True
                )
                await event.send(event.plain_result("验证通过，已自动同意进群"))

        # 主动退群事件
        elif (
            self.conf["enable_black"]
            and raw.get("post_type") == "notice"
            and raw.get("notice_type") == "group_decrease"
            and raw.get("sub_type") == "leave"
        ):
            nickname = (await client.get_stranger_info(user_id=user_id))[
                "nickname"
            ] or "未知昵称"
            reply = f"{nickname}({user_id}) 主动退群了"
            if self.conf["auto_black"]:
                self.group_join_manager.blacklist_on_leave(str(group_id), str(user_id))
                reply += "，已拉进黑名单"
            await event.send(event.plain_result(reply))

        # 进群禁言
        elif (
            raw.get("notice_type") == "group_increase"
            and str(user_id) != event.get_self_id()
        ):
            await event.send(event.plain_result(self.conf["increase"]["welcome"]))
            if self.conf["increase"]["ban_time"] > 0:
                try:
                    await client.set_group_ban(
                        group_id=group_id,
                        user_id=user_id,
                        duration=self.conf["increase"]["ban_time"],
                    )
                except Exception:
                    pass

    @staticmethod
    async def approve(
        event: AiocqhttpMessageEvent, extra: str = "", approve: bool = True
    ) -> str | None:
        """处理进群申请"""
        text = get_reply_message_str(event)
        if not text:
            return "未引用任何【进群申请】"
        lines = text.split("\n")
        if "【进群申请】" in text and len(lines) >= 4:
            nickname = lines[1].split("：")[1]  # 第2行冒号后文本为nickname
            flag = lines[3].split("：")[1]  # 第4行冒号后文本为flag
            try:
                await event.bot.set_group_add_request(
                    flag=flag, sub_type="add", approve=approve, reason=extra
                )
                if approve:
                    reply = f"已同意{nickname}进群"
                else:
                    reply = f"已拒绝{nickname}进群" + (
                        f"\n理由：{extra}" if extra else ""
                    )
                return reply
            except Exception:
                return "这条申请处理过了或者格式不对"
