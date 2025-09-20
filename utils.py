from datetime import datetime
import os

from aiohttp import ClientSession
from astrbot.core.message.components import At, BaseMessageComponent, Image, Reply
from astrbot.core.platform.sources.aiocqhttp.aiocqhttp_message_event import (
    AiocqhttpMessageEvent,
)
from astrbot import logger

BAN_ME_QUOTES: list[str] = [
    "还真有人有这种奇怪的要求",
    "满足你",
    "静一会也挺好的",
    "是你自己要求的哈！",
    "行，你去静静",
    "好好好，禁了",
    "主人你没事吧？",
]


ADMIN_HELP = (
    "【群管帮助】(前缀以bot设置的为准)\n\n"
    "- 禁言 <时长(秒)> @<用户> - 禁言指定用户，不填时长则随机\n"
    "- 禁我 <时长(秒)> - 禁言自己，不填时长则随机\n"
    "- 解禁 @<用户> - 解除指定用户的禁言\n"
    "- 开启全员禁言 - 开启本群的全体禁言\n"
    "- 关闭全员禁言 - 关闭本群的全体禁言\n"
    "- 改名 <新昵称> @<用户> - 修改指定用户的群昵称\n"
    "- 改我 <新昵称> - 修改自己的群昵称\n"
    "- 头衔 <新头衔> @<用户> - 设置指定用户的群头衔\n"
    "- 申请头衔 <新头衔> - 设置自己的群头衔\n"
    "- 踢了 @<用户> - 将指定用户踢出群聊\n"
    "- 拉黑 @<用户> - 将指定用户踢出群聊并拉黑\n"
    "- 上管 @<用户> - 设置指定用户为管理员\n"
    "- 下管 @<用户> - 取消指定用户的管理员身份\n"
    "- 设为精华 - 将引用的消息设置为群精华\n"
    "- 移除精华 - 将引用的消息移出群精华\n"
    "- 查看精华 - 查看群精华消息列表\n"
    "- 撤回 - (引用消息)撤回 | 撤回 @某人(默认bot) 数量(默认10)\n"
    "- 设置群头像 - 引用图片设置群头像\n"
    "- 设置群名 <新群名> - 修改群名称\n"
    "- 发布群公告 <内容> - 发布群公告，可引用图片\n"
    "- 查看群公告 - 查看群公告\n"
    "- 开启宵禁 <HH:MM> <HH:MM> - 开启宵禁任务，需输入开始时间、结束时间\n"
    "- 关闭宵禁 - 关闭当前群的宵禁任务\n"
    "- 添加进群关键词 <关键词> - 添加自动批准进群的关键词，多个关键词用空格分隔\n"
    "- 删除进群关键词 <关键词> - 删除自动批准进群的关键词，多个关键词用空格分隔\n"
    "- 查看进群关键词 - 查看当前群的自动批准进群关键词\n"
    "- 添加进群黑名单 <QQ号> - 添加进群黑名单，多个QQ号用空格分隔\n"
    "- 删除进群黑名单 <QQ号> - 从进群黑名单中删除指定QQ号\n"
    "- 查看进群黑名单 - 查看当前群的进群黑名单\n"
    "- 同意进群 - 同意引用的进群申请\n"
    "- 拒绝进群 <理由> - 拒绝引用的进群申请，可附带拒绝理由\n"
    "- 群友信息 - 查看群成员信息\n"
    "- 清理群友 <未发言天数> <群等级> - 清理群友，可指定未发言天数和群等级\n"
    "- 群管帮助 - 显示本插件的帮助信息"
)


def print_logo():
    """打印欢迎 Logo"""
    logo = r"""
 ________  __                  __            __
|        \|  \                |  \          |  \
 \$$$$$$$$| $$____    ______  | $$  _______ | $$  ______    ______
    /  $$ | $$    \  |      \ | $$ /       \| $$ |      \  /      \
   /  $$  | $$$$$$$\  \$$$$$$\| $$|  $$$$$$$| $$  \$$$$$$\|  $$$$$$\
  /  $$   | $$  | $$ /      $$| $$ \$$    \ | $$ /      $$| $$   \$$
 /  $$___ | $$  | $$|  $$$$$$$| $$ _\$$$$$$\| $$|  $$$$$$$| $$
|  $$    \| $$  | $$ \$$    $$| $$|       $$| $$ \$$    $$| $$
 \$$$$$$$$ \$$   \$$  \$$$$$$$ \$$ \$$$$$$$  \$$  \$$$$$$$ \$$

        """
    print("\033[92m" + logo + "\033[0m")  # 绿色文字
    print("\033[94m欢迎使用群管插件！\033[0m")  # 蓝色文字


async def get_nickname(event: AiocqhttpMessageEvent, user_id) -> str:
    """获取指定群友的群昵称或Q名"""
    client = event.bot
    group_id = event.get_group_id()
    all_info = await client.get_group_member_info(
        group_id=int(group_id), user_id=int(user_id)
    )
    return all_info.get("card") or all_info.get("nickname")


def get_ats(event: AiocqhttpMessageEvent) -> list[str]:
    """获取被at者们的id列表"""
    return [
        str(seg.qq)
        for seg in event.get_messages()
        if (isinstance(seg, At) and str(seg.qq) != event.get_self_id())
    ]


def get_replyer_id(event: AiocqhttpMessageEvent) -> str | None:
    """获取被引用消息者的id"""
    for seg in event.get_messages():
        if isinstance(seg, Reply):
            return str(seg.sender_id)


def get_reply_message_str(event: AiocqhttpMessageEvent) -> str | None:
    """
    获取被引用的消息解析后的纯文本消息字符串。
    """
    return next(
        (
            seg.message_str
            for seg in event.message_obj.message
            if isinstance(seg, Reply)
        ),
        "",
    )


def format_time(timestamp):
    """格式化时间戳"""
    return datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d")


async def download_image(url: str, save_path: str) -> str | None:
    """下载图片并保存到本地"""
    url = url.replace("https://", "http://")
    try:
        async with ClientSession() as client:
            response = await client.get(url)
            img_bytes = await response.read()

            os.makedirs(os.path.dirname(save_path), exist_ok=True)

            with open(save_path, "wb") as img_file:
                img_file.write(img_bytes)

            logger.info(f"图片已保存: {save_path}")
            return save_path
    except Exception as e:
        logger.error(f"图片下载并保存失败: {e}")
        return None


def extract_image_url(chain: list[BaseMessageComponent]) -> str | None:
    """从消息链中提取图片URL"""
    for seg in chain:
        if isinstance(seg, Image):
            return seg.url
        elif isinstance(seg, Reply) and seg.chain:
            for reply_seg in seg.chain:
                if isinstance(reply_seg, Image):
                    return reply_seg.url
    return None



