"""自动化接口模块（控制层）。

ControlClient 是抽象接口；BaguetteControl 是基于 baguette CLI 的实现。
迁移到 vphone 时，写一个同签名的 VphoneControl 即可，上层无需改动。
"""
from .base import ControlClient
from .baguette import BaguetteControl

__all__ = ["ControlClient", "BaguetteControl"]
