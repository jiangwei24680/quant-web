# -*- coding: utf-8 -*-
"""
gen_webdata.py —— 从 quant.db 生成网站数据 data/latest.json（只用公开全市场数据，
不含任何个人持仓/成本信息，可安全推送到公开仓库供 Cloudflare Pages 部署）。

用法: python3 gen_webdata.py [--db ~/workspace/quantdb/quant.db] [--date YYYY-MM-DD] [--out data]
默认取库中最新的交易日。
"""
import os, sys, json, sqlite3, argparse, time, urllib.request

DEFAULT_DB = os.path.expanduser('~/workspace/quantdb/quant.db')
UA = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
SLIST_HOSTS = ['push2.eastmoney.com', '82.push2.eastmoney.com']
# 非题材类板块过滤：指数成分、通道类、地域板块、风格/业绩标签不算影响涨跌的概念
_SKIP_SUB = ('融资融券', '沪股通', '深股通', '港股通', 'MSCI', '富时', '标普', '转融券', '季报', '年报',
             '中证', '深成', '上证', '深证', '沪深', 'GDR', '创业板', '科创板')


def _get_json(url, hosts=None):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read().decode('utf-8'))



def _interp(x, anchors):
    if x <= anchors[0][0]:
        return anchors[0][1]
    if x >= anchors[-1][0]:
        return anchors[-1][1]
    for (x0, y0), (x1, y1) in zip(anchors, anchors[1:]):
        if x0 <= x <= x1:
            return y0 + (y1 - y0) * (x - x0) / (x1 - x0)
    return anchors[-1][1]


_POSITION_REF = {
    '高潮': '两极分化：减仓兑现（心法第46/58条）',
    '主升': '主升期重仓，去弱留强、仓位向龙头集中（心法第46/58条）',
    '启动': '新周期启动：半仓到七八成（心法第58条）',
    '混沌': '混沌期不超过三四成（心法第58条）',
    '低迷': '弱市少做：不超过一两成（心法第39/58条）',
    '退潮': '退潮防御：降到一成或空仓（心法第51/52/53条）',
    '冰点': '冰点控仓，寻找新猎物（心法第46条）',
}


def _load_xinfa():
    p = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'xinfa_lines.json')
    try:
        return json.load(open(p, encoding='utf-8'))
    except Exception:
        return []


