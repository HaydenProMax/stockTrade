from __future__ import annotations

import contextlib
import io
from datetime import date
from typing import Any, Callable

from fund_signal.providers.base import MarketDataProvider
from fund_signal.types import PriceBar


class AkshareProvider(MarketDataProvider):
    name = "akshare"

    def history(self, symbol: str, start: date | None = None, end: date | None = None) -> list[PriceBar]:
        import akshare as ak

        start_text = start.strftime("%Y%m%d") if start else "20000101"
        end_text = end.strftime("%Y%m%d") if end else date.today().strftime("%Y%m%d")
        errors: list[str] = []

        for label, fetch in _history_candidates(ak, symbol, start_text, end_text):
            try:
                data = fetch()
            except Exception as exc:  # noqa: BLE001 - upstream sources fail in different ways
                errors.append(f"{label}: {exc}")
                continue
            bars = _to_price_bars(data, start=start, end=end, source=f"{self.name}:{label}")
            if bars:
                return bars
            errors.append(f"{label}: empty result")

        raise RuntimeError("; ".join(errors))

    def fund_purchase_status(self):
        import akshare as ak

        return ak.fund_purchase_em()

    def fund_nav_history(self, symbol: str, period: str = "成立来") -> list[PriceBar]:
        import akshare as ak

        data = ak.fund_open_fund_info_em(symbol=symbol, indicator="单位净值走势", period=period)
        if data is None or data.empty:
            return []

        bars: list[PriceBar] = []
        for _, row in data.iterrows():
            nav_date = _date_value(_first(row, "净值日期", "date"))
            nav = float(_first(row, "单位净值", "nav"))
            bars.append(
                PriceBar(
                    date=nav_date,
                    open=nav,
                    high=nav,
                    low=nav,
                    close=nav,
                    volume=None,
                    source="akshare:fund_open_fund_info_em",
                )
            )
        return bars


def _history_candidates(ak: Any, symbol: str, start_text: str, end_text: str) -> list[tuple[str, Callable[[], Any]]]:
    prefixed_symbol = _with_market_prefix(symbol)
    candidates: list[tuple[str, Callable[[], Any]]] = []

    if _looks_like_hk_index(symbol):
        candidates.extend(
            [
                ("stock_hk_index_daily_sina", lambda: ak.stock_hk_index_daily_sina(symbol=symbol)),
                ("stock_hk_index_daily_em", lambda: ak.stock_hk_index_daily_em(symbol=symbol)),
            ]
        )
        return candidates

    global_index_symbol = _global_index_name(symbol)
    if global_index_symbol:
        candidates.append(
            ("index_global_hist_sina", lambda: ak.index_global_hist_sina(symbol=global_index_symbol))
        )
        return candidates

    if _looks_like_us_symbol(symbol):
        candidates.append(("stock_us_daily", lambda: ak.stock_us_daily(symbol=symbol, adjust="")))
        return candidates

    if _looks_like_etf(symbol):
        candidates.append(
            (
                "fund_etf_hist_em",
                lambda: ak.fund_etf_hist_em(
                    symbol=symbol,
                    period="daily",
                    start_date=start_text,
                    end_date=end_text,
                    adjust="",
                ),
            )
        )

    candidates.extend(
        [
            (
                "stock_zh_index_daily_em",
                lambda: ak.stock_zh_index_daily_em(
                    symbol=prefixed_symbol,
                    start_date=start_text,
                    end_date=end_text,
                ),
            ),
            (
                "stock_zh_index_daily_tx",
                lambda: _quiet(
                    ak.stock_zh_index_daily_tx,
                    symbol=prefixed_symbol,
                    start_date=start_text,
                    end_date=end_text,
                ),
            ),
            ("stock_zh_index_daily", lambda: ak.stock_zh_index_daily(symbol=prefixed_symbol)),
            (
                "index_zh_a_hist",
                lambda: ak.index_zh_a_hist(
                    symbol=symbol,
                    period="daily",
                    start_date=start_text,
                    end_date=end_text,
                ),
            ),
        ]
    )
    return candidates


def _quiet(fetch: Callable[..., Any], **kwargs: Any) -> Any:
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        return fetch(**kwargs)


def _to_price_bars(data: Any, start: date | None, end: date | None, source: str) -> list[PriceBar]:
    if data is None or data.empty:
        return []

    bars: list[PriceBar] = []
    for _, row in data.iterrows():
        bar_date = _date_value(_first(row, "date", "日期"))
        if start and bar_date < start:
            continue
        if end and bar_date >= end:
            continue
        bars.append(
            PriceBar(
                date=bar_date,
                open=_optional_float(_first_optional(row, "open", "开盘")),
                high=_optional_float(_first_optional(row, "high", "最高")),
                low=_optional_float(_first_optional(row, "low", "最低")),
                close=float(_first(row, "close", "收盘")),
                volume=_optional_float(_first_optional(row, "volume", "成交量", "amount", "成交额")),
                source=source,
            )
        )
    return bars


def _first(row: Any, *columns: str) -> Any:
    value = _first_optional(row, *columns)
    if value is None:
        raise KeyError(f"Missing columns {columns}; got {list(row.index)}")
    return value


def _first_optional(row: Any, *columns: str) -> Any:
    for column in columns:
        if column in row:
            return row[column]
    return None


def _date_value(value: Any) -> date:
    if hasattr(value, "date"):
        return value.date()
    text = str(value)
    if len(text) == 8 and text.isdigit():
        return date.fromisoformat(f"{text[:4]}-{text[4:6]}-{text[6:]}")
    return date.fromisoformat(text)


def _optional_float(value: Any) -> float | None:
    try:
        import pandas as pd

        if value is None or pd.isna(value):
            return None
    except Exception:  # noqa: BLE001 - keep conversion defensive
        if value is None:
            return None
    return float(value)


def _with_market_prefix(symbol: str) -> str:
    if symbol.startswith(("sh", "sz", "bj", "csi")):
        return symbol
    if symbol.startswith(("399", "159")):
        return f"sz{symbol}"
    if symbol.startswith(("000", "510", "515", "560", "588")):
        return f"sh{symbol}"
    return symbol


def _looks_like_etf(symbol: str) -> bool:
    return symbol.startswith(("15", "51", "56", "58"))


def _looks_like_hk_index(symbol: str) -> bool:
    return symbol in {"HSTECH"}


def _looks_like_us_symbol(symbol: str) -> bool:
    return symbol.replace(".", "").isalpha()


def _global_index_name(symbol: str) -> str | None:
    aliases = {
        "NIKKEI225": "日经225指数",
        "^N225": "日经225指数",
    }
    return aliases.get(symbol)
