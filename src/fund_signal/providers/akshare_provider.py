from __future__ import annotations

from datetime import date

from fund_signal.providers.base import MarketDataProvider
from fund_signal.types import PriceBar


class AkshareProvider(MarketDataProvider):
    name = "akshare"

    def history(self, symbol: str, start: date | None = None, end: date | None = None) -> list[PriceBar]:
        import akshare as ak

        # A-share index history. ETF/proxy support can be added behind this provider boundary.
        start_text = start.strftime("%Y%m%d") if start else "20000101"
        end_text = end.strftime("%Y%m%d") if end else date.today().strftime("%Y%m%d")
        data = ak.index_zh_a_hist(symbol=symbol, period="daily", start_date=start_text, end_date=end_text)
        if data.empty:
            return []

        bars: list[PriceBar] = []
        for _, row in data.iterrows():
            bars.append(
                PriceBar(
                    date=row["日期"].date() if hasattr(row["日期"], "date") else date.fromisoformat(str(row["日期"])),
                    open=float(row["开盘"]),
                    high=float(row["最高"]),
                    low=float(row["最低"]),
                    close=float(row["收盘"]),
                    volume=float(row["成交量"]) if "成交量" in row else None,
                    source=self.name,
                )
            )
        return bars

    def fund_purchase_status(self):
        import akshare as ak

        return ak.fund_purchase_em()
