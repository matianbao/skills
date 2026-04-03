#!/usr/bin/env python3
"""
A股市场情绪分析 - 自动采集 + 钉钉推送
支持两种模式:
  - 交互模式: python3 a_stock_dingtalk.py (跳过交易日检查，直接采集+推送)
  - 定时模式: python3 a_stock_dingtalk.py --cron (检查交易日，周末/节假日跳过)
"""

import urllib.request
import json
import re
import sys
import time
import hmac
import hashlib
import base64
import urllib.parse
from datetime import datetime

# ============================================================
# 钉钉配置
# ============================================================
WEBHOOK_URL = "https://oapi.dingtalk.com/robot/send?access_token=9edfb2a3680fe4397836700d00ad04503042c00fba838151cbbb665eba58d8be"
SECRET = "SECe1799f0b4f4c621fa3a778f93cdbfa26d4224aeb23d02e06cd890cce148c0247"


def fetch(url, headers=None, timeout=10):
    try:
        hdrs = headers or {}
        hdrs.setdefault('User-Agent', 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)')
        req = urllib.request.Request(url, headers=hdrs)
        resp = urllib.request.urlopen(req, timeout=timeout)
        return resp.read()
    except Exception:
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


def collect_data():
    data = {}
    today = datetime.now().strftime("%Y-%m-%d")
    data['date'] = today

    print("=" * 60)
    print("A股市场数据采集")
    print("=" * 60)

    # 1. 大盘指数
    print("\n【1】大盘指数")
    raw = fetch('https://hq.sinajs.cn/list=s_sh000001,s_sz399001,s_sz399006',
                {'Referer': 'https://finance.sina.com.cn'})
    data['indices'] = []
    if raw:
        text = raw.decode('gbk', errors='replace')
        names = {'s_sh000001': '上证指数', 's_sz399001': '深证成指', 's_sz399006': '创业板指'}
        for line in text.strip().split('\n'):
            for code, name in names.items():
                if code in line:
                    parts = line.split('"')[1].split(',')
                    if len(parts) >= 6:
                        idx = {'name': name, 'price': parts[1], 'change': parts[2],
                               'pct': parts[3], 'amount_yi': int(parts[5]) / 10000}
                        data['indices'].append(idx)
                        sign = '+' if float(parts[2]) >= 0 else ''
                        print(f"  {name}: {parts[1]} | {sign}{parts[2]} ({sign}{parts[3]}%) | 成交额: {idx['amount_yi']:.0f}亿")
    else:
        print("  ❌ 获取失败")

    # 2. 大盘详情
    print("\n【2】大盘详情（开盘/最高/最低）")
    raw = fetch('https://qt.gtimg.cn/q=sh000001,sz399001,sz399006')
    data['details'] = []
    if raw:
        text = raw.decode('gbk', errors='replace')
        for line in text.strip().split('\n'):
            parts = line.split('~')
            if len(parts) > 35:
                det = {'name': parts[1], 'open': parts[5], 'high': parts[33],
                       'low': parts[34], 'yesterday': parts[4]}
                data['details'].append(det)
                print(f"  {parts[1]}: 开盘 {parts[5]} | 最高 {parts[33]} | 最低 {parts[34]} | 昨收 {parts[4]}")
    else:
        print("  ❌ 获取失败")

    # 3. 行业板块
    print("\n【3】行业板块排行")
    raw = fetch('https://vip.stock.finance.sina.com.cn/q/view/newSinaHy.php',
                {'Referer': 'https://finance.sina.com.cn'})
    data['sectors'] = []
    if raw:
        text = raw.decode('gbk', errors='replace')
        try:
            start = text.index('{'); end = text.rindex('}') + 1
            jdata = json.loads(text[start:end])
            for key, val in jdata.items():
                parts = val.split(',')
                if len(parts) >= 13:
                    data['sectors'].append((parts[1], float(parts[5]), parts[12]))
            data['sectors'].sort(key=lambda x: x[1], reverse=True)
            print("  领涨:")
            for name, pct, leader in data['sectors'][:5]:
                print(f"    {name}: {pct:+.2f}% (龙头: {leader})")
            print("  领跌:")
            for name, pct, leader in data['sectors'][-5:]:
                print(f"    {name}: {pct:+.2f}% (龙头: {leader})")
        except Exception:
            print("  ❌ 解析失败")
    else:
        print("  ❌ 获取失败")

    # 4. 概念板块
    print("\n【4】概念板块排行")
    raw = fetch('https://vip.stock.finance.sina.com.cn/q/view/newFLJK.php?param=class',
                {'Referer': 'https://finance.sina.com.cn'})
    data['concepts'] = []
    if raw:
        text = raw.decode('gbk', errors='replace')
        try:
            start = text.index('{'); end = text.rindex('}') + 1
            jdata = json.loads(text[start:end])
            for key, val in jdata.items():
                parts = val.split(',')
                if len(parts) >= 13:
                    data['concepts'].append((parts[1], float(parts[5]), parts[12]))
            data['concepts'].sort(key=lambda x: x[1], reverse=True)
            print("  领涨:")
            for name, pct, leader in data['concepts'][:5]:
                print(f"    {name}: {pct:+.2f}% (龙头: {leader})")
            print("  领跌:")
            for name, pct, leader in data['concepts'][-5:]:
                print(f"    {name}: {pct:+.2f}% (龙头: {leader})")
        except Exception:
            print("  ❌ 解析失败")
    else:
        print("  ❌ 获取失败")

    # 5. 沪深港通资金
    print("\n【5】沪深港通资金")
    raw = fetch('https://push2.eastmoney.com/api/qt/kamt/get?fields1=f1,f2,f3,f4&fields2=f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61,f62,f63,f64,f65,f66,f67,f68,f69,f70,f71,f72,f73,f74,f75,f76,f77,f78,f79,f80,f81,f82,f83,f84,f85,f86',
                {'Referer': 'https://data.eastmoney.com/'})
    data['funds'] = {}
    if raw:
        fdata = json.loads(raw.decode('utf-8')).get('data', {})
        hk2sh = fdata.get('hk2sh', {}); hk2sz = fdata.get('hk2sz', {})
        sh2hk = fdata.get('sh2hk', {}); sz2hk = fdata.get('sz2hk', {})
        data['funds'] = {
            'north_hgt': hk2sh.get('buySellAmt', 0) / 10000,
            'north_sgt': hk2sz.get('buySellAmt', 0) / 10000,
            'south_sh2hk': sh2hk.get('netBuyAmt', 0) / 10000,
            'south_sz2hk': sz2hk.get('netBuyAmt', 0) / 10000,
        }
        f = data['funds']
        print(f"  北向成交额: 沪股通 {f['north_hgt']:.0f}亿 + 深股通 {f['north_sgt']:.0f}亿 = 合计 {f['north_hgt']+f['north_sgt']:.0f}亿")
        south = f['south_sh2hk'] + f['south_sz2hk']
        if south != 0:
            print(f"  南向净买入: 港股通(沪) {f['south_sh2hk']:+.2f}亿 + 港股通(深) {f['south_sz2hk']:+.2f}亿 = 合计 {south:+.2f}亿")
        else:
            print("  南向净买入: 数据为0（可能港股今日休市）")
        print("  北向净流入: 自2024年8月起不再实时披露（监管政策调整）")
    else:
        print("  ❌ 获取失败")

    # 6. 涨跌家数
    print("\n【6】涨跌家数统计")
    up = down = flat = limit_up = limit_down = 0
    page = 1; total = 0
    while page <= 70:
        raw = fetch(f'https://vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php/Market_Center.getHQNodeData?page={page}&num=80&sort=changepercent&asc=0&node=hs_a',
                    {'Referer': 'https://finance.sina.com.cn'})
        if not raw: break
        try:
            sdata = json.loads(raw.decode('gbk', errors='replace'))
        except Exception:
            break
        if not sdata: break
        for s in sdata:
            pct = float(s.get('changepercent', 0))
            if pct > 0: up += 1
            elif pct < 0: down += 1
            else: flat += 1
            if pct >= 9.9: limit_up += 1
            if pct <= -9.9: limit_down += 1
        total += len(sdata); page += 1
    data['breadth'] = {'up': up, 'down': down, 'flat': flat,
                       'limit_up': limit_up, 'limit_down': limit_down, 'total': total}
    if total > 0:
        print(f"  上涨: {up} 家 | 下跌: {down} 家 | 平盘: {flat} 家 (共 {total} 只)")
        print(f"  涨停(≥9.9%): {limit_up} 家 | 跌停(≤-9.9%): {limit_down} 家")
    else:
        print("  ❌ 获取失败")

    # 7. 板块趋势 (同花顺 - 过去10个交易日)
    print("\n【7】板块趋势分析（过去10个交易日）")
    _sector_raw = fetch('https://q.10jqka.com.cn/thshy/', {'Referer': 'https://q.10jqka.com.cn/'})
    data['sector_trend'] = []
    if _sector_raw:
        _sector_text = _sector_raw.decode('gbk', errors='replace')
        _sector_pairs = re.findall(r'/thshy/detail/code/(\d+)/"[^>]*>([^<]+)<', _sector_text)
        _sector_map = {}
        for _code, _name in _sector_pairs:
            _kraw = fetch(f'https://d.10jqka.com.cn/v6/line/bk_{_code}/01/last15.js',
                          {'Referer': f'https://stockpage.10jqka.com.cn/bk_{_code}/'})
            if not _kraw: continue
            try:
                _ktext = _kraw.decode('utf-8', errors='replace')
                _s = _ktext.index('(') + 1; _e = _ktext.rindex(')')
                _jdata = json.loads(_ktext[_s:_e])
                _lines = _jdata.get('data', '').split(';')
                _closes = []
                for _line in _lines:
                    if not _line.strip(): continue
                    _p = _line.split(',')
                    if len(_p) >= 5:
                        _closes.append(float(_p[4]))
                if len(_closes) >= 11:
                    _changes = [(_closes[j] / _closes[j-1] - 1) * 100
                                for j in range(max(1, len(_closes)-10), len(_closes))]
                    _sector_map[_name] = _changes
            except Exception:
                pass
        if _sector_map:
            _ranked = sorted(_sector_map.items(), key=lambda x: sum(x[1]), reverse=True)
            data['sector_trend'] = _ranked
            print("  累计领涨 TOP5:")
            for _name, _changes in _ranked[:5]:
                _total = sum(_changes)
                _streak = 0
                for _c in reversed(_changes):
                    if _c > 0: _streak += 1
                    else: break
                _day_strs = [f"\033[31m{c:+.1f}%\033[0m" if c > 0 else f"\033[32m{c:+.1f}%\033[0m" for c in _changes[-5:]]
                print(f"    {_name}: 累计{_total:+.1f}% | 近5日: {' '.join(_day_strs)} | 连涨{_streak}天")
            print("  累计领跌 TOP5:")
            for _name, _changes in _ranked[-5:]:
                _total = sum(_changes)
                _day_strs = [f"\033[31m{c:+.1f}%\033[0m" if c > 0 else f"\033[32m{c:+.1f}%\033[0m" for c in _changes[-5:]]
                print(f"    {_name}: 累计{_total:+.1f}% | 近5日: {' '.join(_day_strs)}")
        else:
            print("  ❌ 板块K线解析失败")
    else:
        print("  ❌ 板块列表获取失败")

    print("\n" + "=" * 60)
    print("数据采集完成")
    print("=" * 60)

    return data


