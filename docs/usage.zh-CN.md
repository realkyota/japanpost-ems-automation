# 日本邮政 EMS：Mac 本地 Python 程序

当前版本：`20261112-always-write-diagnostic-1`。

自动化终点：到达 `M061000.do`「送り状の印刷をする」页面，点击「注意事項に同意して送り状を印刷」，然后停止所有自动操作。浏览器保持打开，后续打印由你处理；完成后在终端按回车才关闭程序浏览器。不再自动捕获 PDF、打开预览、发送系统打印任务或继续点完成按钮。

## 运行和更新

需要 Python 3.10+、Playwright 支持的 macOS 和联网下载依赖。

首次运行：终端输入 `bash` 加空格，将 setup_login.command 拖进去并回车，按提示把登录资料保存到 Mac 钥匙串。之后同样运行 run.command，选择真实 shipment.json。也可双击 .command 文件；若 macOS 不允许直接执行，使用终端方法。

更新时可把新版文件复制到原程序文件夹并替换同名文件，保留原 output 文件夹及已有依赖。钥匙串账号和 shipment.json 无需重新设置。启动时检查终端版本，避免运行旧代码。

## 流程

1. 自动尝试登录，等待主菜单。
2. 若有「前回のデータから作成」弹窗，选择「新しく作成する」。若清除草稿后返回主菜单，再点击「送り状作成」；没有弹窗则直接点击创建。
3. 保留当前已选寄件人，点击底部流程「次へ」。不使用列表中间的翻页按钮。
4. 点击「お届け先の入力」，填写 JSON 中的收件人。
5. 选择 EMS（物品），等待输入区展开；填写 Doll、价格、重量、数量，选择 JAPAN（日本）和 HS 代码，点击「確定」。
6. 设置赠送/无偿信息、勾选已确认无危险品及同意怀疑有危险品时开封检查的声明，进入発送页。
7. 填写提供的発送信息，进入确认页并尝试登记（--stop-before-register 可停在确认页）。
8. 查找本次浏览器的官方印刷页面/窗口，点击截图中的准确按钮「注意事項に同意して送り状を印刷」，停止。

验证码及官网错误需要你处理。程序暂停时，请先在官网完成提示的当前步骤，再回终端按回车。它没有访问你的原有 Chrome 窗口，只控制自己新开的浏览器。

## 包裹固定规则与 JSON

用户确认的常用包裹：Doll ×1、单价 2,000 JPY、每件物品重量 2,000g、赠送/无偿、原产国日本、HS代码 9503002190。数量、价格、重量和类别由 JSON 提供；旧 JSON 没有 origin/hsCode 时自动补 JP 和 9503002190，明确指定的值仍优先使用。这是本次用户提供的规则，不是通用商品分类建议。

程序一次处理一位收件人、一条内容品。安装包 shipment.example.json 是虚构示例，会被拒绝出单；请使用另行生成的真实 shipment.json。自己编辑示例时须改成真实资料并删除 `_example` 字段。所有金额、数量、电话、邮编、重量均使用字符串。

| 对象/字段 | 含义 |
| --- | --- |
| recipient | name、country、address1、address2、city、state、postalCode、phone、fax、email |
| country | 两位大写国家/地区代码；香港 HK、澳门 MO、台湾 TW |
| shipment.item | name、unitPrice、quantity、weightGrams、origin、hsCode |
| unitPrice | 每件单价，本版 JPY |
| weightGrams | 每件物品重量，不含包装 |
| category | 官网日语类别，例如真实赠送用 贈物 |
| paid | true 为销售/有償，false 为无偿 |
| invoice | prescribed，规定份数 |
| noDangerousGoods | true 表示已确认不含危险品并同意对应检查声明 |
| totalWeightGrams | 可选，包含包装的总重量；未提供时保留官网值 |
| shipDate | 自动使用程序启动当天日本日期的次日；运行时覆盖 JSON 中旧日期 |
| insuredValueYen | 可选，损害要偿额，日元 |

## 常用命令

在程序文件夹运行：

