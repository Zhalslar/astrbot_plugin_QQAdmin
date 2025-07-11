import asyncio
from collections import defaultdict, deque
import os
import random
import textwrap
from datetime import datetime
import time

from aiocqhttp import CQHttp
from astrbot import logger
from astrbot.api.event import filter
from astrbot.api.star import Context, Star, register
from astrbot.core import AstrBotConfig
from astrbot.core.message.components import Plain
from astrbot.core.platform.sources.aiocqhttp.aiocqhttp_message_event import (
    AiocqhttpMessageEvent,
)
from astrbot.core.utils.session_waiter import (
    session_waiter,
    SessionController,
)
from astrbot.api.star import StarTools
from astrbot.core.star.filter.event_message_type import EventMessageType
from .core.curfew_manager import CurfewManager
from .core.group_join_manager import GroupJoinManager
from .core.permission import (
    PermLevel,
    PermissionManager,
    perm_required,
)
from .core.utils import *


@register(
    "astrbot_plugin_QQAdmin",
    "Zhalslar",
    "群管插件，帮助你管理群聊",
    "3.0.5",
    "https://github.com/Zhalslar/astrbot_plugin_QQAdmin",
)
class AdminPlugin(Star):
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.admins_id: set[str] = set(context.get_config().get("admins_id", []))
        self.config = config
        self._load_config()
        self.curfew_managers: dict[str, CurfewManager] = {}

    def _load_config(self):
        """加载并初始化插件配置"""
        superusers_set = set(self.config.get("superusers", []))
        superusers_set.update(self.context.get_config().get("admins_id", []))
        self.superusers = list(superusers_set)

        ban_time_setting = self.config.get("ban_time_setting", {})
        self.ban_rand_time_min: int = ban_time_setting.get("ban_rand_time_min", 30)
        self.ban_rand_time_max: int = ban_time_setting.get("ban_rand_time_max", 300)

        night_ban_config = self.config.get("night_ban_config", {})
        self.night_start_time: str = night_ban_config.get("night_start_time", "23:30")
        self.night_end_time: str = night_ban_config.get("night_end_time", "6:00")

        forbidden_config = self.config.get("forbidden_config", {})
        raw_words = forbidden_config.get("forbidden_words", "")
        if isinstance(raw_words, str):
            self.forbidden_words = [word.strip() for word in raw_words.split("，") if word.strip()]
        elif isinstance(raw_words, list):
            self.forbidden_words = [word.strip() for word in raw_words if word.strip()]
        else:
            self.forbidden_words = []
        self.forbidden_words_group: list[str] = forbidden_config.get(
            "forbidden_words_group", []
        )
        self.forbidden_words_ban_time: int = forbidden_config.get(
            "forbidden_words_ban_time", 60
        )
        spamming_config = self.config.get("spamming_config", {})
        self.min_interval = spamming_config.get("min_interval", 0.5)
        self.min_count = spamming_config.get("min_count", 4)
        self.spamming_ban_time = spamming_config.get("spamming_ban_time", 600)
        self.spamming_group_whitelist = spamming_config.get(
            "spamming_group_whitelist", []
        )
        self.msg_timestamps: dict[str, dict[str, deque[float]]] = defaultdict(
            lambda: defaultdict(lambda: deque(maxlen=self.min_count))
        )
        self.last_banned_time: dict[str, dict[str, float]] = defaultdict(
            lambda: defaultdict(float)
        )
        self.last_banned_time: dict[str, dict[str, float]] = defaultdict(
            lambda: defaultdict(float)
        )

        self.enable_audit: bool = self.config.get("enable_audit", False)
        self.admin_audit: bool = self.config.get("admin_audit", False)
        self.enable_black: bool = self.config.get("enable_black", False)
        self.auto_black: bool = self.config.get("auto_black", False)

        self.level_threshold: int = self.config.get("level_threshold", 50)
        self.perms: dict = self.config.get("perms", {})

    async def initialize(self):
        # 初始化权限管理器
        PermissionManager.get_instance(
            superusers=self.superusers,
            perms=self.perms,
            level_threshold=self.level_threshold,
        )
        # 初始化进群管理器
        self.plugin_data_dir = StarTools.get_data_dir("astrbot_plugin_QQAdmin")
        group_join_data = os.path.join(self.plugin_data_dir, "group_join_data.json")
        self.group_join_manager = GroupJoinManager(group_join_data)
        # 概率打印LOGO（qwq）
        if random.random() < 0.01:
            print_logo()

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

    @filter.command("禁言")
    @perm_required(PermLevel.ADMIN)
    async def set_group_ban(self, event: AiocqhttpMessageEvent, ban_time=None):
        """禁言 60 @user"""
        if not ban_time or not isinstance(ban_time, int):
            ban_time = random.randint(self.ban_rand_time_min, self.ban_rand_time_max)
        for tid in get_ats(event):
            try:
                await event.bot.set_group_ban(
                    group_id=int(event.get_group_id()),
                    user_id=int(tid),
                    duration=ban_time,
                )
            except:  # noqa: E722
                pass
        event.stop_event()

    @filter.command("禁我")
    @perm_required(PermLevel.ADMIN)
    async def set_group_ban_me(
        self, event: AiocqhttpMessageEvent, ban_time: int | None = None
    ):
        """禁我 60"""
        if not ban_time or not isinstance(ban_time, int):
            ban_time = random.randint(self.ban_rand_time_min, self.ban_rand_time_max)
        try:
            await event.bot.set_group_ban(
                group_id=int(event.get_group_id()),
                user_id=int(event.get_sender_id()),
                duration=ban_time,
            )
            yield event.plain_result(random.choice(BAN_ME_QUOTES))
        except Exception:
            yield event.plain_result("我可禁言不了你")
        event.stop_event()

    @filter.command("解禁")
    @perm_required(PermLevel.ADMIN)
    async def cancel_group_ban(self, event: AiocqhttpMessageEvent):
        """解禁@user"""
        for tid in get_ats(event):
            await event.bot.set_group_ban(
                group_id=int(event.get_group_id()), user_id=int(tid), duration=0
            )
        event.stop_event()

    @filter.command("开启全员禁言", alias={"全员禁言"})
    @perm_required(PermLevel.ADMIN)
    async def set_group_whole_ban(self, event: AiocqhttpMessageEvent):
        """全员禁言"""
        await event.bot.set_group_whole_ban(
            group_id=int(event.get_group_id()), enable=True
        )
        yield event.plain_result("已开启全体禁言")

    @filter.command("关闭全员禁言")
    @perm_required(PermLevel.ADMIN)
    async def cancel_group_whole_ban(self, event: AiocqhttpMessageEvent):
        """关闭全员禁言"""
        await event.bot.set_group_whole_ban(
            group_id=int(event.get_group_id()), enable=False
        )
        yield event.plain_result("已关闭全员禁言")

    @filter.command("改名")
    @perm_required(PermLevel.ADMIN)
    async def set_group_card(
        self, event: AiocqhttpMessageEvent, target_card: str | int | None = None
    ):
        """改名 xxx @user"""
        target_card = target_card or event.get_sender_name()
        tids = get_ats(event) or [event.get_sender_id()]
        for tid in tids:
            target_name = await get_nickname(event, user_id=tid)
            replay = f"已将{target_name}的群昵称改为【{target_card}】"
            yield event.plain_result(replay)
            await event.bot.set_group_card(
                group_id=int(event.get_group_id()),
                user_id=int(tid),
                card=str(target_card),
            )

    @filter.command("改我")
    @perm_required(PermLevel.ADMIN)
    async def set_group_card_me(
        self, event: AiocqhttpMessageEvent, target_card: str | int | None = None
    ):
        """改我 xxx"""
        target_card = target_card or event.get_sender_name()
        await event.bot.set_group_card(
            group_id=int(event.get_group_id()),
            user_id=int(event.get_sender_id()),
            card=str(target_card),
        )
        yield event.plain_result(f"已将你的群昵称改为【{target_card}】")

    @filter.command("头衔")
    @perm_required(PermLevel.OWNER)
    async def set_group_special_title(
        self, event: AiocqhttpMessageEvent, new_title: str | int | None = None
    ):
        """头衔 xxx @user"""
        new_title = str(new_title) or event.get_sender_name()
        tids = get_ats(event) or [event.get_sender_id()]
        for tid in tids:
            target_name = await get_nickname(event, user_id=tid)
            yield event.plain_result(f"已将{target_name}的头衔改为【{new_title}】")
            await event.bot.set_group_special_title(
                group_id=int(event.get_group_id()),
                user_id=int(tid),
                special_title=new_title,
                duration=-1,
            )

    @filter.command("申请头衔", alias={"我要头衔"})
    @perm_required(PermLevel.OWNER)
    async def set_group_special_title_me(
        self, event: AiocqhttpMessageEvent, new_title: str | int | None = None
    ):
        """申请头衔 xxx"""
        new_title = str(new_title) or event.get_sender_name()
        await event.bot.set_group_special_title(
            group_id=int(event.get_group_id()),
            user_id=int(event.get_sender_id()),
            special_title=new_title,
            duration=-1,
        )
        yield event.plain_result(f"已将你的头衔改为【{new_title}】")

    @filter.command("踢了")
    @perm_required(PermLevel.ADMIN)
    async def set_group_kick(self, event: AiocqhttpMessageEvent):
        """踢了@user"""
        for tid in get_ats(event):
            target_name = await get_nickname(event, user_id=tid)
            await event.bot.set_group_kick(
                group_id=int(event.get_group_id()),
                user_id=int(tid),
                reject_add_request=False,
            )
            yield event.plain_result(f"已将【{tid}-{target_name}】踢出本群")

    @filter.command("拉黑")
    @perm_required(PermLevel.ADMIN)
    async def set_group_block(self, event: AiocqhttpMessageEvent):
        """拉黑 @user"""
        for tid in get_ats(event):
            target_name = await get_nickname(event, user_id=tid)
            await event.bot.set_group_kick(
                group_id=int(event.get_group_id()),
                user_id=int(tid),
                reject_add_request=True,
            )
            yield event.plain_result(f"已将【{tid}-{target_name}】踢出本群并拉黑!")

    @filter.command("设为管理员")
    @perm_required(PermLevel.OWNER, check_at=False)
    async def set_group_admin(self, event: AiocqhttpMessageEvent):
        """设置管理员@user"""
        for tid in get_ats(event):
            await event.bot.set_group_admin(
                group_id=int(event.get_group_id()), user_id=int(tid), enable=True
            )
            chain = [At(qq=tid), Plain(text="你已被设为管理员")]
            yield event.chain_result(chain)

    @filter.command("取消管理员")
    @perm_required(PermLevel.OWNER)
    async def cancel_group_admin(self, event: AiocqhttpMessageEvent):
        """取消管理员@user"""
        for tid in get_ats(event):
            await event.bot.set_group_admin(
                group_id=int(event.get_group_id()), user_id=int(tid), enable=False
            )
            chain = [At(qq=tid), Plain(text="你的管理员身份已被取消")]
            yield event.chain_result(chain)

    @filter.command("设为精华", alias={"设精"})
    @perm_required(PermLevel.ADMIN)
    async def set_essence_msg(self, event: AiocqhttpMessageEvent):
        """将引用消息添加到群精华"""
        first_seg = event.get_messages()[0]
        if isinstance(first_seg, Reply):
            await event.bot.set_essence_msg(message_id=int(first_seg.id))
            yield event.plain_result("已设为精华消息")
            event.stop_event()

    @filter.command("移除精华", alias={"移精"})
    @perm_required(PermLevel.ADMIN)
    async def delete_essence_msg(self, event: AiocqhttpMessageEvent):
        """将引用消息移出群精华"""
        first_seg = event.get_messages()[0]
        if isinstance(first_seg, Reply):
            await event.bot.delete_essence_msg(message_id=int(first_seg.id))
            yield event.plain_result("已移除精华消息")
            event.stop_event()

    @filter.command("查看精华", alias={"群精华"})
    @perm_required(PermLevel.ADMIN)
    async def get_essence_msg_list(self, event: AiocqhttpMessageEvent):
        """查看群精华"""
        essence_data = await event.bot.get_essence_msg_list(
            group_id=int(event.get_group_id())
        )
        yield event.plain_result(f"{essence_data}")
        event.stop_event()
        # TODO 做张好看的图片来展示

    @filter.command("撤回")
    @perm_required(PermLevel.MEMBER)
    async def delete_msg(self, event: AiocqhttpMessageEvent):
        """(引用消息)撤回 | 撤回 @某人(默认bot) 数量(默认10)"""
        client = event.bot
        chain = event.get_messages()
        first_seg = chain[0]
        if isinstance(first_seg, Reply):
            try:
                await client.delete_msg(message_id=int(first_seg.id))
            except Exception:
                yield event.plain_result("我无权撤回这条消息")
            finally:
                event.stop_event()
        elif any(isinstance(seg, At) for seg in chain):
            target_ids = get_ats(event) or [event.get_self_id()]
            target_ids = {str(uid) for uid in target_ids}

            end_arg = event.message_str.split()[-1]
            count = int(end_arg) if end_arg.isdigit() else 10

            payloads = {
                "group_id": int(event.get_group_id()),
                "message_seq": 0,
                "count": count,
                "reverseOrder": True,
            }
            result: dict = await client.api.call_action(
                "get_group_msg_history", **payloads
            )

            messages = list(reversed(result.get("messages", [])))
            delete_count = 0
            sem = asyncio.Semaphore(10)

            # 撤回消息
            async def try_delete(message: dict):
                nonlocal delete_count
                if str(message["sender"]["user_id"]) not in target_ids:
                    return
                async with sem:
                    try:
                        await client.delete_msg(message_id=message["message_id"])
                        delete_count += 1
                    except Exception:
                        pass

            # 并发撤回
            tasks = [try_delete(msg) for msg in messages]
            await asyncio.gather(*tasks)

            yield event.plain_result(f"已从{count}条消息中撤回{delete_count}条")

    @filter.event_message_type(EventMessageType.GROUP_MESSAGE)
    @perm_required(PermLevel.ADMIN)
    async def check_forbidden_words(self, event: AiocqhttpMessageEvent):
        """
        自动检测违禁词，撤回并禁言
        """
        # 群聊白名单
        if (
            self.forbidden_words_group
            and event.get_group_id() not in self.forbidden_words_group
        ):
            return
        if not self.forbidden_words or not event.message_str:
            return
        # 检测违禁词
        for word in self.forbidden_words:
            if word in event.message_str:
                yield event.plain_result("不准发禁词！")
                # 撤回消息
                try:
                    message_id = event.message_obj.message_id
                    await event.bot.delete_msg(message_id=int(message_id))
                except Exception:
                    pass
                # 禁言发送者
                if self.forbidden_words_ban_time > 0:
                    try:
                        await event.bot.set_group_ban(
                            group_id=int(event.get_group_id()),
                            user_id=int(event.get_sender_id()),
                            duration=self.forbidden_words_ban_time,
                        )
                    except Exception:
                        pass
                break

    @filter.event_message_type(filter.EventMessageType.GROUP_MESSAGE)
    @perm_required(PermLevel.ADMIN)
    async def spamming_ban(self, event: AiocqhttpMessageEvent):
        """刷屏检测与禁言"""
        if self.min_count ==0:
            return
        group_id = event.get_group_id()
        if (
            self.spamming_group_whitelist
            and group_id not in self.spamming_group_whitelist
        ):
            return
        user_id = event.get_sender_id()
        now = time.time()

        last_time = self.last_banned_time[group_id][user_id]
        if now - last_time < self.spamming_ban_time:
            return


        timestamps = self.msg_timestamps[group_id][user_id]
        timestamps.append(now)

        if len(timestamps) >= self.min_count:
            recent = list(timestamps)[-self.min_count:]
            intervals = [recent[i + 1] - recent[i] for i in range(self.min_count - 1)]
            if (
                all(interval < self.min_interval for interval in intervals)
                and self.spamming_ban_time
            ):

                # 提前写入禁止标记，防止并发重复禁
                self.last_banned_time[group_id][user_id] = now

                # 提前写入禁止标记，防止并发重复禁
                self.last_banned_time[group_id][user_id] = now

                try:
                    await event.bot.set_group_ban(
                        group_id=int(group_id),
                        user_id=int(user_id),
                        duration=self.spamming_ban_time,
                    )
                    yield event.plain_result(
                        f"检测到{get_nickname(event, user_id)}刷屏，已禁言"
                    )
                    nickname = await get_nickname(event, user_id)
                    yield event.plain_result(f"检测到{nickname}刷屏，已禁言")
                    nickname = await get_nickname(event, user_id)
                    yield event.plain_result(f"检测到{nickname}刷屏，已禁言")
                except Exception as e:
                    logger.warning(f"刷屏禁言失败：{e}")
                timestamps.clear()

    @filter.command("设置群头像")
    @perm_required(PermLevel.ADMIN)
    async def set_group_portrait(self, event: AiocqhttpMessageEvent):
        """(引用图片)设置群头像"""
        image_url = extract_image_url(chain=event.get_messages())
        if not image_url:
            yield event.plain_result("未获取到新头像")
            return
        await event.bot.set_group_portrait(
            group_id=int(event.get_group_id()),
            file=image_url,
        )
        yield event.plain_result("群头像更新啦>v<")

    @filter.command("设置群名")
    @perm_required(PermLevel.ADMIN)
    async def set_group_name(
        self, event: AiocqhttpMessageEvent, group_name: str | int | None = None
    ):
        """/设置群名 xxx"""
        if not group_name:
            yield event.plain_result("未输入新群名")
            return
        await event.bot.set_group_name(
            group_id=int(event.get_group_id()), group_name=str(group_name)
        )
        yield event.plain_result(f"本群群名更新为：{group_name}")

    @filter.command("发布群公告")
    @perm_required(PermLevel.ADMIN)
    async def send_group_notice(self, event: AiocqhttpMessageEvent):
        """(可引用一张图片)/发布群公告 xxx"""
        content = event.message_str.removeprefix("发布群公告").strip()
        if not content:
            yield event.plain_result("你又不说要发什么群公告")
            return
        if image_url := extract_image_url(chain=event.get_messages()):
            temp_path = os.path.join(
                self.plugin_data_dir,
                "group_notice_image",
                f"group_notice_image_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png",
            )
            image_path = await download_image(image_url, temp_path)
            if not image_path:
                yield event.plain_result("图片获取失败")
                return
        await event.bot._send_group_notice(
            group_id=int(event.get_group_id()), content=content, image=image_path
        )
        event.stop_event()

    @filter.command("查看群公告")
    @perm_required(PermLevel.MEMBER)
    async def get_group_notice(self, event: AiocqhttpMessageEvent):
        """查看群公告"""
        notices = await event.bot._get_group_notice(group_id=int(event.get_group_id()))

        formatted_messages = []
        for notice in notices:
            sender_id = notice["sender_id"]
            publish_time = datetime.fromtimestamp(notice["publish_time"]).strftime(
                "%Y-%m-%d %H:%M:%S"
            )
            message_text = notice["message"]["text"].replace("&#10;", "\n\n")

            formatted_message = (
                f"【{publish_time}-{sender_id}】\n\n"
                f"{textwrap.indent(message_text, '    ')}"
            )
            formatted_messages.append(formatted_message)

        notices_str = "\n\n\n".join(formatted_messages)
        url = await self.text_to_image(notices_str)
        yield event.image_result(url)
        # TODO 做张好看的图片来展示

    @filter.command("开启宵禁")
    @perm_required(PermLevel.ADMIN)
    async def start_curfew(
        self,
        event: AiocqhttpMessageEvent,
        input_start_time: str | None = None,
        input_end_time: str | None = None,
    ):
        """开启宵禁 00:00 23:59，重启bot后宵禁任务会被清除"""

        group_id = event.get_group_id()

        start_time_str = (
            (input_start_time or self.night_start_time).strip().replace("：", ":")
        )
        end_time_str = (
            (input_end_time or self.night_end_time).strip().replace("：", ":")
        )
        if (
            group_id in self.curfew_managers
            and self.curfew_managers[group_id].is_running()
        ):
            yield event.plain_result("本群已有宵禁任务在运行！请先关闭现有任务。")
            return

        try:
            curfew_manager = CurfewManager(
                bot=event.bot,
                group_id=group_id,
                start_time_str=start_time_str,
                end_time_str=end_time_str,
            )
            await curfew_manager.start_curfew_task()
            self.curfew_managers[group_id] = curfew_manager
            yield event.plain_result(
                f"已创建宵禁任务：{start_time_str}~{end_time_str}。"
            )
        except ValueError as e:
            yield event.plain_result(f"时间格式不正确：{e}")
        except Exception as e:
            logger.error(f"启动宵禁任务失败 (群ID: {group_id}): {e}", exc_info=True)
            yield event.plain_result("启动宵禁任务失败。")

    @filter.command("关闭宵禁")
    @perm_required(PermLevel.ADMIN)
    async def stop_curfew(self, event: AiocqhttpMessageEvent):
        """取消宵禁任务"""
        group_id = event.get_group_id()
        if not group_id:
            yield event.plain_result("无法获取群ID，操作失败。")
            return
        if (
            group_id in self.curfew_managers
            and self.curfew_managers[group_id].is_running()
        ):
            curfew_manager = self.curfew_managers[group_id]
            await curfew_manager.stop_curfew_task()
            del self.curfew_managers[group_id]
            yield event.plain_result("已关闭本群的宵禁")
        else:
            yield event.plain_result("本群没有宵禁任务在运行")
        event.stop_event()

    @filter.command("添加进群关键词")
    @perm_required(PermLevel.ADMIN)
    async def add_accept_keyword(self, event: AiocqhttpMessageEvent):
        """添加自动批准进群的关键词"""
        if keywords := event.message_str.removeprefix("添加进群关键词").strip().split():
            self.group_join_manager.add_keyword(event.get_group_id(), keywords)
            yield event.plain_result(f"新增进群关键词：{keywords}")
        else:
            yield event.plain_result("未输入任何关键词")

    @filter.command("删除进群关键词")
    @perm_required(PermLevel.ADMIN)
    async def remove_accept_keyword(self, event: AiocqhttpMessageEvent):
        """删除自动批准进群的关键词"""
        if keywords := event.message_str.removeprefix("删除进群关键词").strip().split():
            self.group_join_manager.remove_keyword(event.get_group_id(), keywords)
            yield event.plain_result(f"已删进群关键词：{keywords}")
        else:
            yield event.plain_result("未指定要删除的关键词")

    @filter.command("查看进群关键词")
    @perm_required(PermLevel.ADMIN)
    async def view_accept_keywords(self, event: AiocqhttpMessageEvent):
        """查看自动批准进群的关键词"""
        keywords = self.group_join_manager.get_keywords(event.get_group_id())
        if not keywords:
            yield event.plain_result("本群没有设置进群关键词")
            return
        yield event.plain_result(f"本群的进群关键词：{keywords}")

    @filter.command("添加进群黑名单")
    async def add_reject_ids(self, event: AiocqhttpMessageEvent):
        """添加指定ID到进群黑名单"""
        parts = event.message_str.strip().split(" ")
        if len(parts) < 2:
            yield event.plain_result("请提供至少一个用户ID。")
            return
        reject_ids = list(set(parts[1:]))
        self.group_join_manager.add_reject_id(event.get_group_id(), reject_ids)
        yield event.plain_result(f"进群黑名单新增ID：{reject_ids}")

    @filter.command("删除进群黑名单")
    @perm_required(PermLevel.ADMIN)
    async def remove_reject_ids(self, event: AiocqhttpMessageEvent):
        """从进群黑名单中删除指定ID"""
        parts = event.message_str.strip().split(" ")
        if len(parts) < 2:
            yield event.plain_result("请提供至少一个用户ID。")
            return
        ids = list(set(parts[1:]))
        self.group_join_manager.remove_reject_id(event.get_group_id(), ids)
        yield event.plain_result(f"已从黑名单中删除：{ids}")

    @filter.command("查看进群黑名单")
    @perm_required(PermLevel.ADMIN)
    async def view_reject_ids(self, event: AiocqhttpMessageEvent):
        """查看进群黑名单"""
        ids = self.group_join_manager.get_reject_ids(event.get_group_id())
        if not ids:
            yield event.plain_result("本群没有设置进群黑名单")
            return
        yield event.plain_result(f"本群的进群黑名单：{ids}")

    @filter.command("同意进群")
    @perm_required(PermLevel.ADMIN)
    async def agree_add_group(self, event: AiocqhttpMessageEvent, extra: str = ""):
        """同意申请者进群"""
        reply = await self.approve(event=event, extra=extra, approve=True)
        if reply:
            yield event.plain_result(reply)

    @filter.command("拒绝进群")
    @perm_required(PermLevel.ADMIN)
    async def refuse_add_group(self, event: AiocqhttpMessageEvent, extra: str = ""):
        """拒绝申请者进群"""
        reply = await self.approve(event=event, extra=extra, approve=False)
        if reply:
            yield event.plain_result(reply)

    @filter.platform_adapter_type(filter.PlatformAdapterType.AIOCQHTTP)
    async def event_monitoring(self, event: AiocqhttpMessageEvent):
        """监听进群/退群事件"""
        raw = getattr(event.message_obj, "raw_message", None)
        if not isinstance(raw, dict):
            return

        client = event.bot

        # 进群申请事件
        if (
            self.enable_audit
            and raw.get("post_type") == "request"
            and raw.get("request_type") == "group"
            and raw.get("sub_type") == "add"
        ):
            user_id = str(raw.get("user_id", ""))
            group_id = str(raw.get("group_id", ""))
            comment = raw.get("comment")
            flag = raw.get("flag", "")
            nickname = (await client.get_stranger_info(user_id=int(user_id)))[
                "nickname"
            ] or "未知昵称"
            reply = f"【收到进群申请】同意进群吗：\n昵称：{nickname}\nQQ：{user_id}\nflag：{flag}"
            if comment:
                reply += f"\n{comment}"
            if self.admin_audit:
                await self._send_admin(client, reply)
            else:
                yield event.plain_result(reply)

            if self.group_join_manager.should_reject(group_id, user_id):
                await client.set_group_add_request(
                    flag=flag, sub_type="add", approve=False, reason="黑名单用户"
                )
                yield event.plain_result("黑名单用户，已自动拒绝进群")
            elif comment and self.group_join_manager.should_approve(group_id, comment):
                await client.set_group_add_request(
                    flag=flag, sub_type="add", approve=True
                )
                yield event.plain_result("验证通过，已自动同意进群")

        # 主动退群事件
        elif (
            self.enable_black
            and raw.get("post_type") == "notice"
            and raw.get("notice_type") == "group_decrease"
            and raw.get("sub_type") == "leave"
        ):
            group_id = str(raw.get("group_id", ""))
            user_id = str(raw.get("user_id", ""))
            nickname = (await client.get_stranger_info(user_id=int(user_id)))[
                "nickname"
            ] or "未知昵称"
            reply = f"{nickname}({user_id}) 主动退群了"
            if self.auto_black:
                self.group_join_manager.blacklist_on_leave(group_id, user_id)
                reply += "，已拉进黑名单"
            yield event.plain_result(reply)

    @staticmethod
    async def approve(
        event: AiocqhttpMessageEvent, extra: str = "", approve: bool = True
    ) -> str | None:
        """处理进群申请"""
        text = get_reply_message_str(event)
        if not text:
            return "未引用任何【进群申请】"
        lines = text.split("\n")
        if "【收到进群申请】" in text and len(lines) >= 5:
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

    @filter.command("群友信息")
    @perm_required(PermLevel.MEMBER)
    async def get_group_member_list(self, event: AiocqhttpMessageEvent):
        """查看群友信息，人数太多时可能会处理失败"""
        yield event.plain_result("获取中...")
        client = event.bot
        group_id = event.get_group_id()
        members_data = await client.get_group_member_list(group_id=int(group_id))
        info_list = [
            (
                f"{format_time(member['join_time'])}："
                f"【{member['level']}】"
                f"{member['user_id']}-"
                f"{member['nickname']}"
            )
            for member in members_data
        ]
        info_list.sort(key=lambda x: datetime.strptime(x.split("：")[0], "%Y-%m-%d"))
        info_str = "进群时间：【等级】QQ-昵称\n\n"
        info_str += "\n\n".join(info_list)
        # TODO 做张好看的图片来展示
        url = await self.text_to_image(info_str)
        yield event.image_result(url)

    @filter.command("清理群友")
    @perm_required(PermLevel.MEMBER)
    async def clear_group_member(
        self,
        event: AiocqhttpMessageEvent,
        inactive_days: int = 30,
        under_level: int = 10,
    ):
        """/清理群友 未发言天数 群等级"""

        group_id = event.get_group_id()
        sender_id = event.get_sender_id()

        try:
            members_data = await event.bot.get_group_member_list(group_id=int(group_id))
        except Exception as e:
            yield event.plain_result(f"获取群成员信息失败：{e}")
            return

        threshold_ts = int(datetime.now().timestamp()) - inactive_days * 86400
        clear_ids: list[int] = []
        info_lines: list[str] = []

        for member in members_data:  # type: ignore
            last_sent = member.get("last_sent_time", 0)
            level = int(member.get("level", 0))
            user_id = member.get("user_id", "")
            nickname = member.get("nickname", "（无昵称）")

            if last_sent < threshold_ts and level < under_level:
                clear_ids.append(user_id)
                last_active_str = format_time(last_sent)
                info_lines.append(
                    f"- **{last_active_str}**｜**{level}**级｜`{user_id}` - {nickname}"
                )

        if not clear_ids:
            yield event.plain_result("无符合条件的群友")
            return

        # 按发言时间排序
        info_lines.sort(key=lambda x: datetime.strptime(x.split("**")[1], "%Y-%m-%d"))

        info_str = (
            f"### 共 **{len(clear_ids)}** 位群友 **{inactive_days}** 天内无发言，群等级低于 **{under_level}** 级\n\n"
            + "\n".join(info_lines)
            + "\n\n### 请发送 **确认清理** 或 **取消清理** 来处理这些群友！"
        )

        url = await self.text_to_image(info_str)
        yield event.image_result(url)

        yield event.chain_result([At(qq=cid) for cid in clear_ids])

        @session_waiter(timeout=60)  # type: ignore
        async def empty_mention_waiter(
            controller: SessionController, event: AiocqhttpMessageEvent
        ):
            if group_id != event.get_group_id() or sender_id != event.get_sender_id():
                return

            if event.message_str == "取消清理":
                await event.send(event.plain_result("清理群友任务已取消"))
                controller.stop()
                return

            if event.message_str == "确认清理":
                msg_list = []
                for clear_id in clear_ids:
                    try:
                        target_name = await get_nickname(event, user_id=clear_id)
                        await event.bot.set_group_kick(
                            group_id=int(group_id),
                            user_id=int(clear_id),
                            reject_add_request=False,
                        )
                        msg_list.append(f"✅ 已将 {target_name}({clear_id}) 踢出本群")
                    except Exception as e:
                        msg_list.append(f"❌ 踢出 {target_name}({clear_id}) 失败")
                        logger.error(f"踢出 {target_name}({clear_id}) 失败：{e}")

                if msg_list:
                    await event.send(event.plain_result("\n".join(msg_list)))
                controller.stop()

        try:
            await empty_mention_waiter(event)
        except TimeoutError as _:
            yield event.plain_result("等待超时！")
        except Exception as e:
            logger.error("清理群友任务出错: " + str(e))
        finally:
            event.stop_event()

    @filter.command("群管帮助")
    async def qq_admin_help(self, event: AiocqhttpMessageEvent):
        """查看群管帮助"""
        url = await self.text_to_image(ADMIN_HELP)
        yield event.image_result(url)

    async def terminate(self):
        """可选择实现异步的插件销毁方法，当插件被卸载/停用时会调用。"""
        # 遍历所有宵禁管理器并停止它们
        for group_id, manager in list(self.curfew_managers.items()):
            if manager.is_running():
                await manager.stop_curfew_task()
            del self.curfew_managers[group_id]
        logger.info("插件 astrbot_plugin_QQAdmin 已被终止。")
