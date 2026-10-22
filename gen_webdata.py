# -*- coding: utf-8 -*-
"""
gen_webdata.py —— 从 quant.db 生成网站数据 data/latest.json（只用公开全市场数据，
不含任何个人持仓/成本信息，可安全推送到公开仓库供 Cloudflare Pages 部署）。

用法: python3 gen_webdata.py [--db ~/workspace/quantdb/quant.db] [--date YYYY-MM-DD] [--out data]
默认取库中最新的交易日。
"""
import os, sys, json, sqlite3, argparse

DEFAULT_DB = os.path.expanduser('~/workspace/quantdb/quant.db')


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
               'top_in': top('DESC'), 'top_out': top('ASC')}
    conn.close()

    os.makedirs(args.out, exist_ok=True)
    path = os.path.join(args.out, 'latest.json')
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(payload, f, ensure_ascii=False)
    print('已生成 %s：%s 共 %d 只，上涨 %d，下跌 %d，平盘 %d' % (path, day, total, up, down, flat))


if __name__ == '__main__':
    main()
