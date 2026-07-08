# iosfarm — iOS 模拟器自动化 + 抓包框架

把 **iOS 模拟器当基座**的分层框架：用真实移动版 Safari 自动访问页面、做手势交互，并在
网络层抓取原始 HTTP 请求/响应。**框架领域无关**——具体业务(如 Google 搜索)以可插拔的
**Flow** 形式接入，只调用 Session 暴露的能力，不碰底层管道。

> 环境：**macOS + Apple Silicon + Xcode**。`brew install baguette ios-webkit-debug-proxy mitmproxy`，
> `pip install -r requirements.txt`。真机级指纹的局限见 `docs/COMPARISON_vphone_vs_baguette.md`。

## 分层架构

```
                    ┌─────────────── Flow（业务流程）───────────────┐
                    │  google_search / 你的下一个业务…              │
                    └───────────────────┬──────────────────────────┘
                                        │ 只用 Session 的方法
                    ┌───────────────────▼──────────────────────────┐
                    │                 Session（门面）               │
                    │  组合四大模块，context manager 自动起停       │
                    └──┬──────────┬───────────┬───────────┬─────────┘
          ┌────────────▼──┐ ┌─────▼──────┐ ┌──▼─────────┐ ┌▼───────────────┐
          │  lifecycle    │ │  control   │ │  capture   │ │  proxy         │
          │ 模拟器生命周期 │ │ 自动化接口 │ │  抓包      │ │ 代理设置/切换   │
          │ boot/shutdown │ │ tap/type/  │ │ webkit /   │ │ set/clear/     │
          │ erase/resolve │ │ swipe/shot │ │ mitmproxy  │ │ rotate(upstream)│
          └───────────────┘ └────────────┘ └────────────┘ └────────────────┘
```

四个模块各自独立、接口清晰，可单独用，也可整体替换(如把 control 换成 vphone)。

## 目录

```
iosfarm/
  config.py            配置(dataclass) — 单一事实来源
  lifecycle/           模拟器生命周期：SimulatorManager
  control/             自动化接口：ControlClient(抽象) + BaguetteControl(实现)
  capture/             抓包：CaptureBackend(抽象) + WebKitCapture / MitmproxyCapture + addon
  proxy/               代理：ProxyManager(set/clear/rotate + CA trust)
  session.py           Session 门面：组合四模块
  flows/               业务流程：Flow(抽象) + 注册表 + google_search(示例)
config.json            默认配置(模拟器/抓包/代理/各 flow 参数)
run.py                 CLI：跑一个 flow
captures/              产物：flow JSON + _index.jsonl + 截图 + 结果
docs/                  方案与对比文档
```

## 快速上手

```bash
# 依赖
brew install baguette ios-webkit-debug-proxy mitmproxy
pip install -r requirements.txt

# 前置：boot 一台模拟器，Safari 打开一个真实页面(webkit 后端需要可检查的页面)
# 编辑 config.json：capture.hosts 填目标域，flows 填参数

# 跑内置业务流程
python3 run.py --list
python3 run.py --flow google_search
python3 run.py --flow google_search --params '{"query":"anthropic","scrolls":3}'

# 产物
ls captures/                       # *.json（req/resp）、shot_*.png、result_google_search.json
```

## 编程接口（Session）

```python
from iosfarm import Config, Session

cfg = Config.from_file("config.json")
with Session(cfg) as s:            # 自动 boot + 起抓包(+可选代理)，退出自动收尾
    marker = s.mark()             # 标记抓包起点
    s.open("https://www.google.com/search?q=claude")
    s.wait_idle()                 # 阻塞到网络静默
    s.scroll("up", 500); s.wait_idle()
    s.screenshot("results")
    for flow in s.flows_since(marker):   # 结构化 req/resp(headers+body)
        print(flow["status_code"], flow["url"])
```

Session 暴露的方法：
- **导航/控制**：`open / tap / double_tap / swipe / scroll / type_text / key / press / describe_ui / screenshot`
- **抓包**：`mark / wait_idle / flows_since / index_since`
- **代理**：`rotate_proxy`

## 写一个新业务流程

```python
# iosfarm/flows/my_flow.py
from .base import Flow, FlowResult, register

@register
class MyFlow(Flow):
    name = "my_flow"
    def run(self, session, params):
        marker = session.mark()
        session.open(params["url"])
        session.wait_idle()
        flows = session.flows_since(marker)
        return FlowResult(name=self.name, params=params,
                          captured=len(flows), data={"urls":[f["url"] for f in flows]})
```
在 `flows/__init__.py` 里 `from . import my_flow` 完成注册，即可 `python3 run.py --flow my_flow`。
Flow 里**没有任何** boot/代理/抓包/文件格式的代码——全交给框架。

## 抓包后端（config.capture.backend）

| 后端 | 机制 | 出网 TLS | 能改写请求 | 何时用 |
|------|------|---------|-----------|--------|
| `webkit`(默认) | ios-webkit-debug-proxy 浏览器内抓取 | 模拟器 Safari 自己的(不碰) | ✗ | 大多数场景；不想污染指纹 |
| `mitmproxy` | 系统代理 MITM | 代理重发的(会变) | ✓ | 需要改写请求，或只查 JS 层指纹 |

两者写入**完全相同**的 `captures/*.json` + `_index.jsonl`，Flow/Session 代码无感。
webkit 后端排障(iwdp 空 `/json` 等)见 `docs/PLAN_B_in_browser_capture.md`。

## 代理 / 多 IP

模拟器用 Mac 的网络栈，**所有模拟器 + Mac 共享一个出口 IP**，系统代理是全机唯一值。
`ProxyManager.rotate()` 在 `config.proxy.upstreams` 间轮换(串行换 IP，非并发)。
纯转发 SOCKS 上游 + webkit 后端 = 换 IP 而不动 TLS。详见
`docs/COMPARISON_vphone_vs_baguette.md` 与 `docs/PLAN_A_proxy_tls_impersonation.md`。

## 迁移到 vphone(真机指纹)

模拟器 TLS/指纹**不等于真 iPhone**。要真机级只有 vphone。迁移只需把 control 换成同签名的
`VphoneControl`、capture 换成真机方式，`session.py`/`flows`/`config` 全复用。见
`docs/COMPARISON_vphone_vs_baguette.md` 的迁移一节。