```bash
bash run.command shipment.json
bash run.command shipment.json --validate-only
bash run.command shipment.json --stop-before-register
bash run.command shipment.json --manual-login
bash run.command shipment.json --login
bash run.command --forget-login
```

--login 是本次临时输入、不保存；默认读取本程序的 Mac 钥匙串记录。修改已保存凭据可重跑 setup_login.command。兼容旧 --print 参数，但本版只点击官网印刷按钮，不再发送系统打印任务。

## 卡住时

等待采用每 200ms 直接检查，不依赖动画帧；字段支持有/无 placeholder 和跨行表格。创建流程会检查官方新窗口；鼠标点击返回但同页无 POST/无跳转时，对同一主菜单链接最多尝试一次 Enter，不对最终登记/印刷重复激活。

若主菜单仍卡住，会生成 output/diagnostic-main-menu.json。上传此文件可看到具体按钮结构、动作类型、可见状态、窗口路径和异常，不必仅凭截图判断。报告不读取密码、文本输入值、Cookie、请求头或请求正文，网址查询参数/片段会移除。

## 登记与打印

output/run-state.json 保存资料哈希和登记尝试时间，防止中断后重复出单，不保存地址明文。更新程序时保留 output。若已有登记尝试，应先在官网「発送予定データ」核查；仅在确认要再次创建时用 --allow-repeat。没有打印不代表登记失败。

登记后若返回主菜单，程序不会重新创建，会提示你从「発送予定データ」核查并进入印刷页。达到本次截图的印刷页后，只点击官方印刷按钮一次并停止。浏览器和打印窗口留给你，不自动关闭或继续后续步骤。

## 验证状态

程序根据用户截图和一次公开登录页只读检查适配。本地单元、DOM 模拟、跨行布局、空文档导航、新窗口、单次键盘回退和停止终点测试已通过；未在你的 Mac/真实账号上完成端到端验证。点击官网印刷不代表实际纸张已打印。

```bash
python3 -m unittest discover -v
# 以下测试需 Node.js，仅测试用，正常运行不需要
node test_login.cjs
node test_content.cjs
```

手动安装：

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m playwright install chromium
.venv/bin/python japanpost.py shipment.json
```


## 発送予定日自动选择运行次日

本版启动时记录日本时间（UTC+9）的日期，発送予定日固定为该日期加一天。例如日本日期 2026/11/12 启动，选择 2026/11/13。跨月、跨年和闰日通过标准日期运算处理，JSON 中的旧日期会在运行时覆盖；原文件不改写。日期下拉框支持带星期、日文年月日和紧凑数字 option value。目标日期不存在或匹配不唯一时停止，不默默改选其他日期。

防重复记录使用输入配置的哈希，日期自动变化不绕过已有登记尝试。run-state.json 只记录是否尝试登记，不记录按钮异常，也不证明官网已登记成功。若报防重复，请先到「発送予定データ」核查；明确要另一张新单才使用 --allow-repeat，不要删除记录来解决打印或按钮问题。

真正的主菜单按钮定位故障需要 output/diagnostic-main-menu.json，或带具体异常的终端日志。单独上传 run-state.json 无法判断按钮的 DOM/动作问题。


## 诊断文件不存在时：启动即创建

旧版只在主菜单失败分支保存，且网页 DOM 读取异常可能导致写文件步骤被跳过。本版在正式运行入口、选择 JSON 和防重复检查之前创建 output/diagnostic-main-menu.json，终端显示完整绝对路径。即使配置文件错误、防重复拦截或网页 DOM 无法读取，基础报告及失败阶段仍会保留。

程序同时记录阶段事件，并在点击创建之前尽量记录按钮元数据。主菜单失败时先写基础异常，再读取 DOM；DOM 读取失败会记录类型，不再因此丢失整个文件。Mac 上主菜单失败或提前退出时会用 Finder 定位报告。若磁盘/目录权限确实不允许写入，启动会明确报出完整路径和失败类型。

使用本版运行到问题出现后，上传终端所示路径下的 JSON 文件。报告不会保存密码、输入框文本值、Cookie、请求头/正文。仅有 run-state.json 仍不足以定位按钮问题。此更新修复诊断可用性，并不宣称已确定主菜单点击问题的根因。
