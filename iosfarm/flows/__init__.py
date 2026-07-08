"""业务流程模块。导入具体流程以完成注册。"""
from .base import Flow, FlowResult, register, get_flow, list_flows
from . import google_search  # noqa: F401  (registers GoogleSearchFlow)

__all__ = ["Flow", "FlowResult", "register", "get_flow", "list_flows"]
