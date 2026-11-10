# Windows 浏览器外发（DLPTest HTTPS POST）

> case 级业务说明：记录本组浏览器 case 的覆盖范围与逐动作行为约定，供写/改这批 case 时查阅。
> 属**纯业务**内容，随 case 演进更新即可，不进 README / tech_design 等框架文档
> （见 [AGENTS.md](../../AGENTS.md) §4）。浏览器通道的能力概述、运行命令、进程清理等框架/配置
> 行为仍在 [README.md](../../README.md) 的「Windows 浏览器通道」节；完整设计与真机证据见
> 归档稿 [browser_channel_design.md](../archive/browser_channel_design.md)（CHG-014）。

`cases/web/other/windows/` 已接入 Edge、谷歌、360 极速、Firefox、2345、360 安全、猎豹、
傲游、QQ、搜狗的 DLPTest HTTPS POST；世界之窗因页面/UI 异常本期跳过。

逐动作行为约定：

- `drag_drop`：浏览器最大化铺底，AI 从左侧资源管理器把唯一文件拖入右侧上传框；
- `click_upload`：AI 点击上传框，完整文件路径由 hard step 写入系统文件对话框；
- 上传前将 File upload 卡片居中；Submit 不可见时只允许向下滚动一次；
- 提交前 hard step 重新激活浏览器，Submit 的 click/scroll 各最多一次；
- Firefox、QQ、360 极速的启动提示由独立 AI step 按视觉关闭，禁止固定坐标；
- 两条都以完整 `Received. Nothing was stored...` 文案做视觉验收。文件进入队列本身
  不算完成外发。
