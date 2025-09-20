import asyncio
from collections import defaultdict, deque
import random
import time
from astrbot.api import logger
from astrbot.core.config.astrbot_config import AstrBotConfig
from astrbot.core.platform.sources.aiocqhttp.aiocqhttp_message_event import (
    AiocqhttpMessageEvent,
)
from ..utils import get_ats, get_nickname


class EnhanceHandle:
    def __init__(self, config: AstrBotConfig):
        self.conf = config
        self.msg_timestamps: dict[str, dict[str, deque[float]]] = defaultdict(
            lambda: defaultdict(lambda: deque(maxlen=self.conf["spamming"]["count"]))
        )
        self.last_banned_time: dict[str, dict[str, float]] = defaultdict(
            lambda: defaultdict(float)
        )
        # 记录投票 {group_id: {"target": target_id, "votes": {user_id: bool}, "expire": timestamp, "threshold": threshold,}}
        self.vote_cache: dict[str, dict] = {}

    async def check_forbidden_words(self, event: AiocqhttpMessageEvent):
        """违禁词禁言"""
        # 群聊白名单
        if event.get_group_id() not in self.conf["forbidden"]["whitelist"]:
            return
        if not self.conf["forbidden"]["words"] or not event.message_str:
            return
        # 检测违禁词
        for word in self.conf["forbidden"]["words"]:
            if word in event.message_str:
                # 撤回消息
                try:
                    message_id = event.message_obj.message_id
                    await event.bot.delete_msg(message_id=int(message_id))
                except Exception:
                    pass
                # 禁言发送者
                if self.conf["forbidden"]["ban_time"] > 0:
                    try:
                        await event.bot.set_group_ban(
                            group_id=int(event.get_group_id()),
                            user_id=int(event.get_sender_id()),
                            duration=self.conf["forbidden"]["ban_time"],
                        )
                    except Exception:
                        logger.error(f"bot在群{event.get_group_id()}权限不足，禁言失败")
                        pass
                break

    async def spamming_ban(self, event: AiocqhttpMessageEvent):
        """刷屏禁言"""
        group_id = event.get_group_id()
        sender_id = event.get_sender_id()
        if (
            sender_id == event.get_self_id()
            or self.conf["spamming"]["count"] == 0
            or len(event.get_messages()) == 0
        ):
            return
        if group_id not in self.conf["spamming"]["whitelist"]:
            return
        now = time.time()

        last_time = self.last_banned_time[group_id][sender_id]
        if now - last_time < self.conf["spamming"]["ban_time"]:
            return

        timestamps = self.msg_timestamps[group_id][sender_id]
        timestamps.append(now)
        count = self.conf["spamming"]["count"]
        if len(timestamps) >= count:
            recent = list(timestamps)[-count:]
            intervals = [recent[i + 1] - recent[i] for i in range(count - 1)]
            if (
                all(
                    interval < self.conf["spamming"]["interval"]
                    for interval in intervals
                )
                and self.conf["spamming"]["ban_time"]
            ):
                # 提前写入禁止标记，防止并发重复禁
                self.last_banned_time[group_id][sender_id] = now

                try:
                    await event.bot.set_group_ban(
                        group_id=int(group_id),
                        user_id=int(sender_id),
                        duration=self.conf["spamming"]["ban_time"],
                    )
                    nickname = await get_nickname(event, sender_id)
                    await event.send(
                        event.plain_result(f"检测到{nickname}刷屏，已禁言")
                    )
                except Exception:
                    logger.error(f"bot在群{group_id}权限不足，禁言失败")
                timestamps.clear()


    async def start_vote_mute(self, event, ban_time: int | None = None):
        """
        发起投票禁言：如果已有对该用户的投票，直接提示
        """
        target_ids = get_ats(event)
        if not target_ids:
            return
        target_id = target_ids[0]
        if not ban_time or not isinstance(ban_time, int):
            ban_time = random.randint(*map(int, self.conf["random_ban_time"].split("~")))
        group_id = event.get_group_id()

        if group_id in self.vote_cache:
            await event.send(event.plain_result("群内已有正在进行的禁言投票"))
            return

        # 动态计算 threshold
        base_threshold = 3
        max_threshold = 10
        threshold = base_threshold + ban_time // 300  # 每 300s 增加 1 票
        threshold = max(base_threshold, min(threshold, max_threshold))

        expire_at = time.time() + self.conf["vote_ban"]["ttl"]
        self.vote_cache[group_id] = {
            "target": target_id,
            "votes": {},
            "ban_time": ban_time,
            "expire": expire_at,
            "threshold": threshold,
        }

        nickname = await get_nickname(event, target_id)
        await event.send(
            event.plain_result(
                f"已发起对 {nickname} 的禁言投票(禁言{ban_time}秒)，输入“赞同禁言/反对禁言”进行表态，{self.conf['vote_ban']['ttl']}秒后结算"
            )
        )

        # ===== 新增：定时结算逻辑 =====
        async def settle_vote():
            await asyncio.sleep(self.conf["vote_ban"]["ttl"])
            record = self.vote_cache.get(group_id)
            if not record:
                return  # 已被提前结算
            votes = list(record["votes"].values())
            agree_count = sum(votes)
            disagree_count = len(votes) - agree_count
            nickname2 = await get_nickname(event, record["target"])

            # 到期按多数票决定（平票视为否决）
            if agree_count > disagree_count:
                try:
                    await event.bot.set_group_ban(
                        group_id=int(group_id),
                        user_id=int(record["target"]),
                        duration=record["ban_time"],
                    )
                    await event.send(event.plain_result(f"投票时间到！已禁言{nickname2}"))
                except Exception:
                    logger.error(f"bot在群{group_id}权限不足，禁言失败")
            else:
                await event.send(
                    event.plain_result(f"投票时间到！禁言被否决，{nickname2}安全了")
                )
            # 清理投票记录
            del self.vote_cache[group_id]

        asyncio.create_task(settle_vote())


    async def vote_mute(self, event: AiocqhttpMessageEvent, agree: bool):
        """
        赞同/反对禁言
        agree=True 表示赞同，False 表示反对
        """
        group_id = event.get_group_id()
        voter_id = event.get_sender_id()

        record = self.vote_cache.get(group_id)
        if not record:
            await event.send(event.plain_result("当前没有进行中的禁言投票"))
            return

        threshold = record["threshold"]
        target_id = record["target"]

        # 目标不能投票（提前检查，避免把目标的票计入）
        if voter_id == target_id:
            await event.send(event.plain_result("你不能参与投票"))
            return

        # 记录/更新该用户的立场
        record["votes"][voter_id] = agree

        votes = list(record["votes"].values())
        agree_count = sum(votes)
        disagree_count = len(votes) - agree_count
        nickname = await get_nickname(event, target_id)

        # 提前达成赞同阈值 → 立即禁言
        if agree_count >= threshold:
            try:
                await event.bot.set_group_ban(
                    group_id=int(group_id),
                    user_id=int(target_id),
                    duration=record["ban_time"],
                )
                await event.send(event.plain_result(f"投票通过！已禁言{nickname}"))
            except Exception:
                logger.error(f"bot在群{group_id}权限不足，禁言失败")
            finally:
                # 清理记录（定时任务见前面会检测到记录已删除并直接返回）
                del self.vote_cache[group_id]
            return

        # 提前达成反对阈值 → 立即否决
        if disagree_count >= threshold:
            await event.send(event.plain_result(f"禁言投票被否决，{nickname}安全了"))
            del self.vote_cache[group_id]
            return

        # 否则展示当前进度
        await event.send(
            event.plain_result(
                f"禁言【{nickname}】：\n赞同({agree_count}/{threshold})\n反对({disagree_count}/{threshold})"
            )
        )
