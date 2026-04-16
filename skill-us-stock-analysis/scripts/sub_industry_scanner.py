#!/usr/bin/env python3
"""
美股子行业扫描 V2 — 个股级动态 A 股映射
扫描 22 个子行业 ~70 个标的，按强弱排名输出，动态映射到 A 股对标标的。

Usage:
    python3 sub_industry_scanner.py          # 采集+终端输出+钉钉推送
    python3 sub_industry_scanner.py --no-push  # 仅采集+终端输出，不推送
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
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed

# ============================================================
# 钉钉配置
# ============================================================
WEBHOOK_URL = "https://oapi.dingtalk.com/robot/send?access_token=9edfb2a3680fe4397836700d00ad04503042c00fba838151cbbb665eba58d8be"
SECRET = "SECe1799f0b4f4c621fa3a778f93cdbfa26d4224aeb23d02e06cd890cce148c0247"

# ============================================================
# 个股级 A 股映射 — 每个 ticker 3-5 个对标
# 四元组: (映射强度, 产业链位置, A股标的, 映射逻辑)
#   映射强度: A=收入直接对标 B+=强间接 B=同赛道间接 C+=弱关联 C=仅概念
#   产业链: 同业=直接竞争 上游=供应商 下游=客户 配套=卖水人/服务商
# ============================================================
US_STOCK_MAP = {
    # === 半导体 ===
    'NVDA': [
        ('A', '上游', '中际旭创(300308)', 'AI算力基建光模块,NVDA算力需求直接拉动'),
        ('B+', '配套', '工业富联(601138)', 'AI服务器代工,NVDA GPU服务器制造商'),
        ('B', '配套', '长电科技(600584)', '先进封装,GPU/HBM封装'),
        ('B', '同业', '海光信息(688041)', 'AI计算,GPU vs CPU'),
        ('C+', '同业', '寒武纪(688256)', 'AI推理芯片,概念对标但体量差距极大'),
    ],
    'TSM': [
        ('A', '同业', '中芯国际(688981)', '晶圆代工直接竞争'),
        ('B+', '上游', '北方华创(002371)', '设备,代工厂扩产受益'),
        ('B+', '上游', '中微公司(688012)', '刻蚀设备,扩产受益'),
        ('B', '配套', '长电科技(600584)', '封装测试配套'),
    ],
    'AVGO': [
        ('A', '上游', '中际旭创(300308)', '光模块大客户,Tomahawk交换芯片配套'),
        ('A', '上游', '新易盛(300502)', '光模块,AVGO光互连芯片配套'),
        ('B', '同业', '卓胜微(300782)', '射频芯片,AVGO无线业务对标'),
        ('B', '下游', '中兴通讯(000063)', '网络设备,使用AVGO交换芯片'),
    ],
    'AMD': [
        ('A', '同业', '海光信息(688041)', 'x86 CPU授权,最直接对标'),
        ('B', '同业', '寒武纪(688256)', 'AI计算芯片'),
        ('B', '配套', '长电科技(600584)', '先进封装'),
        ('B', '配套', '工业富联(601138)', '服务器代工'),
    ],
    'QCOM': [
        ('B', '下游', '闻泰科技(600745)', '安卓手机模组,QCOM下游集成'),
        ('B', '同业', '卓胜微(300782)', '射频前端'),
        ('B', '同业', '韦尔股份(603501)', '手机CIS芯片,同为手机供应商'),
        ('B', '下游', '传音控股(688036)', '非洲手机龙头,QCOM芯片客户'),
    ],
    # === 半导体设备 ===
    'AMAT': [
        ('A', '同业', '北方华创(002371)', '综合设备CVD/PVD/刻蚀'),
        ('B+', '同业', '拓荆科技(688072)', '薄膜沉积CVD,AMAT CVD业务直接对标'),
        ('B', '同业', '盛美上海(688082)', '清洗设备'),
        ('B', '同业', '华海清科(688120)', 'CMP抛光'),
    ],
    'LRCX': [
        ('A', '同业', '中微公司(688012)', '刻蚀设备直接对标'),
        ('B+', '同业', '北方华创(002371)', '也有刻蚀产线'),
        ('B', '同业', '拓荆科技(688072)', '薄膜沉积'),
    ],
    'KLAC': [
        ('B', '同业', '精测电子(300567)', '半导体检测设备'),
        ('B', '同业', '长川科技(300604)', '测试设备'),
        ('B', '同业', '华海清科(688120)', 'CMP+检测'),
    ],
    'ASML': [
        ('B', '同业', '北方华创(002371)', '最接近国产设备平台'),
        ('B', '同业', '中微公司(688012)', '前道设备'),
        ('B', '配套', '茂莱光学(688502)', '精密光学,光刻配套间接'),
    ],
    # === 软件/SaaS ===
    'MSFT': [
        ('B+', '同业', '金山办公(688111)', 'Office对标,AI+办公'),
        ('B', '同业', '用友网络(600588)', '企业IT'),
        ('B', '同业', '中国软件(600536)', '操作系统对标Windows'),
        ('B', '同业', '浪潮信息(000977)', '云计算基础设施对标Azure'),
    ],
    'CRM': [
        ('B', '同业', '用友网络(600588)', '企业管理CRM/ERP'),
        ('B', '同业', '广联达(002410)', '建筑行业SaaS'),
        ('B', '同业', '金蝶国际(0268.HK)', '企业云SaaS'),
    ],
    'ORCL': [
        ('B+', '同业', '达梦数据(688692)', '国产数据库,对标Oracle'),
        ('B', '同业', '用友网络(600588)', 'ERP'),
        ('B', '同业', '海量数据(603138)', '数据库'),
        ('B', '同业', '金蝶国际(0268.HK)', '云ERP'),
    ],
    'ADBE': [
        ('B', '同业', '万兴科技(300624)', '创意软件'),
        ('B', '同业', '福昕软件(688095)', 'PDF,直接对标Adobe PDF业务'),
        ('B', '同业', '金山办公(688111)', '办公+AI'),
    ],
    # === 网络安全 ===
    'CRWD': [
        ('B+', '同业', '奇安信(688561)', '端点安全平台'),
        ('B', '同业', '深信服(300454)', '终端安全+EDR'),
        ('B', '同业', '安恒信息(688023)', '安全检测'),
    ],
    'PANW': [
        ('B+', '同业', '深信服(300454)', '网安综合平台'),
        ('B', '同业', '奇安信(688561)', '综合安全'),
        ('B', '同业', '启明星辰(002439)', '网安'),
    ],
    'FTNT': [
        ('B+', '同业', '启明星辰(002439)', '防火墙/IDS'),
        ('B', '同业', '深信服(300454)', '安全硬件'),
        ('B', '同业', '天融信(002212)', '防火墙/安全网关'),
    ],
    'ZS': [
        ('B', '同业', '安恒信息(688023)', '云安全'),
        ('B', '同业', '奇安信(688561)', '零信任'),
        ('B', '同业', '深信服(300454)', '云安全'),
    ],
    # === 机器人/自动化 ===
    'ISRG': [
        ('B+', '同业', '微创机器人(2252.HK)', '手术机器人,对标达芬奇'),
        ('B', '同业', '天智航(688277)', '骨科手术机器人'),
        ('B', '配套', '迈瑞医疗(300760)', '手术室设备配套'),
    ],
    'ABBNY': [
        ('A', '同业', '汇川技术(300124)', '伺服/变频器,直接对标'),
        ('B', '同业', '埃斯顿(002747)', '工业机器人+运动控制'),
        ('B', '同业', '中控技术(688777)', 'DCS/工业自动化'),
    ],
    'ROK': [
        ('B+', '同业', '汇川技术(300124)', 'PLC/伺服'),
        ('B', '同业', '中控技术(688777)', 'DCS/PLC'),
        ('B', '同业', '信捷电气(603416)', '小型PLC'),
    ],
    'FANUY': [
        ('B+', '同业', '埃斯顿(002747)', '工业机器人本体'),
        ('B', '上游', '汇川技术(300124)', '伺服电机核心零部件'),
        ('B', '上游', '绿的谐波(688017)', '谐波减速器,机器人关节核心'),
        ('B', '同业', '新时达(002527)', '工业机器人'),
    ],
    # === 生物科技 ===
    'AMGN': [
        ('B+', '同业', '百济神州(688235)', '创新药,全球化'),
        ('B', '同业', '恒瑞医药(600276)', '创新药龙头'),
        ('B', '配套', '药明康德(603259)', 'CRO/CDMO卖水人'),
    ],
    'GILD': [
        ('B', '同业', '恒瑞医药(600276)', '创新药'),
        ('B', '同业', '科伦药业(002422)', '创新药+仿制药'),
        ('B', '同业', '信达生物(1801.HK)', '创新药'),
        ('B', '配套', '药明康德(603259)', 'CRO/CDMO'),
    ],
    'VRTX': [
        ('B', '同业', '百济神州(688235)', '创新药'),
        ('B', '同业', '信达生物(1801.HK)', 'Biotech'),
        ('B', '配套', '凯莱英(002821)', 'CDMO'),
    ],
    'REGN': [
        ('B', '同业', '恒瑞医药(600276)', '抗体药物'),
        ('B', '同业', '康方生物(9926.HK)', '双抗创新药'),
        ('B', '配套', '药明生物(2269.HK)', '生物药CDMO'),
    ],
    # === 医疗器械 ===
    'MDT': [
        ('A', '同业', '迈瑞医疗(300760)', '综合器械'),
        ('B', '同业', '微创医疗(0853.HK)', '心血管器械'),
        ('B', '同业', '乐普医疗(300003)', '心血管植入'),
    ],
    'ABT': [
        ('B+', '同业', '迈瑞医疗(300760)', '监护/影像'),
        ('B', '同业', '万孚生物(300482)', 'POCT诊断'),
        ('B', '同业', '新产业(300832)', '化学发光'),
        ('B', '同业', '安图生物(603658)', '免疫诊断'),
    ],
    'SYK': [
        ('B+', '同业', '威高骨科(688161)', '骨科器械'),
        ('B', '同业', '大博医疗(002901)', '骨科植入'),
        ('B', '同业', '春立医疗(688236)', '关节假体'),
        ('B', '同业', '三友医疗(688085)', '脊柱植入'),
    ],
    # === 油气开采 ===
    'XOM': [
        ('A', '同业', '中国石油(601857)', '综合油气最对标'),
        ('B+', '同业', '中国海油(600938)', '上游开采'),
        ('B', '同业', '中国石化(600028)', '综合油气+炼化'),
    ],
    'CVX': [
        ('B+', '同业', '中国石油(601857)', '综合油气'),
        ('B', '同业', '中国石化(600028)', '炼化'),
        ('B', '同业', '中国海油(600938)', '上游'),
    ],
    'COP': [
        ('A', '同业', '中国海油(600938)', '纯上游开采'),
        ('B', '配套', '中海油服(601808)', '油田服务'),
        ('B', '同业', '中曼石油(603619)', '钻探服务'),
    ],
    'EOG': [
        ('B+', '同业', '中国海油(600938)', '上游开采'),
        ('B', '配套', '中海油服(601808)', '油田服务'),
        ('B', '同业', '中曼石油(603619)', '钻探'),
    ],
    # === 金矿 ===
    'NEM': [
        ('A', '同业', '山东黄金(600547)', '金矿,金价beta'),
        ('A', '同业', '紫金矿业(601899)', '金铜矿'),
        ('B+', '同业', '中金黄金(600489)', '黄金'),
        ('B', '同业', '赤峰黄金(600988)', '海外金矿'),
    ],
    'GOLD': [
        ('A', '同业', '紫金矿业(601899)', '多金属(金铜)对标Barrick'),
        ('A', '同业', '山东黄金(600547)', '金矿'),
        ('B+', '同业', '中金黄金(600489)', '黄金'),
        ('B', '同业', '银泰黄金(000975)', '黄金'),
    ],
    'AEM': [
        ('A', '同业', '山东黄金(600547)', '纯金矿'),
        ('B+', '同业', '中金黄金(600489)', '黄金'),
        ('B', '同业', '赤峰黄金(600988)', '黄金'),
    ],
    'WPM': [
        ('B', '同业', '紫金矿业(601899)', '多金属'),
        ('B', '同业', '山东黄金(600547)', '金价beta'),
        ('B', '同业', '银泰黄金(000975)', '黄金'),
    ],
    # === 铜矿 ===
    'FCX': [
        ('A', '同业', '紫金矿业(601899)', '全球化铜金矿'),
        ('B+', '同业', '洛阳钼业(603993)', '铜钴矿'),
        ('B', '同业', '西部矿业(601168)', '铜铅锌'),
        ('B', '同业', '铜陵有色(000630)', '铜矿+冶炼(注意冶炼弹性低)'),
    ],
    'SCCO': [
        ('A', '同业', '紫金矿业(601899)', '铜矿'),
        ('B', '同业', '西部矿业(601168)', '铜矿'),
        ('B', '同业', '云南铜业(000878)', '铜矿+冶炼'),
    ],
    'TECK': [
        ('B+', '同业', '洛阳钼业(603993)', '多金属矿(铜钴)'),
        ('B', '同业', '紫金矿业(601899)', '多金属'),
        ('B', '同业', '驰宏锌锗(600497)', '锌矿'),
    ],
    'HBM': [
        ('B+', '同业', '紫金矿业(601899)', '铜金矿'),
        ('B', '同业', '西部矿业(601168)', '铜矿'),
        ('B', '同业', '洛阳钼业(603993)', '铜钴'),
    ],
    # === 锂电池 ===
    'ALB': [
        ('A', '同业', '天齐锂业(002466)', '锂矿,锂价beta最大'),
        ('A', '同业', '赣锋锂业(002460)', '锂矿+电池'),
        ('B+', '下游', '宁德时代(300750)', '电池制造,锂价涨成本承压但量增'),
        ('B', '下游', '亿纬锂能(300014)', '电池制造'),
    ],
    'SQM': [
        ('A', '同业', '天齐锂业(002466)', 'SQM第二大股东'),
        ('B+', '同业', '赣锋锂业(002460)', '锂矿+加工'),
        ('B+', '下游', '宁德时代(300750)', '电池制造'),
        ('B', '下游', '亿纬锂能(300014)', '电池'),
    ],
    # === 铀矿/核能 ===
    'CCJ': [
        ('B+', '下游', '中国核电(601985)', '核电运营,铀价+电价'),
        ('B+', '下游', '中国广核(003816)', '核电运营'),
        ('B', '配套', '中国核建(601611)', '核电工程建设'),
        ('B', '配套', '兰石重装(603169)', '核电设备'),
    ],
    'UEC': [
        ('B', '下游', '中国核电(601985)', '核电运营'),
        ('B', '下游', '中国广核(003816)', '核电运营'),
        ('B', '配套', '中国核建(601611)', '核电建设'),
    ],
    'NXE': [
        ('B', '下游', '中国核电(601985)', '核电运营'),
        ('B', '下游', '中国广核(003816)', '核电运营'),
        ('B', '配套', '中国核建(601611)', '核电产业链'),
    ],
    'LEU': [
        ('B', '下游', '中国核电(601985)', '核电运营'),
        ('B', '下游', '中国广核(003816)', '核电运营'),
        ('B', '配套', '中国核建(601611)', '核电产业链'),
    ],
    # === 太阳能 ===
    'FSLR': [
        ('A', '同业', '隆基绿能(601012)', '组件龙头'),
        ('B+', '同业', '晶科能源(688223)', '组件'),
        ('B+', '同业', 'TCL中环(002129)', '硅片+组件'),
        ('B', '同业', '通威股份(600438)', '硅料+电池片'),
    ],
    'ENPH': [
        ('A', '同业', '阳光电源(300274)', '逆变器龙头'),
        ('B+', '同业', '锦浪科技(300763)', '组串式逆变器'),
        ('B', '同业', '固德威(688390)', '户用逆变器'),
        ('B', '同业', '德业股份(605117)', '微型逆变器'),
    ],
    'SEDG': [
        ('A', '同业', '阳光电源(300274)', '逆变器'),
        ('B+', '同业', '固德威(688390)', '逆变器'),
        ('B', '同业', '锦浪科技(300763)', '逆变器'),
    ],
    'RUN': [
        ('B', '下游', '正泰电器(601877)', '户用光伏/分布式'),
        ('B', '配套', '阳光电源(300274)', '逆变器'),
        ('B', '配套', '锦浪科技(300763)', '户用逆变器'),
    ],
    # === 军工航天 ===
    'LMT': [
        ('A', '同业', '中航沈飞(600760)', '战斗机'),
        ('B+', '上游', '航发动力(600893)', '航空发动机'),
        ('B', '配套', '中航光电(002179)', '航空连接器'),
        ('B', '同业', '洪都航空(600316)', '教练机/无人机'),
    ],
    'RTX': [
        ('B+', '同业', '航发动力(600893)', '航空发动机对标普惠'),
        ('B', '同业', '中航沈飞(600760)', '军机'),
        ('B', '配套', '中航光电(002179)', '连接器'),
        ('B', '配套', '航天电器(002025)', '军工连接器'),
    ],
    'NOC': [
        ('B', '同业', '航天电子(600879)', '航天电子'),
        ('B', '同业', '中航沈飞(600760)', '隐身军机'),
        ('B', '同业', '中国卫星(600118)', '卫星制造'),
        ('B', '配套', '中航光电(002179)', '连接器'),
    ],
    'GD': [
        ('B+', '同业', '中国船舶(600150)', '造船/军舰'),
        ('B', '同业', '中国重工(601989)', '军船/潜艇'),
        ('B', '同业', '中航沈飞(600760)', '军工'),
        ('B', '配套', '中国动力(600482)', '船用动力'),
    ],
    # === 住宅建筑 ===
    'DHI': [
        ('B', '同业', '保利发展(600048)', '房地产'),
        ('B', '配套', '北新建材(000786)', '石膏板'),
        ('B', '配套', '东方雨虹(002271)', '防水'),
        ('B', '配套', '伟星新材(002372)', '管道建材'),
    ],
    'LEN': [
        ('B', '同业', '保利发展(600048)', '房地产'),
        ('B', '同业', '万科A(000002)', '房地产'),
        ('B', '配套', '东方雨虹(002271)', '防水'),
        ('B', '配套', '三棵树(603737)', '涂料'),
    ],
    'NVR': [
        ('B', '同业', '保利发展(600048)', '房地产'),
        ('B', '配套', '北新建材(000786)', '建材'),
        ('B', '配套', '东方雨虹(002271)', '防水'),
    ],
    'PHM': [
        ('B', '同业', '保利发展(600048)', '房地产'),
        ('B', '配套', '东方雨虹(002271)', '防水'),
        ('B', '配套', '北新建材(000786)', '建材'),
    ],
    # === 零售 ===
    'AMZN': [
        ('A', '同业', '阿里巴巴(9988.HK)', '电商+云'),
        ('B+', '同业', '京东(9618.HK)', '自营电商+物流'),
        ('B', '配套', '顺丰控股(002352)', '物流'),
        ('B', '同业', '浪潮信息(000977)', '云计算基础设施(对标AWS)'),
    ],
    'WMT': [
        ('B', '同业', '永辉超市(601933)', '超市'),
        ('B', '同业', '高鑫零售(6808.HK)', '大卖场'),
        ('B', '同业', '家家悦(603708)', '区域超市'),
    ],
    'COST': [
        ('B', '同业', '永辉超市(601933)', '超市'),
        ('B', '同业', '名创优品(9896.HK)', '会员制零售理念交集'),
        ('B', '同业', '家家悦(603708)', '超市'),
    ],
    'TGT': [
        ('B', '同业', '永辉超市(601933)', '零售'),
        ('B', '同业', '王府井(600859)', '百货零售'),
        ('B', '同业', '家家悦(603708)', '区域零售'),
    ],
    # === 中概互联网 ===
    'BABA': [
        ('A', '同业', '阿里巴巴(9988.HK)', '同一公司港股'),
        ('B', '下游', '圆通速递(600233)', '物流配套'),
        ('B', '下游', '韵达股份(002120)', '快递物流'),
    ],
    'PDD': [
        ('B', '同业', '美团(3690.HK)', '中国互联网'),
        ('B', '下游', '中通快递(2057.HK)', '拼多多包裹物流'),
        ('B', '同业', '京东(9618.HK)', '电商竞争'),
    ],
    'JD': [
        ('A', '同业', '京东(9618.HK)', '同一公司港股'),
        ('B', '配套', '顺丰控股(002352)', '物流竞争'),
        ('B', '下游', '韵达股份(002120)', '快递物流'),
    ],
    'BIDU': [
        ('A', '同业', '百度(9888.HK)', '同一公司港股'),
        ('B', '同业', '科大讯飞(002230)', 'AI技术'),
        ('B', '同业', '金山办公(688111)', 'AI应用'),
    ],
    # === 光通信 ===
    'COHR': [
        ('A', '同业', '中际旭创(300308)', '800G光模块直接竞争'),
        ('A', '同业', '新易盛(300502)', '800G光模块'),
        ('B+', '上游', '天孚通信(300394)', '光无源器件'),
        ('B', '配套', '太辰光(300570)', 'MPO连接器'),
        ('B', '上游', '源杰科技(688498)', '光芯片'),
    ],
    'LITE': [
        ('A', '同业', '光迅科技(002281)', '光器件+模块,业务组成最相似'),
        ('B+', '上游', '天孚通信(300394)', '光无源器件'),
        ('B', '同业', '华工科技(000988)', '激光+光通信'),
        ('B', '上游', '光库科技(300620)', '光纤器件'),
    ],
    'CIEN': [
        ('B+', '同业', '中兴通讯(000063)', '网络设备,光传输'),
        ('B', '同业', '烽火通信(600498)', '光通信设备'),
        ('B', '同业', '华工科技(000988)', '光通信'),
    ],
    'VIAV': [
        ('B', '同业', '光库科技(300620)', '光学器件'),
        ('B', '同业', '天孚通信(300394)', '光无源器件'),
        ('B', '配套', '华工科技(000988)', '光通信'),
    ],
    # === AI算力 (NVDA/AMD/AVGO 复用半导体条目) ===
    'MRVL': [
        ('B', '同业', '澜起科技(688008)', '互连芯片,数据中心互联'),
        ('B', '配套', '中际旭创(300308)', '光模块,数据中心光互连'),
        ('B', '配套', '新易盛(300502)', '光模块'),
    ],
    # === AI应用 ===
    'PLTR': [
        ('B', '同业', '科大讯飞(002230)', 'AI应用'),
        ('B', '配套', '中科曙光(603019)', 'AI基础设施'),
        ('B', '同业', '太极股份(002368)', '政务IT/大数据'),
        ('B', '同业', '浪潮信息(000977)', 'AI服务器'),
    ],
    'SNOW': [
        ('B', '同业', '星环科技(688031)', '大数据平台'),
        ('B', '同业', '恒生电子(600570)', '数据平台'),
        ('B', '同业', '达梦数据(688692)', '数据库'),
    ],
    'DDOG': [
        ('B', '同业', '宝兰德(688058)', '中间件/运维'),
        ('B', '同业', '太极股份(002368)', 'IT运维'),
        ('B', '同业', '恒生电子(600570)', '金融IT'),
    ],
    'MDB': [
        ('B', '同业', '达梦数据(688692)', '国产数据库'),
        ('B', '同业', '海量数据(603138)', '数据库'),
        ('B', '同业', '星环科技(688031)', '大数据平台'),
    ],
    # === 存储/HBM ===
    'MU': [
        ('B', '同业', '兆易创新(603986)', 'NOR Flash/DRAM'),
        ('C+', '配套', '长电科技(600584)', '存储/HBM封装'),
        ('B', '同业', '北京君正(300223)', 'DRAM(收购ISSI)'),
        ('C', '同业', '东芯股份(688110)', 'NOR/NAND'),
    ],
    'WDC': [
        ('C+', '同业', '兆易创新(603986)', '存储芯片'),
        ('C', '同业', '德明利(001309)', '存储模组'),
        ('C', '同业', '北京君正(300223)', 'DRAM'),
    ],
    'STX': [
        ('C', '同业', '兆易创新(603986)', '存储概念'),
        ('C', '配套', '长电科技(600584)', '封装'),
        ('C', '同业', '德明利(001309)', '存储模组'),
    ],
    # === 新能源车 ===
    'TSLA': [
        ('A', '同业', '比亚迪(002594)', '新能源车龙头'),
        ('B+', '上游', '宁德时代(300750)', '电池'),
        ('B', '上游', '亿纬锂能(300014)', '电池'),
        ('B', '配套', '拓普集团(601689)', '底盘/热管理,特斯拉供应商'),
        ('B', '配套', '三花智控(002050)', '热管理,特斯拉供应链'),
    ],
    'RIVN': [
        ('B', '同业', '比亚迪(002594)', '新能源车'),
        ('B+', '上游', '宁德时代(300750)', '电池'),
        ('B', '同业', '长城汽车(601633)', '皮卡+新能源'),
    ],
    'LI': [
        ('A', '同业', '理想汽车(2015.HK)', '同一公司港股'),
        ('B+', '上游', '宁德时代(300750)', '电池'),
        ('B', '配套', '德赛西威(002920)', '智能座舱'),
        ('B', '同业', '长安汽车(000625)', '增程式竞争'),
    ],
    'NIO': [
        ('A', '同业', '蔚来(9866.HK)', '同一公司港股'),
        ('B+', '上游', '宁德时代(300750)', '电池'),
        ('B', '配套', '德赛西威(002920)', '智能座舱/自动驾驶'),
        ('B', '同业', '小鹏汽车(9868.HK)', '新势力竞争'),
    ],
}

# ============================================================
# 22 个子行业定义
# ============================================================
SUB_INDUSTRIES = {
    '半导体': {'tickers': ['NVDA', 'TSM', 'AVGO', 'AMD', 'QCOM']},
    '半导体设备': {'tickers': ['AMAT', 'LRCX', 'KLAC', 'ASML']},
    '软件/SaaS': {'tickers': ['MSFT', 'CRM', 'ORCL', 'ADBE']},
    '网络安全': {'tickers': ['CRWD', 'PANW', 'FTNT', 'ZS']},
    '机器人/自动化': {'tickers': ['ISRG', 'ABBNY', 'ROK', 'FANUY']},
    '生物科技': {'tickers': ['AMGN', 'GILD', 'VRTX', 'REGN']},
    '医疗器械': {'tickers': ['MDT', 'ABT', 'SYK', 'ISRG']},
    '油气开采': {'tickers': ['XOM', 'CVX', 'COP', 'EOG']},
    '金矿': {'tickers': ['NEM', 'GOLD', 'AEM', 'WPM']},
    '铜矿': {
        'tickers': ['FCX', 'SCCO', 'TECK', 'HBM'],
        'caveat': '只选矿商不选冶炼商,冶炼商赚加工费铜价弹性低',
    },
    '锂电池': {
        'tickers': ['ALB', 'SQM'],
        'caveat': 'LTHM已退市;锂价涨对电池制造商是成本压力',
    },
    '铀矿/核能': {
        'tickers': ['CCJ', 'UEC', 'NXE', 'LEU'],
        'caveat': 'A股无上市铀矿企业,仅核电运营商(下游),铀价传导间接',
    },
    '太阳能': {'tickers': ['FSLR', 'ENPH', 'SEDG', 'RUN']},
    '军工航天': {'tickers': ['LMT', 'RTX', 'NOC', 'GD']},
    '住宅建筑': {
        'tickers': ['DHI', 'LEN', 'NVR', 'PHM'],
        'caveat': '美国住宅建筑与A股地产周期完全脱钩,映射传导极弱',
    },
    '零售': {
        'tickers': ['AMZN', 'WMT', 'COST', 'TGT'],
        'caveat': '中美零售驱动力差异大',
    },
    '中概互联网': {
        'tickers': ['BABA', 'PDD', 'JD', 'BIDU'],
        'caveat': '中概港股上市的是同一批公司',
    },
    '光通信': {'tickers': ['COHR', 'LITE', 'CIEN', 'VIAV']},
    'AI算力': {
        'tickers': ['NVDA', 'AMD', 'AVGO', 'MRVL'],
        'caveat': '美股涨因全球AI订单,A股涨因国产替代叙事,驱动力不同',
    },
    'AI应用': {
        'tickers': ['PLTR', 'SNOW', 'DDOG', 'MDB'],
        'caveat': '中美SaaS模式差异极大',
    },
    '存储/HBM': {
        'tickers': ['MU', 'WDC', 'STX'],
        'caveat': 'A股无HBM直接对标,仅弱关联',
    },
    '新能源车': {'tickers': ['TSLA', 'RIVN', 'LI', 'NIO']},
}


# ============================================================
# 工具函数
# ============================================================

def fetch(url, timeout=15):
    try:
        req = urllib.request.Request(url, headers={
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
        })
        resp = urllib.request.urlopen(req, timeout=timeout)
        return resp.read()
    except Exception:
        return None


def fetch_yahoo_chart(ticker, days=30):
    """从 Yahoo Finance 获取K线数据。"""
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
        return {'price': price, 'closes': closes, 'volumes': volumes}
    except Exception:
        return None


def calc_metrics(closes, volumes):
    """计算今日涨跌%、5日涨跌%、5日趋势、量比、综合得分。"""
    if len(closes) < 2:
        return None
    pct_1d = (closes[-1] / closes[-2] - 1) * 100
    pct_5d = 0
    trend5 = ''
    if len(closes) >= 6:
        pct_5d = (closes[-1] / closes[-6] - 1) * 100
        changes = [closes[i] / closes[i - 1] - 1 for i in range(max(1, len(closes) - 5), len(closes))]
        trend5 = ''.join(['↑' if c > 0 else '↓' for c in changes])
    vol_ratio = 0
    if len(volumes) >= 20 and volumes[-1]:
        avg_vol = sum(volumes[-20:]) / 20
        vol_ratio = volumes[-1] / avg_vol if avg_vol > 0 else 0
    score = pct_5d * 0.6 + pct_1d * 0.4
    return {
        'pct_1d': pct_1d, 'pct_5d': pct_5d, 'trend5': trend5,
        'vol_ratio': vol_ratio, 'score': score,
    }


def extract_stock_code(name_str):
    """从 '中际旭创(300308)' 提取 A 股代码，返回 'sz300308' 格式。港股返回 None。"""
    m = re.search(r'\((\d{6})\)', name_str)
    if not m:
        return None
    code = m.group(1)
    return f'sh{code}' if code.startswith('6') else f'sz{code}'


def fetch_a_share_prices():
    """批量获取 A 股实时行情（预留，当前未调用）。"""
    codes = set()
    for info in US_STOCK_MAP.values():
        for _, _, name, _ in info:
            code = extract_stock_code(name)
            if code:
                codes.add(code)
    if not codes:
        return {}
    code_str = ','.join(sorted(codes))
    try:
        req = urllib.request.Request(
            f'https://hq.sinajs.cn/list={code_str}',
            headers={
                'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)',
                'Referer': 'https://finance.sina.com.cn',
            }
        )
        resp = urllib.request.urlopen(req, timeout=10)
        raw = resp.read()
    except Exception:
        return {}
    results = {}
    text = raw.decode('gbk', errors='replace')
    for line in text.strip().split('\n'):
        if '=' not in line or '"' not in line:
            continue
        code_part = line.split('=')[0].replace('var hq_str_', '').strip()
        data_str = line.split('"')[1]
        parts = data_str.split(',')
        if len(parts) >= 4 and parts[2] and parts[3]:
            try:
                yesterday = float(parts[2])
                current = float(parts[3])
                if yesterday > 0 and current > 0:
                    pct = (current / yesterday - 1) * 100
                    results[code_part] = {'price': current, 'pct': pct}
            except ValueError:
                pass
    return results


# ============================================================
# 扫描逻辑
# ============================================================

def scan_all():
    """并行拉取所有 ticker，按子行业分组计算排名。"""
    # 1. 收集所有 unique tickers
    all_tickers = set()
    for info in SUB_INDUSTRIES.values():
        for t in info['tickers']:
            all_tickers.add(t)

    total = len(all_tickers)
    print(f"  共 {total} 个标的，并行拉取中...")

    # 2. 并行拉取
    ticker_data = {}
    done_count = [0]
    def _fetch_one(ticker):
        result = fetch_yahoo_chart(ticker)
        done_count[0] += 1
        status = '✓' if (result and len(result.get('closes', [])) >= 2) else '✗'
        print(f"  [{done_count[0]:2d}/{total}] {ticker:6s} {status}", flush=True)
        return ticker, result

    with ThreadPoolExecutor(max_workers=10) as pool:
        futures = [pool.submit(_fetch_one, t) for t in sorted(all_tickers)]
        for future in as_completed(futures):
            ticker, data = future.result()
            ticker_data[ticker] = data

    # 3. 计算每个 ticker 的指标
    ticker_metrics = {}
    for ticker, data in ticker_data.items():
        if data and len(data.get('closes', [])) >= 2:
            m = calc_metrics(data['closes'], data['volumes'])
            if m:
                ticker_metrics[ticker] = m

    # 4. 按子行业分组
    results = []
    for name, info in SUB_INDUSTRIES.items():
        stocks = []
        for ticker in info['tickers']:
            if ticker in ticker_metrics:
                stocks.append({
                    'ticker': ticker,
                    'a_shares': US_STOCK_MAP.get(ticker, []),
                    **ticker_metrics[ticker],
                })
        if not stocks:
            continue
        stocks.sort(key=lambda x: x['score'], reverse=True)
        avg_score = sum(s['score'] for s in stocks) / len(stocks)
        results.append({
            'name': name,
            'stocks': stocks,
            'avg_score': avg_score,
            'caveat': info.get('caveat'),
        })

    results.sort(key=lambda x: x['avg_score'], reverse=True)
    return results


# ============================================================
# 报告生成
# ============================================================

def format_a_shares(a_shares, indent='  '):
    """格式化 A 股映射列表。"""
    return '\n'.join(f"{indent}- [{g}|{c}] {n} — {l}" for g, c, n, l in a_shares)


def print_terminal_report(ranked):
    """终端输出排名报告。"""
    print("\n" + "=" * 60)
    print(f"子行业强弱排名（共 {len(ranked)} 个）")
    print("映射: [A]=收入直接对标 [B]=同赛道间接 [C]=仅概念")
    print("产业链: 同业=直接竞争 上游=供应商 下游=客户 配套=卖水人")
    print("=" * 60)

    for i, r in enumerate(ranked, 1):
        print(f"\n  {i:2d}. {r['name']} (综合: {r['avg_score']:+.2f}%)")
        if r.get('caveat'):
            print(f"      ⚠ {r['caveat']}")
        for s in r['stocks']:
            vol_str = f" 量比:{s['vol_ratio']:.1f}" if s['vol_ratio'] > 0 else ''
            print(f"    {s['ticker']:6s} {s['pct_1d']:+6.2f}% | 5日:{s['pct_5d']:+6.1f}% {s['trend5']}{vol_str}")
            for g, c, n, l in s['a_shares']:
                print(f"      [{g:2s}|{c}] {n} — {l}")


def build_dingtalk_report(ranked, date):
    """构建钉钉 Markdown 报告。"""
    unique_tickers = set()
    for r in ranked:
        for s in r['stocks']:
            unique_tickers.add(s['ticker'])

    lines = []
    lines.append(f"# 美股子行业强弱 + A股映射 — {date}\n")
    lines.append(f"共扫描 {len(ranked)} 个子行业 {len(unique_tickers)} 个标的")
    lines.append("映射: [A]=收入直接对标 [B]=同赛道间接 [C]=仅概念")
    lines.append("产业链: 同业/上游/下游/配套\n")

    # TOP 10
    lines.append("## 强势 TOP10\n")
    for i, r in enumerate(ranked[:10], 1):
        lines.append(f"**{i}. {r['name']}** (综合: {r['avg_score']:+.1f}%)\n")
        for j, s in enumerate(r['stocks']):
            vol_str = f" 量比:{s['vol_ratio']:.1f}" if s['vol_ratio'] > 0 else ''
            if j < 2:
                # 前 2 只领涨股展开 A 股映射
                lines.append(
                    f"- **{s['ticker']}** {s['pct_1d']:+.2f}% | "
                    f"5日: {s['trend5']} ({s['pct_5d']:+.1f}%){vol_str}"
                )
                lines.append(format_a_shares(s['a_shares'], indent='  '))
            else:
                lines.append(
                    f"- {s['ticker']} {s['pct_1d']:+.2f}% | "
                    f"5日: {s['trend5']} ({s['pct_5d']:+.1f}%)"
                )
        if r.get('caveat'):
            lines.append(f"\n> ⚠️ {r['caveat']}")
        lines.append("")

    # BOTTOM 5
    lines.append("## 弱势 BOTTOM5\n")
    for i, r in enumerate(ranked[-5:], 1):
        stock_str = ' '.join(f"{s['ticker']}:{s['pct_1d']:+.1f}%" for s in r['stocks'])
        lines.append(f"**{i}. {r['name']}** | 综合: {r['avg_score']:+.1f}% | {stock_str}")

    lines.append("\n---")
    lines.append("> 映射四原则: 收入来源对齐 > 利润驱动力对齐 > 产业链位置 > 弹性位置")
    lines.append("> 免责声明: 仅供参考，不构成投资建议。")
    return "\n".join(lines)


# ============================================================
# 钉钉推送
# ============================================================

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


# ============================================================
# 主流程
# ============================================================

def main():
    no_push = '--no-push' in sys.argv
    today = datetime.now().strftime("%Y-%m-%d")

    print(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] 子行业扫描 V2 启动")
    print("=" * 60)

    print("\n【1】并行扫描所有标的")
    ranked = scan_all()

    if not ranked:
        print("[SKIP] 未获取到数据，跳过")
        return

    print_terminal_report(ranked)

    if not no_push:
        print("\n推送到钉钉...")
        report = build_dingtalk_report(ranked, today)
        send_dingtalk(f"美股子行业扫描 {today}", report)

    print(f"\n[DONE] 完成")


if __name__ == "__main__":
    main()
