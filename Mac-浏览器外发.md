# Mac 浏览器外发用例

## 覆盖范围

`cases/web/other/mac/` 已接入以下浏览器，每款包含 DLPTest HTTPS POST 的拖拽上传和点击上传：

| 浏览器 | case 前缀 | 启动方式 |
|---|---|---|
| Safari | `web.other.safari` | 新建并精确跟踪本 case 的 window id |
| 谷歌浏览器 | `web.other.chrome` | 独立 profile |
| Edge 浏览器 | `web.other.edge` | 独立 profile |
| 火狐浏览器 | `web.other.firefox` | 独立 profile |
| 360 极速浏览器 | `web.other.360_speed` | 独立 profile |

## 共同约束

- 每条 case 新开受管窗口，结束时只关闭本 case 窗口/profile，不触碰用户原窗口。
- 地址栏 URL 只从 `config.web.sites.dlptest.https_post_url` 读取，通过剪贴板整段粘贴，
  不逐字符输入。
- 每条 case 创建独占临时目录和唯一文件名，执行后删除该目录。
- 拖拽上传只从本 case Finder 窗口拖一次，文件入队后再点击右侧 Submit。
- 点击上传通过 `Command+Shift+G` 粘贴本次完整路径；第一次 Return 定位文件，
  第二次 Return 打开文件。
- Submit 最多允许两次 click，仅用于第一次点击关闭遮挡弹窗或明确未命中按钮时纠正；
  请求结果出现后禁止重复提交。

## 执行

```bash
# 五款浏览器全部 10 条
./scripts/run_case_mac.sh \
  --cases-dir cases/web/other/mac \
  --debug-shots \
  --no-reflect

# 单款两条
./scripts/run_case_mac.sh \
  --cases-dir cases/web/other/mac \
  --filter web.other.firefox.dlptest_https_post \
  --debug-shots \
  --no-reflect

# 单条点击上传
./scripts/run_case_mac.sh \
  --cases-dir cases/web/other/mac \
  --filter web.other.firefox.dlptest_https_post.click_upload \
  --debug-shots \
  --no-reflect
```

脚本会在独立 Terminal.app 窗口运行，并把输出和退出码写入 `.tmp/mac_runs/`。

## 真机结果

2026-08-21 分别执行五款点击上传批次和五款拖拽批次：

- 点击上传：`total=5 failed=0 error=0 inconclusive=5`
- 拖拽上传：`total=5 failed=0 error=0 inconclusive=5`

10 条均完成唯一文件入队、一次 HTTPS POST、完整成功文案和临时资源清理。运行未启用
DLP 客户端日志或服务端验收，因此最终结论按设计为 `inconclusive`；这不等于生产 DLP
策略通过。
