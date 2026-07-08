"""iosfarm — 一个把 iOS 模拟器当"基座"的自动化 + 抓包框架。

分层：
    lifecycle/   模拟器生命周期（create/boot/shutdown/erase/resolve）
    control/     自动化接口（tap/swipe/type/screenshot/open_url…），可换底座
    capture/     抓包（WebKit inspector / mitmproxy），统一落盘格式
    proxy/       系统代理设置与切换（http/https/socks + upstream 轮换）
    session.py   Session 门面：把上面四层组合成一个运行时
    flows/       业务流程（Flow 抽象 + 具体流程，如 google_search）

典型用法见 run.py 与 README。
"""
from .config import Config
from .session import Session
from .lifecycle import SimulatorManager
from .apps import AppManager
from .flows.base import Flow, FlowResult, register, get_flow, list_flows

__all__ = [
    "Config", "Session",
    "SimulatorManager", "AppManager",
    "Flow", "FlowResult", "register", "get_flow", "list_flows",
]
