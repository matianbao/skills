#!/usr/bin/env python3
"""
每日市场热点 & 供需数据采集
输出 JSON 到 /tmp/daily_hotspots.json，供 Skill 层 LLM 分析使用。

数据源：
  - 新浪财经全球快讯（stock_info_global_sina）
  - 新浪财经滚动新闻 API
  - CCTV 新闻联播（经济相关）
  - AKShare 期货行情（国内主力合约）
  - 新浪行业/概念板块排行
"""

import json
import sys
import time
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path

OUTPUT_PATH = "/tmp/daily_hotspots.json"
CONFIG_PATH = Path(__file__).parent / "config.json"


def load_config():
    with open(CONFIG_PATH, "r") as f:
        return json.load(f)


def fetch_url(url, headers=None, timeout=10):
    try:
        hdrs = headers or {}
        hdrs.setdefault("User-Agent", "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)")
        req = urllib.request.Request(url, headers=hdrs)
        resp = urllib.request.urlopen(req, timeout=timeout)
        return resp.read()
    except Exception as e:
        print(f"  [WARN] 请求失败: {url[:80]}... => {e}")
        return None


# ─────────────────────────────────────────────
# 模块一：热点新闻
# ─────────────────────────────────────────────
def fetch_sina_global_news():
    """新浪财经全球要闻（通过 AKShare）"""
    print("\n【1a】新浪财经全球要闻")
    try:
        import akshare as ak
        df = ak.stock_info_global_sina()
        news = []
        for _, row in df.head(30).iterrows():
            news.append({
                "time": str(row.get("时间", "")),
                "content": str(row.get("内容", "")),
                "source": "新浪财经"
            })
        print(f"  获取 {len(news)} 条")
        return news
    except Exception as e:
        print(f"  [FAIL] {e}")
        return []


def fetch_sina_roll_news():
    """新浪财经滚动新闻（财经要闻频道）"""
    print("\n【1b】新浪财经滚动新闻")
    url = "https://feed.mix.sina.com.cn/api/roll/get?pageid=153&lid=2516&k=&num=30&page=1"
    raw = fetch_url(url, {"Referer": "https://finance.sina.com.cn"})
    if not raw:
        return []
    try:
        data = json.loads(raw)
        items = data.get("result", {}).get("data", [])
        news = []
        for item in items:
            news.append({
                "time": item.get("ctime", ""),
                "title": item.get("title", ""),
                "url": item.get("url", ""),
                "source": "新浪滚动"
            })
        print(f"  获取 {len(news)} 条")
        return news
    except Exception as e:
        print(f"  [FAIL] 解析失败: {e}")
        return []


def fetch_cctv_news():
    """CCTV 新闻联播（筛选经济/政策相关）"""
    print("\n【1c】CCTV 新闻联播")
    today = datetime.now().strftime("%Y%m%d")
    try:
        import akshare as ak
        df = ak.news_cctv(date=today)
        keywords = ["经济", "产业", "制造", "科技", "数字", "能源", "金融",
                     "投资", "贸易", "关税", "改革", "市场", "消费", "就业"]
        news = []
        for _, row in df.iterrows():
            title = str(row.get("title", ""))
            if any(kw in title for kw in keywords):
                news.append({
                    "title": title,
                    "content": str(row.get("content", ""))[:500],
                    "source": "CCTV"
                })
        print(f"  获取 {len(news)} 条经济相关")
        return news
    except Exception as e:
        print(f"  [FAIL] {e}")
        return []


# ─────────────────────────────────────────────
# 模块二：核心商品/期货价格
# ─────────────────────────────────────────────
SINA_FOREIGN_SYMBOLS = {
    "hf_CL": "WTI原油",
    "hf_OIL": "布伦特原油",
    "hf_NG": "天然气(Henry Hub)",
    "hf_GC": "COMEX黄金",
    "hf_SI": "COMEX白银",
}


