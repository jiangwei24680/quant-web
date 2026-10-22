// 观察名单同步接口（Cloudflare Pages Function）
// POST /api/watchlist  {password, codes:["600519", ...]}
// 校验口令后，用 GH_TOKEN（仅限 quant-web 仓库 Contents 读写的细粒度令牌）
// 把名单写回仓库 watchlist.json；每日任务拉取该文件生成数据。
function json(obj, status) {
  return new Response(JSON.stringify(obj), {
    status: status || 200,
    headers: { 'Content-Type': 'application/json; charset=utf-8' }
  });
}

export async function onRequestPost({ request, env }) {
  if (!env.GH_TOKEN || !env.WATCH_PASSWORD) {
    return json({ error: '接口还没配密钥（GH_TOKEN / WATCH_PASSWORD）' }, 503);
  }
  let body;
  try { body = await request.json(); } catch (e) { return json({ error: '请求格式不对' }, 400); }
  if (!body || body.password !== env.WATCH_PASSWORD) {
    return json({ error: '口令不对' }, 401);
  }
  const codes = body.codes;
  if (!Array.isArray(codes) || codes.length > 50 || !codes.every(c => /^\d{6}$/.test(c))) {
    return json({ error: '代码格式不对（要 6 位数字，最多 50 只）' }, 400);
  }
  const repo = 'jiangwei24680/quant-web';
  const gh = {
    'Authorization': 'Bearer ' + env.GH_TOKEN,
    'User-Agent': 'quant-watch-sync',
    'Accept': 'application/vnd.github+json'
  };
  const cur = await fetch('https://api.github.com/repos/' + repo + '/contents/watchlist.json', { headers: gh });
  if (!cur.ok) return json({ error: '读名单失败 ' + cur.status }, 502);
  const curJ = await cur.json();
  const text = JSON.stringify(codes.map(code => ({ code })), null, 1) + '\n';
  const content = btoa(String.fromCharCode.apply(null, new TextEncoder().encode(text)));
  const put = await fetch('https://api.github.com/repos/' + repo + '/contents/watchlist.json', {
    method: 'PUT',
    headers: gh,
    body: JSON.stringify({ message: 'sync watchlist from panel', content, sha: curJ.sha })
  });
  if (!put.ok) return json({ error: '写入失败 ' + put.status }, 502);
  return json({ ok: true, count: codes.length });
}