def build_report(d):
    lines = []
    date = d['date']
    lines.append(f"# A股盘后复盘 {date}\n")

    # 情绪判断
    b = d['breadth']
    total_amount = sum(i['amount_yi'] for i in d['indices']) if d['indices'] else 0
    if b['up'] == 0 and b['down'] == 0:
        avg_pct = sum(float(i['pct']) for i in d['indices']) / len(d['indices']) if d['indices'] else 0
        if avg_pct >= 1: mood, icon = "偏乐观", "🟡"
        elif avg_pct >= -0.3: mood, icon = "中性", "⚪"
        elif avg_pct >= -1.5: mood, icon = "偏悲观", "🟠"
        else: mood, icon = "悲观", "🔴"
        ratio = 0
    else:
        ratio = b['up'] / b['down'] if b['down'] > 0 else 999
        if ratio >= 3: mood, icon = "乐观", "🟢"
        elif ratio >= 1.5: mood, icon = "偏乐观", "🟡"
        elif ratio >= 0.8: mood, icon = "中性", "⚪"
        elif ratio >= 0.4: mood, icon = "偏悲观", "🟠"
        else: mood, icon = "悲观", "🔴"

    lines.append(f"**今日情绪: {mood} {icon}**\n")

    # 大盘表现
    lines.append("## 大盘表现\n")
    for idx in d['indices']:
        sign = "+" if float(idx['change']) >= 0 else ""
        lines.append(f"- **{idx['name']}** {idx['price']}  "
                     f"{sign}{idx['change']} ({sign}{idx['pct']}%)  "
                     f"成交 {idx['amount_yi']:.0f}亿")
    if d['details']:
        lines.append("")
        for det in d['details']:
            lines.append(f"- {det['name']}: 开盘 {det['open']} / 最高 {det['high']} / 最低 {det['low']}")

    # 板块分析
    lines.append("\n## 板块分析\n")
    if d['sectors']:
        lines.append("**领涨行业:**")
        for name, pct, leader in d['sectors'][:5]:
            lines.append(f"- {name} {pct:+.2f}% (龙头: {leader})")
        lines.append("\n**领跌行业:**")
        for name, pct, leader in d['sectors'][-5:]:
            lines.append(f"- {name} {pct:+.2f}% (龙头: {leader})")
    if d['concepts']:
        lines.append("\n**热门概念:**")
        for name, pct, leader in d['concepts'][:5]:
            lines.append(f"- {name} {pct:+.2f}% (龙头: {leader})")

    # 资金流向
    lines.append("\n## 资金流向\n")
    f = d.get('funds', {})
    if f:
        north = f.get('north_hgt', 0) + f.get('north_sgt', 0)
        lines.append(f"- 北向成交额: 沪股通 {f.get('north_hgt', 0):.0f}亿 + 深股通 {f.get('north_sgt', 0):.0f}亿 = **{north:.0f}亿**")
        south_sh = f.get('south_sh2hk', 0); south_sz = f.get('south_sz2hk', 0)
        south = south_sh + south_sz
        if south != 0:
            lines.append(f"- 南向净买入: 港股通(沪) {south_sh:+.1f}亿 + 港股通(深) {south_sz:+.1f}亿 = **{south:+.1f}亿**")
        else:
            lines.append("- 南向净买入: 数据为0（港股可能休市）")
        lines.append("- 北向净流入: 自2024年8月起不再披露")

    # 市场温度计
    lines.append("\n## 市场温度计\n")
    if b['total'] > 0:
        lines.append(f"- 涨跌家数: 上涨 **{b['up']}** / 下跌 **{b['down']}** / 平盘 {b['flat']}")
        lines.append(f"- 涨停 **{b['limit_up']}** 家 / 跌停 **{b['limit_down']}** 家")
        lines.append(f"- 涨跌比: **{ratio:.1f}:1**")
    else:
        lines.append("- 涨跌家数: 数据暂未获取到")
    lines.append(f"- 沪深合计成交: **{total_amount:.0f}亿**")

    # 板块趋势
    if d.get('sector_trend'):
        lines.append("\n## 板块趋势（过去10个交易日）\n")
        ranked = d['sector_trend']
        lines.append("**累计领涨 TOP5:**")
        for name, changes in ranked[:5]:
            total_chg = sum(changes)
            streak = 0
            for c in reversed(changes):
                if c > 0: streak += 1
                else: break
            day_strs = [f'<font color="#FF0000">{c:+.1f}%</font>' if c > 0 else f'<font color="#00AA00">{c:+.1f}%</font>' for c in changes[-5:]]
            lines.append(f"- **{name}** {total_chg:+.1f}% | {' '.join(day_strs)} | 连涨{streak}天")
        lines.append("\n**累计领跌 TOP5:**")
        for name, changes in ranked[-5:]:
            total_chg = sum(changes)
            day_strs = [f'<font color="#FF0000">{c:+.1f}%</font>' if c > 0 else f'<font color="#00AA00">{c:+.1f}%</font>' for c in changes[-5:]]
            lines.append(f"- **{name}** {total_chg:+.1f}% | {' '.join(day_strs)}")

    lines.append("\n---")
    lines.append("> 免责声明: 以上基于公开数据自动生成，不构成投资建议。")
    return "\n".join(lines)


def main():
    cron_mode = '--cron' in sys.argv
    print(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] A股复盘脚本启动 ({'定时模式' if cron_mode else '交互模式'})")

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
    send_dingtalk(f"A股复盘 {data['date']}", report)
    print("[DONE] 完成")


if __name__ == "__main__":
    main()
