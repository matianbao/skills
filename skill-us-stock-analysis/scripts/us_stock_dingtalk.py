#!/usr/bin/env python3
"""
美股市场复盘 - 自动采集 + 钉钉推送
支持两种模式:
  - 交互模式: python3 us_stock_dingtalk.py (直接采集+推送)
  - 定时模式: python3 us_stock_dingtalk.py --cron (检查交易日，周末跳过)
"""

import urllib.request
import json
import sys
import time
import hmac
import hashlib
import base64
import urllib.parse
from datetime import datetime, timedelta

# ============================================================
# 钉钉配置（与 A 股共用同一机器人）
# ============================================================
WEBHOOK_URL = "https://oapi.dingtalk.com/robot/send?access_token=9edfb2a3680fe4397836700d00ad04503042c00fba838151cbbb665eba58d8be"
SECRET = "SECe1799f0b4f4c621fa3a778f93cdbfa26d4224aeb23d02e06cd890cce148c0247"


def fetch(url, headers=None, timeout=15):
    try:
        hdrs = headers or {}
        hdrs.setdefault('User-Agent', 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36')
        req = urllib.request.Request(url, headers=hdrs)
        resp = urllib.request.urlopen(req, timeout=timeout)
        return resp.read()
    except Exception as e:
        print(f"  请求失败: {e}")
        return None


def sign_url(webhook_url, secret):
    timestamp = str(round(time.time() * 1000))
    string_to_sign = f"{timestamp}\n{secret}"
    hmac_code = hmac.new(
        secret.encode('utf-8'),
        string_to_sign.encode('utf-8'),
        digestmod=hashlib.sha256
    ).digest()
    sign = urllib.parse.quote_plus(base64.b64encode(hmac_code))
    return f"{webhook_url}&timestamp={timestamp}&sign={sign}"


def send_dingtalk(title, text):
    url = sign_url(WEBHOOK_URL, SECRET)
    payload = json.dumps({
        "msgtype": "markdown",
        "markdown": {"title": title, "text": text}
    }).encode('utf-8')
    req = urllib.request.Request(url, data=payload, headers={'Content-Type': 'application/json'})
    try:
        resp = urllib.request.urlopen(req, timeout=10)
        result = json.loads(resp.read().decode('utf-8'))
        if result.get('errcode') == 0:
            print("[OK] 钉钉推送成功")
        else:
            print(f"[FAIL] 钉钉返回错误: {result}")
        return result
    except Exception as e:
        print(f"[FAIL] 钉钉推送异常: {e}")
        return None


def fetch_yahoo_chart(ticker, days=60):
    """从 Yahoo Finance 获取K线数据"""
    end_ts = int(datetime.now().timestamp())
    start_ts = int((datetime.now() - timedelta(days=days)).timestamp())
    url = f'https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?period1={start_ts}&period2={end_ts}&interval=1d'
    raw = fetch(url)
    if not raw:
        return None
    try:
        data = json.loads(raw.decode('utf-8'))
        result = data.get('chart', {}).get('result', [{}])[0]
        meta = result.get('meta', {})
        quote = result.get('indicators', {}).get('quote', [{}])[0]
        closes = [x for x in quote.get('close', []) if x is not None]
        volumes = [x for x in quote.get('volume', []) if x is not None]
        price = meta.get('regularMarketPrice', 0)
        # 用K线倒数第二根收盘价作为昨收，chartPreviousClose 是范围起点的价格
        if len(closes) >= 2:
            prev_close = closes[-2]
        else:
            prev_close = meta.get('previousClose', meta.get('chartPreviousClose', 0))
        return {
            'price': price,
            'prev_close': prev_close,
            'closes': closes,
            'volumes': volumes,
        }
    except Exception:
        return None


def collect_data():
    data = {}
    today = datetime.now().strftime("%Y-%m-%d")
    data['date'] = today

    print("=" * 60)
    print("美股市场数据采集")
    print("=" * 60)

    # 1. 三大指数 + VIX + 10Y 国债
    print("\n【1】三大指数 + 风险指标")
    indices_config = {
        '^GSPC': '标普500 (S&P 500)',
        '^DJI': '道琼斯 (Dow Jones)',
        '^IXIC': '纳斯达克 (NASDAQ)',
    }
    risk_config = {
        '^VIX': 'VIX 恐慌指数',
        '^TNX': '10Y 美债收益率',
    }

    data['indices'] = []
    for ticker, name in indices_config.items():
        info = fetch_yahoo_chart(ticker, days=60)
        if info and info['price']:
            price = info['price']
            prev = info['prev_close']
            change = price - prev if prev else 0
            pct = (change / prev * 100) if prev else 0
            closes = info['closes']

            # 简单趋势判断
            trend = ""
            if len(closes) >= 20:
                ma5 = sum(closes[-5:]) / 5
                ma20 = sum(closes[-20:]) / 20
                if price > ma5 > ma20:
                    trend = "短期多头"
                elif price < ma5 < ma20:
                    trend = "短期空头"
                else:
                    trend = "震荡"

            idx = {
                'name': name, 'ticker': ticker,
                'price': price, 'change': change, 'pct': pct,
                'trend': trend, 'closes': closes,
                'volumes': info['volumes'],
            }
            data['indices'].append(idx)
            sign = '+' if change >= 0 else ''
            print(f"  {name}: {price:,.2f} | {sign}{change:,.2f} ({sign}{pct:.2f}%) | {trend}")
        else:
            print(f"  {name}: 获取失败")

    data['risk'] = {}
    for ticker, name in risk_config.items():
        info = fetch_yahoo_chart(ticker, days=30)
        if info and info['price']:
            price = info['price']
            prev = info['prev_close']
            change = price - prev if prev else 0
            pct = (change / prev * 100) if prev else 0
            data['risk'][ticker] = {
                'name': name, 'price': price, 'change': change, 'pct': pct,
            }
            sign = '+' if change >= 0 else ''
            print(f"  {name}: {price:.2f} | {sign}{change:.2f} ({sign}{pct:.2f}%)")
        else:
            print(f"  {name}: 获取失败")

    # 2. 行业板块（11 个 SPDR 行业 ETF）
    print("\n【2】行业板块表现")
    sector_etfs = {
        'XLK': '科技',
        'XLF': '金融',
        'XLV': '医疗保健',
        'XLY': '非必需消费',
        'XLP': '必需消费',
        'XLE': '能源',
        'XLI': '工业',
        'XLB': '材料',
        'XLU': '公用事业',
        'XLRE': '房地产',
        'XLC': '通信服务',
    }

    data['sectors'] = []
    for ticker, name in sector_etfs.items():
        info = fetch_yahoo_chart(ticker, days=30)
        if info and info['price']:
            price = info['price']
            prev = info['prev_close']
            change = price - prev if prev else 0
            pct = (change / prev * 100) if prev else 0

            # 5日涨跌趋势
            closes = info['closes']
            trend5 = ""
            pct_5d = 0
            if len(closes) >= 6:
                changes = [(closes[i] / closes[i-1] - 1) * 100 for i in range(max(1, len(closes)-5), len(closes))]
                trend5 = ''.join(['↑' if c > 0 else '↓' for c in changes])
                pct_5d = (closes[-1] / closes[-6] - 1) * 100 if closes[-6] else 0

            data['sectors'].append({
                'ticker': ticker, 'name': name,
                'price': price, 'pct': pct, 'trend5': trend5, 'pct_5d': pct_5d,
            })

    # 按涨跌排序
    data['sectors'].sort(key=lambda x: x['pct'], reverse=True)
    if data['sectors']:
        print("  领涨:")
        for s in data['sectors'][:5]:
            print(f"    {s['name']}({s['ticker']}): {s['pct']:+.2f}% | 5日: {s['trend5']} ({s['pct_5d']:+.1f}%)")
        print("  领跌:")
        for s in data['sectors'][-3:]:
            print(f"    {s['name']}({s['ticker']}): {s['pct']:+.2f}% | 5日: {s['trend5']} ({s['pct_5d']:+.1f}%)")

    # 3. 市场广度指标（通过板块 ETF 涨跌统计近似）
    print("\n【3】市场广度")
    data['breadth'] = {}
    if data['sectors']:
        up_sectors = sum(1 for s in data['sectors'] if s['pct'] > 0)
        down_sectors = sum(1 for s in data['sectors'] if s['pct'] < 0)
        data['breadth'] = {'up_sectors': up_sectors, 'down_sectors': down_sectors}
        print(f"  板块涨跌: {up_sectors} 涨 / {down_sectors} 跌 (共 {len(data['sectors'])} 个行业)")
    else:
        print("  数据不足")

    print("\n" + "=" * 60)
    print("数据采集完成")
    print("=" * 60)

    return data


def build_report(d):
    lines = []
    date = d['date']
    lines.append(f"# 美股盘后复盘 {date}\n")

    # 情绪判断
    sp500 = next((i for i in d['indices'] if i['ticker'] == '^GSPC'), None)
    vix = d['risk'].get('^VIX', {})
    vix_price = vix.get('price', 0)

    # 综合情绪: 基于标普涨跌幅 + VIX 水平
    if sp500:
        pct = sp500['pct']
        if pct >= 1.5 and vix_price < 20:
            mood, icon = "乐观", "\U0001f7e2"
        elif pct >= 0.3:
            mood, icon = "偏乐观", "\U0001f7e1"
        elif pct >= -0.3:
            mood, icon = "中性", "\u26aa"
        elif pct >= -1.5:
            mood, icon = "偏悲观", "\U0001f7e0"
        else:
            mood, icon = "悲观", "\U0001f534"
        # VIX 过高修正情绪
        if vix_price >= 30 and mood in ("乐观", "偏乐观"):
            mood, icon = "中性", "\u26aa"
    else:
        mood, icon = "未知", "\u26aa"

    lines.append(f"**今日情绪: {mood} {icon}**\n")

    # 三大指数
    lines.append("## 三大指数表现\n")
    for idx in d['indices']:
        sign = "+" if idx['change'] >= 0 else ""
        lines.append(f"- **{idx['name']}** {idx['price']:,.2f}  "
                     f"{sign}{idx['change']:,.2f} ({sign}{idx['pct']:.2f}%)  "
                     f"趋势: {idx['trend']}")

    # 风险指标
    lines.append("\n## 风险指标\n")
    vix_data = d['risk'].get('^VIX')
    if vix_data:
        vp = vix_data['price']
        if vp < 15:
            vix_desc = "低位平稳"
        elif vp < 20:
            vix_desc = "正常"
        elif vp < 30:
            vix_desc = "偏高"
        else:
            vix_desc = "恐慌"
        lines.append(f"- **VIX 恐慌指数**: {vp:.2f} ({vix_desc})")
    tnx_data = d['risk'].get('^TNX')
    if tnx_data:
        lines.append(f"- **10Y 美债收益率**: {tnx_data['price']:.2f}%")

    # 市场广度
    b = d.get('breadth', {})
    if b.get('up_sectors') is not None:
        lines.append(f"\n## 市场广度\n")
        lines.append(f"- 行业板块: **{b['up_sectors']}** 涨 / **{b['down_sectors']}** 跌")

    # 板块表现
    if d['sectors']:
        lines.append("\n## 板块表现\n")
        lines.append("**领涨行业:**")
        for s in d['sectors'][:5]:
            lines.append(f"- {s['name']}({s['ticker']}) {s['pct']:+.2f}% | 5日: {s['trend5']} ({s['pct_5d']:+.1f}%)")
        lines.append("\n**领跌行业:**")
        for s in d['sectors'][-3:]:
            lines.append(f"- {s['name']}({s['ticker']}) {s['pct']:+.2f}% | 5日: {s['trend5']} ({s['pct_5d']:+.1f}%)")

    lines.append("\n---")
    lines.append("> 免责声明: 以上基于公开数据自动生成，不构成投资建议。")
    return "\n".join(lines)


def main():
    cron_mode = '--cron' in sys.argv
    print(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] 美股复盘脚本启动 ({'定时模式' if cron_mode else '交互模式'})")

    # 美股周末休市（周六=5，周日=6）
    if cron_mode and datetime.now().weekday() >= 5:
        print("[SKIP] 今日非交易日（周末），跳过")
        return

    print("[1/3] 采集市场数据...")
    data = collect_data()

    if not data['indices']:
        print("[SKIP] 未获取到指数数据，可能为节假日，跳过推送")
        return

    print("\n[2/3] 生成报告...")
    report = build_report(data)
    print(report)

    print("\n[3/3] 推送到钉钉...")
    send_dingtalk(f"美股复盘 {data['date']}", report)
    print("[DONE] 完成")


if __name__ == "__main__":
    main()
