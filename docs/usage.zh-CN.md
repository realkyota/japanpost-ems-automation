# 日本邮政 EMS 自动化：公开版使用说明

本项目通过 Python 和 Playwright，在 macOS 本地读取 JSON，填写日本邮政国际邮便网站的收件人与包裹信息。

## 运行

需要 Python 3.10+ 和支持 Playwright 的 macOS。在程序目录打开终端：

```bash
bash setup_login.command
bash run.command /path/to/Recipient_Name.json
```

首次运行下载依赖和 Chromium。登录资料可选保存在本机钥匙串；也可使用 `--manual-login` 自行登录。

## 输入资料

`shipment.example.json` 只包含通用占位信息，会被程序阻止出单。姓名、地址、金额、重量及 HS 代码均为虚构示例，000000 不是实际申报代码。请复制到独立文件，填写真实资料后删除 `_example`。

公开版不内置个人包裹固定值。物品名称、单价、数量、重量、原产国、HS 代码、类别与有偿/无偿状态均应按实际情况填写。原产国必须明确提供；需要 HS 代码时请提供适用的代码。确认物品及危险品声明后才能设置 `noDangerousGoods: true`。电话号码、邮编、金额、数量、重量使用字符串。

| 字段 | 含义 |
| --- | --- |
| recipient | 姓名、两位国家/地区代码、分行地址、城市、州、邮编、电话和邮箱 |
| shipment.item | 英文物品名、单价、数量、物品重量、原产国和 HS 代码 |
| category / paid | 实际内容品类别与是否有偿 |
| invoice | prescribed，打印规定份数 |
| totalWeightGrams | 可选，含包装总重量 |
| shipDate | 运行时自动使用日本日期的次日，原文件不改写 |

截图或文本转 JSON 是独立步骤，程序本身没有 OCR 功能。

## 流程与停止位置

程序登录后处理前回数据弹窗，保留已选寄件人，直接输入收件人，选择 EMS（物品），填写内容品并点击「確定」，设置发送信息，确认登记。到达官方印刷页后点击「注意事項に同意して送り状を印刷」，停止自动操作并保留浏览器。完成后回终端按 Enter 关闭。

```bash
bash run.command /path/to/Recipient_Name.json --validate-only
bash run.command /path/to/Recipient_Name.json --stop-before-register
bash run.command /path/to/Recipient_Name.json --manual-login
bash run.command --forget-login
```

`--stop-before-register` 在确认页停止，不登记。验证提示及官网错误由使用者处理。

## 记录与故障诊断

保留 `output/run-state.json`，避免中断后重复登记。它只记录资料指纹和登记尝试时间，不能证明登记成功。中断后应先查官网「発送予定データ」，确认需要另一张单时才用 `--allow-repeat`。

启动时会创建 `output/diagnostic-main-menu.json`，终端显示路径。报告不读取密码、文本输入值、Cookie 或请求正文；分享前仍应自行检查。真实资料、运行输出、截图和打印文件均不应提交 GitHub。

## 测试

```bash
python3 -m unittest discover -v
node test_login.cjs
node test_content.cjs
node test_dispatch.cjs
```

测试使用模拟对象和 DOM 样例，不登录真实账号。网站变化可能需要更新定位逻辑。项目由 AI 辅助开发，项目所有者定义流程、测试并反馈问题。
