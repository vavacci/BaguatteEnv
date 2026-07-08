"""Framework exceptions."""


class IosFarmError(RuntimeError):
    """Base class for all framework errors."""


class ControlError(IosFarmError):
    """A device-control command (baguette/simctl) failed."""


class CaptureError(IosFarmError):
    """The capture layer failed to start or attach."""


class LifecycleError(IosFarmError):
    """Simulator lifecycle operation (boot/create/erase) failed."""


class ProxyError(IosFarmError):
    """System-proxy configuration failed."""
