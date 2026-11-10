# Windows AI应用外发（千问 / 元宝 / Kimi / Poe）

> case 级业务说明：记录本组 case 的覆盖范围与逐动作行为约定，供写/改这批 case 时查阅。
> 属**纯业务**内容，随 case 演进更新即可，不进 README / tech_design 等框架文档
> （见 [AGENTS.md](../../AGENTS.md) §4：纯业务改动无需更新框架文档）。

`cases/desktop_app/ai_chat/windows/case_<app>.py` 使用独立的
`desktop_app.ai_chat` 通道与 `ai_chat_windows_common.py` 脚手架，不复用 IM 的联系人/群聊
语义。当前已适配四款：

- **千问 / 元宝**：各 5 条 —— 拖拽文档、上传文档、复制粘贴文档、上传图片、截屏提问；
- **Kimi**：4 条 —— 文件与图片共用同一个上传入口，故只保留上传文件（拖拽文档、上传文件、
  复制粘贴文档、截图）；
- **Poe**：3 条 —— 拖拽文档、上传文件、复制粘贴文档，不含截图。

每条 case 先按 app 要求确认发送前状态（千问需“日常模式”，办公模式下真机手动发送也不可用；
元宝/Kimi/Poe 无模式切换），再进入左侧第一条历史对话；左侧没有历史对话时沿用当前对话页。输入区
必须为空，否则只请求用户处理，不自动清除草稿。附件前先写入“这是测试文件，收到后回复收到即可，
无需解析”和本次唯一文件名/截图标识，声明不单独发送。发送方式随 app 而定：千问/元宝/Poe 文档
由 hard step 只按一次回车；**Kimi 回车只换行、不发送，文档改由 AI 只点击一次发送按钮**，并在
同一步做 change 验收（要求聊天区新增我方消息且输入框已清空）。Poe 点“+”后直接弹系统文件对话框，
没有二级附件菜单。图片/截图统一由 AI 只点击一次发送按钮。视觉验收要求同时看到我方本次声明、
唯一标识和附件、输入框清空、该消息后的新 AI 回复；AI 回复不能代替我方外发证据。文字与图片
显示为相邻两条我方消息也属于同一轮外发。

```powershell
# 仅验证 GUI 动作，不声明 DLP 策略（把 qianwen 换成 yuanbao / kimi 即可）
.\scripts\run_case.ps1 -Filter desktop_app.ai_chat.qianwen -DebugShots
.\scripts\wait_run.ps1
```

不传 `-Policy` 时不启用客户端日志或服务端控制面验收。即使 GUI/视觉动作成功，最终 DLP
结论仍是 `inconclusive`，不能描述为生产策略通过。
