/* Tiny dependency-free canvas line/bar charts. */

function drawChart(canvas, series, opts) {
  // series: [{name, color, data: [{x, y}]}], opts: {yfmt, title, fill}
  opts = opts || {};
  const dpr = window.devicePixelRatio || 1;
  const W = canvas.clientWidth || 400, H = canvas.height / dpr || 160;
  canvas.width = W * dpr; canvas.height = (opts.h || 160) * dpr;
  canvas.style.height = (opts.h || 160) + 'px';
  const ctx = canvas.getContext('2d');
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  const h = opts.h || 160;
  ctx.clearRect(0, 0, W, h);
  const padL = 46, padR = 8, padT = opts.title ? 20 : 8, padB = 18;
  const pw = W - padL - padR, ph = h - padT - padB;

  let xs = [], ys = [];
  for (const s of series) for (const p of s.data) { xs.push(p.x); ys.push(p.y); }
  if (!xs.length) {
    ctx.fillStyle = '#4d5a68'; ctx.font = '12px sans-serif';
    ctx.fillText('no data yet', W / 2 - 30, h / 2);
    return;
  }
  let xmin = Math.min(...xs), xmax = Math.max(...xs);
  let ymin = Math.min(...ys), ymax = Math.max(...ys);
  if (opts.zero) ymin = Math.min(0, ymin);
  if (ymax === ymin) { ymax += 1; ymin -= 1; }
  const yr = ymax - ymin; ymax += yr * 0.07; ymin -= yr * 0.07;
  if (xmax === xmin) xmax += 1;
  const X = x => padL + (x - xmin) / (xmax - xmin) * pw;
  const Y = y => padT + (1 - (y - ymin) / (ymax - ymin)) * ph;

  // gridlines + y labels
  ctx.strokeStyle = '#1c2530'; ctx.fillStyle = '#7d8b99';
  ctx.font = '10px Consolas, monospace'; ctx.lineWidth = 1;
  const yfmt = opts.yfmt || (v => fmtCompact(v));
  for (let i = 0; i <= 4; i++) {
    const yv = ymin + (ymax - ymin) * i / 4;
    const yy = Y(yv);
    ctx.beginPath(); ctx.moveTo(padL, yy); ctx.lineTo(W - padR, yy); ctx.stroke();
    ctx.fillText(yfmt(yv), 2, yy + 3);
  }
  // zero line
  if (ymin < 0 && ymax > 0) {
    ctx.strokeStyle = '#3a4a5c';
    ctx.beginPath(); ctx.moveTo(padL, Y(0)); ctx.lineTo(W - padR, Y(0)); ctx.stroke();
  }
  // x labels (first/last)
  ctx.fillStyle = '#5d6b79';
  const xfmt = opts.xfmt || (v => String(v));
  ctx.fillText(xfmt(xmin), padL, h - 5);
  const lastLabel = xfmt(xmax);
  ctx.fillText(lastLabel, W - padR - ctx.measureText(lastLabel).width, h - 5);

  for (const s of series) {
    ctx.strokeStyle = s.color; ctx.lineWidth = 1.6;
    ctx.beginPath();
    let first = true;
    for (const p of s.data) {
      const px = X(p.x), py = Y(p.y);
      if (first) { ctx.moveTo(px, py); first = false; } else ctx.lineTo(px, py);
    }
    ctx.stroke();
    if (opts.fill && series.length === 1) {
      ctx.lineTo(X(s.data[s.data.length - 1].x), Y(Math.max(ymin, 0)));
      ctx.lineTo(X(s.data[0].x), Y(Math.max(ymin, 0)));
      ctx.closePath();
      ctx.fillStyle = s.color + '22'; ctx.fill();
    }
  }
  // title + legend
  if (opts.title) {
    ctx.fillStyle = '#cdd7e1'; ctx.font = 'bold 11px sans-serif';
    ctx.fillText(opts.title, padL, 13);
  }
  if (series.length > 1) {
    let lx = W - padR - 10;
    ctx.font = '10px sans-serif';
    for (let i = series.length - 1; i >= 0; i--) {
      const s = series[i];
      const w = ctx.measureText(s.name).width;
      lx -= w + 16;
      ctx.fillStyle = s.color; ctx.fillRect(lx, 6, 10, 3);
      ctx.fillStyle = '#7d8b99'; ctx.fillText(s.name, lx + 13, 12);
    }
  }
}

function fmtCompact(v) {
  const a = Math.abs(v);
  if (a >= 1e12) return (v / 1e12).toFixed(1) + 'T';
  if (a >= 1e9) return (v / 1e9).toFixed(1) + 'B';
  if (a >= 1e6) return (v / 1e6).toFixed(1) + 'M';
  if (a >= 1e4) return (v / 1e3).toFixed(0) + 'K';
  if (a >= 100) return v.toFixed(0);
  if (a >= 1) return v.toFixed(1);
  return v.toFixed(2);
}

/* Convenience: chart a metric history array [{month, key}] */
function metricChart(id, hist, key, opts) {
  const el = document.getElementById(id);
  if (!el) return;
  const data = hist.map((m, i) => ({ x: i, y: (opts && opts.map ? opts.map(m[key]) : m[key]) }))
                   .filter(p => p.y !== undefined && p.y !== null && isFinite(p.y));
  const labels = hist.map(m => m.month || m.m);
  drawChart(el, [{ name: key, color: opts && opts.color || '#58a6ff', data }],
    Object.assign({
      xfmt: i => labels[Math.max(0, Math.min(labels.length - 1, Math.round(i)))] || '',
    }, opts || {}));
}
