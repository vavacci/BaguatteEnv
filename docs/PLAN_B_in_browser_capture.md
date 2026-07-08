# 方案 B：浏览器内抓取（不插代理，出网 TLS = 真机 Safari）

## 适用场景

目标在**网络层做指纹**（JA3/JA4、HTTP2 帧、header 顺序 —— Cloudflare / Akamai / PerimeterX
常见），或你就是要**真机 iOS Safari 原样出网**、一点不想伪装。本方案不做 MITM，
Safari 用自己的栈发真实连接，你只在旁边**被动观察**响应，所以网络层指纹天然保真。

两条子路线，优先 B1，不够再上 B2。

---

## B1（推荐起步）：WebKit 远程调试协议抓取

### 原理

用 [`ios-webkit-debug-proxy`](https://github.com/google/ios-webkit-debug-proxy)（**明确支持
iOS 模拟器**）把 Safari 的 Web Inspector 暴露成类 CDP 的 WebSocket 接口，订阅 **Network 域**
事件、用 `Network.getResponseBody` 读响应体。抓取发生在浏览器**内部**，网络连接仍是 Safari
自己发的 → JA3/JA4/HTTP2 全真。

```
Safari(模拟器) ──真实 TLS──▶ 源站          ← 网络层零改动，指纹保真
     │
     └─ webinspectord (lockdown/usbmux, 宿主侧)
              │
        ios-webkit-debug-proxy  ──WS(类CDP)──▶  你的抓取脚本
                                                Network.enable
                                                Network.responseReceived
                                                Network.getResponseBody
```

### 步骤（已落地为脚本）

1. **模拟器 Safari 无需开关**：iOS 模拟器的 Safari 默认就可被检查，Settings 里**没有也不需要**
   Web Inspector 开关（那开关只有真机才有）。只需 Mac Safari ▸ 设置 ▸ 高级 ▸ 显示开发菜单，
   Develop ▸ [Simulator] 能看到页面即证明 inspector 正常。
2. **装并起 iwdp**：`brew install ios-webkit-debug-proxy`，然后跑本框架的
   **`./start_iwdp.sh`** —— 它自动探测每次开机都变化的 `webinspectord_sim` socket 路径并
   用 `-s unix:<path>` 传给 iwdp（见下方 Troubleshooting，这是关键坑）。
3. **发现页面**：`start_iwdp.sh` 会打印 `localhost:9221/json`（设备）和 `localhost:9222/json`
   （页面 + `webSocketDebuggerUrl`）。
4. **抓包**：跑 **`python3 webkit_capture.py --port 9222`** —— 它连页面 WS、发 `Network.enable`，
   监听 `requestWillBeSent` / `responseReceived` / `loadingFinished`，对匹配白名单的响应调
   `Network.getResponseBody` 取正文，落盘成与 mitmproxy addon **完全一致**的
   `captures/*.json` + `_index.jsonl`。
5. **导航与交互仍用现有控制层**：另开一个终端 `python3 orchestrator.py`（`simctl openurl` +
   baguette 手势）。因为 `webkit_capture.py` 写的 `_index.jsonl` 格式一致，orchestrator 的
   网络静默等待逻辑**零改动**即可用。`baguette_client.py` 也不动。

> 典型启动顺序：`./start_iwdp.sh` → 后台 `python3 webkit_capture.py --port 9222 &`
> → `python3 orchestrator.py`。收尾 `./start_iwdp.sh stop`。

### Troubleshooting：iwdp `/json` 返回空（实测踩过的坑）

**症状**：`localhost:9221/json` 或 `9222/json` 返回空；iwdp 的 `-d` 日志里只看到 HTTP 端
收到 `GET /json`（`ss.recv fd=5`），但**没有任何连接 webinspectord 的动作**，即发现了 0 个设备。

**根因**：iwdp 的 `-s` / `--simulator-webinspector` 默认值是 `localhost:27753`（旧 TCP 调试端口），
而**新 Xcode 已废除 TCP、只保留 Unix socket**，路径形如
`/private/tmp/com.apple.launchd.XXXX/com.apple.webinspectord_sim.socket`，且**每次 boot 重新生成**。
所以 iwdp 连了个不存在的端口 → 空列表。（另一独立的老坑：`/etc/hosts` 缺 `::1 localhost`，
因为 sim inspector 走 IPv6；一般系统已自带。）

**修法**（`start_iwdp.sh` 已自动化）：
```bash
# 探测当前 socket（每次开机都要重取）
lsof -aUc launchd_sim 2>/dev/null | grep webinspectord_sim
# 显式喂给 iwdp：
ios_webkit_debug_proxy -F -c null:9221,:9222-9322 \
  -s unix:/private/tmp/com.apple.launchd.XXXX/com.apple.webinspectord_sim.socket
```
`-s` 接受 `HOSTNAME:PORT` 或 `UNIX:PATH`。若 booted 了多台模拟器会有多个 socket，`-s` 一次
只对应一台；`start_iwdp.sh` 默认取第一个，需要指定就 `SIM_SOCK=unix:/…/xxx.socket ./start_iwdp.sh`。

### 隐蔽性（Web Inspector 暴露什么特征）

- **对源站：零特征。** 走 `webinspectord` 的宿主侧通道，不经过、不改动到源站的 TLS，
  无额外 header、无网络指纹变化。
- **对页面 JS：无标准可见标志。** 不像 Chrome 的 `navigator.webdriver`；Safari 远程
  inspector 附加不挂 `window` 标志。桌面 devtools 那套检测（视口差、窗口尺寸、`console`
  getter）依赖视口变化，远程调试不改视口 → 基本失效。
- **必须规避的行为信号**：
  1. **不要发 `Network.setCacheDisabled`**（DevTools 前端默认会发，导致请求永不带
     `If-None-Match`/`If-Modified-Since`，是异常信号）。自写客户端不发即可。
  2. **不要用 `debugger` 断点暂停**（有站点用 `debugger` 计时探测调试器）。
  3. 不开 `Emulation` / UA override 等改行为的域，只用 Network 被动读取。
- **残余弱信号**：附加 inspector 有微小执行开销，极少数站点做 JS 计时旁证，噪声大、
  单独不足以判定。

### 优缺点

| | |
|---|---|
| ✅ | 网络层指纹 100% 真机；不碰 TLS |
| ✅ | 对目标基本隐形；无需签名扩展、无需注入 |
| ✅ | 复用现有控制/编排层，改动小 |
| ❌ | Network 域抓取对**某些资源类型的 body / Web Worker 内请求**有时不稳或拿不全 |
| ❌ | 只能被动读，**不能改写请求**（要改写用方案 A） |
| ❌ | 协议偏 WebKit 私有，跨 Xcode/iOS 版本偶有差异 |

---

## B2（进阶）：向模拟器 WebKit 网络进程注入 dylib

### 原理

iOS **模拟器进程本质是 macOS 进程**，可用 `DYLD_INSERT_LIBRARIES` 注入 dylib 到
`com.apple.WebKit.Networking`（或 SafariViewService），hook `NSURLSession` /
CFNetwork（`URLSession:dataTask:didReceiveData:`、`CFURLRequest` 等）在**应用层**抓
完整 req/resp。TLS 仍由 Safari 完成 → 指纹保真，且抓取比 inspector 更全。与 workspace 里
`troll` / `palera1n` 的注入思路一脉相承。

```
DYLD_INSERT_LIBRARIES=hook.dylib  注入 → WebKit.Networking 进程
     hook NSURLSession/CFNetwork  →  完整 req/resp（含 worker、二进制）
Safari 真实 TLS ─▶ 源站            ←  网络层不动
```

### 步骤（要点）

1. 用 fishhook / `method_swizzling` 写 `hook.dylib`，拦 CFNetwork/NSURLSession 回调，
   把 URL、headers、body 落盘（结构对齐本框架 `captures/*.json`）。
2. 以注入方式启动目标进程：`simctl spawn <udid> launchctl setenv DYLD_INSERT_LIBRARIES …`
   或用 `SIMCTL_CHILD_DYLD_INSERT_LIBRARIES` 环境前缀启动 Safari 相关进程。
3. 导航/交互仍用 `simctl openurl` + baguette。

### 隐蔽性

- 对源站零特征（网络层不动）；对页面 JS 不可见（JS 看不到 native hook）。
- 唯一暴露面是“进程内是否有异常 dylib”，但这里没有对手 App 在做反注入自检
  （目标是网页，不是加固 App），实际最隐蔽。

### 优缺点

| | |
|---|---|
| ✅ | 抓取最全（worker、二进制、所有 CFNetwork 流量）；网络层保真；最隐蔽 |
| ❌ | 工程量最大（写/维护 hook，跟随 iOS 运行时符号变化） |
| ❌ | 强依赖模拟器私有细节，脆于系统升级 |

---

## 选型小结

- **先做 B1**（ios-webkit-debug-proxy）：改动最小、隐蔽、指纹保真，多数场景够用。
- **B1 抓不全 worker/特定资源时上 B2**（dylib 注入）：最全最稳，但要写 hook。
- 需要**改写请求**或目标只查 JS 层 → 回**方案 A**。

## 验证（B1/B2 通用）

1. 访问 `tls.peet.ws/api/all` / `tls.browserleaks.com/json`，确认 JA3/JA4/HTTP2 指纹
   与“同机型真机 Safari 直连”基线**完全一致**（证明没被污染）。
2. 对一个已知会发 XHR/fetch 的页面，确认 `captures/` 能拿到对应响应体。
3. B1 额外确认：请求带正常缓存头（说明没误发 `setCacheDisabled`）。