def compute_sentiment(conn, day, ladder, total, up, state_path):
    """情绪周期（按游资心法口径机械计算）：涨停热度25+连板高度20+赚钱效应30+市场广度25，
    跌停压力最多扣20。赚钱效应=昨日涨停股今日平均涨幅，靠 sentiment_state.json 跨日积累。"""
    import datetime as _dt
    zt = ladder.get('zt') or 0
    dt = ladder.get('dt') or 0
    zt_list = ladder.get('zt_list') or []
    max_boards = max([z.get('boards') or 1 for z in zt_list], default=0)
    lianban = sum(1 for z in zt_list if (z.get('boards') or 1) >= 2)
    effect = None
    leader = None
    retreat = None
    try:
        st = json.load(open(state_path, encoding='utf-8'))
    except Exception:
        st = None
    if st and st.get('date') and st['date'] < day and st.get('zt'):
        prev = st['zt']
        codes = [z['code'] for z in prev]
        q = ','.join('?' * len(codes))
        rows = dict(conn.execute(
            'SELECT code, pct_chg FROM daily_bar WHERE date=? AND code IN (%s)' % q,
            [day] + codes).fetchall())
        pcts = [rows[c] for c in codes if c in rows and rows[c] is not None]
        if pcts:
            avg = sum(pcts) / len(pcts)
            red = sum(1 for p in pcts if p > 0) / len(pcts)
            pmax = max(z.get('boards') or 1 for z in prev)
            lead_codes = [z['code'] for z in prev if (z.get('boards') or 1) == pmax]
            lead_pct = rows.get(lead_codes[0]) if lead_codes else None
            m = conn.execute('SELECT name FROM stock_meta WHERE code=?',
                             (lead_codes[0],)).fetchone() if lead_codes else None
            leader = {'code': lead_codes[0], 'name': (m[0] if m else lead_codes[0]),
                      'boards': pmax, 'pct': lead_pct}
            effect = {'n': len(pcts), 'avg_pct': round(avg, 2), 'red_ratio': round(red, 3)}
            if lead_pct is not None and lead_pct <= -9:
                retreat = '昨日总龙头 %s 今日 %.2f%%（核按钮，心法第51条）' % (leader['name'], lead_pct)
            elif avg <= -3 and dt >= max(10, zt // 2):
                retreat = '昨日涨停股今日平均 %.2f%%，亏钱效应扩散' % avg
    p_zt = round(min(25, zt * 25 / 90))
    p_bd = round(min(20, max_boards * 20 / 8))
    p_br = round(min(25, (up / total) * 25 / 0.7)) if total else 0
    p_ef = round(_interp(effect['avg_pct'],
                         [(-3, 0), (-2, 5), (-1, 9), (0, 14), (1, 19), (2, 24), (4, 30)])) if effect else None
    pen = round(min(20, dt * 20 / 40))
    got = p_zt + p_bd + p_br - pen + (p_ef or 0)
    mx = 75 + (30 if effect else 0)
    score = max(0, min(100, round(got / mx * 100))) if mx else 0
    if retreat:
        stage = '退潮'
    elif score >= 80:
        stage = '高潮'
    elif score >= 65:
        stage = '主升'
    elif score >= 50:
        stage = '启动'
    elif score >= 35:
        stage = '混沌'
    elif score >= 20:
        stage = '低迷'
    else:
        stage = '冰点'
    lines = _load_xinfa()
    xinfa = lines[_dt.date.fromisoformat(day).toordinal() % len(lines)] if lines else None
    sent = {'score': score, 'stage': stage,
            'parts': {'zt': p_zt, 'boards': p_bd, 'effect': p_ef, 'breadth': p_br, 'dt_penalty': -pen},
            'facts': {'zt': zt, 'dt': dt, 'max_boards': max_boards, 'lianban': lianban,
                      'effect_avg': effect['avg_pct'] if effect else None,
                      'effect_red': effect['red_ratio'] if effect else None,
                      'leader': leader},
            'retreat': retreat,
            'position_ref': _POSITION_REF.get(stage, ''),
            'xinfa': xinfa}
    try:
        with open(state_path, 'w', encoding='utf-8') as f:
            json.dump({'date': day,
                       'zt': [{'code': z['code'], 'boards': z.get('boards') or 1} for z in zt_list]},
                      f, ensure_ascii=False)
    except Exception as e:
        print('情绪状态保存失败：%s' % e)
    return sent


def fetch_ladder(day):
    """涨停/跌停池 + 连板梯队（按连板数分组，取 >=2 板）。day: YYYY-MM-DD"""
    d8 = day.replace('-', '')
    base = 'https://push2ex.eastmoney.com/%s?ut=7eea3edcaed734bea9cbfc24409ed989&dpt=wz.ztzt&Pageindex=0&pagesize=300&sort=fbt:asc&date=%s'
    out = {'zt': 0, 'dt': 0, 'groups': [], 'zt_list': [], 'dt_list': []}
    try:
        d = _get_json(base % ('getTopicZTPool', d8))
        data = d.get('data') or {}
        out['zt'] = data.get('tc') or 0
        groups = {}
        for x in data.get('pool') or []:
            lbc = x.get('lbc') or 1
            out['zt_list'].append({'code': x.get('c'), 'name': x.get('n'),
                                   'pct': x.get('zdp'), 'boards': lbc})
            if lbc >= 2:
                groups.setdefault(lbc, []).append({'code': x.get('c'), 'name': x.get('n'), 'ind': x.get('hybk') or ''})
        out['groups'] = [{'boards': k, 'stocks': groups[k]} for k in sorted(groups, reverse=True)]
    except Exception as e:
        print('涨停池拉取失败：%s' % e)
    try:
        d = _get_json(base % ('getTopicDTPool', d8))
        data = d.get('data') or {}
        out['dt'] = data.get('tc') or 0
        for x in data.get('pool') or []:
            out['dt_list'].append({'code': x.get('c'), 'name': x.get('n'), 'pct': x.get('zdp')})
    except Exception as e:
        print('跌停池拉取失败：%s' % e)
    return out


def fetch_concepts(code, stock_pct):
    """取个股所属题材板块，按与个股涨跌同向的强弱取前 2：涨股取最强题材、跌股取最弱题材。"""
    secid = ('1.' if code[0] in '69' else '0.') + code
    tpl = ('https://{host}/api/qt/slist/get?spt=3&fltt=2&invt=2&pn=1&pz=100&po=1'
           '&fields=f12,f14,f3&secid=%s') % secid
    rows = None
    for rnd in range(2):
        for h in SLIST_HOSTS:
            try:
                req = urllib.request.Request(tpl.format(host=h), headers=UA)
                with urllib.request.urlopen(req, timeout=12) as r:
                    d = json.loads(r.read().decode('utf-8'))
                diff = (d.get('data') or {}).get('diff') or {}
                rows = list(diff.values()) if isinstance(diff, dict) else diff
                break
            except Exception:
                time.sleep(1 + rnd)
        if rows is not None:
            break
    if not rows:
        return []
    boards = []
    for x in rows:
        name = x.get('f14') or ''
        pct = x.get('f3')
        if not name or not isinstance(pct, (int, float)):
            continue
        if name.endswith('板块') or name.endswith('股') or '_' in name or any(s in name for s in _SKIP_SUB):
            continue
        boards.append({'name': name, 'pct': round(pct, 2)})
    boards.sort(key=lambda b: -b['pct'] if (stock_pct or 0) >= 0 else b['pct'])
    return boards[:2]


def fetch_watch(conn, day):
    """观察名单当日事实：价/涨跌/主力净流入取自 quant.db，换手/市盈率一次 ulist 补齐。"""
    cfg = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'watchlist.json')
    try:
        codes = [w['code'] for w in json.load(open(cfg, encoding='utf-8'))]
    except Exception as e:
        print('观察名单读取失败：%s' % e)
        return []
    extra = {}
    try:
        secids = ','.join(('1.' if c[0] in '69' else '0.') + c for c in codes)
        url = ('https://push2.eastmoney.com/api/qt/ulist.np/get?fltt=2&invt=2'
               '&fields=f8,f9,f12&secids=%s') % secids
        d = _get_json(url)
        diff = (d.get('data') or {}).get('diff') or {}
        rows = list(diff.values()) if isinstance(diff, dict) else diff
        for x in rows:
            extra[x.get('f12')] = {'turnover': x.get('f8'), 'pe': x.get('f9')}
    except Exception as e:
        print('观察名单换手/PE拉取失败：%s' % e)
    out = []
    for code in codes:
        r = conn.execute('SELECT close, pct_chg FROM daily_bar WHERE code=? AND date=?',
                         (code, day)).fetchone()
        if not r:
            continue
        m = conn.execute('SELECT name FROM stock_meta WHERE code=?', (code,)).fetchone()
        f = conn.execute('SELECT main_net FROM fund_flow_daily WHERE code=? AND date=?',
                         (code, day)).fetchone()
        it = {'code': code, 'name': (m[0] if m else code),
              'price': round(r[0], 2) if r[0] else None,
              'pct': round(r[1], 2) if r[1] is not None else None,
              'main_net': int(f[0]) if f and f[0] is not None else None}
        it.update(extra.get(code, {}))
        it['concepts'] = fetch_concepts(code, it['pct'])
        out.append(it)
    return out


