# 方案 A：代理抓包 + TLS 指纹伪造（mitmproxy / utls）

## 适用场景

目标**只在 JS / 应用层做指纹**（navigator、canvas、UA、自定义上报如 a4 之类），
或者你**接受在网络层伪装成一个固定的 iOS Safari 档案**而不是让真机原样出网。
如果目标严格校验 JA3/JA4 + HTTP2 帧且档案更新很快，本方案维护成本高，优先看方案 B。

## 核心约束（必须先理解）

> **最终发往源站那一跳的 TLS 栈，决定了源站看到的 JA3/JA4。**

MITM 代理会**终止** Safari 的 TLS 再**重新发起**到源站，这重新发起的 ClientHello
是代理 TLS 库产生的。所以：

- stock mitmproxy 的出网用 Python/OpenSSL → JA3 是 mitmproxy 的，明显穿帮
  （已知问题 mitmproxy#4575，Cloudflare 可识别）。
- 要伪造，就必须让**做最后一跳的组件**用 utls / BoringSSL 这类能重排 ClientHello
  （扩展顺序、GREASE、supported_groups、ALPN）的库，并锁定一个 iOS Safari 档案。
- 走了 MITM 后，页面 JS 在隧道**内**发出的指纹（canvas/UA/a4 上报）**原样透传、保真**；
  丢的只是网络层指纹。所以本方案的价值 = 保住 JS 层真实性 + 把网络层伪装成某个 iOS 档案。

## 架构

两种拓扑，按“抓包能力 vs 简单度”取舍。

### A1（推荐起步）：单个 utls-MITM 代理，兼做抓包 + 出网伪造

```
Safari(模拟器) ──TLS──▶ ja3proxy / utls-MITM ──utls(iOS Safari 档案)──▶ 源站
                         │(自签 CA，装进模拟器信任)
                         └─ 落盘 req/resp（明文）
```

- 组件：[`ja3proxy`](https://github.com/LyleMi/ja3proxy)（可设 JA3/客户端档案）或自建
  Go 代理用 [utls](https://github.com/refraction-networking/utls) 的 `HelloIOS_*` ClientHelloID。
- 一个进程搞定 MITM 解密、抓包、出网伪造。抓包/脚本能力比 mitmproxy 弱。

### A2：mitmproxy 抓包 + utls-MITM 出网（双 MITM 链）

```
Safari(模拟器) ─▶ mitmproxy(MITM, 抓包+脚本) ─▶ utls-MITM(第二层 MITM, 出网伪造) ─▶ 源站
                  │CA①装进模拟器                 │CA②被 mitmproxy 信任(upstream)
                  └─ capture_addon.py 落盘        └─ 用 utls iOS 档案发 ClientHello
```

- 保留 mitmproxy 的强抓包/脚本（复用现有 `capture_addon.py`），出网真实性交给第二层。
- 关键接线：mitmproxy `--mode upstream:https://127.0.0.1:<port>`，且让 mitmproxy
  信任第二层代理的 CA（`--set ssl_verify_upstream_trusted_ca=<ca②>`）。第二层必须也是
  MITM（有自己的 CA）才能拿到明文再用 utls 重发。复杂度较高。

## 实施步骤（以 A1 为主线）

1. **装工具**：`go install` ja3proxy，或自建 utls 代理；确认其支持设定 iOS Safari 档案。
2. **信任 CA**：`xcrun simctl keychain booted add-root-cert <代理CA.pem>`
   （模拟器 erase/新建后需重做）。
3. **设系统代理**指向该代理：`networksetup -setwebproxy / -setsecurewebproxy Wi-Fi 127.0.0.1 <port>`。
4. **选定 iOS Safari 档案**：
   - utls 内置 `HelloIOS_11_1 / HelloIOS_12_1 / HelloIOS_13 / HelloIOS_14 / HelloSafari_16_0` 等，
     **注意这些可能落后于当前 Safari**；必要时先在真机/模拟器抓一份当前 Safari 的
     ClientHello，手工构造 `ClientHelloSpec` 覆盖默认档案。
   - HTTP/2 帧指纹（SETTINGS、WINDOW_UPDATE、header 顺序、伪首部顺序）也要对上，
     否则 Akamai/Cloudflare 的 HTTP2 指纹一样穿帮。
5. **抓包落盘**：A1 用 ja3proxy 的日志/自建代理里加落盘；A2 直接复用 `capture_addon.py`。
6. **验证指纹**（关键）：让模拟器 Safari 访问指纹自检站点，比对是否等于真机：
   - JA3/JA4：`tls.peet.ws/api/all`、`tls.browserleaks.com/json`
   - HTTP2：同上返回的 `http2` / akamai 指纹
   - 对照“同机型真机 Safari 直连”的基线，两者 hash 一致才算成功。

## 优点 / 缺点

| | |
|---|---|
| ✅ | 复用现有 mitmproxy 框架（A2）；抓包在明文层，最完整（含图片/顶层导航/worker 全都抓得到） |
| ✅ | JS/应用层指纹保真（隧道内透传） |
| ❌ | **网络层是“伪造的档案”而非真机原样**；档案更新滞后就穿帮 |
| ❌ | iOS Safari 的 utls 档案稀缺，多数工具只做 Chrome/Firefox，往往要自己抓包构造 |
| ❌ | HTTP/2 帧指纹要额外对齐；维护成本随目标升级持续存在 |
| ❌ | A2 双 MITM 接线复杂，易错 |

## 何时选它

- 目标的风控**只查 JS 层**（那网络层伪不伪造都无所谓，A 方案抓包最省事、最全）。
- 或你需要**明文改写请求**（改参数、注入）——这是代理相对浏览器内抓取的独有能力。
- 若目标严查且频繁更新网络层指纹 → 转**方案 B**（让真机原样出网，根本不碰这层）。

## 工作量评估

- A1：中。找/配一个支持 iOS 档案的 utls 代理是主要成本。
- A2：中高。双 MITM 链路 + CA 信任链调试。
- 持续成本：高（跟着 Safari 版本维护档案）。
