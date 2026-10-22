// app.js —— 量化市场看板：榜单渲染 + 点击个股看 60日K线/今日分时
// K线/分时/外围指标由浏览器直连东方财富接口（接口回显跨域许可，无需代理）
var KLINE_HOSTS = ['push2his.eastmoney.com', '82.push2his.eastmoney.com'];
var PUSH_HOSTS = ['push2.eastmoney.com', '82.push2.eastmoney.com', '48.push2.eastmoney.com'];
function secidOf(code) { return (/^[69]/.test(code) ? '1.' : '0.') + code; }
function emFetch(hosts, path) {
  var i = 0;
  function attempt() {
    return fetch('https://' + hosts[i] + path).then(function (r) {
      if (!r.ok) throw new Error('http ' + r.status);
      return r.json();
    }).catch(function (e) {
      if (++i < hosts.length) return attempt();
      throw e;
    });
  }
  return attempt();
}

(function () {
  var fmtPct = function (p) {
    if (p === null || p === undefined) return '–';
    var s = (p > 0 ? '+' : '') + Number(p).toFixed(2) + '%';
    return '<span class="' + (p > 0 ? 'up' : (p < 0 ? 'dn' : '')) + '">' + s + '</span>';
  };
  var fmtYi = function (yuan) { return (yuan / 1e8).toFixed(2); };
  var conceptCell = function (list) {
    if (!list || !list.length) return '<td class="concepts">—</td>';
    return '<td class="concepts">' + list.map(function (c) {
      return '<b>' + c.name + '</b> ' + fmtPct(c.pct);
    }).join('<br>') + '</td>';
  };
  var moneyRow = function (it, cls) {
    return '<tr data-code="' + it.code + '"><td><span>' + it.name + '</span><span class="code">' + it.code + '</span></td>'
      + conceptCell(it.concepts)
      + '<td>' + (it.price === null ? '–' : it.price.toFixed(2)) + '</td>'
      + '<td>' + fmtPct(it.pct) + '</td>'
      + '<td class="' + cls + '">' + fmtYi(it.main_net) + '</td></tr>';
  };
  var screenRow = function (it) {
    return '<tr data-code="' + it.code + '"><td><span>' + it.name + '</span><span class="code">' + it.code + '</span></td>'
      + conceptCell(it.concepts)
      + '<td>' + (it.price === null ? '–' : Number(it.price).toFixed(2)) + '</td>'
      + '<td>' + fmtPct(it.pct) + '</td>'
      + '<td class="score">' + it.score + '</td></tr>';
  };

  fetch('data/latest.json?t=' + Date.now()).then(function (r) { return r.json(); }).then(function (d) {
    document.getElementById('date').textContent = d.date;
    document.getElementById('total').textContent = d.total;
    document.getElementById('up').textContent = d.up;
    document.getElementById('down').textContent = d.down;
    document.getElementById('flat').textContent = d.flat;
    document.getElementById('top-in').innerHTML = d.top_in.map(function (it) { return moneyRow(it, 'up'); }).join('');
    document.getElementById('top-out').innerHTML = d.top_out.map(function (it) { return moneyRow(it, 'dn'); }).join('');
    renderLadder(d.ladder);
  }).catch(function () {
    document.getElementById('error').style.display = 'block';
    document.getElementById('date').textContent = '暂无';
  });

  fetch('data/screen.json?t=' + Date.now()).then(function (r) { return r.json(); }).then(function (d) {
    document.getElementById('screen').innerHTML = d.items.map(screenRow).join('');
    if (d.meta) {
      document.getElementById('stratMeta').innerHTML = '<b>' + d.meta.name + '</b>｜' + d.meta.rule
        + '｜今日共评 ' + d.meta.scored + ' 只，榜单取前 ' + d.items.length + ' 只';
    } else {
      document.getElementById('stratMeta').innerHTML = '<b>综合评分策略</b>｜成交额前150 → 60日涨幅为正预筛 → 逐只K线算 趋势40+资金30+动量15+活跃15';
    }
  }).catch(function () {
    document.getElementById('screen').innerHTML = '<tr><td colspan="5" style="text-align:left;color:#8b949e">选股榜数据生成中，稍后刷新。</td></tr>';
    document.getElementById('stratMeta').textContent = '策略数据生成中…';
  });

  // 外围指标（浏览器直连东财，打开页面即最新）
  emFetch(PUSH_HOSTS, '/api/qt/ulist.np/get?fltt=2&invt=2&fields=f2,f3,f12,f14&secids=100.HSI,100.N225,100.SPX,100.NDX,100.DJIA,122.XAU,102.CL00Y')
  .then(function (d) {
    var diff = (d.data && d.data.diff) || {};
    var rows = Array.isArray(diff) ? diff : Object.keys(diff).map(function (k) { return diff[k]; });
    if (!rows.length) return;
    document.getElementById('globals').innerHTML = rows.map(function (x) {
      var cls = x.f3 > 0 ? 'up' : (x.f3 < 0 ? 'dn' : '');
      return '<span class="gchip">' + x.f14 + '<span class="p ' + cls + '">' + Number(x.f2).toFixed(2)
        + ' ' + (x.f3 > 0 ? '+' : '') + Number(x.f3).toFixed(2) + '%</span></span>';
    }).join('');
  }).catch(function () {});

  // 连板梯队（随 latest.json 每日更新）
  function renderLadder(l) {
    var el = document.getElementById('ladder');
    if (!l) { el.innerHTML = '<p class="hint">暂无数据</p>'; return; }
    var maxB = l.groups && l.groups.length ? l.groups[0].boards : 1;
    var html = '<p class="lsum">涨停 <b class="up">' + l.zt + '</b> 家 · 跌停 <b class="dn">' + l.dt
      + '</b> 家 · 最高 ' + maxB + ' 连板</p>';
    if (!l.groups || !l.groups.length) {
      html += '<p class="hint">今日无 2 连板以上股票。</p>';
    } else {
      html += l.groups.map(function (g) {
        return '<div class="lgroup"><span class="b">' + g.boards + ' 连板</span>' + g.stocks.map(function (s) {
          return '<span class="s" data-code="' + s.code + '" data-name="' + s.name + '">' + s.name + '<i>' + s.ind + '</i></span>';
        }).join('') + '</div>';
      }).join('');
    }
    el.innerHTML = html;
  }

  // ---------- 个股详情 ----------
  var detail = document.getElementById('detail');
  document.getElementById('closeDetail').onclick = function () { detail.style.display = 'none'; };
  detail.addEventListener('click', function (e) { if (e.target === detail) detail.style.display = 'none'; });
  document.body.addEventListener('click', function (e) {
    if (!e.target.closest) return;
    var tr = e.target.closest('tr[data-code]');
    if (tr) { openDetail(tr.getAttribute('data-code'), tr.querySelector('td span').textContent); return; }
    var chip = e.target.closest('.s[data-code]');
    if (chip) openDetail(chip.getAttribute('data-code'), chip.getAttribute('data-name'));
  });

  function setupCanvas(cv, h) {
    var dpr = window.devicePixelRatio || 1;
    var w = cv.clientWidth || cv.parentElement.clientWidth - 24;
    cv.width = w * dpr; cv.height = h * dpr;
    cv.style.height = h + 'px';
    var ctx = cv.getContext('2d');
    ctx.scale(dpr, dpr);
    return { ctx: ctx, w: w, h: h };
  }
  function maArr(bars, n) {
    var out = [];
    for (var i = 0; i < bars.length; i++) {
      if (i < n - 1) { out.push(null); continue; }
      var s = 0; for (var j = 0; j < n; j++) s += bars[i - j].close;
      out.push(s / n);
    }
    return out;
  }
  function drawKline(cv, bars) {
    var H = 240, s = setupCanvas(cv, H), ctx = s.ctx, W = s.w;
    var volH = 44, priceH = H - volH - 18;
    var hi = -1e18, lo = 1e18, vmax = 0;
    bars.forEach(function (b) { hi = Math.max(hi, b.high); lo = Math.min(lo, b.low); vmax = Math.max(vmax, b.vol); });
    var pad = (hi - lo) * 0.06 || 1; hi += pad; lo -= pad;
    var X = function (i) { return (i + 0.5) * W / bars.length; };
    var Y = function (p) { return (hi - p) / (hi - lo) * priceH + 4; };
    ctx.strokeStyle = '#30363d'; ctx.fillStyle = '#8b949e'; ctx.font = '10px sans-serif';
    ctx.beginPath(); ctx.moveTo(0, Y(hi - pad) + 0.5); ctx.lineTo(W, Y(hi - pad) + 0.5); ctx.stroke();
    ctx.fillText(hi.toFixed(2), 4, 12); ctx.fillText(lo.toFixed(2), 4, priceH);
    var bw = Math.max(1, W / bars.length * 0.62);
    bars.forEach(function (b, i) {
      var up = b.close >= b.open, col = up ? '#f85149' : '#3fb950';
      ctx.strokeStyle = col; ctx.fillStyle = col;
      ctx.beginPath(); ctx.moveTo(X(i), Y(b.high)); ctx.lineTo(X(i), Y(b.low)); ctx.stroke();
      var y1 = Y(Math.max(b.open, b.close)), y2 = Y(Math.min(b.open, b.close));
      ctx.fillRect(X(i) - bw / 2, y1, bw, Math.max(1, y2 - y1));
      var vh = b.vol / vmax * (volH - 6);
      ctx.globalAlpha = 0.75; ctx.fillRect(X(i) - bw / 2, H - 14 - vh, bw, vh); ctx.globalAlpha = 1;
    });
    var mas = [[5, '#e6edf3'], [10, '#d29922'], [20, '#bc8cff'], [60, '#3fb950']];
    mas.forEach(function (cfg) {
      var arr = maArr(bars, cfg[0]);
      ctx.strokeStyle = cfg[1]; ctx.beginPath(); var started = false;
      arr.forEach(function (v, i) {
        if (v === null) return;
        if (!started) { ctx.moveTo(X(i), Y(v)); started = true; } else ctx.lineTo(X(i), Y(v));
      });
      ctx.stroke();
    });
    ctx.fillStyle = '#8b949e';
    ctx.fillText(bars[0].date.slice(5), 4, H - 2);
    var last = bars[bars.length - 1];
    ctx.fillText(last.date.slice(5), W - 40, H - 2);
  }
  function drawMinute(cv, pts, preClose) {
    var H = 180, s = setupCanvas(cv, H), ctx = s.ctx, W = s.w;
    if (!pts.length) { ctx.fillStyle = '#8b949e'; ctx.font = '12px sans-serif'; ctx.fillText('暂无分时数据（未开盘或接口忙）', 12, 24); return; }
    var volH = 34, priceH = H - volH - 16;
    var hi = preClose || 0, lo = preClose || 1e18, vmax = 0;
    pts.forEach(function (p) { hi = Math.max(hi, p.price, p.avg || 0); lo = Math.min(lo, p.price, p.avg || 1e18); vmax = Math.max(vmax, p.vol); });
    var pad = (hi - lo) * 0.12 || 0.01; hi += pad; lo -= pad;
    var X = function (i) { return i / 240 * W; };
    var Y = function (p) { return (hi - p) / (hi - lo) * priceH + 4; };
    ctx.font = '10px sans-serif'; ctx.fillStyle = '#8b949e';
    if (preClose) {
      ctx.strokeStyle = '#8b949e'; ctx.setLineDash([4, 4]);
      ctx.beginPath(); ctx.moveTo(0, Y(preClose)); ctx.lineTo(W, Y(preClose)); ctx.stroke(); ctx.setLineDash([]);
      ctx.fillText('昨收 ' + preClose.toFixed(2), 4, Y(preClose) - 3);
    }
    var lastP = pts[pts.length - 1].price;
    ctx.strokeStyle = lastP >= (preClose || lastP) ? '#f85149' : '#3fb950'; ctx.lineWidth = 1.4;
    ctx.beginPath();
    pts.forEach(function (p, i) { var x = X(i), y = Y(p.price); if (i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y); });
    ctx.stroke(); ctx.lineWidth = 1;
    ctx.strokeStyle = '#d29922'; ctx.beginPath();
    pts.forEach(function (p, i) { if (!p.avg) return; var x = X(i), y = Y(p.avg); if (i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y); });
    ctx.stroke();
    pts.forEach(function (p, i) {
      var vh = p.vol / vmax * (volH - 6);
      ctx.fillStyle = p.price >= (pts[i - 1] ? pts[i - 1].price : preClose || p.price) ? '#f85149' : '#3fb950';
      ctx.fillRect(X(i) - 0.7, H - 12 - vh, 1.4, vh);
    });
    ctx.fillStyle = '#8b949e';
    ctx.fillText('09:30', 4, H - 1); ctx.fillText('15:00', W - 32, H - 1);
  }
  function openDetail(code, name) {
    detail.style.display = 'block';
    document.getElementById('dName').textContent = name || code;
    document.getElementById('dCode').textContent = code;
    var ld = document.getElementById('dLoading');
    ld.style.display = 'block'; ld.textContent = '加载中…';
    var done = 0;
    function fin() { if (++done === 2) ld.style.display = 'none'; }
    emFetch(KLINE_HOSTS, '/api/qt/stock/kline/get?secid=' + secidOf(code)
      + '&fields1=f1,f2,f3&fields2=f51,f52,f53,f54,f55,f56,f57,f59&klt=101&fqt=1&end=20500101&lmt=66')
    .then(function (d) {
      var rows = (d.data && d.data.klines) || [];
      var bars = rows.map(function (s) {
        var p = s.split(',');
        return { date: p[0], open: +p[1], close: +p[2], high: +p[3], low: +p[4], vol: +p[5], amt: +p[6] };
      });
      if (bars.length) drawKline(document.getElementById('kCanvas'), bars.slice(-60));
      fin();
    }).catch(function () { ld.textContent = 'K线加载失败，接口忙，请稍后再点一次。'; fin(); });
    emFetch(PUSH_HOSTS, '/api/qt/stock/trends2/get?secid=' + secidOf(code)
      + '&fields1=f1,f2,f3,f4,f5,f6,f7,f8,f9,f10,f11,f12,f13&fields2=f51,f52,f53,f54,f55,f56,f57,f58&ndays=1&iscr=0&iscca=0')
    .then(function (d) {
      var rows = (d.data && d.data.trends) || [];
      var pts = rows.map(function (s) {
        var p = s.split(',');
        return { t: p[0].slice(11), price: +p[2], avg: +p[7], vol: +p[5] };
      });
      drawMinute(document.getElementById('mCanvas'), pts, d.data && d.data.preClose);
      fin();
    }).catch(function () { fin(); });
  }
})();