def fetch_foreign_futures():
    """通过新浪实时行情获取外盘期货"""
    print("\n【2a】外盘期货实时行情")
    symbols = ",".join(SINA_FOREIGN_SYMBOLS.keys())
    raw = fetch_url(
        f"https://hq.sinajs.cn/list={symbols}",
        {"Referer": "https://finance.sina.com.cn"}
    )
    results = []
    if not raw:
        print("  获取失败")
        return results
    text = raw.decode("gbk", errors="replace")
    for line in text.strip().split("\n"):
        for code, display in SINA_FOREIGN_SYMBOLS.items():
            if code in line:
                try:
                    parts = line.split('"')[1].split(",")
                    # 格式: 最新价,,开盘,最高,最高(历史?),最低,时间,昨收,昨结算,...,日期,名称
                    price = float(parts[0])
                    prev_close = float(parts[7]) if parts[7] else None
                    prev_settle = float(parts[8]) if parts[8] else None
                    ref = prev_settle or prev_close
                    day_chg = ((price - ref) / ref * 100) if ref and ref > 0 else None
                    entry = {
                        "name": display,
                        "symbol": code,
                        "price": price,
                        "date": parts[12] if len(parts) > 12 else "",
                        "day_chg_pct": round(day_chg, 2) if day_chg is not None else None,
                        "week_chg_pct": None,
                        "month_chg_pct": None,
                        "source": "sina_foreign"
                    }
                    results.append(entry)
                    sign = "+" if (day_chg or 0) >= 0 else ""
                    print(f"  {display}: {price} | 日{sign}{day_chg:.2f}%" if day_chg else f"  {display}: {price}")
                except Exception as e:
                    print(f"  {display}: [FAIL] {e}")
    return results


def fetch_commodity_prices(config):
    """获取国内期货价格及涨跌幅"""
    print("\n【2b】国内期货价格")
    import akshare as ak

    results = []
    for name, cfg in config.get("commodities", {}).items():
        symbol = cfg["symbol"]
        display = cfg.get("display", name)
        # 跳过外盘品种（已由 fetch_foreign_futures 处理）
        if cfg.get("exchange") in ("NYMEX", "IPE", "COMEX"):
            continue
        try:
            df = ak.futures_zh_daily_sina(symbol=symbol)
            if df.empty:
                print(f"  {display}: 无数据")
                continue

            # 最新一行
            latest = df.iloc[-1]
            price = float(latest["close"])
            settle = float(latest.get("settle", price))

            # 日涨跌幅：对比前一日收盘
            day_chg = None
            if len(df) >= 2:
                prev_close = float(df.iloc[-2]["close"])
                if prev_close > 0:
                    day_chg = (price - prev_close) / prev_close * 100

            # 周涨跌幅（5个交易日前）
            week_chg = None
            if len(df) >= 6:
                week_close = float(df.iloc[-6]["close"])
                if week_close > 0:
                    week_chg = (price - week_close) / week_close * 100

            # 月涨跌幅（22个交易日前）
            month_chg = None
            if len(df) >= 23:
                month_close = float(df.iloc[-23]["close"])
                if month_close > 0:
                    month_chg = (price - month_close) / month_close * 100

            entry = {
                "name": display,
                "symbol": symbol,
                "price": price,
                "settle": settle,
                "date": str(latest["date"]),
                "day_chg_pct": round(day_chg, 2) if day_chg is not None else None,
                "week_chg_pct": round(week_chg, 2) if week_chg is not None else None,
                "month_chg_pct": round(month_chg, 2) if month_chg is not None else None,
                "volume": int(latest.get("volume", 0)),
                "hold": int(latest.get("hold", 0)),
            }
            results.append(entry)

            sign = "+" if (day_chg or 0) >= 0 else ""
            print(f"  {display}: {price:.1f} | 日{sign}{day_chg:.2f}%" if day_chg else f"  {display}: {price:.1f}")

            time.sleep(0.3)  # 避免请求过快

        except Exception as e:
            print(f"  {display}: [FAIL] {e}")

    return results


# ─────────────────────────────────────────────
# 模块三：板块排行
# ─────────────────────────────────────────────
def fetch_sectors():
    """申万二级行业指数排行（数据更准确）"""
    print("\n【3a】申万行业板块排行")
    try:
        import akshare as ak
        df = ak.index_realtime_sw(symbol="二级行业")
        df["pct"] = (df["最新价"].astype(float) - df["昨收盘"].astype(float)) / df["昨收盘"].astype(float) * 100
        df = df.sort_values("pct", ascending=False)
        sectors = []
        for _, row in df.iterrows():
            sectors.append({
                "name": row["指数名称"],
                "code": row["指数代码"],
                "pct": round(row["pct"], 2),
                "type": "industry"
            })
        up = sum(1 for s in sectors if s["pct"] > 0)
        print(f"  上涨 {up} / 下跌 {len(sectors) - up} / 共 {len(sectors)}")
        print("  领涨:")
        for s in sectors[:5]:
            print(f"    {s['name']}: {s['pct']:+.2f}%")
        print("  领跌:")
        for s in sectors[-5:]:
            print(f"    {s['name']}: {s['pct']:+.2f}%")
        return sectors
    except Exception as e:
        print(f"  [FAIL] 申万数据获取失败: {e}，回退到新浪")
        return _fetch_sectors_sina_fallback()


