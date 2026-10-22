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
_SKIP_SUB = ('融资融券', '沪股通', '深股通', '港股通', 'MSCI', '富时', '标普', '转融券', '季报', '年报')


def _get_json(url, hosts=None):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read().decode('utf-8'))


def fetch_ladder(day):
    """涨停/跌停池 + 连板梯队（按连板数分组，取 >=2 板）。day: YYYY-MM-DD"""
    d8 = day.replace('-', '')
    base = 'https://push2ex.eastmoney.com/%s?ut=7eea3edcaed734bea9cbfc24409ed989&dpt=wz.ztzt&Pageindex=0&pagesize=300&sort=fbt:asc&date=%s'
    out = {'zt': 0, 'dt': 0, 'groups': []}
    try:
        d = _get_json(base % ('getTopicZTPool', d8))
        data = d.get('data') or {}
        out['zt'] = data.get('tc') or 0
        groups = {}
        for x in data.get('pool') or []:
            lbc = x.get('lbc') or 1
            if lbc >= 2:
                groups.setdefault(lbc, []).append({'code': x.get('c'), 'name': x.get('n'), 'ind': x.get('hybk') or ''})
        out['groups'] = [{'boards': k, 'stocks': groups[k]} for k in sorted(groups, reverse=True)]
    except Exception as e:
        print('涨停池拉取失败：%s' % e)
    try:
        d = _get_json(base % ('getTopicDTPool', d8))
        out['dt'] = (d.get('data') or {}).get('tc') or 0
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

    payload = {'date': day, 'total': total, 'up': up, 'down': down, 'flat': flat,
               'top_in': top('DESC'), 'top_out': top('ASC'),
               'ladder': fetch_ladder(day)}
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


if __name__ == '__main__':
    main()