def _board_of(code, name):
    """按代码前缀分板块并给出涨停幅度（%）：创业板 30 开头是 20cm，单独识别。"""
    if code.startswith('30'):
        return '创业板', 20.0
    if code.startswith('68'):
        return '科创板', 20.0
    if code.startswith('4') or code.startswith('8') or code.startswith('920'):
        return '北交所', 30.0
    if 'ST' in (name or '').upper():
        return '主板', 5.0
    return '主板', 10.0


def compute_radar(conn, day):
    """全市场雷达（Excel finally.xls 雷达的网页版，数据源换成 quant.db）：
    扫最新一日全市场，满足任一信号即入榜——
      逼近涨停：涨幅 >= 涨停幅-0.5（主板 9.5 / 创业板·科创板 19 / 北交所 29，ST 主板 4.5）
      涨幅达标：主板 >=5%、创业板/科创板 >=10%、北交所 >=15%
      放量上涨：量比 >=2 且涨幅为正
      主力抢筹：主力净流入居全市场前 30 且涨幅为正
    量比口径：当日成交量 / 近 5 个交易日（不含当日）平均成交量。东财量比的分母是
    近 5 日每分钟均量折算值，盘后用日量均值近似，量级可比、数值不完全等同；
    历史不足 5 日的股票量比为空，只能靠涨幅/资金信号入榜。
    排序按信号强度：逼近涨停 > 涨幅达标 > 放量上涨 > 主力抢筹，同级按涨幅降序。
    总量 <=50 条；创业板（30 开头）单独保名额：当日触发信号的全部列入（上限 30）。"""
    rows = conn.execute(
        """SELECT b.code, m.name, b.pct_chg, b.volume, b.turnover, f.main_net
           FROM daily_bar b
           LEFT JOIN stock_meta m ON b.code = m.code
           LEFT JOIN fund_flow_daily f ON b.code = f.code AND f.date = b.date
           WHERE b.date = ? AND b.pct_chg IS NOT NULL""", (day,)).fetchall()
    top_money = {r[0] for r in conn.execute(
        """SELECT code FROM fund_flow_daily
           WHERE date = ? AND main_net > 0 ORDER BY main_net DESC LIMIT 30""", (day,))}
    gain_thr = {5.0: 5.0, 10.0: 5.0, 20.0: 10.0, 30.0: 15.0}
    hits = []
    for code, name, pct, vol, turnover, net in rows:
        name = name or code
        board, lim = _board_of(code, name)
        near = pct >= lim - 0.5
        gain = pct >= gain_thr[lim]
        vr = None
        if pct > 0:
            prev = [r[0] for r in conn.execute(
                """SELECT volume FROM daily_bar
                   WHERE code = ? AND date < ? AND volume > 0
                   ORDER BY date DESC LIMIT 5""", (code, day))]
            if prev and vol:
                vr = vol / (sum(prev) / len(prev))
        vol_sig = vr is not None and vr >= 2 and pct > 0
        money_sig = code in top_money and pct > 0
        if not (near or gain or vol_sig or money_sig):
            continue
        signals = []
        if near:
            signals.append('逼近涨停')
        if gain:
            signals.append('涨幅达标')
        if vol_sig:
            signals.append('放量上涨')
        if money_sig:
            signals.append('主力抢筹')
        hits.append({'code': code, 'name': name, 'board': board,
                     'pct': round(pct, 2),
                     'vol_ratio': round(vr, 2) if vr is not None else None,
                     'main_net': int(net) if net is not None else None,
                     'turnover': round(turnover, 2) if turnover is not None else None,
                     'signals': signals, 'near_limit': bool(near)})

    def strength(r):
        grp = 0 if r['near_limit'] else (1 if '涨幅达标' in r['signals']
              else (2 if '放量上涨' in r['signals'] else 3))
        return (grp, -r['pct'])

    hits.sort(key=strength)
    gem = [r for r in hits if r['board'] == '创业板'][:30]
    gem_codes = {r['code'] for r in gem}
    rest = [r for r in hits if r['code'] not in gem_codes]
    lst = sorted(gem + rest[:max(0, 50 - len(gem))], key=strength)[:50]
    return {'date': day, 'list': lst, 'gem_list': gem}


