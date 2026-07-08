# vphone vs baguette / 模拟器 —— 对比与迁移

## 本质区别

- **baguette** = 控制 **Apple 的 iOS 模拟器**。模拟器跑的是**为 Mac 架构编译、改过的 iOS 框架**,
  以 macOS 进程运行,**共用 Mac 的内核和网络栈**。**不是真 iOS**。
- **vphone**（[Lakr233/vphone-cli](https://github.com/Lakr233/vphone-cli)）= 用 Apple
  **Virtualization.framework v3** 起一台 VM，里面跑**未修改的完整真 iOS 26**（`iPhone17,3`），
  有独立 guest 内核、可越狱、可 SSH/VNC。**是真 iOS**，只是在 VM 里。

## 逐项对比

| 维度 | iOS 模拟器（baguette 控制） | vphone（真 iOS VM） |
|------|------------------------------|----------------------|
| 跑的是什么 | 改过的 iOS 框架 + **Mac 内核** | **未修改完整 iOS**，独立 guest 内核 |
| 技术本质 | 运行时模拟（非虚拟化） | 硬件虚拟化（Virtualization.framework v3） |
| TLS / 网络栈 | **Mac 的** Security 框架 + Mac 网络栈 | **真 iOS 的** TLS 栈，VM 虚拟网卡(NAT) |
| GPU / Canvas / WebGL | 走 **Mac 的 GPU/驱动** | 真 iOS 渲染路径 |
| 越狱 / tweak / SSH | ✗ | ✓（Sileo/TrollStore/apt，`ssh -p 2222 root@127.0.0.1` 密码 alpine） |
| 装真 .ipa | 受限（需模拟器构建） | ✓ 真 ipa/tipa |
| 门槛 | **低**：装 Xcode 即可，秒起，不动 SIP | **高**：关 SIP + AMFI 绕过 + ~128GB 磁盘 + 几十 GB 下载；仅物理 Apple Silicon，不能嵌套 |
| 控制接口 | CLI + HTTP/WS，a11y 树、60fps 流、farm | `vm/vphone.sock` 截屏/触摸/按键/剪贴板 + vphone-mcp |
| 启动稳健性 | 高 | 脆（Recovery/NVRAM/首启合规校验等坑，见 `vphone/README.md`） |

## 对"真实 iOS 指纹"的关键结论

> 模拟器的 Safari 用的是 **Mac 的 Security 框架、跑在 Mac 内核上**，它在
> **TLS(JA3/JA4)、HTTP2、Canvas/WebGL** 等多层都有"我是模拟器/我在 Mac 上"的破绽。
> 即使用方案 B（WebKit inspector）抓包保住的也只是**模拟器 Safari 的 TLS，不等于真 iPhone**。

- **要真机级指纹 → 只有 vphone。** 真 iOS → JA3/JA4/WebKit/渲染全真；越狱后可在**真 iOS 信任库**
  装代理 CA 做标准真机 MITM，或装 tweak hook 网络，或走纯转发代理换 IP 而 TLS 仍是真 iOS。
- **要快速/轻量/先跑通 → baguette + 模拟器。** 适合功能验证、UI 自动化、抓页面结构；
  **别指望它骗过认真的设备指纹风控。**

## 从"模拟器底座"迁移到"vphone 底座"

本框架刻意把**控制层**、**抓包层**、**编排层**解耦，迁移时只换前两层，编排层复用：

| 层 | 模拟器版（现在） | vphone 版（迁移后） | 可复用? |
|----|------------------|----------------------|---------|
| 控制层 | `baguette_client.py`（baguette CLI） | 写一个 `vphone_client.py`：连 `vm/vphone.sock`，实现 tap/swipe/screenshot/press（协议见 vphone-cli Swift 源码），或直接用 vphone-mcp | 换实现，**接口保持一致** |
| 导航 | `xcrun simctl openurl` | VM 内触发（`ssh` 里 `uiopen <url>`，或点 Safari 地址栏） | 换命令 |
| 抓包层 | 方案 B WebKit inspector / 方案 A 系统代理 | **真机方式**：越狱内装 mitmproxy CA 到真 iOS 信任库 + 系统代理；或 tweak hook CFNetwork | 换实现，**产物格式一致** |
| 编排层 | `session.py` / `orchestrator.py` / `targets.json` | **原样复用**（只要控制层暴露相同方法） | ✓ 直接复用 |
| 产物 | `captures/*.json` + `_index.jsonl` | 同格式 | ✓ 直接复用 |

**迁移要点**：让 `vphone_client.py` 暴露和 `baguette_client.py` **相同的方法签名**
（`tap/swipe/scroll/type/press/describe_ui/screenshot`），则 `session.py` / `orchestrator.py`
只需把注入的 client 换掉即可，一行编排逻辑都不用改。

## 建议路径

先用 **baguette + 模拟器**把编排/抓包/落盘全流程调通（快、便宜），验证 `targets.json` 配置与
capture 格式；确认反爬确实卡在设备指纹层后，再上 **vphone** 换底座。两者控制层高度同构，
迁移成本主要在"抓包层改真机方式" + "vphone 那套 SIP/AMFI/镜像的一次性搭建"。
