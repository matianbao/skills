#!/usr/bin/env python3
"""个股技术分析数据采集脚本。

Usage:
    python3 analyze_stock.py TICKER
    python3 analyze_stock.py AAPL
"""

import urllib.request
import json
import sys
from datetime import datetime, timedelta


def fetch(url, timeout=15):
    try:
        req = urllib.request.Request(url, headers={
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
        })
        resp = urllib.request.urlopen(req, timeout=timeout)
        return resp.read()
    except Exception as e:
        print(f"  请求失败: {e}")
        return None


def main():
    if len(sys.argv) < 2:
        print("Usage: python3 analyze_stock.py TICKER", file=sys.stderr)
        sys.exit(1)

    TICKER = sys.argv[1].upper()

    print("=" * 60)
    print(f"美股数据采集 — {TICKER}")
    print("=" * 60)

    # ============================================================
    # 1. 获取历史K线数据 (Yahoo Finance)
    # 获取6个月数据用于计算技术指标
    # ============================================================
    print(f"\n【1】{TICKER} 历史行情数据")
    end_ts = int(datetime.now().timestamp())
    start_ts = int((datetime.now() - timedelta(days=180)).timestamp())
    url = f'https://query1.finance.yahoo.com/v8/finance/chart/{TICKER}?period1={start_ts}&period2={end_ts}&interval=1d'
    raw = fetch(url)

    closes = []
    volumes = []
    highs = []
    lows = []
    opens = []
    timestamps = []

    if raw:
        data = json.loads(raw.decode('utf-8'))
        result = data.get('chart', {}).get('result', [{}])[0]
        meta = result.get('meta', {})
        indicators = result.get('indicators', {})
        quote = indicators.get('quote', [{}])[0]
        ts_list = result.get('timestamp', [])

        closes = [x for x in quote.get('close', []) if x is not None]
        volumes = [x for x in quote.get('volume', []) if x is not None]
        highs = [x for x in quote.get('high', []) if x is not None]
        lows = [x for x in quote.get('low', []) if x is not None]
        opens = [x for x in quote.get('open', []) if x is not None]
        timestamps = ts_list

        currency = meta.get('currency', 'USD')
        price = meta.get('regularMarketPrice', 0)
        prev_close = meta.get('chartPreviousClose', meta.get('previousClose', 0))
        change = price - prev_close if prev_close else 0
        change_pct = (change / prev_close * 100) if prev_close else 0

        print(f"  最新价: {price:.2f} {currency}")
        print(f"  涨跌: {'+' if change>=0 else ''}{change:.2f} ({'+' if change_pct>=0 else ''}{change_pct:.2f}%)")
        if closes:
            print(f"  6个月最高: {max(highs):.2f} | 6个月最低: {min(lows):.2f}")
            print(f"  最新成交量: {volumes[-1]:,.0f}" if volumes else "")
            # 成交量对比20日均量
            if len(volumes) >= 20:
                avg_vol_20 = sum(volumes[-20:]) / 20
                vol_ratio = volumes[-1] / avg_vol_20 if avg_vol_20 > 0 else 0
                print(f"  20日均量: {avg_vol_20:,.0f} | 量比: {vol_ratio:.2f}")
    else:
        print("  Yahoo Finance 数据获取失败")

    # ============================================================
    # 2. 计算技术指标
    # ============================================================
    print(f"\n【2】技术指标")

    if len(closes) >= 5:
        # 均线系统
        def sma(data, period):
            if len(data) < period:
                return None
            return sum(data[-period:]) / period

        ma5 = sma(closes, 5)
        ma10 = sma(closes, 10)
        ma20 = sma(closes, 20)
        ma50 = sma(closes, 50)
        ma120 = sma(closes, 120)
        ma200 = sma(closes, 200)

        print("  均线系统:")
        current = closes[-1]
        for name, val in [("MA5", ma5), ("MA10", ma10), ("MA20", ma20),
                           ("MA50", ma50), ("MA120", ma120), ("MA200", ma200)]:
            if val:
                pos = "上方" if current > val else "下方"
                diff_pct = (current - val) / val * 100
                print(f"    {name}: {val:.2f} (股价在其{pos}, 偏离 {'+' if diff_pct>=0 else ''}{diff_pct:.1f}%)")

        # 均线排列
        mas = [x for x in [ma5, ma10, ma20, ma50] if x is not None]
        if len(mas) >= 3:
            if all(mas[i] >= mas[i+1] for i in range(len(mas)-1)):
                print("    均线排列: 多头排列 (短期均线在上)")
            elif all(mas[i] <= mas[i+1] for i in range(len(mas)-1)):
                print("    均线排列: 空头排列 (长期均线在上)")
            else:
                print("    均线排列: 交叉/震荡排列")

        # RSI (14日)
        if len(closes) >= 15:
            gains = []
            losses = []
            for i in range(1, len(closes)):
                diff = closes[i] - closes[i-1]
                gains.append(max(diff, 0))
                losses.append(max(-diff, 0))

            period = 14
            avg_gain = sum(gains[-period:]) / period
            avg_loss = sum(losses[-period:]) / period
            if avg_loss > 0:
                rs = avg_gain / avg_loss
                rsi = 100 - (100 / (1 + rs))
            else:
                rsi = 100
            rsi_signal = "超买区间" if rsi > 70 else ("超卖区间" if rsi < 30 else "中性区间")
            print(f"\n  RSI(14): {rsi:.1f} — {rsi_signal}")

        # MACD (12, 26, 9)
        if len(closes) >= 35:
            def ema(data, period):
                k = 2 / (period + 1)
                result = [data[0]]
                for i in range(1, len(data)):
                    result.append(data[i] * k + result[-1] * (1 - k))
                return result

            ema12 = ema(closes, 12)
            ema26 = ema(closes, 26)
            dif = [ema12[i] - ema26[i] for i in range(len(closes))]
            dea = ema(dif, 9)
            macd_hist = [(dif[i] - dea[i]) * 2 for i in range(len(closes))]

            print(f"\n  MACD:")
            print(f"    DIF: {dif[-1]:.3f}")
            print(f"    DEA: {dea[-1]:.3f}")
            print(f"    MACD柱: {macd_hist[-1]:.3f}")
            if dif[-1] > dea[-1] and dif[-2] <= dea[-2]:
                print(f"    信号: 金叉 (看涨信号)")
            elif dif[-1] < dea[-1] and dif[-2] >= dea[-2]:
                print(f"    信号: 死叉 (看跌信号)")
            elif dif[-1] > dea[-1]:
                print(f"    信号: DIF在DEA上方 (多头趋势)")
            else:
                print(f"    信号: DIF在DEA下方 (空头趋势)")

        # 布林带 (20日)
        if len(closes) >= 20:
            mid = ma20
            std = (sum((c - mid) ** 2 for c in closes[-20:]) / 20) ** 0.5
            upper = mid + 2 * std
            lower = mid - 2 * std
            bandwidth = (upper - lower) / mid * 100

            print(f"\n  布林带(20):")
            print(f"    上轨: {upper:.2f} | 中轨: {mid:.2f} | 下轨: {lower:.2f}")
            print(f"    带宽: {bandwidth:.1f}%")
            if current > upper:
                print(f"    位置: 突破上轨 (可能超买或强势突破)")
            elif current < lower:
                print(f"    位置: 跌破下轨 (可能超卖或弱势破位)")
            else:
                pct_b = (current - lower) / (upper - lower) * 100
                print(f"    位置: 带内 ({pct_b:.0f}% 位置)")

        # 支撑位和阻力位 (基于近期高低点)
        if len(closes) >= 20:
            recent_highs = highs[-20:]
            recent_lows = lows[-20:]
            print(f"\n  关键价位:")
            print(f"    近20日最高: {max(recent_highs):.2f} (阻力位参考)")
            print(f"    近20日最低: {min(recent_lows):.2f} (支撑位参考)")
            if ma50:
                print(f"    MA50支撑/阻力: {ma50:.2f}")
            if ma200:
                print(f"    MA200支撑/阻力: {ma200:.2f}")
    else:
        print("  数据不足，无法计算技术指标")

    # ============================================================
    # 3. 基本面快照
    # ============================================================
    print(f"\n【3】基本面快照")
    url2 = f'https://query1.finance.yahoo.com/v10/finance/quoteSummary/{TICKER}?modules=defaultKeyStatistics,financialData,price'
    raw2 = fetch(url2)
    if raw2:
        try:
            d = json.loads(raw2.decode('utf-8'))
            result = d.get('quoteSummary', {}).get('result', [{}])[0]
            stats = result.get('defaultKeyStatistics', {})
            fin = result.get('financialData', {})
            price_info = result.get('price', {})

            pe = stats.get('forwardPE', {}).get('raw', 'N/A')
            pb = stats.get('priceToBook', {}).get('raw', 'N/A')
            market_cap = price_info.get('marketCap', {}).get('fmt', 'N/A')
            eps = stats.get('trailingEps', {}).get('raw', 'N/A')
            rev_growth = fin.get('revenueGrowth', {}).get('raw', 'N/A')
            profit_margin = fin.get('profitMargins', {}).get('raw', 'N/A')
            target = fin.get('targetMeanPrice', {}).get('raw', 'N/A')
            rec = fin.get('recommendationKey', 'N/A')

            print(f"  市值: {market_cap}")
            if pe != 'N/A': print(f"  前瞻市盈率(Forward PE): {pe:.1f}")
            if pb != 'N/A': print(f"  市净率(PB): {pb:.2f}")
            if eps != 'N/A': print(f"  每股收益(EPS): {eps:.2f}")
            if rev_growth != 'N/A': print(f"  营收增长率: {rev_growth*100:.1f}%")
            if profit_margin != 'N/A': print(f"  利润率: {profit_margin*100:.1f}%")
            if target != 'N/A': print(f"  分析师目标均价: {target:.2f}")
            if rec != 'N/A': print(f"  分析师建议: {rec}")
        except:
            print("  解析失败")
    else:
        print("  基本面数据获取失败")

    print("\n" + "=" * 60)
    print("数据采集完成")
    print("=" * 60)


if __name__ == "__main__":
    main()
