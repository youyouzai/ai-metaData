"""业务数据查询：步骤说明 + SQL/参数日志（logger: mdm.business）"""

from __future__ import annotations

import logging
import textwrap
from typing import Any, Iterable, Optional, Sequence, Tuple, Union

from app.config import MDM_BUSINESS_LOG

_LOG = logging.getLogger("mdm.business")


def step(msg: str, **ctx: Any) -> None:
    if not MDM_BUSINESS_LOG:
        return
    if ctx:
        tail = " ".join(f"{k}={v!r}" for k, v in ctx.items())
        _LOG.info("%s | %s", msg, tail)
    else:
        _LOG.info("%s", msg)


_Params = Union[Sequence[Any], Tuple[Any, ...], None]


def sql_exec(cur, sql: str, params: _Params = None, *, step: str) -> None:
    """执行 SQL；开启 MDM_BUSINESS_LOG 时打印 SQL 与参数。"""
    if MDM_BUSINESS_LOG:
        body = textwrap.dedent(sql).strip()
        _LOG.info("[%s] SQL:\n%s", step, body)
        if params is None:
            _LOG.info("[%s] PARAMS: ()", step)
        elif isinstance(params, dict):
            _LOG.info("[%s] PARAMS: %r", step, params)
        else:
            _LOG.info("[%s] PARAMS: %r", step, tuple(params))  # type: ignore[arg-type]
    if params is None:
        cur.execute(sql)
    else:
        cur.execute(sql, params)


def result_summary(label: str, *, rows: int, sample_keys: Optional[Iterable[str]] = None) -> None:
    if not MDM_BUSINESS_LOG:
        return
    if sample_keys is not None:
        keys = list(sample_keys)
        _LOG.info("%s | rows=%s keys=%s", label, rows, keys)
    else:
        _LOG.info("%s | rows=%s", label, rows)