_OVERSOLD_WARMUP = 30    # 与回测一致：DMA 预热 30 个交易日后才出信号
_OVERSOLD_MIN_HIST = 40  # 样本门槛：历史 >=40 个交易日


def _oversold_signals(rows):
    """复刻回测脚本 backtest_gaoyuan.py 的 compute_signals 口径（通达信语义、全程因果）：
    返回 (A, C, dma) 三个与 rows 等长的序列——
    A = 甲 AND 乙；甲：收盘低于量加权成本线 DMA(典型价, VOL/近13日量近似) 17% 以上；
        乙：(C - MIN(REF(C,5)*0.83, REF(C,21)*0.72))/C < 0.05（近5日跌17%/近21日跌28% 后贴近极值）；
    C = A AND 丙（磨底）：CAPITAL 由换手率反推（流通股本 = 成交量/(换手率/100)，
        回测已用茅台校验），最近 8 日内「贴换手周期低点」（收盘为过去一个换手周期内最低收盘）天数 > 3。
    rows: [(date, open, high, low, close, volume, amount, turnover), ...] 按日期升序。"""
    n = len(rows)
    O = [r[1] for r in rows]; H = [r[2] for r in rows]; L = [r[3] for r in rows]
    C = [r[4] for r in rows]; V = [r[5] for r in rows]; AMT = [r[6] for r in rows]
    TO = [r[7] for r in rows]
    X = [(O[i] + H[i] + L[i] + C[i]) / 4.0 for i in range(n)]
    # 新浪/腾讯回填的历史行 amount 可能为 NULL：用 量×典型价 近似补齐，避免 DMA 累加时崩溃
    AMT = [AMT[i] if AMT[i] is not None else (V[i] or 0) * X[i] for i in range(n)]

    dma = [None] * n
    amt13 = 0.0
    y = None
    for i in range(n):
        amt13 += AMT[i]
        if i >= 13:
            amt13 -= AMT[i - 13]
        if i >= 12 and V[i] and AMT[i]:
            avg_price = AMT[i] / V[i]              # 元/股
            nsyj6 = amt13 / avg_price              # 近13日成交量（股，当日均价折算）
            a = V[i] / nsyj6 if nsyj6 > 0 else 0.0
            a = min(max(a, 0.0), 1.0)
            y = X[i] if y is None else a * X[i] + (1 - a) * y
            dma[i] = y
        elif y is not None:
            dma[i] = y

    at_low = [False] * n
    for i in range(n):
        if not TO[i] or TO[i] <= 0 or not V[i]:
            continue
        capital = V[i] / (TO[i] / 100.0)           # 流通股本（股）
        s, k = 0.0, 0
        while i - k >= 0 and s < capital:
            s += V[i - k]; k += 1
        if s < capital:
            continue                               # 历史不足，NSYJ2 不可判
        win = C[i - k + 1:i + 1]
        at_low[i] = C[i] <= min(win)

    A = [False] * n
    Cc = [False] * n
    for i in range(n):
        if i < _OVERSOLD_WARMUP or dma[i] is None or i < 21:
            continue
        jia = (C[i] - dma[i]) / dma[i] * 100.0 < -17.0
        if not jia:
            continue
        yi = (C[i] - min(C[i - 5] * 0.83, C[i - 21] * 0.72)) / C[i] < 0.05
        if not yi:
            continue
        A[i] = True
        Cc[i] = sum(1 for j in range(max(0, i - 7), i + 1) if at_low[j]) > 3
    return A, Cc, dma


