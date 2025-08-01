import asyncio
from datetime import datetime, time, timedelta, timezone
import json
from pathlib import Path
from typing import Optional

from aiocqhttp import CQHttp
from astrbot import logger

# 创建北京时区对象 (UTC+8)
BEIJING_TIMEZONE = timezone(timedelta(hours=8))
CURFEW_DATA_PATH = Path("data/curfew_tasks.json")

class Curfew:
    """
    管理群组宵禁功能的类。
    每个 CurfewManager 实例负责一个群组的宵禁状态和调度。
    """

    def __init__(
        self,
        bot: CQHttp,
        group_id: str,
        start_time_str: str,
        end_time_str: str,
    ):
        self.bot = bot
        self.group_id = group_id
        self._start_time_str = start_time_str
        self._end_time_str = end_time_str
        self.curfew_task: Optional[asyncio.Task] = None
        self.whole_ban_status: bool = False
        self._active = False  # 添加活动状态标志

        try:
            # 解析为无时区的time对象
            self.start_time: time = datetime.strptime(start_time_str, "%H:%M").time()
            self.end_time: time = datetime.strptime(end_time_str, "%H:%M").time()
        except ValueError as e:
            logger.error(f"宵禁时间格式错误 for group {group_id}: {e}", exc_info=True)
            raise ValueError("宵禁时间格式必须是 HH:MM") from e

        logger.info(
            f"群 {self.group_id} 的宵禁管理器初始化成功，北京时间段：{start_time_str}~{end_time_str}"
        )

    def is_running(self) -> bool:
        """检查宵禁任务是否正在运行。"""
        return self.curfew_task is not None and not self.curfew_task.done()

    async def start_curfew_task(self):
        """启动宵禁后台调度任务。"""
        if self.is_running():
            logger.warning(f"群 {self.group_id} 的宵禁任务已在运行，无需重复启动。")
            return

        if self._active:
            logger.warning(f"群 {self.group_id} 的宵禁任务已激活，无需重复启动。")
            return

        self._active = True
        self.curfew_task = asyncio.create_task(self._scheduler_loop())
        logger.info(f"群 {self.group_id} 的宵禁任务已启动。")

    async def stop_curfew_task(self):
        """停止宵禁后台调度任务。"""
        if not self._active:
            logger.warning(f"群 {self.group_id} 的宵禁任务未运行，无需停止。")
            return

        self._active = False

        if self.curfew_task and not self.curfew_task.done():
            self.curfew_task.cancel()
            try:
                await self.curfew_task  # 等待任务完成取消
            except asyncio.CancelledError:
                logger.info(f"群 {self.group_id} 的宵禁任务已成功取消。")
            except Exception as e:
                logger.error(
                    f"停止群 {self.group_id} 宵禁任务时发生异常: {e}", exc_info=True
                )
        self.curfew_task = None
        logger.info(f"群 {self.group_id} 的宵禁任务已停止。")

    async def _scheduler_loop(self):
        """宵禁后台调度器，使用时间差计算代替循环检查"""
        logger.info(
            f"群 {self.group_id} 宵禁调度循环开始，北京时间段：{self.start_time.strftime('%H:%M')}~{self.end_time.strftime('%H:%M')}"
        )

        try:
            while self._active:
                # 获取当前北京时间 (UTC+8)
                current_dt = datetime.now(BEIJING_TIMEZONE)
                current_date = current_dt.date()
                if self.start_time >= self.end_time:
                    # 跨天宵禁逻辑
                    if current_dt.time() < self.end_time:
                        # 当前在第二天的凌晨，起始时间应为昨天
                        start_dt = datetime.combine(current_date - timedelta(days=1), self.start_time)
                        end_dt = datetime.combine(current_date, self.end_time)
                    else:
                        # 当前在第一天晚上，结束时间为第二天
                        start_dt = datetime.combine(current_date, self.start_time)
                        end_dt = datetime.combine(current_date + timedelta(days=1), self.end_time)
                else:
                    # 不跨天，直接使用当天的时间
                    start_dt = datetime.combine(current_date, self.start_time)
                    end_dt = datetime.combine(current_date, self.end_time)

                # 设置为北京时区
                start_dt = start_dt.replace(tzinfo=BEIJING_TIMEZONE)
                end_dt = end_dt.replace(tzinfo=BEIJING_TIMEZONE)

                # 判断是否在宵禁时段内
                is_during_curfew = start_dt <= current_dt < end_dt

                # 计算下次检查时间 - 使用更智能的时间差计算
                if is_during_curfew:
                    next_check = min(end_dt - current_dt, timedelta(seconds=60))
                    if not self.whole_ban_status:
                        await self._enable_curfew()
                else:
                    # 计算到宵禁开始的时间
                    if current_dt < start_dt:
                        next_check = start_dt - current_dt
                    else:
                        # 如果当前时间已超过结束时间，计算到明天的开始时间
                        next_check = (start_dt + timedelta(days=1)) - current_dt

                    if self.whole_ban_status:
                        await self._disable_curfew()

                # 确保等待时间至少1秒，不超过1小时
                sleep_time = max(
                    timedelta(seconds=1), min(next_check, timedelta(hours=1))
                )
                await asyncio.sleep(sleep_time.total_seconds())

        except asyncio.CancelledError:
            # 任务被取消，正常退出
            logger.info(f"群 {self.group_id} 的宵禁任务被取消")
            raise
        except Exception as e:
            logger.error(
                f"群 {self.group_id} 宵禁任务发生未处理异常: {e}", exc_info=True
            )
        finally:
            self._active = False
            self.curfew_task = None

    async def _enable_curfew(self):
        """启用宵禁（内部方法）"""
        try:
            await self.bot.send_group_msg(
                group_id=int(self.group_id),
                message=f"【{self.start_time.strftime('%H:%M')}】本群宵禁开始！",
            )
            await self.bot.set_group_whole_ban(group_id=int(self.group_id), enable=True)
            self.whole_ban_status = True
            logger.info(f"群 {self.group_id} 已开启全体禁言。")
        except Exception as e:
            logger.error(f"群 {self.group_id} 宵禁开启失败: {e}", exc_info=True)

    async def _disable_curfew(self):
        """禁用宵禁（内部方法）"""
        try:
            await self.bot.send_group_msg(
                group_id=int(self.group_id),
                message=f"【{self.end_time.strftime('%H:%M')}】本群宵禁结束！",
            )
            await self.bot.set_group_whole_ban(
                group_id=int(self.group_id), enable=False
            )
            self.whole_ban_status = False
            logger.info(f"群 {self.group_id} 已解除全体禁言。")
        except Exception as e:
            logger.error(f"群 {self.group_id} 宵禁解除失败: {e}", exc_info=True)


