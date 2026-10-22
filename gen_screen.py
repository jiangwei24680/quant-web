# -*- coding: utf-8 -*-
"""
gen_screen.py —— 每日选股榜生成：复用 quant_tool 的评分管线，产出 data/screen.json
逻辑同 quant_tool.py screen：成交额前150 → 60日涨幅>0 预筛60只 → 逐只K线评分 → 前15
"""
import os, sys, json, time, datetime
sys.path.insert(0, os.path.expanduser('~/workspace/your_files'))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import quant_tool as qt
from gen_webdata import fetch_concepts

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data', 'screen.json')
POOL, DEEP, TOP = 150, 60, 15


def main():
    rows = qt.clist('f6', 'f2,f3,f6,f8,f12,f14,f24,f62,f184', pz=POOL)
    rows = [r for r in rows if isinstance(r.get('f2'), (int, float)) and r['f2'] > 0
            and 'ST' not in r['f14']]
    rows = [r for r in rows if isinstance(r.get('f24'), (int, float)) and r['f24'] > 0][:DEEP]
    scored = []
    for r in rows:
        try:
            kl = qt.kline(r['f12'])
            if len(kl) < 60:
                continue
            ind = qt.indicators(kl)
            total, parts = qt.score_stock(ind, r)
            scored.append({'code': r['f12'], 'name': r['f14'], 'price': r['f2'],
                           'pct': r['f3'], 'amt_yi': round((r.get('f6') or 0) / 1e8, 1),
                           'turnover': r.get('f8'), 'g60': r.get('f24'),
                           'main_net': r.get('f62'), 'score': total,
                           'parts': list(parts)})
        except Exception as e:
            print('skip %s: %s' % (r.get('f12'), e))
        time.sleep(0.05)
    scored.sort(key=lambda x: -x['score'])
    top_items = scored[:TOP]
    for it in top_items:
        it['concepts'] = fetch_concepts(it['code'], it['pct'])
        time.sleep(0.15)
    day = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8))).strftime('%Y-%m-%d')
    data = {'date': day, 'items': top_items,
            'meta': {'name': '综合评分策略', 'pool': POOL, 'scored': len(scored),
                     'rule': '成交额前150 → 60日涨幅为正预筛 → 逐只K线算 趋势40+资金30+动量15+活跃15'}}
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    print('screen.json 生成：%s 共 %d 只，榜首 %s %d 分' % (
        day, len(data['items']),
        data['items'][0]['name'] if data['items'] else '-', data['items'][0]['score'] if data['items'] else 0))


if __name__ == '__main__':
    main()
