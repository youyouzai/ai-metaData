"""应用启动时初始化控制台日志 + 内存环形缓冲（供 /web/logs 实时查看）。"""

import logging
import sys

from app.config import MDM_BUSINESS_LOG
from app import log_buffer


class RingBufferLogHandler(logging.Handler):
    """将格式化后的日志写入 log_buffer，供 SSE 推送。"""

    def emit(self, record: logging.LogRecord) -> None:
        try:
            log_buffer.append_formatted(self.format(record))
        except Exception:
            self.handleError(record)


def setup_logging() -> None:
    bus = logging.getLogger("mdm.business")
    bus.setLevel(logging.INFO if MDM_BUSINESS_LOG else logging.WARNING)
    fmt = logging.Formatter("%(asctime)s %(levelname)s [%(name)s] %(message)s")

    if not any(isinstance(h, logging.StreamHandler) for h in bus.handlers):
        h = logging.StreamHandler(sys.stdout)
        h.setLevel(logging.DEBUG)
        h.setFormatter(fmt)
        bus.addHandler(h)

    if not any(isinstance(h, RingBufferLogHandler) for h in bus.handlers):
        rh = RingBufferLogHandler()
        rh.setLevel(logging.DEBUG)
        rh.setFormatter(fmt)
        bus.addHandler(rh)

    bus.propagate = False