class CurfewManager:
    """统一管理群宵禁任务及其持久化"""

    def __init__(self, bot):
        self.bot = bot
        self.tasks: dict[str, Curfew] = {}
        self.load_tasks()

    def load_tasks(self):
        """从JSON加载所有宵禁任务（用于重启恢复）"""
        if not CURFEW_DATA_PATH.exists():
            logger.info("未找到宵禁数据文件，跳过加载。")
            return

        try:
            with open(CURFEW_DATA_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            logger.error(f"加载宵禁任务失败：{e}", exc_info=True)
            return

        for group_id, times in data.items():
            try:
                cw = Curfew(
                    bot=self.bot,
                    group_id=group_id,
                    start_time_str=times["start_time"],
                    end_time_str=times["end_time"],
                )
                self.tasks[group_id] = cw
                asyncio.create_task(cw.start_curfew_task())
                logger.info(f"群 {group_id} 的宵禁任务已恢复。")
            except Exception as e:
                logger.error(f"恢复群 {group_id} 的宵禁任务失败：{e}", exc_info=True)

    def save_tasks(self):
        """将当前所有任务信息保存到JSON"""
        try:
            CURFEW_DATA_PATH.parent.mkdir(parents=True, exist_ok=True)
            with open(CURFEW_DATA_PATH, "w", encoding="utf-8") as f:
                json.dump(
                    {
                        gid: {
                            "start_time": cm._start_time_str,
                            "end_time": cm._end_time_str,
                        }
                        for gid, cm in self.tasks.items()
                    },
                    f,
                    ensure_ascii=False,
                    indent=2,
                )
            logger.info("宵禁任务数据已保存。")
        except Exception as e:
            logger.error(f"保存宵禁任务失败：{e}", exc_info=True)

    async def stop_all_tasks(self):
        """关闭并保存所有宵禁任务"""
        for cw in self.tasks.values():
            await cw.stop_curfew_task()
        self.save_tasks()

    async def enable_curfew(
        self, group_id: str, start_time: str, end_time: str
    ):
        """对外接口：开启一个群的宵禁任务"""
        if group_id in self.tasks:
            await self.tasks[group_id].stop_curfew_task()

        cw = Curfew(self.bot, group_id, start_time, end_time)
        self.tasks[group_id] = cw
        await cw.start_curfew_task()
        self.save_tasks()
        logger.info(f"群 {group_id} 的宵禁任务已添加并启动")


    async def disable_curfew(self, group_id: str) -> bool:
        """对外接口：关闭一个群的宵禁任务"""
        cw = self.tasks.pop(group_id, None)
        if cw:
            await cw.stop_curfew_task()
            self.save_tasks()
            logger.info(f"群 {group_id} 的宵禁任务已停止并移除。")
            return True
        else:
            logger.warning(f"尝试关闭不存在的宵禁任务：群 {group_id}")
            return False

    def get_task(self, group_id: str) -> Curfew | None:
        """获取某个群的宵禁管理器（供外部调用）"""
        return self.tasks.get(group_id)
