# Windows IM 外发（阿里旺旺）

> case 级业务说明：记录本组 IM case 的覆盖范围与逐动作行为约定，供写/改这批 case 时查阅。
> 属**纯业务**内容，随 case 演进更新即可，不进 README / tech_design 等框架文档
> （见 [AGENTS.md](../../AGENTS.md) §4）。托盘识别、独立窗口跑法等能力/运行说明仍在
> [README.md](../../README.md)。

## 阿里旺旺图片外发

`cases/desktop_app/im/windows/case_aliww.py` 覆盖拖拽、对话框上传、复制粘贴和自带截图四类
外发。阿里旺旺只支持图片，前三类从 `assets/samples/` 生成本次唯一名图片副本；四类均先把
唯一文件名文字粘进输入框，再加入图片，最后由 hard step 只按一次回车发送。拖拽分屏后会先
关闭本 case 的资源管理器并恢复阿里旺旺原窗口尺寸，再确认图片预览。

若托盘按钮的 UIAutomation Name 只有淘宝账号串、不含“旺旺”等产品名，在不入库的
`config/config.secret.yaml` 中配置：

```yaml
platform:
  overrides:
    windows:
      tray_hints:
        aliww: ["你的托盘账号匹配串"]
```
