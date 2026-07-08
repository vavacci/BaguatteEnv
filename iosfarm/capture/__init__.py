"""抓包模块。

CaptureBackend 是统一接口；两种实现：
    WebKitCapture     经 ios-webkit-debug-proxy 在浏览器内抓取（不碰 TLS）
    MitmproxyCapture  经系统代理 MITM 抓取（可改写请求，但改变出网 TLS）
两者写入相同的 captures/*.json + _index.jsonl（见 base.RecordWriter）。
"""
from .base import CaptureBackend, RecordWriter, encode_body

__all__ = ["CaptureBackend", "RecordWriter", "encode_body"]


def make_capture(cfg, base_dir):
    """Factory: build the capture backend named by cfg.capture.backend."""
    backend = cfg.capture.backend
    if backend == "webkit":
        from .webkit import WebKitCapture
        return WebKitCapture(cfg, base_dir)
    if backend == "mitmproxy":
        from .mitm import MitmproxyCapture
        return MitmproxyCapture(cfg, base_dir)
    raise ValueError(f"unknown capture backend: {backend!r}")
