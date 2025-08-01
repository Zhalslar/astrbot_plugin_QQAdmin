
<div align="center">

![:name](https://count.getloli.com/@astrbot_plugin_QQAdmin?name=astrbot_plugin_QQAdmin&theme=minecraft&padding=6&offset=0&align=top&scale=1&pixelated=1&darkmode=auto)

# astrbot_plugin_QQAdmin

_✨ [astrbot](https://github.com/AstrBotDevs/AstrBot) QQ群管插件 ✨_  

[![License](https://img.shields.io/badge/License-MIT-green.svg)](https://opensource.org/licenses/MIT)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](https://www.python.org/)
[![AstrBot](https://img.shields.io/badge/AstrBot-3.4%2B-orange.svg)](https://github.com/Soulter/AstrBot)
[![GitHub](https://img.shields.io/badge/作者-Zhalslar-blue)](https://github.com/Zhalslar)

</div>

## 🤝 介绍

- 本插件利用Onebot协议接口，实现了QQ群的各种管理功能，旨在帮助用户更方便地管理群聊。  
- 功能包括：禁言、全体禁言、踢人、拉黑、改群昵称、改头衔、设管理员、设精华、撤回消息、改群头像、改群名、发群公告等等。
- 同时本插件实现了权限控制：超级管理员 > 群主 > 管理员 > 成员。

## 📦 安装

- 可以直接在astrbot的插件市场搜索astrbot_plugin_QQAdmin，点击安装，耐心等待安装完成即可  

- 或者可以直接克隆源码到插件文件夹：

```bash
# 克隆仓库到插件目录
cd /AstrBot/data/plugins
git clone https://github.com/Zhalslar/astrbot_plugin_QQAdmin

# 控制台重启AstrBot
```

## ⌨️ 使用说明

群管功能丰富，指令繁多，可以发送“/群管帮助”命令来查看具体用法。

### 群管插件命令表

| 命令 | 功能描述 |
|------|----------|
| `/禁言 <时长(秒)> @<用户>` | 禁言指定用户，不填时长则随机禁言 |
| `/禁我 <时长(秒)>` | 禁言自己，不填时长则随机禁言 |
| `/解禁 @<用户>` | 解除指定用户的禁言 |
| `/开启全员禁言` | 开启本群的全体禁言 |
| `/关闭全员禁言` | 关闭本群的全体禁言 |
| `/改名 <新昵称> @<用户>` | 修改指定用户的群昵称 |
| `/改我 <新昵称>` | 修改自己的群昵称 |
| `/头衔 <新头衔> @<用户>` | 设置指定用户的群头衔 |
| `/申请头衔 <新头衔>` | 设置自己的群头衔 |
| `/踢了 @<用户>` | 将指定用户踢出群聊 |
| `/拉黑 @<用户>` | 将指定用户踢出群聊并拉黑 |
| `/设置管理员 @<用户>` | 设置指定用户为管理员 |
| `/取消管理员 @<用户>` | 取消指定用户的管理员身份 |
| `/设为精华` | 将引用的消息设置为群精华 |
| `/移除精华` | 将引用的消息移出群精华 |
| `/查看精华` | 查看群精华消息列表 |
| `/撤回` | 撤回引用的消息和自己发送的消息 |
| `/设置群头像` | 引用图片设置群头像 |
| `/设置群名 <新群名>` | 修改群名称 |
| `/发布群公告 <内容>` | 发布群公告，可引用图片 |
| `/查看群公告` | 查看群公告 |
| `/开启宵禁 <HH:MM> <HH:MM>` | 开启宵禁任务，需输入开始时间和结束时间（24小时制） |
| `/关闭宵禁` | 关闭当前群的宵禁任务 |
| `/添加进群关键词 <关键词>` | 添加自动批准进群关键词，多个关键词用空格分隔 |
| `/删除进群关键词 <关键词>` | 删除自动批准进群关键词，多个关键词用空格分隔 |
| `/查看进群关键词` | 查看当前群的自动批准进群关键词 |
| `/添加进群黑名单 <QQ号>` | 添加进群黑名单，多个 QQ 号用空格分隔 |
| `/删除进群黑名单 <QQ号>` | 从进群黑名单中删除指定 QQ 号 |
| `/查看进群黑名单` | 查看当前群的进群黑名单 |
| `/同意进群` | 同意引用的进群申请 |
| `/拒绝进群 <理由>` | 拒绝引用的进群申请，可附带拒绝理由 |
| `/群友信息` | 查看群成员信息 |
| `/清理群友 <未发言天数> <群等级>` | 清理群友，可指定未发言天数和群等级（默认30天、等级低于10） |
| `/群管帮助` | 显示本插件的帮助信息 |

## 常见问题

Q: 格式校验未通过: ['错误的类型 forbidden_config.forbidden_words: 期望是 list, 得到了 str', '错误的类型 forbidden_config.forbidden_words: 期望是 list, 得到了 str']  
A: 该问题为历史遗留问题，找到/AstrBot/data/config/astrbot_plugin_qqadmin_config.json，将 forbidden_words:"", 改成 forbidden_words": [],

## 🤝 配置

进入插件配置面板进行配置

- 可自定义超级管理员名单（这里的超管不是全局超管，而是仅仅针对本插件而言）
- 所有命令都可以自定义使用者的身份等级：超级管理员 > 群主 > 管理员 > 成员
- 可自定义随机禁言的时长范围
- 可自定义默认的宵禁时长范围
- 更多自定义配置自行探索
![tmp1872](https://github.com/user-attachments/assets/39eb983d-7eb0-4df7-a8b7-1f5fb8f7eef0)

## 📌 注意事项

- 本插件目前仅测试了napcat协议端，其他协议端可能会存在一些不兼容问题（以具体情况为准）
- 想第一时间得到反馈的可以来作者的插件反馈群（QQ群）：460973561（不点star不给进）
- 群管插件目前功能已基本稳定，建议非必要不更新

## 👥 贡献指南

- 🌟 Star 这个项目！（点右上角的星星，感谢支持！）
- 🐛 提交 Issue 报告问题
- 💡 提出新功能建议
- 🔧 提交 Pull Request 改进代码

## 🤝 TODO

- [x] 权限控制
- [x] 禁言、解禁、随机禁言、全体禁言、解除全体禁言
- [x] 踢人、拉黑
- [x] 改群昵称、改头衔
- [x] 设置管理员、取消管理员
- [x] 撤回指定消息
- [x] 改群头像、改群名
- [x] 发布群公告、删除群公告
- [x] 定时宵禁
- [x] 违禁词撤回并禁言
- [x] 进群审批
- [x] 清理长时间不活跃的群友
- [ ] 群文件管理（打算另起一个插件来写，尽请期待）