def _fetch_sectors_sina_fallback():
    """新浪行业板块排行（备用）"""
    raw = fetch_url(
        "https://vip.stock.finance.sina.com.cn/q/view/newSinaHy.php",
        {"Referer": "https://finance.sina.com.cn"}
    )
    sectors = []
    if raw:
        text = raw.decode("gbk", errors="replace")
        try:
            start = text.index("{")
            end = text.rindex("}") + 1
            jdata = json.loads(text[start:end])
            for key, val in jdata.items():
                parts = val.split(",")
                if len(parts) >= 13:
                    sectors.append({
                        "name": parts[1],
                        "pct": float(parts[5]),
                        "leader": parts[12],
                        "type": "industry"
                    })
            sectors.sort(key=lambda x: x["pct"], reverse=True)
        except Exception:
            pass
    return sectors


def fetch_concepts():
    """新浪概念板块排行"""
    print("\n【3b】概念板块排行")
    raw = fetch_url(
        "https://vip.stock.finance.sina.com.cn/q/view/newFLJK.php?param=class",
        {"Referer": "https://finance.sina.com.cn"}
    )
    concepts = []
    if raw:
        text = raw.decode("gbk", errors="replace")
        try:
            start = text.index("{")
            end = text.rindex("}") + 1
            jdata = json.loads(text[start:end])
            for key, val in jdata.items():
                parts = val.split(",")
                if len(parts) >= 13:
                    concepts.append({
                        "name": parts[1],
                        "pct": float(parts[5]),
                        "leader": parts[12],
                        "type": "concept"
                    })
            concepts.sort(key=lambda x: x["pct"], reverse=True)
            print("  领涨:")
            for c in concepts[:5]:
                print(f"    {c['name']}: {c['pct']:+.2f}% (龙头: {c['leader']})")
            print("  领跌:")
            for c in concepts[-5:]:
                print(f"    {c['name']}: {c['pct']:+.2f}% (龙头: {c['leader']})")
        except Exception as e:
            print(f"  [FAIL] 解析失败: {e}")
    else:
        print("  获取失败")
    return concepts


# ─────────────────────────────────────────────
# 模块五：板块核心产品价格趋势
# ─────────────────────────────────────────────
SECTOR_PRODUCT_MAP = {
    "通信设备": [
        ("光纤光缆", None),  # 非标品，SKILL.md 中用 WebSearch 补充
    ],
    "焦炭": [
        ("焦炭", "J0"),
        ("焦煤", "JM0"),
    ],
    "燃气": [
        ("上海原油", "SC0"),
    ],
    "电池": [
        ("碳酸锂", "LC0"),
    ],
    "光伏设备": [
        ("玻璃", "FG0"),
        ("纯碱", "SA0"),
    ],
    "有色金属": [
        ("沪铜", "CU0"),
        ("沪铝", "AL0"),
    ],
    "钢铁": [
        ("螺纹钢", "RB0"),
        ("铁矿石", "I0"),
    ],
    "化工": [
        ("甲醇", "MA0"),
        ("PTA", "TA0"),
        ("聚丙烯", "PP0"),
        ("塑料(LLDPE)", "L0"),
    ],
    "贵金属": [
        ("黄金", "AU0"),
        ("白银", "AG0"),
    ],
    "能源": [
        ("上海原油", "SC0"),
    ],
}