def compute_oversold(conn, day):
    """超跌观察名单（「高远综合抄底」原公式全条件 = 回测变体C，仅作观察标记，不进选股评分）。
    事件 = 甲&乙&丙 首次触发（前一日不成立）后 5 个交易日内首次收阳（C>O）确认，以确认日为信号日；
    同一股票 20 个交易日内重复事件只记第一次（与回测去重口径一致）。
    返回「当日处于确认状态」的名单：确认日在最近 5 个交易日内（确认后未超过 5 个交易日，
    按该股自身交易日序列计）。纯 quant.db 计算，不依赖任何外部接口；
    样本为历史 >=40 个交易日、且当日有行情的股票，日期 <= day。"""
    codes = [r[0] for r in conn.execute(
        'SELECT code FROM daily_bar WHERE date<=? GROUP BY code HAVING COUNT(*)>=?',
        (day, _OVERSOLD_MIN_HIST))]
    names = dict(conn.execute('SELECT code, name FROM stock_meta').fetchall())
    out = []
    for code in codes:
        rows = conn.execute(
            'SELECT date,open,high,low,close,volume,amount,turnover,pct_chg FROM daily_bar '
            'WHERE code=? AND date<=? ORDER BY date', (code, day)).fetchall()
        if not rows or rows[-1][0] != day:
            continue                               # 当日无行情（停牌等），无当日涨幅可报
        idx_day = len(rows) - 1
        _, Cc, dma = _oversold_signals([(r[0], r[1], r[2], r[3], r[4], r[5], r[6], r[7]) for r in rows])
        # 首次触发 -> 5 个交易日内阳线确认（复刻回测 first_triggers + confirm_events）
        pairs = []                                 # (confirm_idx, trigger_idx)
        for f in range(_OVERSOLD_WARMUP + 1, len(rows)):
            if Cc[f] and not Cc[f - 1]:
                for j in range(f, min(f + 5, len(rows))):
                    if rows[j][4] > rows[j][1]:    # C > O 收阳
                        pairs.append((j, f))
                        break
        pairs.sort()
        kept = []
        for j, f in pairs:                         # 去重：同股 20 个交易日内只计第一次
            if not kept or j - kept[-1][0] >= 20:
                kept.append((j, f))
        for j, f in kept:
            if 0 <= idx_day - j <= 5:              # 确认后未超过 5 个交易日，仍在观察窗
                name = names.get(code) or code
                board, _lim = _board_of(code, name)
                c_day = rows[idx_day][4]
                dev = (c_day - dma[idx_day]) / dma[idx_day] * 100.0 if dma[idx_day] else None
                base21 = rows[idx_day - 21][4] if idx_day >= 21 else None
                ret21 = (c_day / base21 - 1) * 100.0 if base21 else None
                pct = rows[idx_day][8]
                out.append({'code': code, 'name': name, 'board': board,
                            'pct': round(pct, 2) if pct is not None else None,
                            'dev_cost': round(dev, 2) if dev is not None else None,
                            'ret21': round(ret21, 2) if ret21 is not None else None,
                            'signal_date': rows[f][0], 'confirm_date': rows[j][0]})
                break
    out.sort(key=lambda r: r['confirm_date'], reverse=True)
    return out[:30]


