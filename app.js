// app.js —— 读取 data/latest.json 并渲染量化市场看板
(function () {
  var fmtPct = function (p) {
    if (p === null || p === undefined) return '–';
    var s = (p > 0 ? '+' : '') + p.toFixed(2) + '%';
    return '<span class="' + (p > 0 ? 'up' : (p < 0 ? 'dn' : '')) + '">' + s + '</span>';
  };
  var fmtYi = function (yuan) {
    return (yuan / 1e8).toFixed(2);
  };
  var row = function (it, cls) {
    var pct = fmtPct(it.pct);
    return '<tr><td><span>' + it.name + '</span><span class="code">' + it.code + '</span></td>'
      + '<td>' + (it.price === null ? '–' : it.price.toFixed(2)) + '</td>'
      + '<td>' + pct + '</td>'
      + '<td class="' + cls + '">' + fmtYi(it.main_net) + '</td></tr>';
  };

  fetch('data/latest.json')
    .then(function (r) {
      if (!r.ok) throw new Error('http ' + r.status);
      return r.json();
    })
    .then(function (d) {
      document.getElementById('date').textContent = d.date;
      document.getElementById('total').textContent = d.total;
      document.getElementById('up').textContent = d.up;
      document.getElementById('down').textContent = d.down;
      document.getElementById('flat').textContent = d.flat;
      document.getElementById('top-in').innerHTML = d.top_in.map(function (it) { return row(it, 'up'); }).join('');
      document.getElementById('top-out').innerHTML = d.top_out.map(function (it) { return row(it, 'dn'); }).join('');
    })
    .catch(function () {
      document.getElementById('error').style.display = 'block';
      document.getElementById('date').textContent = '暂无';
    });
})();