def fetch_sector_product_trends():
    """获取板块核心产品的价格趋势（近20个交易日）"""
    print("\n【5】板块核心产品价格趋势")
    import akshare as ak

    results = {}
    seen_symbols = set()

    for sector, products in SECTOR_PRODUCT_MAP.items():
        sector_data = []
        for pname, symbol in products:
            if symbol is None:
                sector_data.append({"name": pname, "note": "非标品，需WebSearch补充"})
                continue
            if symbol in seen_symbols:
                continue
            seen_symbols.add(symbol)

            try:
                df = ak.futures_zh_daily_sina(symbol=symbol)
                if df.empty or len(df) < 2:
                    sector_data.append({"name": pname, "symbol": symbol, "note": "数据不足"})
                    continue

                recent = df.tail(20)
                latest = float(recent.iloc[-1]["close"])
                latest_date = str(recent.iloc[-1]["date"])

                # 各周期涨跌幅
                def calc_chg(n):
                    if len(recent) > n:
                        ref = float(recent.iloc[-(n + 1)]["close"])
                        return round((latest - ref) / ref * 100, 2) if ref > 0 else None
                    return None

                chg1 = calc_chg(1)
                chg5 = calc_chg(5)
                chg10 = calc_chg(10)
                chg20 = None
                if len(recent) >= 20:
                    ref20 = float(recent.iloc[0]["close"])
                    chg20 = round((latest - ref20) / ref20 * 100, 2) if ref20 > 0 else None

                # 近10日收盘价序列（用于趋势图）
                prices_10 = [float(r["close"]) for _, r in recent.tail(10).iterrows()]
                mn, mx = min(prices_10), max(prices_10)
                rng = mx - mn if mx > mn else 1
                sparkline = ""
                for p in prices_10:
                    level = int((p - mn) / rng * 4)
                    sparkline += ["▁", "▂", "▃", "▅", "█"][level]

                entry = {
                    "name": pname,
                    "symbol": symbol,
                    "price": latest,
                    "date": latest_date,
                    "chg_1d": chg1,
                    "chg_5d": chg5,
                    "chg_10d": chg10,
                    "chg_20d": chg20,
                    "sparkline": sparkline,
                    "prices_10d": prices_10,
                }
                sector_data.append(entry)

                chg5_str = f"{chg5:+.2f}%" if chg5 is not None else "—"
                chg20_str = f"{chg20:+.2f}%" if chg20 is not None else "—"
                print(f"  {pname}({symbol}): {latest:.0f} | 5日{chg5_str} | 20日{chg20_str} | {sparkline}")

                time.sleep(0.3)

            except Exception as e:
                print(f"  {pname}({symbol}): [FAIL] {e}")
                sector_data.append({"name": pname, "symbol": symbol, "error": str(e)})

        results[sector] = sector_data

    return results


# ─────────────────────────────────────────────
# 模块四：大盘指数
# ─────────────────────────────────────────────
def fetch_indices():
    """大盘指数"""
    print("\n【4】大盘指数")
    raw = fetch_url(
        "https://hq.sinajs.cn/list=s_sh000001,s_sz399001,s_sz399006",
        {"Referer": "https://finance.sina.com.cn"}
    )
    indices = []
    if raw:
        text = raw.decode("gbk", errors="replace")
        names = {"s_sh000001": "上证指数", "s_sz399001": "深证成指", "s_sz399006": "创业板指"}
        for line in text.strip().split("\n"):
            for code, name in names.items():
                if code in line:
                    parts = line.split('"')[1].split(",")
                    if len(parts) >= 6:
                        idx = {
                            "name": name,
                            "price": parts[1],
                            "change": parts[2],
                            "pct": parts[3],
                            "volume_yi": round(int(parts[5]) / 10000, 0),
                        }
                        indices.append(idx)
                        sign = "+" if float(parts[2]) >= 0 else ""
                        print(f"  {name}: {parts[1]} | {sign}{parts[2]} ({sign}{parts[3]}%) | 成交 {idx['volume_yi']:.0f}亿")
    else:
        print("  获取失败")
    return indices


# ─────────────────────────────────────────────
# 主流程
# ─────────────────────────────────────────────
def main():
    print("=" * 60)
    print(f"每日市场热点数据采集 — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("=" * 60)

    config = load_config()
    result = {"date": datetime.now().strftime("%Y-%m-%d"), "fetch_time": datetime.now().isoformat()}

    # 大盘指数
    result["indices"] = fetch_indices()

    # 热点新闻
    result["news_global"] = fetch_sina_global_news()
    result["news_roll"] = fetch_sina_roll_news()
    result["news_cctv"] = fetch_cctv_news()

    # 期货价格
    result["commodities_foreign"] = fetch_foreign_futures()
    result["commodities_domestic"] = fetch_commodity_prices(config)

    # 板块排行
    result["sectors"] = fetch_sectors()
    result["concepts"] = fetch_concepts()

    # 板块核心产品价格趋势
    result["sector_product_trends"] = fetch_sector_product_trends()

    # 汇总统计
    total_news = len(result["news_global"]) + len(result["news_roll"]) + len(result["news_cctv"])
    total_commodities = len(result["commodities_foreign"]) + len(result["commodities_domestic"])
    total_sectors = len(result["sectors"])
    total_concepts = len(result["concepts"])

    print("\n" + "=" * 60)
    print(f"采集完成: 新闻 {total_news} 条 | 商品 {total_commodities} 个 | 行业 {total_sectors} 个 | 概念 {total_concepts} 个")
    print("=" * 60)

    # 输出 JSON
    output = config.get("output_path", OUTPUT_PATH)
    with open(output, "w") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(f"\n已保存到 {output}")

    return result


if __name__ == "__main__":
    main()