def _log_oversold(day, items):
    """当日超跌观察名单追加留底到本地文件（同一日期只记一次），为将来攒够样本复测备查；
    该文件只在本机，不进公开仓库。"""
    path = os.path.expanduser('~/workspace/goals/goal-5/hidden_files/oversold_log.jsonl')
    try:
        if os.path.exists(path):
            with open(path, encoding='utf-8') as f:
                for line in f:
                    try:
                        if json.loads(line).get('date') == day:
                            print('超跌观察留底：%s 已记录，跳过' % day)
                            return
                    except Exception:
                        continue
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'a', encoding='utf-8') as f:
            f.write(json.dumps({'date': day, 'items': items}, ensure_ascii=False) + '\n')
        print('超跌观察留底：已记入 %s（%s，%d 条）' % (path, day, len(items)))
    except Exception as e:
        print('超跌观察留底失败：%s' % e)


def pick_date(conn, arg):
    if arg:
        return arg
    return conn.execute('SELECT MAX(date) FROM daily_bar').fetchone()[0]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--db', default=DEFAULT_DB)
    ap.add_argument('--date', default=None)
    ap.add_argument('--out', default=os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data'))
    args = ap.parse_args()

    conn = sqlite3.connect(args.db)
    day = pick_date(conn, args.date)

    total = conn.execute('SELECT COUNT(*) FROM daily_bar WHERE date=?', (day,)).fetchone()[0]
    up = conn.execute("SELECT COUNT(*) FROM daily_bar WHERE date=? AND pct_chg > 0", (day,)).fetchone()[0]
    down = conn.execute("SELECT COUNT(*) FROM daily_bar WHERE date=? AND pct_chg < 0", (day,)).fetchone()[0]
    flat = total - up - down

    def top(order, n=20):
        cur = conn.execute(
            """SELECT b.code, m.name, b.close, b.pct_chg, f.main_net
               FROM daily_bar b
               LEFT JOIN stock_meta m ON b.code = m.code
               LEFT JOIN fund_flow_daily f ON b.code = f.code AND f.date = b.date
               WHERE b.date = ? AND f.main_net IS NOT NULL
               ORDER BY f.main_net %s LIMIT ?""" % order, (day, n))
        out = []
        for code, name, close, pct, net in cur.fetchall():
            out.append({'code': code, 'name': name or code, 'price': round(close, 2) if close else None,
                        'pct': round(pct, 2) if pct is not None else None,
                        'main_net': int(net)})
        return out

    ladder = fetch_ladder(day)
    state_path = os.path.join(os.path.dirname(os.path.abspath(args.db)), 'sentiment_state.json')
    # 当日资金流覆盖数：为 0 时说明 em_fundflow 未跑/失败，资金榜降级为空——在 latest.json 里留标记可辨
    ff_n = conn.execute('SELECT COUNT(*) FROM fund_flow_daily WHERE date=?', (day,)).fetchone()[0]
    payload = {'date': day, 'total': total, 'up': up, 'down': down, 'flat': flat,
               'fund_flow': {'stocks': ff_n},
               'top_in': top('DESC'), 'top_out': top('ASC'),
               'ladder': ladder,
               'sentiment': compute_sentiment(conn, day, ladder, total, up, state_path),
               'watch': fetch_watch(conn, day)}
    radar = compute_radar(conn, day)
    radar['oversold'] = compute_oversold(conn, day)
    _log_oversold(day, radar['oversold'])
    conn.close()

    # 给榜单每只股附上影响其涨跌的相关题材（概念/行业，取同向最强/最弱 2 个）
    for it in payload['top_in'] + payload['top_out']:
        it['concepts'] = fetch_concepts(it['code'], it['pct'])
        time.sleep(0.15)

    os.makedirs(args.out, exist_ok=True)
    path = os.path.join(args.out, 'latest.json')
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(payload, f, ensure_ascii=False)
    print('已生成 %s：%s 共 %d 只，上涨 %d，下跌 %d，平盘 %d' % (path, day, total, up, down, flat))

    rpath = os.path.join(args.out, 'radar.json')
    with open(rpath, 'w', encoding='utf-8') as f:
        json.dump(radar, f, ensure_ascii=False)
    print('已生成 %s：雷达 %d 条（创业板 %d 条），超跌观察 %d 条' % (rpath, len(radar['list']), len(radar['gem_list']), len(radar.get('oversold') or [])))

    # 全市场当日名单（供看板点概览数字看涨/跌/平全名单，按代码前缀筛选）
    conn2 = sqlite3.connect(args.db)
    cur = conn2.execute(
        """SELECT b.code, m.name, b.close, b.pct_chg, f.main_net
           FROM daily_bar b
           LEFT JOIN stock_meta m ON b.code = m.code
           LEFT JOIN fund_flow_daily f ON b.code = f.code AND f.date = b.date
           WHERE b.date = ?""", (day,))
    movers = [{'c': code, 'n': name or code,
               'p': round(close, 2) if close else None,
               'pc': round(pct, 2) if pct is not None else None,
               'mn': int(net) if net is not None else None}
              for code, name, close, pct, net in cur.fetchall()]
    conn2.close()
    mpath = os.path.join(args.out, 'movers.json')
    with open(mpath, 'w', encoding='utf-8') as f:
        json.dump({'date': day, 'items': movers}, f, ensure_ascii=False)
    print('已生成 %s：全市场 %d 只' % (mpath, len(movers)))


if __name__ == '__main__':
    main()
