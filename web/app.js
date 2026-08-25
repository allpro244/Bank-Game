/* Bank Game UI. Vanilla JS, talks to the local JSON API. */

let MODE = localStorage.getItem('bg_mode') || 'owner';   // 'owner' | 'banker'
let SUM = null;          // latest /api/summary
let TAB = MODE === 'owner' ? 'desk' : 'dashboard';
let SEC = {};            // section cache
let BUSY = false;
const REVEALED = new Set();   // tabs opened this session (deep links stay visible)

/* ---------------- glossary & owner-mode labels ----------------
   Every entry: b = banker label, o = plain-English label, g = tooltip.
   Owner mode swaps labels; both modes get the tooltip. Same game either way. */
const DICT = {
  nim:  { b: 'NIM', o: 'Lending margin',
    g: 'Net interest margin: what your assets earn minus what your funding costs, as a % of earning assets. The core of bank profit. 3.5-4% is healthy.' },
  roa:  { b: 'ROA / ROE', o: 'Return on assets / equity',
    g: 'ROA: yearly profit as a % of everything the bank owns (0.9-1.3% is good). ROE: profit as a % of YOUR money in the bank — the owner’s score (10%+ is good).' },
  eff:  { b: 'Efficiency', o: 'Cost per $1 of revenue',
    g: 'Operating costs divided by revenue. 60% means you spend 60 cents to make a dollar. LOWER is better; under 60% is strong, over 80% is a problem.' },
  npa:  { b: 'NPAs', o: 'Bad loans',
    g: 'Nonperforming assets: loans no longer paying, plus foreclosed property, as a % of assets. Under 1% is clean; over 3% brings examiners.' },
  cet1: { b: 'CET1', o: 'Core capital',
    g: 'Your highest-quality capital (common equity) as a % of risk-weighted assets. The loss cushion regulators watch hardest. 6.5%+ = "well-capitalized"; 9%+ is comfortable.' },
  leverage: { b: 'Leverage ratio', o: 'Capital vs total assets',
    g: 'Core capital as a % of TOTAL assets, ignoring risk weights. A blunt backstop: 5%+ required to be well-capitalized.' },
  aoci: { b: 'AOCI', o: 'Paper gain/loss on bonds',
    g: 'Unrealized gains/losses on sellable (AFS) bonds, flowing straight through your equity as rates move. Paper — until a crisis forces you to sell.' },
  htm:  { b: 'HTM', o: 'Locked-away bonds',
    g: 'Held-to-maturity: bonds carried at cost so paper losses stay hidden from equity. Sell even one and accounting rules force the WHOLE book marked to market at once (the SVB trap).' },
  afs:  { b: 'AFS', o: 'Sellable bonds',
    g: 'Available-for-sale: bonds marked to market value daily, with gains/losses hitting equity (AOCI). Flexible, but your equity breathes with rates.' },
  camels: { b: 'CAMELS', o: 'Regulator report card',
    g: 'Exam rating 1 (best) to 5 (about to fail) across Capital, Asset quality, Management, Earnings, Liquidity, Sensitivity to rates. 3 = watch list. 4 = forced restrictions.' },
  pca:  { b: 'PCA', o: 'Capital status',
    g: 'Prompt Corrective Action: the regulatory ladder from "well-capitalized" down to seizure. Each rung down removes powers (brokered deposits, dividends, growth).' },
  ldr:  { b: 'LDR', o: 'Loans vs deposits',
    g: 'Loans divided by deposits. Around 0.8-1.0 is balanced; above ~1.05 you’re funding loans with borrowed money.' },
  cof:  { b: 'CoF', o: 'Cost of funding',
    g: 'The average interest rate you pay across all deposits. Keeping this low while keeping depositors is the deposit game.' },
  uninsured: { b: 'Uninsured', o: 'Big deposits (uninsured)',
    g: 'Share of deposits above the $250,000 FDIC insurance limit. Insured money sleeps through a crisis; uninsured money runs at the first bad headline.' },
  tbv:  { b: 'TBV/sh', o: 'Book value per share',
    g: 'Tangible book value per share: hard net worth (excluding goodwill) divided by shares. The bedrock valuation of a bank.' },
  reserves: { b: 'Reserves', o: 'Loss reserve',
    g: 'The allowance for credit losses: money already set aside (through past earnings) for loans expected to go bad. Recomputed quarterly under CECL rules.' },
  duration: { b: 'Duration', o: 'Rate sensitivity (years)',
    g: 'How hard bond prices move when rates move: a duration of 5 means roughly -5% price for +1% in rates. Longer duration = more yield, more pain when rates rise.' },
  fhlb: { b: 'FHLB', o: 'FHLB (backup borrowing)',
    g: 'The Federal Home Loan Bank: a lender banks can borrow from against loan/bond collateral. Respectable and fast — your first line of backup liquidity.' },
  dw:   { b: 'Discount window', o: 'Fed emergency loans',
    g: 'Borrowing from the Federal Reserve itself. Always available, slightly pricey, and habitual use tells examiners you have a funding problem.' },
  brokered: { b: 'Brokered', o: 'Bought deposits',
    g: 'Deposits purchased through brokers rather than earned from customers. Instant funding at a premium price — banned if your capital slips below well-capitalized.' },
  spread: { b: 'Spread bp', o: 'Your price vs market (bp)',
    g: 'Basis points (1bp = 0.01%) versus the going market rate. Negative = undercut competitors to win volume with thinner margins; positive = premium pricing.' },
  standards: { b: 'Standards', o: 'How picky you are',
    g: 'Underwriting standards. Loose books more volume from weaker borrowers — and every loan pool permanently remembers the standards it was written under when the next recession arrives.' },
  stance: { b: 'Loan stance', o: 'Appetite for this line',
    g: 'Starve, Hold, Grow, or Hunt. Each one writes your price versus the street, how picky you are, and whether this line may grow. Loans already booked keep the rate and standards they were written under.' },
  tier: { b: 'Tier', o: 'Borrower grade',
    g: 'Credit grade: A = strong borrower, low loss risk; B = acceptable; C = marginal, priced up for risk (about 6x the default rate of an A).' },
  dscr: { b: 'DSCR', o: 'Payment coverage',
    g: 'Debt service coverage ratio: borrower cash flow vs loan payments. 1.3x means 30% cushion. Below 1.2x is thin; below 1.0x they can’t afford the loan.' },
  ltv:  { b: 'LTV', o: 'Loan vs collateral',
    g: 'Loan-to-value: loan size vs collateral worth. 70% LTV means the collateral covers you even if it loses 30% of its value in foreclosure.' },
  oreo: { b: 'OREO', o: 'Foreclosed property',
    g: 'Other Real Estate Owned: property you seized from defaulted borrowers. Costs money to hold, sells at a discount — get rid of it.' },
  cra:  { b: 'CRA', o: 'Community lending grade',
    g: 'Community Reinvestment Act rating: are you lending where you take deposits? A poor rating blocks regulators from approving your acquisitions.' },
  bsa:  { b: 'BSA / AML', o: 'Anti-money-laundering',
    g: 'Bank Secrecy Act program: know your customers, monitor transactions, file suspicious-activity reports. Chronic underinvestment ends in nine-figure fines.' },
  cecl: { b: 'CECL', o: 'Expected-loss reserving',
    g: 'Current Expected Credit Losses: each quarter you must reserve for the LIFETIME expected losses of every loan on day one — front-loading the pain of growth.' },
  interchange: { b: 'Interchange', o: 'Card swipe income',
    g: 'The slice of every debit-card purchase the bank keeps. Cut roughly in half by law (the Durbin amendment) once you cross $10B in assets.' },
  liquidity: { b: 'Liquidity', o: 'Ready cash',
    g: 'Cash plus sellable securities as a % of assets: what you could hand back to depositors tomorrow without borrowing. Under ~8% is living dangerously.' },
};

function dt(key, override) {
  const e = DICT[key];
  if (!e) return esc(override || key);
  const label = override || (MODE === 'owner' ? e.o : e.b);
  const tip = e.g + (MODE === 'owner' && e.b !== e.o ? ' (Bankers call this "' + e.b + '".)' : '');
  return `<span class="term" title="${esc(tip)}">${esc(label)}</span>`;
}

function toggleMode() {
  MODE = MODE === 'owner' ? 'banker' : 'owner';
  localStorage.setItem('bg_mode', MODE);
  toast(MODE === 'owner'
    ? 'Owner view: plain language, Your Desk first. Same game underneath.'
    : 'Banker view: full jargon, dense dashboard first.');
  refresh();
}

function showGlossary() {
  const body = Object.values(DICT)
    .sort((a, b) => a.o.localeCompare(b.o))
    .map(e => `${e.o}${e.b !== e.o ? '  ("' + e.b + '")' : ''}\n   ${e.g}`)
    .join('\n\n');
  showText('Glossary — banking, translated', esc(body));
}

/* ---------------- helpers ---------------- */
const $ = id => document.getElementById(id);
const esc = s => String(s == null ? '' : s)
  .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
// JSON safe to embed inside a single-quoted HTML attribute
const jattr = o => JSON.stringify(o ?? null).replace(/&/g, '\\u0026')
  .replace(/'/g, '&#39;').replace(/</g, '\\u003c');

function fm(cents) {           // full dollars with commas
  if (cents == null) return '—';
  const d = Math.round(cents / 100);
  const sign = d < 0 ? '-' : '';
  return sign + '$' + Math.abs(d).toLocaleString('en-US');
}
function fmc(cents) {          // compact
  if (cents == null) return '—';
  const d = cents / 100, a = Math.abs(d), s = d < 0 ? '-$' : '$';
  if (a >= 1e12) return s + (a / 1e12).toFixed(2) + 'T';
  if (a >= 1e9) return s + (a / 1e9).toFixed(2) + 'B';
  if (a >= 1e6) return s + (a / 1e6).toFixed(2) + 'M';
  if (a >= 1e3) return s + (a / 1e3).toFixed(0) + 'K';
  return s + a.toFixed(0);
}
function pct(v, dp) { return v == null ? '—' : (v * 100).toFixed(dp == null ? 2 : dp) + '%'; }
function durationTrapCopy() {
  const era = (SUM.meta || {}).era;
  const y = parseInt(((SUM.time || {}).date || '2000').slice(0, 4), 10);
  if (era === 'historical' && y >= 2015) {
    return 'This is the Silicon Valley Bank dial. If unrealized losses approach your capital and your uninsured depositors notice, the run starts.';
  }
  return 'This is the duration trap. Long bonds bought cheap, then rates rise: paper losses vs capital. Uninsured depositors who notice start the run.';
}
function cls(v) { return v > 0 ? 'pos' : v < 0 ? 'neg' : ''; }
function moneyIn(id) {         // dollars input -> cents
  const v = parseFloat($(id).value);
  if (isNaN(v)) throw 'enter a number';
  return Math.round(v * 100);
}
function numIn(id) {
  const v = parseFloat($(id).value);
  if (isNaN(v)) throw 'enter a number';
  return v;
}

async function api(path, body) {
  const opts = body === undefined ? {} :
    { method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body) };
  const r = await fetch(path, opts);
  const j = await r.json();
  if (j.error) throw j.error;
  return j;
}

function runBanner(run) {
  run = run || {};
  if (run.run) {
    return `<div class="banner red" style="margin-bottom:10px"><b>DEPOSITORS ARE PULLING MONEY.</b>
      ${esc(run.cause || 'The bank is being run on')}. Day ${run.run_days || 1}
      · out so far ${fm(run.outflow || 0)}. Pay up, draw FHLB, raise capital — the balances will not wait.</div>`;
  }
  if (run.watch) {
    return `<div class="banner" style="margin-bottom:10px;border-color:var(--warn)">
      <b>Rumor is rising</b> (${esc(run.cause || 'watch the book')}).
      Checking is sticky; money market is not. Do not let this become a run.</div>`;
  }
  return '';
}

function toast(msg, isErr) {
  const t = document.createElement('div');
  t.className = 'toastmsg' + (isErr ? ' err' : '');
  t.textContent = msg;
  $('toast').appendChild(t);
  setTimeout(() => t.remove(), isErr ? 7000 : 3500);
}

async function act(action, payload) {
  if (BUSY) return;
  try {
    BUSY = true;
    const r = await api('/api/action', { action, payload });
    if (r.result && r.result.message) toast(r.result.message);
    await refresh();
  } catch (e) { toast(String(e), true); }
  finally { BUSY = false; }
}

async function setPol(path, value) {
  try {
    await api('/api/set', { path, value });
    toast('Policy updated: ' + path.split('.').pop());
    await refresh();
  } catch (e) { toast(String(e), true); }
}

async function advance(unit) {
  if (BUSY) return;
  BUSY = true;
  try {
    let r = await api('/api/advance', { unit, max_days: unit === 'until' ? 1260 : undefined });
    if (unit !== 'until' && r.result && r.result.inbox && (r.result.days || 0) === 0) {
      const ok = confirm('Your Desk still has a decision. Advance anyway? '
        + 'Unanswered memos will age and may expire.');
      if (ok) r = await api('/api/advance', { unit, skip_inbox: true });
      else {
        toast('The clock stopped: something on Your Desk needs a decision first.');
        await refresh();
        return;
      }
    }
    await refresh();
    const evs = r.result.events || [];
    const blocked = evs.some(e => e.blocking);
    if (unit === 'until' && (r.result.days || 0) > 0) {
      const why = r.result.stopped ? (' Stopped: ' + r.result.stopped + '.') : '';
      toast('Played ' + r.result.days + ' days to ' + (r.result.date || '') + '.' + why);
    } else if (r.result.inbox) toast('The clock stopped: something on Your Desk needs a decision first.');
    else if (blocked) toast('The clock stopped: something needs your attention.');
  } catch (e) { toast(String(e), true); }
  finally { BUSY = false; }
}

/* ---------------- refresh & routing ---------------- */
async function refresh() {
  SUM = await api('/api/summary');
  if (SUM.no_game) { showSaves(); return; }
  $('savescreen').classList.add('hidden');
  $('topbar').classList.remove('hidden');
  $('layout').classList.remove('hidden');
  renderTopbar();
  renderFranchise();
  renderNav();
  await renderTab();
  renderEventModal();
}

function renderTopbar() {
  const b = SUM.bank;
  $('tb-name').textContent = b.name;
  $('tb-date').textContent = SUM.time.display || SUM.time.date;
  $('tb-assets').textContent = fmc(b.assets);
  const cashEl = $('tb-cash');
  cashEl.textContent = fmc(b.cash);
  cashEl.title = 'Spendable: vault ' + fmc(b.vault) +
    ' · at the Fed ' + fmc(b.fed_balances) +
    ' · fed funds sold ' + fmc(b.fed_funds_sold);
  $('tb-equity').textContent = fmc(b.equity);
  const ni = $('tb-ni');
  ni.textContent = fmc(b.ni_mtd);
  ni.className = cls(b.ni_mtd);
  const reg = SUM.regulation;
  const pcaColor = reg.pca === 'well' ? 'g' : reg.pca === 'adequate' ? 'y' : 'r';
  const pcaOwner = {well: 'Solid capital', adequate: 'Adequate',
    under: 'Undercapitalized', significant: 'Trouble', critical: 'Critical'};
  const pcaLabel = MODE === 'owner' ? (pcaOwner[reg.pca] || reg.pca)
                                   : reg.pca.toUpperCase();
  const camelsLabel = MODE === 'owner'
    ? ('Report card ' + reg.camels.composite)
    : ('CAMELS ' + reg.camels.composite);
  const examMo = reg.months_to_exam;
  const examLabel = examMo == null ? '' :
    `<span class="pill ${examMo <= 3 ? 'y' : 'b'}">${MODE === 'owner' ? 'Examiners' : 'Exam'} ${examMo} mo</span>`;
  const dw = reg.dw_uses || 0;
  const dwLabel = dw ? `<span class="pill ${dw >= 5 ? 'r' : 'y'}">${MODE === 'owner' ? 'Fed window' : 'Window'} ×${dw}</span>` : '';
  $('tb-pca').innerHTML =
    `<span class="pill ${pcaColor}">${esc(pcaLabel)}</span> ` +
    `<span class="pill ${reg.camels.composite <= 2 ? 'g' : reg.camels.composite === 3 ? 'y' : 'r'}">${esc(camelsLabel)}</span> ` +
    examLabel + ' ' + dwLabel;
}

function renderFranchise() {
  const el = $('franchise');
  if (!el) return;
  const f = SUM.franchise;
  if (!f) { el.innerHTML = ''; return; }
  const run = f.run || SUM.crisis || {};
  const runBit = run.run
    ? `<span class="fbit" style="color:var(--red);font-weight:700">RUN — ${esc(run.cause || 'depositors leaving')}</span>`
    : (run.watch
      ? `<span class="fbit" style="color:var(--warn)">Rumor rising (${esc(run.cause || 'watch deposits')})</span>`
      : '');
  el.innerHTML =
    `<span class="fbit"><b>${esc(f.home)}</b></span>` +
    `<span class="fbit">${esc(f.people)}</span>` +
    `<span class="fbit">${esc(f.cash)}</span>` +
    `<span class="fbit">${esc(f.exam)}</span>` +
    runBit;
}

const TABS = [
  ['desk', 'Your Desk'],
  ['dashboard', 'Dashboard'], ['lending', 'Lending'], ['deposits', 'Deposits'],
  ['treasury', 'Treasury'], ['ops', 'Operations'], ['risk', 'Risk & Reg'],
  ['markets', 'Markets'], ['reports', 'Reports'], ['ledger', 'Ledger'],
  ['events', 'Events'],
];

function tabUnlocked(id) {
  if (MODE === 'banker') return true;
  if (REVEALED.has(id) || TAB === id) return true;
  const always = ['desk', 'deposits', 'lending', 'treasury', 'ops'];
  if (always.includes(id)) return true;
  const u = SUM.unlock || {};
  const months = u.months_closed || 0;
  if (id === 'dashboard') return months >= 1;
  if (id === 'risk') return (u.months_to_exam != null && u.months_to_exam <= 6)
    || u.fraud_open || u.orders;
  if (id === 'markets') return (u.branches || 0) >= 2 || months >= 3;
  if (id === 'reports') return months >= 3;
  if (id === 'ledger') return u.audit || months >= 1;
  if (id === 'events') return (u.pending || 0) > 0 || (u.log_len || 0) > 8;
  return true;
}

function renderNav() {
  const counts = SUM.counts || {};
  const badges = {
    desk: (counts.loan_queue || 0) + (counts.fraud_cases || 0)
          + (SUM.pending || []).length,
    lending: counts.loan_queue || 0,
    risk: counts.fraud_cases || 0,
    events: (SUM.pending || []).length,
  };
  $('nav').innerHTML = TABS.filter(([id]) => tabUnlocked(id)).map(([id, label]) =>
    `<div class="tab ${TAB === id ? 'active' : ''}" onclick="switchTab('${id}')">
       <span>${label}</span>${badges[id] ? `<span class="badge">${badges[id]}</span>` : ''}
     </div>`).join('') +
    `<div style="flex:1;min-height:12px"></div>
     <div class="tab" onclick="showGlossary()"><span>📖 Glossary</span></div>
     <div class="tab" onclick="toggleMode()" title="Owner view: plain language. Banker view: full jargon. Same game.">
       <span>⇄ ${MODE === 'owner' ? 'Owner view' : 'Banker view'}</span></div>
     <div class="helptip" style="padding:8px 14px;line-height:1.35">Keys: space day · w week · m month · q quarter · u play until. Week/month/quarter stop if Your Desk has a decision. Play until uses your credit box and does not stop on quarter close unless you opt in.</div>`;
}

async function switchTab(id) {
  TAB = id;
  REVEALED.add(id);
  renderNav();
  await renderTab();
}

async function section(name) {
  SEC[name] = await api('/api/section?name=' + name);
  return SEC[name];
}

async function renderTab() {
  const m = $('main');
  if (SUM.game_over) { renderGameOver(m); return; }
  try {
    if (TAB === 'desk') await tabDesk(m);
    else if (TAB === 'dashboard') await tabDashboard(m);
    else if (TAB === 'lending') await tabLending(m);
    else if (TAB === 'deposits') await tabDeposits(m);
    else if (TAB === 'treasury') await tabTreasury(m);
    else if (TAB === 'ops') await tabOps(m);
    else if (TAB === 'risk') await tabRisk(m);
    else if (TAB === 'markets') await tabMarkets(m);
    else if (TAB === 'reports') await tabReports(m);
    else if (TAB === 'ledger') await tabLedger(m);
    else if (TAB === 'events') await tabEvents(m);
  } catch (e) {
    m.innerHTML = `<div class="banner red">Failed to render: ${esc(e)}</div>`;
  }
}

function renderGameOver(m) {
  const g = SUM.game_over;
  const kind = g.kind || 'seized';
  const head = kind === 'seized' ? 'THE BANK HAS FAILED'
    : kind === 'retired' ? 'YOU STEPPED AWAY'
    : 'THE BANK WAS SOLD';
  const tone = kind === 'seized' ? 'red' : 'amber';
  const goal = g.goal || {};
  const notes = (g.notes || []).map(n => `<li>${esc(n)}</li>`).join('');
  m.innerHTML = `
    <div class="banner ${tone}" style="font-size:16px">${head}</div>
    <div class="panel">
      <p>${esc(g.summary)}</p>
      <p class="sub" style="margin-top:8px">${esc(g.display_date || g.date)} · ${g.years} years · final assets ${fm(g.assets)}</p>
      ${goal.label ? `<h3>Goal — ${esc(goal.label)}</h3>
        <p>${goal.won ? 'Complete.' : (goal.failed ? 'Not this time.' : esc(goal.text || ''))}</p>` : ''}
      ${g.exam ? `<h3>Last report card</h3><p>${esc(g.exam)}</p>` : ''}
      <div class="kv" style="margin-top:8px">
        <span class="k">Peak loans vs deposits</span><span class="v">${g.peak_ldr != null ? g.peak_ldr.toFixed(2) : '—'}</span>
        <span class="k">Discount window uses</span><span class="v">${g.window_uses != null ? g.window_uses : '—'}</span>
        <span class="k">Paper losses vs core capital</span><span class="v">${g.unreal_vs_cet1 != null ? pct(g.unreal_vs_cet1, 0) : '—'}</span>
      </div>
      ${notes ? `<h3>What mattered</h3><ul class="sub">${notes}</ul>` : ''}
      ${g.earlier ? `<p style="margin-top:10px">${esc(g.earlier)}</p>` : ''}
      <div class="btnrow" style="margin-top:12px">
        <button class="primary" onclick="showSaves()">Back to the title screen</button>
      </div>
    </div>`;
}

/* ---------------- Your Desk ---------------- */
async function tabDesk(m) {
  const d = await section('desk');
  const g = d.gauges;
  const tut = d.tutorial;
  const inbox = d.inbox;
  const nothingPending = !inbox.events.length && !inbox.loans.length && !inbox.fraud.length;
  const allGreen = g.every(x => x.status === 'g');

  const goal = d.goal || SUM.goal;
  const goalBar = goal ? `<div class="panel tight" style="margin-bottom:10px">
      <b>${esc(goal.label)}</b>
      <span class="sub"> — ${esc(goal.text)}</span>
      <div style="margin-top:6px;background:#0a0e13;border-radius:4px;height:8px;overflow:hidden">
        <div style="height:100%;width:${Math.round((goal.pct||0)*100)}%;background:${goal.won ? 'var(--green)' : 'var(--accent)'}"></div>
      </div>
    </div>` : '';
  m.innerHTML = `
    <h2>Your Desk <span class="sub">— what needs you, in plain English. Every light and card clicks through to the full detail.</span></h2>
    ${goalBar}
    ${runBanner(SUM.crisis)}
    ${(SUM.franchise && SUM.franchise.exam_path) ? `<div class="banner" style="margin-bottom:10px;border-color:var(--red)">
      <b>Report card is a ${SUM.franchise.camels}.</b> ${esc(SUM.franchise.exam_path.needed || '')}
      ${(SUM.franchise.exam_path.actions || []).slice(0, 2).map(a => ' ' + esc(a)).join('')}
    </div>` : ''}
    ${pipelineBanner(d.pipeline || (SUM.franchise && SUM.franchise.pipeline))}

    <div class="gauges">
      ${g.map(x => `
        <div class="gauge ${x.status}" onclick="clickGauge('${x.key}')"
             title="Click for what moved and one next step">
          <div class="glabel">${esc(x.label)}</div>
          <div class="ghead">${esc(x.head)}</div>
          <div class="gdetail">${esc(x.detail)}</div>
        </div>`).join('')}
    </div>

    ${tut.active ? renderTutorial(tut) : ''}

    ${d.cards.length ? `<h3>From your advisors</h3>
      <div class="advcards">${d.cards.map(renderAdvCard).join('')}</div>` :
      (allGreen ? `<div class="panel" style="margin-top:10px"><span class="sub">
        Your advisors have nothing urgent. All six lights are green — bank the
        profits, or go make some trouble on the Lending and Markets tabs.</span></div>` : '')}

    <div class="panel tight" style="margin:10px 0">
      <button class="primary" onclick="advance('until')">Play until something needs you</button>
      <label class="sub" style="margin-left:12px;white-space:nowrap">
        <input type="checkbox" ${d.stop_on_quarter ? 'checked' : ''}
          style="width:auto;margin-right:4px"
          onchange="setPol('policies.stop_on_quarter', this.checked)">
        Stop every quarter
      </label>
      <span class="sub"> — runs the clock. Your credit box (Lending) handles matching memos. Stops on exams, runs, fraud, overnight holes, and anything outside the box. Quarter close goes to the log unless you opt in.</span>
    </div>
    <h3>Inbox — decisions waiting on you</h3>
    <div class="panel">
      ${nothingPending ? '<span class="sub">Empty. Advance the clock and the world will bring you problems.</span>' : ''}
      ${inbox.events.map(ev => `<div class="newsitem block">
          <span class="nd">${esc(ev.date)}</span><b>${esc(ev.title)}</b>
          <button class="small primary" onclick="openEvent(${ev.id})">Open</button>
        </div>`).join('')}
      ${inbox.loans.map(a => `<div class="newsitem">
          <span class="nd">loan</span>${esc(a.name)} wants <b>${fm(a.amount)}</b>
          (${esc(a.product.toUpperCase())}, grade ${a.tier}, ${a.days_left} days to answer)
          <button class="small" onclick='showMemo(${jattr(a)})'>Read the memo</button>
        </div>`).join('')}
      ${inbox.fraud.map(c => `<div class="newsitem">
          <span class="nd">fraud</span>Case #${c.id}: ${esc(c.kind.replace('_', ' '))} —
          ${esc(c.name)} (${fm(c.amount)} at risk)
          <button class="small primary" onclick="act('resolve_fraud_case',{case_id:${c.id},choice:'act'})">Act now</button>
          <button class="small" onclick="act('resolve_fraud_case',{case_id:${c.id},choice:'monitor'})">Watch it</button>
        </div>`).join('')}
    </div>`;
}

function renderTutorial(tut) {
  const next = tut.steps.find(s => !s.done);
  return `<div class="panel tutorial">
    <h3 style="margin-top:0">Your first year — a guided tour
      <button class="small" style="float:right" onclick="act('tutorial_off',{})">Skip the tour</button></h3>
    ${tut.steps.map(s => `
      <div class="tutstep ${s.done ? 'done' : (next && s.id === next.id ? 'now' : '')}">
        <span class="tutmark">${s.done ? '✓' : '○'}</span>
        <div><b>${esc(s.title)}</b>
          ${(!s.done && next && s.id === next.id) ? `<div class="sub">${esc(s.text)}</div>
            <div style="margin-top:4px">
              ${s.id === 'welcome'
                ? `<button class="small primary" onclick="clickGauge('earnings')">Show me a health light</button>`
                : `<button class="small primary" onclick="switchTab('${s.tab}')">Take me there</button>`}
              ${s.id !== 'exam' && s.id !== 'welcome' ? `<button class="small" onclick="act('tutorial_ack',{step_id:'${s.id}'})">Mark done</button>` : ''}
            </div>` : ''}
        </div>
      </div>`).join('')}
  </div>`;
}

async function clickGauge(key) {
  try { await api('/api/action', { action: 'tutorial_ack', payload: { step_id: 'welcome' } }); }
  catch (e) { /* tour may be off */ }
  SUM = await api('/api/summary');
  renderTopbar();
  renderFranchise();
  renderNav();
  const d = await section('desk');
  if (TAB === 'desk') await tabDesk($('main'));
  const g = (d.gauges || []).find(x => x.key === key);
  if (g) showGaugeDrill(g, d.cards || []);
}

function showGaugeDrill(g, cards) {
  const statusWord = g.status === 'g' ? 'Fine' : g.status === 'y' ? 'Watch' : 'Trouble';
  const match = (cards || []).find(c => c.tab === g.tab);
  let actionHtml = '';
  if (match && match.actions && match.actions[0]) {
    const a = match.actions[0];
    actionHtml = `<p class="sub" style="margin-top:10px">From your advisors: ${esc(match.title)}</p>
      <button class="primary small" onclick='closeText();doSteps(${jattr(match.id)}, ${jattr(a.steps)})'>${esc(a.label)}</button>`;
  }
  const html = `<div class="memoform">
      <div class="memorow"><span class="k">Status</span>
        <span class="v"><b>${esc(g.head)}</b> — ${statusWord}</span></div>
      <p style="margin-top:8px">${esc(g.detail)}</p>
      <p class="moved">${esc(g.moved || 'Nothing to compare yet.')}</p>
      ${actionHtml}
    </div>`;
  showHtml(g.label, html, [
    ['Open the full book', `closeText();switchTab('${g.tab}')`, 'primary']
  ]);
}

function renderAdvCard(c) {
  const btns = c.actions.map((a, i) =>
    `<button class="primary small" onclick='doSteps(${jattr(c.id)}, ${jattr(a.steps)})'>${esc(a.label)}</button>`
  ).join(' ');
  return `<div class="advcard sev${c.sev}">
    <div class="advtitle">${esc(c.title)}</div>
    <div class="advtext">${esc(c.text)}</div>
    <div class="btnrow" style="margin-top:8px">
      ${btns}
      <button class="small" onclick='showWhy(${jattr(c)})'>Show me why</button>
      <button class="small" onclick="dismissCard('${c.id}')">Ignore</button>
    </div>
  </div>`;
}

function showWhy(c) {
  showText(c.title, esc(c.learn),
    [['Take me to the ' + c.tab + ' tab', `closeText();switchTab('${c.tab}')`, 'primary']]);
}

async function dismissCard(id) {
  try {
    await api('/api/action', { action: 'advisor_dismiss', payload: { card_id: id } });
    toast('Noted. Your advisor will drop it for a while.');
    await refresh();
  } catch (e) { toast(String(e), true); }
}

async function doSteps(cardId, steps) {
  if (BUSY) return;
  BUSY = true;
  const notes = [];
  try {
    for (const s of steps) {
      if (s.kind === 'goto') { TAB = s.tab; REVEALED.add(s.tab); continue; }
      if (s.kind === 'set') {
        await api('/api/set', { path: s.path, value: s.value });
        notes.push('Policy: ' + String(s.path).split('.').pop());
      } else {
        const r = await api('/api/action', { action: s.action, payload: s.payload });
        if (r.result && r.result.message) notes.push(r.result.message);
      }
    }
    await api('/api/action', { action: 'advisor_dismiss', payload: { card_id: cardId } });
    toast(notes.length ? notes.join(' · ') : 'Done. (You could have set this by hand.)');
  } catch (e) {
    toast(notes.length ? ('Partial: ' + notes.join(' · ') + ' — then: ' + e) : String(e), true);
  }
  finally { BUSY = false; }
  await refresh();
}

/* ---------------- Dashboard ---------------- */
async function tabDashboard(m) {
  const b = SUM.bank, mt = SUM.metrics || {}, e = SUM.econ, reg = SUM.regulation;
  const crisis = SUM.crisis || {};
  let warn = '';
  if (SUM.audit_alarm)
    warn += `<div class="banner red">AUDIT ALARM: the books do not balance. ${esc(SUM.audit_alarm.problems.join('; '))}</div>`;
  if (crisis.run_active)
    warn += `<div class="banner red">DEPOSIT RUN IN PROGRESS — day ${crisis.run_days}. Rumor level ${pct(crisis.rumor, 0)}. Get liquidity. Now.</div>`;
  else if (crisis.rumor > 0.25)
    warn += `<div class="banner amber">Depositors are nervous (rumor ${pct(crisis.rumor, 0)}). Watch your uninsured share and capital.</div>`;
  if (reg.orders && reg.orders.length)
    warn += `<div class="banner amber">Enforcement actions: ${esc(reg.orders.join(' · '))}</div>`;
  if (e.recession)
    warn += `<div class="banner amber">The economy is in recession (GDP ${e.gdp.toFixed(1)}%, unemployment ${e.unemployment}%).</div>`;

  m.innerHTML = `
    ${warn}
    <div class="cards">
      ${card('Total assets', fmc(b.assets))}
      ${card('Loans', fmc(b.loans), dt('ldr') + ' ' + (mt.loan_to_deposit != null ? mt.loan_to_deposit.toFixed(2) : '—'))}
      ${card('Deposits', fmc(b.deposits), dt('uninsured') + ' ' + pct(mt.uninsured_pct, 0))}
      ${card('Equity', fmc(b.equity), dt('tbv') + ' ' + fm(mt.tbv_per_share))}
      ${card('Net income (TTM)', fmc(mt.net_income_ttm), 'MTD ' + fmc(b.ni_mtd), cls(mt.net_income_ttm))}
      ${card(dt('roa'), mt.earnings_ready === false || mt.roa == null
        ? '—' : pct(mt.roa) + ' / ' + pct(mt.roe, 1),
        mt.earnings_ready === false || mt.roa == null
          ? 'too early for a year rate'
          : peerNote('roa', mt.roa))}
      ${card(dt('nim'), pct(mt.nim), peerNote('nim', mt.nim) + ' · ' + dt('cof') + ' ' + pct(mt.cost_of_funds))}
      ${card(dt('eff'), pct(mt.efficiency, 0), peerNote('efficiency', mt.efficiency, true))}
      ${card(dt('npa'), pct(mt.npa_ratio), peerNote('npa_ratio', mt.npa_ratio, true) + ' · ' + dt('reserves') + ' ' + pct(mt.reserve_coverage))}
      ${card(dt('cet1'), pct(mt.cet1_ratio, 1), dt('leverage') + ' ' + pct(mt.leverage_ratio, 1))}
      ${card(dt('liquidity'), pct(mt.liquidity_ratio, 1), 'of assets · 8%+ is safe')}
      ${card('Fed funds', pct(e.fed_funds), '10y ' + pct(curveAt(e.curve, 10)))}
    </div>
    <div class="grid g3">
      <div class="panel"><canvas id="ch-assets" class="chart"></canvas></div>
      <div class="panel"><canvas id="ch-ni" class="chart"></canvas></div>
      <div class="panel"><canvas id="ch-curve" class="chart"></canvas></div>
    </div>
    <div class="grid g2" style="margin-top:12px">
      <div class="panel">
        <h3>The economy</h3>
        <div class="kv">
          <span class="k">GDP growth</span><span class="v ${cls(e.gdp)}">${e.gdp.toFixed(1)}%</span>
          <span class="k">Inflation</span><span class="v">${e.inflation.toFixed(1)}%</span>
          <span class="k">Unemployment</span><span class="v">${e.unemployment.toFixed(1)}%</span>
          <span class="k">Consumer confidence</span><span class="v">${e.conf.toFixed(0)}</span>
          <span class="k">Credit stress</span><span class="v ${e.stress > 0.3 ? 'neg' : ''}">${pct(e.stress, 0)}</span>
          <span class="k">Equity index</span><span class="v">${e.equity_index.toLocaleString()}</span>
          <span class="k">Housing index</span><span class="v">${e.housing.toFixed(0)}</span>
          <span class="k">WTI crude</span><span class="v">$${e.oil.toFixed(0)}/bbl</span>
          <span class="k">Natural gas</span><span class="v">$${e.natgas.toFixed(2)}</span>
          <span class="k">Cattle</span><span class="v">$${e.cattle.toFixed(0)}/cwt</span>
          <span class="k">Cotton</span><span class="v">$${e.cotton.toFixed(2)}/lb</span>
        </div>
      </div>
      <div class="panel">
        <h3>This month</h3>
        ${renderDigest(SUM.digest)}
        <div class="sub" style="margin-top:8px">Full log is on the Events tab.</div>
      </div>
    </div>`;
  const hist = (await section('reports')).metrics_history;
  metricChart('ch-assets', hist, 'assets', { title: 'Total assets', map: v => v / 100, yfmt: v => '$' + fmtCompact(v), color: '#58a6ff' });
  metricChart('ch-ni', hist, 'net_income_ttm', { title: 'Net income (TTM)', map: v => v / 100, yfmt: v => '$' + fmtCompact(v), color: '#46c78c', zero: true });
  drawChart($('ch-curve'), [{
    name: 'yield', color: '#e0b050',
    data: SUM.econ.curve.map(([t, y]) => ({ x: t, y: y * 100 })),
  }], { title: 'Yield curve', yfmt: v => v.toFixed(1) + '%', xfmt: v => v + 'y' });
}

function card(k, v, d, extraCls) {
  return `<div class="card"><div class="k">${k}</div>
    <div class="v ${extraCls || ''}">${v}</div>${d ? `<div class="d">${d}</div>` : ''}</div>`;
}

function peerNote(key, mine, lowerBetter) {
  const p = SUM && SUM.peer_avg;
  if (!p || p[key] == null || mine == null) return '';
  const better = lowerBetter ? mine <= p[key] : mine >= p[key];
  return `<span class="${better ? 'pos' : 'warn'}" title="Average of the ${p.n} rival banks closest to your size${lowerBetter ? '. Lower is better.' : ''}">peers ~${pct(p[key], key === 'efficiency' ? 0 : 2)}</span>`;
}
function curveAt(curve, tenor) {
  const p = curve.find(c => c[0] === tenor);
  return p ? p[1] : null;
}
function renderDigest(d) {
  if (!d) return '<span class="sub">Advance a month to get a digest. The firehose lives on Events.</span>';
  const bits = [
    `<div>${esc(d.econ)}</div>`,
    `<div class="kv" style="margin-top:6px">
      <span class="k">Month’s profit</span><span class="v ${cls(d.ni)}">${fm(d.ni)}</span>
      <span class="k">Deposits</span><span class="v ${cls(d.dep_flow)}">${d.dep_flow >= 0 ? '+' : ''}${fmc(d.dep_flow)}</span>
      <span class="k">Loans</span><span class="v ${cls(d.loan_flow)}">${d.loan_flow >= 0 ? '+' : ''}${fmc(d.loan_flow)}</span>
      <span class="k">${MODE === 'owner' ? 'Loans vs deposits' : 'LDR'}</span><span class="v">${d.ldr != null ? d.ldr.toFixed(2) : '—'}</span>
    </div>`,
    d.local ? `<div style="margin-top:6px">${esc(d.local)}</div>` : '',
    d.exam ? `<div class="warn" style="margin-top:6px">${esc(d.exam)}</div>` : '',
    d.lending ? `<div style="margin-top:8px">${esc(d.lending)}</div>` : '',
    d.lending_book && (d.lending_book.new || []).length
      ? `<div class="sub" style="margin-top:4px">${(d.lending_book.new || []).slice(0, 8).map(n =>
          `${esc(n.name)}${(n.count || 1) > 1 ? ' ×' + n.count : ''} ${fm(n.amount)}`).join(' · ')}${
          (d.lending_book.new_count || 0) > 8 ? ' · …' : ''} — full list on Lending.</div>`
      : '',
    d.window ? `<div class="sub">Window used ${d.window} time${d.window === 1 ? '' : 's'} this charter.</div>` : '',
    d.fraud ? `<div class="sub">${d.fraud} fraud case${d.fraud === 1 ? '' : 's'} still open.</div>` : '',
  ];
  return bits.filter(Boolean).join('');
}

function newsList(log) {
  return (log || []).slice().reverse().map(ev =>
    `<div class="newsitem ${ev.blocking ? 'block' : ''}">
       <span class="nd">${esc(ev.date)}</span>${esc(ev.title)}
       ${ev.text ? `<a onclick='showText(${JSON.stringify(esc(ev.title))}, ${JSON.stringify(esc(ev.text))})'> …more</a>` : ''}
     </div>`).join('') || '<span class="sub">Quiet so far.</span>';
}

/* ---------------- consequence previews ----------------
   Live "what will this do" estimates, computed from the same constants
   the engine uses (served in /api/summary so they can't drift). Shown
   while you type, BEFORE the change applies. */
function prevBox(id, text) {
  const el = $(id);
  if (el) el.innerHTML = text ? '≈ ' + text : '';
}
function ratioTxt(r) {
  const p = (r - 1) * 100;
  return (p >= 0 ? '+' : '') + p.toFixed(0) + '%';
}
function prevDep(product, val, cur, balance) {
  const m = SUM.model, bp = parseInt(val);
  if (isNaN(bp)) return prevBox('prev-deposits', '');
  const ratio = Math.exp((m.dep_sens[product] || 0) * (bp - cur) / 100);
  const cost = Math.round(balance * (bp - cur) / 10000);
  prevBox('prev-deposits',
    `${DEP_LABELS[product]} at ${bp >= 0 ? '+' : ''}${bp}bp: balances drift toward ` +
    `${ratioTxt(ratio)} of today's target; interest cost ${cost >= 0 ? '+' : '−'}` +
    `${fmc(Math.abs(cost))}/yr on current balances. Hot money (money market, short ` +
    `CDs) moves in weeks; checking barely moves. Press Enter or click away to apply.`);
}
function prevSpread(product, val, cur) {
  const m = SUM.model, bp = parseInt(val);
  if (isNaN(bp)) return prevBox('prev-lending', '');
  const vol = Math.exp(-m.loan_price_k * (bp - cur) / 100);
  prevBox('prev-lending',
    `${PRODUCT_LABELS[product]} at ${bp >= 0 ? '+' : ''}${bp}bp vs market: new-loan ` +
    `volume ${ratioTxt(vol)}, and each new loan yields ${bp - cur >= 0 ? '+' : ''}` +
    `${bp - cur}bp more than now. Loans already on the books keep their pricing. ` +
    `Press Enter or click away to apply.`);
}
async function applyStd(product, v, cur) {
  const m = SUM.model, t = parseInt(v);
  const vol = m.tight_mult[t] / m.tight_mult[cur];
  const q = m.quality[t] / m.quality[cur];
  await setPol('loans.standards.' + product, t);
  toast(`${PRODUCT_LABELS[product]} standards: new-loan volume ${ratioTxt(vol)} from here, ` +
        `and future loss rates on loans written FROM NOW ON ${ratioTxt(q)}. ` +
        `Loans already booked keep the standards they were written under.`);
}
function prevOD(val, cur, accounts) {
  const fee = Math.round(parseFloat(val) * 100);
  if (isNaN(fee)) return prevBox('prev-fees', '');
  const dInc = Math.round(accounts * 0.055 * (fee - cur) * 12);
  const drag = Math.max(0, (fee - 3000) / 1000 * 0.01);
  const dragCur = Math.max(0, (cur - 3000) / 1000 * 0.01);
  prevBox('prev-fees',
    `Overdraft at $${(fee / 100).toFixed(0)}: fee income ${dInc >= 0 ? '+' : '−'}` +
    `${fmc(Math.abs(dInc))}/yr at today's account count; customer-annoyance drag on ` +
    `deposit growth ${pct(drag, 1)} (now ${pct(dragCur, 1)}). High fees also feed ` +
    `examiner criticism. Press Enter to apply.`);
}

/* ---------------- Lending ---------------- */
const PRODUCT_LABELS = {
  auto: 'Auto', mortgage: 'Mortgage', heloc: 'HELOC', credit_card: 'Credit card',
  small_business: 'Small business', ci: 'C&I', cre: 'CRE',
  construction: 'Construction', ag: 'Agriculture', sba: 'SBA',
};

async function tabLending(m) {
  const q = ['name=lending'];
  if (TAPE_F.product) q.push('tape_product=' + encodeURIComponent(TAPE_F.product));
  if (TAPE_F.status) q.push('tape_status=' + encodeURIComponent(TAPE_F.status));
  if (TAPE_F.offset) q.push('tape_offset=' + TAPE_F.offset);
  const d = await api('/api/section?' + q.join('&'));
  SEC.lending = d;
  const port = d.portfolio;
  const prods = Object.keys(PRODUCT_LABELS).filter(p => d.products_enabled.includes(p));
  m.innerHTML = `
    <h2>Lending</h2>
    <div class="panel">
      <h3>Decisions waiting — read the memo</h3>
      ${d.queue.length ? `<table><tr><th>Borrower</th><th>Product</th><th class="r">Amount</th>
        <th class="r">Rate</th><th>Tier</th><th class="r">${dt('dscr')}</th><th class="r">${dt('ltv')}</th>
        <th>Expires</th><th></th></tr>
        ${d.queue.map(a => `<tr class="click" onclick='showMemo(${jattr(a)})'>
          <td>${esc(a.name)}</td><td>${PRODUCT_LABELS[a.product] || a.product}</td>
          <td class="r">${fm(a.amount)}</td><td class="r">${pct(a.rate)}</td>
          <td>${a.tier}</td><td class="r">${a.dscr.toFixed(2)}x</td>
          <td class="r">${Math.round(a.ltv * 100)}%</td><td>${a.days_left}d</td>
          <td><button class="small" onclick="event.stopPropagation();showMemo(${jattr(a)})">Memo</button>
              <button class="small primary" onclick="event.stopPropagation();act('approve_loan',{app_id:${a.id}})">Approve</button>
              <button class="small" onclick="event.stopPropagation();act('counter_loan',{app_id:${a.id}})">Counter</button>
              <button class="small" onclick="event.stopPropagation();act('participate_loan',{app_id:${a.id}})">Participate</button>
              <button class="small danger" onclick="event.stopPropagation();act('decline_loan',{app_id:${a.id}})">Decline</button></td>
        </tr>`).join('')}</table>`
        : '<span class="sub">No applications pending. The next name lands on Your Desk.</span>'}
    </div>

    <div class="cards" style="margin-top:12px">
      ${card('Loan portfolio', fmc(Object.values(port).reduce((a, x) => a + x.balance, 0)))}
      ${card('Nonperforming', fmc(d.npl_balance))}
      ${card('Allowance (ACL)', fmc(d.allowance), 'CECL requires ' + fmc(d.reserve_required))}
      ${card('Monthly capacity', fmc(d.capacity), 'originated ' + fmc(d.originated_mtd))}
      ${card('Pending approvals', String(d.queue.length))}
    </div>
    ${renderMonthBook(d.month_book)}

    <div class="grid g2">
    <div class="panel">
      <h3>${dt('stance', 'Book appetite')}</h3>
      <div class="helptip">You pick a stance per line — not a spreadsheet. Starve / Hold lock today’s mix. Grow / Hunt have no cap. Preview first; loans already booked keep their rate and standards.</div>
      ${renderMixBar(d.mix || [], prods)}
      <table><tr><th>Product</th><th class="r">Mkt rate</th><th>${dt('stance')}</th>
        <th class="r">Balance</th><th class="r">Mix</th>
        <th class="r">30-89dpd</th><th class="r">${dt('npa', MODE === 'owner' ? 'Not paying' : 'NPL')}</th></tr>
      ${prods.map(p => {
        const st = port[p] || { balance: 0, npl: 0, d3090: 0 };
        const row = (d.mix || []).find(x => x.product === p) || {};
        const stance = row.stance || (d.stances || {})[p] || 'hold';
        const mixPct = Math.round((row.pct || 0) * 100);
        return `<tr>
          <td>${PRODUCT_LABELS[p]}</td>
          <td class="r">${pct(d.market_rates[p])}</td>
          <td>${stanceButtons(p, stance)}</td>
          <td class="r">${fmc(st.balance)}</td>
          <td class="r">${mixPct}%${row.limit ? ` <span class="sub">cap ${row.limit}%</span>` : ''}</td>
          <td class="r ${st.d3090 > 0 ? 'warn' : ''}">${fmc(st.d3090)}</td>
          <td class="r ${st.npl > 0 ? 'neg' : ''}">${fmc(st.npl)}</td>
        </tr>`;
      }).join('')}
      </table>
      <div class="prevbar" id="prev-lending"></div>
    </div>
    <div class="panel">
      <h3>Credit policy box</h3>
      <div class="helptip">Play until uses this box. It is your policy, not the advisor clicking for you. Memos outside the box still stop the clock.</div>
      <div class="ctl"><label>Box</label>
        <select onchange="setPol('loans.credit_box.enabled', this.value === 'true')">
          <option value="false" ${!(d.credit_box && d.credit_box.enabled)?'selected':''}>Off — every large credit comes to the desk</option>
          <option value="true" ${d.credit_box && d.credit_box.enabled?'selected':''}>On — approve A/B, counter C, participate if over the hold</option>
        </select></div>
      <div class="ctl"><label>Max hold $</label>
        <input type="number" id="box-hold" value="${((d.credit_box && d.credit_box.max_hold) || 200000000) / 100}">
        <button class="small" onclick="setPol('loans.credit_box.max_hold', moneyIn('box-hold'))">Set</button></div>
      <div class="ctl"><label>If over the hold</label>
        <select onchange="setPol('loans.credit_box.participate_over', this.value === 'true')">
          <option value="true" ${!(d.credit_box) || d.credit_box.participate_over !== false ? 'selected' : ''}>Participate — keep a slice, sell the rest</option>
          <option value="false" ${d.credit_box && d.credit_box.participate_over === false ? 'selected' : ''}>Stop the clock — I want the memo</option>
        </select></div>
      <h3>Manual approval</h3>
      <div class="ctl"><label>Manual approval above $</label>
        <input type="number" id="apthr" value="${d.approval_threshold / 100}">
        <button class="small" onclick="setPol('loans.approval_threshold', moneyIn('apthr'))">Set</button></div>
      <div class="ctl"><label>Queue policy</label>
        <select onchange="setPol('loans.auto_policy', this.value)">
          <option value="queue" ${d.auto_policy==='queue'?'selected':''}>Send to my desk</option>
          <option value="approve_ab" ${d.auto_policy==='approve_ab'?'selected':''}>Auto-approve A/B tiers</option>
          <option value="decline" ${d.auto_policy==='decline'?'selected':''}>Auto-decline all</option>
        </select></div>
      <div class="ctl"><label>Sell new mortgages to secondary %</label>
        <input type="number" min="0" max="90" value="${Math.round(d.mortgage_sale_frac * 100)}"
          onchange="setPol('loans.mortgage_sale_frac', parseFloat(this.value)/100)"></div>
      <div class="helptip">Selling new 30-year mortgages to the agencies turns them
        into cash this month (and a small gain) instead of a long asset. Raise this
        when loans are outrunning deposits. You give up the interest.</div>
      ${d.mortgage_preview ? `<div class="sub">At ${Math.round((d.mortgage_preview.frac || 0) * 100)}%
        of an estimated ${fm(d.mortgage_preview.est_month_orig)} next month:
        sell ${fm(d.mortgage_preview.sold)}, keep ${fm(d.mortgage_preview.kept)},
        gain about ${fm(d.mortgage_preview.gain)}.</div>` : ''}
      ${d.hire_preview ? `<div class="sub" style="margin-top:8px">Another lender: first-year book NI about ${fm(d.hire_preview.extra_ni)} vs fully-loaded pay ${fm(d.hire_preview.cost)} — ${d.hire_preview.positive ? 'covers the seat' : 'loses money at this scale'}.</div>` : ''}
      <div class="sub" style="margin-top:6px">Approved: ${d.stats.approved_apps}
        · declined: ${d.stats.declined_apps}
        · countered: ${d.stats.countered_apps || 0}
        · participated: ${d.stats.participated_apps || 0}
        · box handled: ${d.stats.box_handled || 0}</div>

      <h3>Sell a seasoned book</h3>
      <div class="helptip">A strip you already own, sold to a living rival. New mortgages still use the slider above. This is not a tape — you cannot buy someone else's loans here.</div>
      ${(d.loan_sales || []).length ? `<table><tr><th>Book</th><th>Town</th><th class="r">Par</th>
        <th class="r">Price</th><th>Buyer</th><th></th></tr>
        ${d.loan_sales.map(s => `<tr>
          <td>${esc(s.label)}</td>
          <td>${esc(s.market_name || '')}</td>
          <td class="r">${fm(s.par)}</td>
          <td class="r ${cls(s.gain)}">${fm(s.price)} <span class="sub">${(s.px_par * 100).toFixed(1)}¢</span></td>
          <td>${esc(s.buyer_name)}</td>
          <td><button class="small" onclick='confirmLoanSale(${jattr(s)})'>Review</button></td>
        </tr>`).join('')}</table>`
        : '<span class="sub">No performing strip of $250k+ right now.</span>'}

      <h3>OREO (foreclosed real estate)</h3>
      ${d.oreo.length ? `<table><tr><th>Market</th><th class="r">Carrying value</th><th class="r">Months held</th></tr>
        ${d.oreo.map(o => `<tr><td>${esc(o.market)}</td><td class="r">${fm(o.value)}</td><td class="r">${o.months_held}</td></tr>`).join('')}</table>`
        : '<span class="sub">None. Keep it that way.</span>'}
    </div>
    </div>

    <div class="panel" style="margin-top:12px">
      <h3>The tape — every loan on the books</h3>
      ${renderTape(d, prods)}
    </div>`;
}

function renderMonthBook(b) {
  if (!b) return `<div class="panel" style="margin-top:12px">
    <h3>Last month on the tape</h3>
    <span class="sub">Advance a month. You will see every note that booked, declined, paid off, or went delinquent.</span>
  </div>`;
  const names = (b.new || []).map(n => `<tr class="click" onclick='showNote(${jattr({
      ...n, balance: n.amount, rate: 0, status: "current",
      market_name: n.market_name, vint: ""})})'>
      <td>${esc(n.name)}${(n.count || 1) > 1 ? ` <span class="sub">×${n.count}</span>` : ''}</td>
      <td>${PRODUCT_LABELS[n.product] || n.product || ''}</td>
      <td>${esc(n.market_name || n.market || '')}</td>
      <td class="r">${fm(n.amount)}</td>
      <td>${esc(n.tier || '')}</td></tr>`).join('');
  const extra = [];
  (b.declined || []).forEach(n => extra.push(`Declined ${esc(n.name)} (${fm(n.amount)})`));
  (b.sold || []).forEach(n => extra.push(`Sold ${esc(n.name)} (${fm(n.amount)})`));
  (b.paid_off || []).forEach(n => extra.push(`Left the book: ${esc(n.name)}`));
  (b.status_changes || []).forEach(n => extra.push(`${esc(n.name)}: ${esc(n.from_status || 'current')} → ${esc(n.status)}`));
  return `<div class="panel" style="margin-top:12px">
    <h3>Last month on the tape — ${esc(b.month || '')}</h3>
    <div>${esc(b.owner || '')}</div>
    ${names ? `<table style="margin-top:8px"><tr><th>Borrower</th><th>Product</th><th>Town</th>
      <th class="r">Amount</th><th>Tier</th></tr>${names}</table>` : ''}
    ${b.new_more ? `<div class="sub">${b.new_more} more new notes on the tape below.</div>` : ''}
    ${extra.length ? `<div class="sub" style="margin-top:6px">${extra.slice(0, 12).join(' · ')}</div>` : ''}
  </div>`;
}

const STANCE_META = {
  starve: { l: 'Starve', t: 'Price up, fortress, lock today’s mix. Run it off.' },
  hold:   { l: 'Hold',   t: 'Match the street, standard underwriting. Click Apply to lock today’s mix.' },
  grow:   { l: 'Grow',   t: 'Shade price, ease a notch, no cap.' },
  hunt:   { l: 'Hunt',   t: 'Buy share. The vintage will remember.' },
};
const MIX_COLOR = {
  auto: '#58a6ff', mortgage: '#46c78c', heloc: '#3fb37f', credit_card: '#7d8b99',
  small_business: '#e0b050', ci: '#c9a227', cre: '#e06060', construction: '#d4894a',
  ag: '#46c78c', sba: '#58a6ff',
};
let TAPE_F = { product: '', status: '', offset: 0 };

function stanceButtons(product, current) {
  return `<div class="stances">${['starve','hold','grow','hunt'].map(s => {
    const m = STANCE_META[s];
    const on = current === s ? ' on' : '';
    return `<button class="small ${s}${on}" title="${esc(m.t)}"
      onclick="clickStance('${product}','${s}')">${m.l}</button>`;
  }).join('')}${current === 'custom' ? ' <span class="sub">custom</span>' : ''}</div>`;
}

function renderMixBar(mix, prods) {
  const rows = (mix || []).filter(x => x.balance > 0 && prods.includes(x.product));
  const tot = rows.reduce((a, x) => a + x.balance, 0) || 1;
  if (!rows.length) return '';
  return `<div class="mixbar">${rows.map(x =>
    `<i style="width:${(x.balance / tot * 100).toFixed(1)}%;background:${MIX_COLOR[x.product] || '#4d5a68'}"
        title="${esc(PRODUCT_LABELS[x.product] || x.product)} ${fm(x.balance)}"></i>`
  ).join('')}</div>
  <div class="mixleg">${rows.map(x =>
    `<span><i style="display:inline-block;width:8px;height:8px;border-radius:2px;background:${MIX_COLOR[x.product] || '#4d5a68'};margin-right:4px"></i>${esc(PRODUCT_LABELS[x.product] || x.product)} <b>${Math.round(x.pct * 100)}%</b></span>`
  ).join('')}</div>`;
}

async function clickStance(product, stance) {
  try {
    const r = await api('/api/action', { action: 'preview_loan_stance',
      payload: { product, stance } });
    const prev = r.result || r;
    const el = $('prev-lending');
    if (el) el.innerHTML = `${esc(prev.owner || '')}
      <button class="small primary" onclick="commitStance('${product}','${stance}')">Apply ${STANCE_META[stance].l}</button>`;
  } catch (e) { toast(String(e), true); }
}

async function commitStance(product, stance) {
  try {
    const r = await api('/api/action', { action: 'set_loan_stance',
      payload: { product, stance } });
    toast((r.result && r.result.message) || (STANCE_META[stance].l + ' applied'));
    await refresh();
  } catch (e) { toast(String(e), true); }
}

function renderTape(d, prods) {
  const t = d.tape || { rows: [], total: 0, named: 0, strips: 0, large: 0, dollars: 0 };
  const filt = `<div class="ctl"><label>Product</label>
      <select onchange="tapeFilter('product', this.value)">
        <option value="">All</option>
        ${prods.map(p => `<option value="${p}" ${TAPE_F.product===p?'selected':''}>${PRODUCT_LABELS[p]}</option>`).join('')}
      </select></div>
    <div class="ctl"><label>Status</label>
      <select onchange="tapeFilter('status', this.value)">
        ${[['','All'],['current','Current'],['d30','30 dpd'],['d60','60 dpd'],['d90','90 dpd'],['npl','Not paying']]
          .map(([v,l]) => `<option value="${v}" ${TAPE_F.status===v?'selected':''}>${l}</option>`).join('')}
      </select></div>
    <span class="sub">${t.total} loans · ${fm(t.dollars)} · ${t.named} named · ${t.strips} strips · ${t.large} large credits</span>`;
  if (!t.rows.length) {
    return `${filt}<div class="sub" style="margin-top:8px">The tape is empty. That should not happen on a living book.</div>`;
  }
  const more = t.total > t.rows.length
    ? `<div class="sub" style="margin-top:6px">Showing ${t.rows.length} of ${t.total}. Filter to narrow, or troubled names sort first.</div>` : '';
  return `${filt}
    <table style="margin-top:8px"><tr><th>Borrower</th><th>Product</th><th>Town</th>
      <th class="r">Balance</th><th class="r">Rate</th><th>Tier</th><th>Status</th><th></th></tr>
      ${t.rows.map(l => `<tr class="click" onclick='showNote(${jattr(l)})'>
        <td>${esc(l.name)}${l.kind==='strip' ? ` <span class="sub">×${l.count}</span>` : ''}</td>
        <td>${PRODUCT_LABELS[l.product] || l.product}</td>
        <td>${esc(l.market_name || l.market)}</td>
        <td class="r">${fm(l.balance)}</td>
        <td class="r">${pct(l.rate)}</td>
        <td>${l.tier}</td>
        <td>${statusPill(l.status)}</td>
        <td>${(() => {
          const sale = (d.loan_sales || []).find(s => s.kind === 'large' && s.loan_id === l.id);
          return sale ? `<button class="small" onclick="event.stopPropagation();confirmLoanSale(${jattr(sale)})">Sell</button>` : '';
        })()}</td></tr>`).join('')}</table>${more}`;
}

function tapeFilter(key, value) {
  TAPE_F[key] = value || '';
  TAPE_F.offset = 0;
  if (TAB === 'lending') renderTab();
}

function showNote(l) {
  const strip = l.kind === 'strip'
    ? `<p class="sub">${l.count} similar ${PRODUCT_LABELS[l.product] || l.product} notes in this vintage, counted together so the save stays playable. The dollars are real.</p>`
    : (l.kind === 'large'
      ? '<p class="sub">Individually underwritten. You signed the memo.</p>'
      : '<p class="sub">A loan on your books. Flow-book notes still roll with their vintage; the dollars here match that pool.</p>');
  showHtml(l.name, `<div class="memoform">
    ${strip}
    <div class="memorow"><span class="k">Product</span><span class="v">${esc(PRODUCT_LABELS[l.product] || l.product)}</span></div>
    <div class="memorow"><span class="k">Town</span><span class="v">${esc(l.market_name || l.market)}</span></div>
    <div class="memorow"><span class="k">Balance</span><span class="v">${fm(l.balance)}</span></div>
    <div class="memorow"><span class="k">Rate</span><span class="v">${pct(l.rate)}</span></div>
    <div class="memorow"><span class="k">Tier</span><span class="v">${esc(l.tier)}</span></div>
    <div class="memorow"><span class="k">Status</span><span class="v">${statusPill(l.status)}</span></div>
    ${l.vint ? `<div class="memorow"><span class="k">Vintage</span><span class="v">${esc(l.vint)}</span></div>` : ''}
  </div>`);
}

function statusPill(s) {
  const map = { current: 'g', d30: 'y', d60: 'y', d90: 'r', npl: 'r' };
  return `<span class="pill ${map[s] || 'b'}">${esc(s.toUpperCase())}</span>`;
}

function confirmLoanSale(s) {
  const html = `<div class="memoform">
      <div class="who-name">${esc(s.label)}</div>
      <div class="sub">${esc(s.buyer_name || '')} · ${esc(s.market_name || '')}</div>
      <div class="memorow"><span class="k">Par sold</span><span class="v">${fm(s.par)}</span></div>
      <div class="memorow"><span class="k">Price</span><span class="v">${fm(s.price)} (${(s.px_par * 100).toFixed(1)} cents)</span></div>
      <div class="memorow"><span class="k">Gain / loss</span>
        <span class="v ${cls(s.gain)}">${fm(s.gain)}</span></div>
      <div class="memorow"><span class="k">Interest given up</span><span class="v">${fm(s.ni_year)}/yr</span></div>
      <div class="memorow"><span class="k">Loans vs deposits after</span>
        <span class="v">${((s.ldr_after || 0) * 100).toFixed(0)}%</span></div>
      <p class="moved">${esc(s.owner)}</p>
    </div>`;
  const payload = {kind: s.kind, product: s.product, market: s.market,
                   amount: s.par, loan_id: s.loan_id};
  showHtml('Sell this book — ' + s.label, html, [
    ['Sell to ' + (s.buyer_name || 'the buyer'),
     `closeText();act('sell_loans',${jattr(payload)})`, 'primary'],
  ]);
}

function showMemo(a) {
  const amt = a.amount || 0;
  const cp = a.counter_preview || {};
  const pp = a.participate_preview || {};
  const hold70 = cp.amount || Math.max(10000000, Math.round(amt * 0.70 / 1000000) * 1000000);
  const hold40 = pp.hold || Math.max(10000000, Math.round(amt * 0.40 / 1000000) * 1000000);
  const extra = cp.extra_bp || 100;
  const term = cp.term_m || Math.max(12, Math.round((a.term_m || 60) * 0.75));
  const ctrRate = cp.rate != null ? pct(cp.rate) : pct((a.rate || 0) + extra / 10000);
  const approveClass = a.can_fund === false ? 'danger' : 'primary';
  const approveLabel = a.can_fund === false ? 'Approve anyway' : 'Approve';
  const html = `<div class="memoform">
      <div class="who-name">${esc(a.name)}</div>
      <div class="sub">${esc(PRODUCT_LABELS[a.product] || a.product)} · grade ${esc(a.tier)}
        · ${fm(amt)} at ${pct(a.rate)} · ${a.term_m || 60} months
        · ${a.days_left} days to answer</div>
      <div class="memorow"><span class="k">Why them</span>
        <span class="v">${esc(a.why || 'A borrower in a market we serve.')}</span></div>
      <div class="memorow"><span class="k">${dt('dscr')}</span>
        <span class="v">${(a.dscr || 0).toFixed(2)}× — ${esc(a.dscr_gloss || '')}</span></div>
      <div class="memorow"><span class="k">${dt('ltv')}</span>
        <span class="v">${Math.round((a.ltv || 0) * 100)}% — ${esc(a.ltv_gloss || '')}</span></div>
      ${a.collateral ? `<div class="memorow"><span class="k">Collateral</span>
        <span class="v">${esc(a.collateral)}</span></div>` : ''}
      <div class="memorow"><span class="k">If we decline</span>
        <span class="v">They walk to ${esc(a.rival || 'a rival')}.</span></div>
      ${a.relationship_line ? `<div class="memorow"><span class="k">Relationship</span>
        <span class="v">${esc(a.relationship_line)}</span></div>` : ''}
      <div class="memorow"><span class="k">Policy</span>
        <span class="v">${esc(a.exception || 'Within published policy.')}</span></div>
      ${a.can_fund === false ? `<div class="banner amber" style="margin-top:10px">We do not have the cash to book this whole hold. Participate, raise deposits, or sell bonds.</div>` : ''}
      <div class="counterbox">
        <b>Counter before they walk</b>
        <p>Offer +${extra}bp (${ctrRate}), hold ${fm(hold70)}, ${term} months. They may take it or leave.</p>
        <p class="sub">Participate: we book ${fm(hold40)}; the rest is sold. Use this when cash cannot cover the whole hold.</p>
      </div>
      ${(!a.why && a.memo) ? `<pre class="memo-fallback" style="margin-top:10px">${esc(a.memo)}</pre>` : ''}
    </div>`;
  showHtml('Credit decision — ' + a.name, html,
    [[approveLabel, `act('approve_loan',{app_id:${a.id}});closeText()`, approveClass],
     ['Counter +100bp', `act('counter_loan',{app_id:${a.id}});closeText()`, ''],
     ['Participate 40%', `act('participate_loan',{app_id:${a.id}});closeText()`, ''],
     ['Decline', `act('decline_loan',{app_id:${a.id}});closeText()`, 'danger']],
    'wide');
}

/* ---------------- Deposits ---------------- */
const DEP_LABELS = {
  checking: 'Free checking', checking_int: 'Interest checking', savings: 'Savings',
  money_market: 'Money market', cd_3m: 'CD 3-month', cd_1y: 'CD 1-year',
  cd_2y: 'CD 2-year', cd_5y: 'CD 5-year',
};

function depositStance(d) {
  const mm = d.offsets_bp.money_market || 0;
  const cd = d.offsets_bp.cd_1y || 0;
  if (mm >= 25 || cd >= 25) return 'You are paying up for hot money.';
  if (mm <= -25 && cd <= -25) return 'You are cheap on deposits — balances will leak.';
  return 'You are near the market on the products that move.';
}

function depHotRow(d, t, p) {
  const mkt = p === 'checking' ? '—' : pct(d.market_rates[p] ?? d.market_rates.savings);
  const stance = p === 'checking' ? '—' :
    `<input type="number" step="5" min="-300" max="300" value="${d.offsets_bp[p]}"
      oninput="prevDep('${p}', this.value, ${d.offsets_bp[p]}, ${t[p]})"
      onchange="setPol('deposits.offsets_bp.${p}', parseInt(this.value))">`;
  return `<tr>
    <td>${DEP_LABELS[p]}</td>
    <td class="r"><b>${pct(d.effective_rates[p])}</b></td>
    <td class="r">${mkt}</td>
    <td class="r">${stance}</td>
    <td class="r">${fmc(t[p])}</td>
  </tr>`;
}

async function tabDeposits(m) {
  const d = await section('deposits');
  const t = d.totals;
  const hot = ['money_market', 'cd_1y', 'checking'];
  m.innerHTML = `
    <h2>Deposits</h2>
    ${runBanner(d.run || SUM.crisis)}
    <div class="panel">
      <p class="stance">${esc(depositStance(d))}</p>
      <h3>The products that move</h3>
      <table><tr><th>Product</th><th class="r">You pay</th><th class="r">Market</th>
        <th class="r">${dt('spread', MODE === 'owner' ? 'Your stance (bp)' : 'Offset bp')}</th>
        <th class="r">Balance</th></tr>
        ${hot.map(p => depHotRow(d, t, p)).join('')}
      </table>
      <div class="helptip">Money market and the 1-year CD reprice fastest. Checking is the cheap core — do not give it away.</div>
    </div>
    <div class="cards" style="margin-top:12px">
      ${card('Total deposits', fmc(t._total), t._accounts.toLocaleString() + ' accounts')}
      ${card('Cost of deposits', pct(d.cost_of_deposits))}
      ${card('Uninsured share', pct(d.uninsured, 0), 'over the $250k FDIC limit')}
      ${card('Money fund yield', pct(d.mmf_rate), 'what hot money can get elsewhere')}
      ${card('Brokered', fmc(d.brokered.reduce((a, b) => a + b.amount, 0)))}
    </div>
    <div class="grid g2">
    <div class="panel">
      <h3>Rates (your offset vs the market, bp)</h3>
      <div class="helptip">Your posted rate tracks the market; the offset is your stance.
        +50bp wins hot money (money market and CDs move fastest), -50bp fattens margin and bleeds balances.</div>
      <table><tr><th>Product</th><th class="r">You pay</th><th class="r">Market</th>
        <th class="r">${dt('spread', MODE === 'owner' ? 'Your stance (bp)' : 'Offset bp')}</th>
        <th class="r">Balance</th><th class="r">Accounts</th></tr>
      ${Object.keys(DEP_LABELS).map(p => `<tr>
        <td>${DEP_LABELS[p]}</td>
        <td class="r"><b>${pct(d.effective_rates[p])}</b></td>
        <td class="r">${p === 'checking' ? '—' : pct(d.market_rates[p] ?? d.market_rates['savings'])}</td>
        <td class="r">${p === 'checking' ? '—' :
          `<input type="number" step="5" min="-300" max="300" value="${d.offsets_bp[p]}"
            oninput="prevDep('${p}', this.value, ${d.offsets_bp[p]}, ${t[p]})"
            onchange="setPol('deposits.offsets_bp.${p}', parseInt(this.value))">`}</td>
        <td class="r">${fmc(t[p])}</td>
        <td class="r">${(sumAccounts(d.pools, p)).toLocaleString()}</td>
      </tr>`).join('')}
      </table>
      <div class="prevbar" id="prev-deposits"></div>
      <div class="ctl" style="margin-top:6px"><label>CD promo bonus (bp on all CDs)</label>
        <input type="number" step="5" min="0" max="300" value="${Math.round(d.promo_cd_bonus * 10000)}"
          onchange="setPol('deposits.promo_cd_bonus', parseFloat(this.value)/10000)"></div>
    </div>
    <div class="panel">
      <h3>Fee schedule</h3>
      <table><tr><th>Fee</th><th class="r">Amount $</th></tr>
        ${[['monthly_fee', 'Monthly maintenance'], ['overdraft_fee', 'Overdraft'],
           ['nsf_fee', 'NSF'], ['atm_fee', 'Foreign ATM'], ['wire_fee', 'Outgoing wire'],
           ['safe_deposit_annual', 'Safe deposit (annual)']].map(([k, label]) => `<tr>
          <td>${label}</td>
          <td class="r"><input type="number" step="1" min="0" id="fee-${k}" value="${(d.fees[k] / 100).toFixed(2)}"
            ${k === 'overdraft_fee' ? `oninput="prevOD(this.value, ${d.fees[k]}, ${sumAccounts(d.pools, 'checking') + sumAccounts(d.pools, 'checking_int')})"` : ''}
            onchange="setPol('deposits.fees.${k}', Math.round(parseFloat(this.value)*100))"></td>
        </tr>`).join('')}
      </table>
      <div class="prevbar" id="prev-fees"></div>
      <div class="helptip">High overdraft fees print money until customers leave and examiners write you up.</div>
      <h3>Wholesale (brokered) deposits</h3>
      ${d.brokered.length ? `<table><tr><th class="r">Amount</th><th class="r">Rate</th><th class="r">Months left</th></tr>
        ${d.brokered.map(b => `<tr><td class="r">${fm(b.amount)}</td><td class="r">${pct(b.rate)}</td>
          <td class="r">${b.months_left}</td></tr>`).join('')}</table>` : '<span class="sub">None outstanding.</span>'}
      <div class="ctl" style="margin-top:6px">
        <label>Issue $</label><input type="number" id="brk-amt" value="1000000">
        <label>months</label><input type="number" id="brk-term" value="12" style="width:52px">
        <button class="small" onclick="act('issue_brokered', {amount: moneyIn('brk-amt'), term: numIn('brk-term')})">Issue</button>
      </div>
    </div>
    </div>
    <div class="panel" style="margin-top:12px">
      <h3>Deposits by market</h3>
      <table><tr><th>Market</th>${Object.keys(DEP_LABELS).map(p => `<th class="r">${DEP_LABELS[p]}</th>`).join('')}<th class="r">Total</th></tr>
      ${Object.entries(d.pools).map(([mid, mk]) => {
        let tot = 0;
        const cells = Object.keys(DEP_LABELS).map(p => {
          const bal = mk.products[p].balance; tot += bal;
          return `<td class="r">${bal ? fmc(bal) : '·'}</td>`;
        }).join('');
        return `<tr><td>${esc(mk.name)}</td>${cells}<td class="r"><b>${fmc(tot)}</b></td></tr>`;
      }).join('')}
      </table>
      ${townStancePanel(d)}
    </div>`;
}
function townStancePanel(d) {
  const mids = Object.keys(d.pools || {});
  if (mids.length < 2) return '';
  const town = d.market_offsets_bp || {};
  const rows = mids.map(mid => {
    const mk = d.pools[mid];
    const ov = town[mid] || {};
    const mm = ov.money_market != null ? ov.money_market : '';
    const cd = ov.cd_1y != null ? ov.cd_1y : '';
    const pay = d.town_rates && d.town_rates[mid] ? pct(d.town_rates[mid].money_market) : '—';
    return `<tr>
      <td>${esc(mk.name)}</td>
      <td class="r">${pay}</td>
      <td class="r"><input type="number" step="5" min="-300" max="300" placeholder="franchise"
        value="${mm}"
        onchange="if(this.value==='')return;setPol('deposits.market_offsets_bp.${mid}.money_market', parseInt(this.value))"></td>
      <td class="r"><input type="number" step="5" min="-300" max="300" placeholder="franchise"
        value="${cd}"
        onchange="if(this.value==='')return;setPol('deposits.market_offsets_bp.${mid}.cd_1y', parseInt(this.value))"></td>
    </tr>`;
  }).join('');
  return `<h3 style="margin-top:14px">Town stance</h3>
    <div class="helptip">Franchise offsets apply everywhere. A town box overrides money market or the 1-year CD in that market only — pay up in the Permian without re-pricing Caprock.</div>
    <table><tr><th>Town</th><th class="r">You pay MM</th>
      <th class="r">MM offset bp</th><th class="r">CD 1y offset bp</th></tr>
      ${rows}
    </table>`;
}
function sumAccounts(pools, p) {
  return Object.values(pools).reduce((a, mk) => a + mk.products[p].accounts, 0);
}

/* ---------------- Treasury ---------------- */
async function tabTreasury(m) {
  const d = await section('treasury');
  const s = d.summary;
  const liq = d.liquidity_ratio;
  const cashLine = liq < 0.06 ? 'Cash is short. A runoff becomes a phone call.'
    : liq < 0.11 ? 'Cash is adequate if nothing surprises us.'
    : 'We can fund a credit or a surprise without selling bonds.';
  m.innerHTML = `
    <h2>Treasury — securities, funding, capital</h2>
    <div class="panel">
      <p class="stance">${esc(cashLine)}</p>
      <div class="kv">
        <span class="k">Spendable cash</span><span class="v">${fm(d.cash)}</span>
        <span class="k">Vault / at the Fed / sold</span>
        <span class="v">${fmc(d.vault)} / ${fmc(d.fed_balances)} / ${fmc(d.fed_funds_sold)}</span>
        <span class="k">${dt('liquidity')}</span><span class="v">${pct(liq, 1)}</span>
      </div>
      <div class="ctl" style="margin-top:8px"><label>Overnight shortfall</label>
        <select onchange="setPol('funding.overnight_policy', this.value)">
          <option value="ask" ${d.overnight_policy==='ask'?'selected':''}>Ask me (default) — clock stops, window is a choice</option>
          <option value="auto" ${d.overnight_policy==='auto'?'selected':''}>Auto — FHLB, then fed funds, window last</option>
        </select></div>
      <div class="helptip">Ask is the owner default. Auto still logs every window use; examiners count them either way.</div>
    </div>
    <div class="cards" style="margin-top:12px">
      ${card('Spendable cash', fmc(d.cash), 'vault ' + fmc(d.vault) + ' · Fed ' + fmc(d.fed_balances))}
      ${card(dt('afs', MODE === 'owner' ? 'Sellable bonds (AFS)' : 'AFS portfolio'), fmc(s.afs_mv), 'book ' + fmc(s.afs_book))}
      ${card(dt('htm', MODE === 'owner' ? 'Locked bonds (HTM)' : 'HTM portfolio'), fmc(s.htm_book), 'unrealized ' + fmc(s.htm_unrealized), cls(s.htm_unrealized))}
      ${card('Portfolio yield', pct(s.yield), dt('duration') + ' ' + s.duration + 'y')}
      ${card(dt('aoci'), fmc(d.aoci), 'marks through equity', cls(d.aoci))}
      ${card(dt('liquidity'), pct(d.liquidity_ratio, 1))}
      ${s.tainted ? card('HTM STATUS', 'TAINTED', 'no more HTM purchases', 'neg') : ''}
    </div>
    ${evePanel(d.eve)}
    <div class="grid g2">
    <div class="panel">
      <h3>Buy securities (at market yield off the live curve)</h3>
      <div class="ctl"><label>Type</label>
        <select id="buy-type">${['treasury','agency','mbs','muni','corporate'].map(t =>
          `<option value="${t}">${t} (${pct(d.type_yields[t])} @5y)</option>`).join('')}</select></div>
      <div class="ctl"><label>Tenor (years)</label><input type="number" id="buy-tenor" value="5" min="0.25" max="30" step="0.25" style="width:60px"></div>
      <div class="ctl"><label>Par $</label><input type="number" id="buy-par" value="1000000"></div>
      <div class="ctl"><label>Class</label><select id="buy-cls"><option>AFS</option><option>HTM</option></select></div>
      <button class="primary small" onclick="act('buy_security', {type: $('buy-type').value, tenor: numIn('buy-tenor'), par: moneyIn('buy-par'), cls: $('buy-cls').value})">Buy</button>
      <div class="helptip">AFS marks to market through AOCI daily. HTM hides the mark until you're forced to sell — then it all comes out at once.</div>

      <h3>Interest-rate hedges</h3>
      ${d.hedges.length ? `<table><tr><th>Kind</th><th class="r">Notional</th><th class="r">Fixed/strike</th><th class="r">Months</th></tr>
        ${d.hedges.map(h => `<tr><td>${esc(h.kind)}</td><td class="r">${fmc(h.notional)}</td>
          <td class="r">${pct(h.fixed || h.strike)}</td><td class="r">${h.months_left}</td></tr>`).join('')}</table>`
        : '<span class="sub">No hedges on. Your rate risk is naked.</span>'}
      <div class="ctl" style="margin-top:6px"><label>Kind</label>
        <select id="hg-kind"><option value="pay_fixed_swap">Pay-fixed swap</option>
        <option value="rate_cap">Rate cap</option></select>
        <label>Notional $</label><input type="number" id="hg-n" value="5000000">
        <label>Tenor y</label><input type="number" id="hg-t" value="3" style="width:52px">
        <button class="small" onclick="act('add_hedge', {kind: $('hg-kind').value, notional: moneyIn('hg-n'), tenor: numIn('hg-t')})">Add</button></div>
    </div>
    <div class="panel">
      <h3>Wholesale funding</h3>
      <div class="kv">
        <span class="k">FHLB capacity remaining</span><span class="v">${fmc(d.funding.fhlb_capacity)}</span>
        <span class="k">Fed funds purchased (o/n)</span><span class="v">${fmc(d.funding.ffp)}</span>
        <span class="k">Discount window drawn</span><span class="v ${d.funding.dw > 0 ? 'neg' : ''}">${fmc(d.funding.dw)}</span>
        <span class="k">Discount window lifetime uses</span><span class="v">${d.funding.dw_uses}</span>
      </div>
      <div class="sub" style="margin-top:6px">Overnight policy is set at the top of this page.</div>
      <div class="ctl" style="margin-top:8px"><label>FHLB advance $</label>
        <input type="number" id="fh-amt" value="2000000">
        <label>months</label><input type="number" id="fh-term" value="12" style="width:52px">
        <button class="small" onclick="act('take_fhlb', {amount: moneyIn('fh-amt'), term: numIn('fh-term')})">Draw</button></div>
      ${d.funding.fhlb.length ? `<table><tr><th class="r">Advance</th><th class="r">Rate</th><th class="r">Months</th><th></th></tr>
        ${d.funding.fhlb.map(a => `<tr><td class="r">${fm(a.amount)}</td><td class="r">${pct(a.rate)}</td>
          <td class="r">${a.months_left}</td><td><button class="small" onclick="act('repay_funding',{kind:'fhlb',item_id:${a.id}})">Repay</button></td></tr>`).join('')}</table>` : ''}
      ${d.funding.subdebt.length ? `<h3>Subordinated debt</h3><table><tr><th class="r">Issue</th><th class="r">Rate</th><th class="r">Months</th></tr>
        ${d.funding.subdebt.map(a => `<tr><td class="r">${fm(a.amount)}</td><td class="r">${pct(a.rate)}</td><td class="r">${a.months_left}</td></tr>`).join('')}</table>` : ''}

      <h3>Capital actions</h3>
      <div class="kv">
        <span class="k">Shares outstanding</span><span class="v">${d.shares.toLocaleString()}</span>
        <span class="k">Tangible book value</span><span class="v">${fm(d.tbv)}</span>
        <span class="k">TBV per share</span><span class="v">${fm(Math.round(d.tbv / d.shares))}</span>
        <span class="k">${d.listed ? 'Last print' : 'Implied private price'}</span>
        <span class="v">${d.quote ? (fm(d.quote.px) + ' · ' + d.quote.price_to_book.toFixed(2) + '× book') : '—'}</span>
      </div>
      ${listingBlock(d)}
      <div class="ctl" style="margin-top:8px"><label>Raise common $</label>
        <input type="number" id="cap-amt" value="2000000">
        <button class="small" onclick="confirmRaiseCommon()">Raise</button></div>
      <div class="ctl"><label>Issue preferred $</label>
        <input type="number" id="pref-amt" value="2000000">
        <button class="small" onclick="act('issue_preferred', {amount: moneyIn('pref-amt')})">Issue</button></div>
      <div class="ctl"><label>Issue sub debt $</label>
        <input type="number" id="sd-amt" value="2000000">
        <button class="small" onclick="act('issue_subdebt', {amount: moneyIn('sd-amt')})">Issue</button></div>
      <div class="ctl"><label>Buy back stock $</label>
        <input type="number" id="bb-amt" value="500000">
        <button class="small" onclick="act('buyback', {amount: moneyIn('bb-amt')})">Buy back</button></div>
      <div class="ctl"><label>Dividend payout % of earnings</label>
        <input type="number" min="0" max="100" value="${d.dividend_payout}"
          onchange="setPol('policies.dividend_payout', parseInt(this.value))"></div>
    </div>
    </div>
    <div class="panel" style="margin-top:12px">
      <h3>Securities portfolio (click a lot to sell)</h3>
      ${d.lots.length ? `<table><tr><th>#</th><th>Type</th><th>Class</th><th class="r">Par</th>
        <th class="r">Coupon</th><th class="r">Mkt value</th><th class="r">Unrealized</th>
        <th class="r">Duration</th><th class="r">Matures in</th><th></th></tr>
        ${d.lots.map(l => {
          const un = l.mv - l.book;
          return `<tr><td>${l.id}</td><td>${esc(l.type)}</td><td>${l.cls}</td>
          <td class="r">${fm(l.par)}</td><td class="r">${pct(l.coupon)}</td>
          <td class="r">${fm(l.mv)}</td><td class="r ${cls(un)}">${fm(un)}</td>
          <td class="r">${l.duration.toFixed(1)}y</td><td class="r">${Math.round(l.maturity_m / 12 * 10) / 10}y</td>
          <td><button class="small ${l.cls === 'HTM' ? 'danger' : ''}"
            onclick="${l.cls === 'HTM' ? `if(confirm('Selling HTM taints the entire HTM book — every unrealized loss hits equity at once. Sure?'))` : ''}act('sell_security',{lot_id:${l.id}})">Sell</button></td></tr>`;
        }).join('')}</table>` : '<span class="sub">No securities. Cash is earning fed funds minus a dime.</span>'}
    </div>`;
}

function evePanel(eve) {
  if (!eve) return '';
  return `<div class="panel" style="margin-top:12px">
    <h3>What a rate jump does to book value</h3>
    <p class="stance">${esc(eve.owner)}</p>
    <div class="kv">
      <span class="k">Asset duration</span><span class="v">${eve.asset_duration}y</span>
      <span class="k">Funding duration</span><span class="v">${eve.liability_duration}y</span>
      <span class="k">Duration gap</span><span class="v">${eve.duration_gap}y</span>
    </div>
    <table><tr><th>Parallel shock</th><th class="r">Δ economic equity</th>
      <th class="r">vs tangible book</th></tr>
      ${(eve.shocks || []).map(s => `<tr>
        <td>${s.bp > 0 ? '+' : ''}${s.bp} bp</td>
        <td class="r ${cls(s.delta_eve)}">${fm(s.delta_eve)}</td>
        <td class="r ${cls(s.delta_eve)}">${pct(s.pct_tbv, 1)}</td>
      </tr>`).join('')}</table>
    <div class="helptip">Same duration gap the examiners sketch. Pay-fixed swaps and caps damp a rising-rate hit. This is not a new exam grade — they still look at paper losses vs capital.</div>
  </div>`;
}

/* ---------------- Operations ---------------- */
const ROLE_LABELS = { tellers: 'Tellers', lenders: 'Lenders', credit_analysts: 'Credit analysts',
  ops: 'Operations', compliance: 'Compliance', it: 'IT / Security', execs: 'Executives' };

async function tabOps(m) {
  const d = await section('ops');
  m.innerHTML = `
    <h2>Operations</h2>
    <div class="cards">
      ${card('Branches', String(d.branches.filter(b => b.open).length))}
      ${card('Digital platform', 'Level ' + d.digital_level + '/5')}
      ${card('Core system age', d.core_system_age.toFixed(1) + ' yrs', d.core_system_age > 8 ? 'OUTAGE RISK' : 'healthy', d.core_system_age > 8 ? 'neg' : '')}
      ${card('Service quality', d.service_quality.toFixed(2))}
    </div>
    <div class="grid g2">
    <div class="panel">
      <h3>Staff</h3>
      <table><tr><th>Role</th><th class="r">Count</th><th class="r">Skill</th>
        <th class="r">Morale</th><th class="r">Salary</th><th></th></tr>
      ${Object.keys(ROLE_LABELS).map(r => {
        const s = d.staff[r];
        return `<tr><td>${ROLE_LABELS[r]}</td><td class="r">${s.count}</td>
          <td class="r">${s.skill.toFixed(1)}</td>
          <td class="r ${s.morale < 0.6 ? 'neg' : s.morale < 0.75 ? 'warn' : 'pos'}">${Math.round(s.morale * 100)}%</td>
          <td class="r">${fmc(s.salary)}/yr</td>
          <td><button class="small" onclick="act('hire',{role:'${r}',count:1})">Hire</button>
              <button class="small" onclick="confirmFire('${r}', ${s.count})">Cut</button>
              <button class="small" onclick="act('train',{role:'${r}'})">Train</button></td></tr>`;
      }).join('')}
      </table>
      <div class="ctl" style="margin-top:8px"><label>Pay vs market (1.0 = market)</label>
        <input type="number" step="0.05" min="0.7" max="2" value="${d.salary_multiplier}"
          onchange="setPol('ops.salary_multiplier', parseFloat(this.value))"></div>
      <div class="ctl"><label>Auto-replace departures</label>
        <select onchange="setPol('ops.auto_backfill', this.value === 'true')">
          <option value="true" ${d.auto_backfill !== false ? 'selected' : ''}>Yes</option>
          <option value="false" ${d.auto_backfill === false ? 'selected' : ''}>No (shrink by attrition)</option>
        </select></div>
      <div class="helptip">Lenders drive loan volume. Compliance keeps examiners calm. Underpaid people quit; your best lender can defect with their book.</div>
      ${d.hire_preview ? `<div class="sub">Another lender: first-year NI about ${fm(d.hire_preview.extra_ni)} vs pay ${fm(d.hire_preview.cost)} — ${d.hire_preview.positive ? 'covers the seat' : 'loses money at this scale'}.</div>` : ''}

      <h3>Technology</h3>
      <div class="ctl"><button class="small primary" onclick="confirmDigital()">Upgrade digital (level ${d.digital_level + 1} · ${fm(d.digital_next_cost || 0)})</button>
        <button class="small" onclick="confirmCore()">Replace core system (${fm(d.core_cost || 0)})</button></div>
      <div class="ctl"><label>Cybersecurity $/mo</label>
        <input type="number" id="cyb" value="${d.cyber_spend / 100}"
          onchange="setPol('ops.cyber_spend', Math.round(parseFloat(this.value)*100))"></div>
      <div class="ctl"><label>Internal audit $/mo</label>
        <input type="number" value="${d.audit_spend / 100}"
          onchange="setPol('ops.audit_spend', Math.round(parseFloat(this.value)*100))"></div>
    </div>
    <div class="panel">
      <h3>Branches</h3>
      <table><tr><th>#</th><th>Market</th><th class="r">Monthly cost</th><th>Opened</th><th></th></tr>
      ${d.branches.filter(b => b.open).map(b => `<tr><td>${b.id}</td>
        <td>${esc(d.markets[b.market] ? d.markets[b.market].name : b.market)}</td>
        <td class="r">${fmc(b.monthly_cost)}</td><td>${esc(b.opened)}</td>
        <td><button class="small danger" onclick="confirmCloseBranch(${b.id}, '${esc(d.markets[b.market] ? d.markets[b.market].name : b.market)}')">Close</button></td></tr>`).join('')}
      </table>
      <div class="ctl" style="margin-top:8px"><label>Open branch in</label>
        <select id="br-mkt" onchange="showBranchPreview()">${branchOptions(d)}</select>
        <button class="small primary" id="br-open" onclick="confirmOpenBranch()">Review & open</button></div>
      <div class="prevbar" id="prev-branch"></div>
      <div class="helptip">Peer towns are the intended second county. Dallas and NYC are capital events — the preview says so before you click.</div>

      <h3>Marketing ($/month by market)</h3>
      <table><tr><th>Market</th><th class="r">Brand</th><th class="r">Spend $/mo</th></tr>
      ${Object.entries(d.brand).map(([mid, br]) => `<tr>
        <td>${esc(d.markets[mid] ? d.markets[mid].name : mid)}</td>
        <td class="r">${br.toFixed(0)}/100</td>
        <td class="r"><input type="number" step="500" min="0" value="${(d.marketing[mid] || 0) / 100}"
          onchange="setPol('ops.marketing.${mid}', Math.round(parseFloat(this.value)*100))"></td>
      </tr>`).join('')}
      </table>
      <div class="helptip">Brand decays ~1.2%/month without spend. Bigger markets need much bigger budgets.</div>

      <h3>Product lines</h3>
      <table><tr><th>Line</th><th class="r">Requires</th><th class="r">Setup</th><th></th></tr>
      ${d.unlocks.map(u => `<tr><td>${esc(u.label)}</td>
        <td class="r">${fmc(u.min_assets)} assets</td><td class="r">${fmc(u.cost)}</td>
        <td>${u.enabled ? '<span class="pill g">LIVE</span>' :
          u.available ? `<button class="small primary" onclick="act('unlock_product',{product:'${u.product}'})">Launch</button>`
                      : '<span class="pill b">TOO SMALL</span>'}</td></tr>`).join('')}
      </table>
    </div>
    </div>`;
  showBranchPreview();
}

const KIND_LABELS = {
  rural: 'Peer towns', small_metro: 'Small metros', suburb: 'Suburbs',
  metro: 'Metros', money_center: 'Money centers',
};
const VERDICT_TEXT = {
  cannot_fund: 'Cannot fund — raise capital or sell bonds first',
  lethal: 'This will dilute you below well-capitalized',
  stretch: 'Stretch — capital gets tight after the gather',
  safe: 'Safe for a bank your size',
  locked: 'Locked — this market is a later weight class',
};

function branchOptions(d) {
  const order = d.kind_order || ['rural', 'small_metro', 'suburb', 'metro', 'money_center'];
  const byKind = {};
  Object.entries(d.markets || {}).forEach(([mid, mk]) => {
    const k = mk.kind || 'rural';
    (byKind[k] = byKind[k] || []).push([mid, mk]);
  });
  return order.map(k => {
    const rows = byKind[k] || [];
    if (!rows.length) return '';
    return `<optgroup label="${esc(KIND_LABELS[k] || k)}">${rows.map(([mid, mk]) => {
      const p = (d.previews || {})[mid] || {};
      const tag = p.verdict === 'locked' ? ' — unlocks at ' + fmc(p.unlock_assets || 0)
        : p.already ? ' — another office'
        : p.verdict === 'cannot_fund' ? ' — cannot fund'
        : p.verdict === 'lethal' ? ' — capital event'
        : p.verdict === 'stretch' ? ' — stretch' : '';
      return `<option value="${esc(mid)}">${esc(mk.name)} · open ${fmc(p.cost || 0)}${tag}</option>`;
    }).join('')}</optgroup>`;
  }).join('');
}

function showBranchPreview() {
  const sel = $('br-mkt');
  const box = $('prev-branch');
  const btn = $('br-open');
  if (!sel || !box) return;
  const d = SEC.ops || {};
  const p = (d.previews || {})[sel.value];
  if (!p) { box.textContent = ''; return; }
  const lev = ((p.proforma_leverage || 0) * 100).toFixed(1);
  const vtxt = VERDICT_TEXT[p.verdict] || p.verdict;
  box.innerHTML =
    `${esc(p.name)}${p.offices ? ' (' + p.offices + ' office' + (p.offices > 1 ? 's' : '') + ' now)' : ''}: `
    + `open ${fm(p.cost)}, ${fm(p.monthly)}/mo, year-1 incremental gather ≈ ${fm(p.year1_gather)}. `
    + `Pro-forma leverage ${lev}% (${esc(vtxt)}).`;
  box.className = 'prevbar' + (p.verdict === 'lethal' || p.verdict === 'cannot_fund' ? ' neg' : '');
  if (btn) {
    btn.disabled = !p.can_fund;
    btn.textContent = p.can_fund
      ? (p.already ? 'Review & open another' : 'Review & open')
      : 'Cannot fund';
  }
}

function marketGroups(d) {
  const order = d.kind_order || ['rural', 'small_metro', 'suburb', 'metro', 'money_center'];
  const byKind = {};
  Object.entries(d.regions || {}).forEach(([mid, r]) => {
    const k = r.kind || 'rural';
    (byKind[k] = byKind[k] || []).push([mid, r]);
  });
  return order.map(k => {
    const rows = byKind[k] || [];
    if (!rows.length) return '';
    return `<div class="kindhead">${esc(KIND_LABELS[k] || k)}</div>
      <table><tr><th>Market</th><th>Kind</th>
        <th class="r">${MODE === 'owner' ? 'Your slice' : 'Your share'}</th>
        <th class="r">$25M ceiling</th>
        <th>Verdict</th><th></th></tr>
      ${rows.map(([mid, r]) => {
        const p = (d.previews || {})[mid] || {};
        const verdict = !r.unlocked
          ? ('Unlocks at ' + fmc(r.unlock_assets || 0) + ' of assets')
          : r.my_branches
          ? 'Another office is allowed (diminishing gather).'
          : (VERDICT_TEXT[p.verdict] || p.verdict || '');
        return `<tr>
          <td title="${esc(r.note)}">${esc(r.name)}</td>
          <td class="sub">${esc(KIND_LABELS[r.kind] || r.kind || '')}</td>
          <td class="r ${r.my_share > 0 ? 'pos' : ''}">${pct(r.my_share, 1)}</td>
          <td class="r">${pct(r.ceiling_25m, 2)}</td>
          <td class="sub">${esc(verdict)}</td>
          <td><button class="small" onclick="openMarketPreview('${esc(mid)}')">${r.my_branches ? 'Another office' : 'Open preview'}</button></td>
        </tr>`;
      }).join('')}
      </table>`;
  }).join('');
}

function openMarketPreview(mid) {
  const d = SEC.markets || {};
  const p = (d.previews || {})[mid];
  if (!p) { toast('No preview for that market.', true); return; }
  const vtxt = VERDICT_TEXT[p.verdict] || p.verdict;
  const html = `<div class="memoform">
      <div class="who-name">${esc(p.name)}</div>
      <div class="sub">${esc(KIND_LABELS[p.kind] || p.kind || '')}</div>
      <div class="memorow"><span class="k">Open cost</span><span class="v">${fm(p.cost)}</span></div>
      <div class="memorow"><span class="k">Monthly</span><span class="v">${fm(p.monthly)}/mo</span></div>
      <div class="memorow"><span class="k">Year-1 gather</span><span class="v">≈ ${fm(p.year1_gather)}</span></div>
      <div class="memorow"><span class="k">Pro-forma leverage</span>
        <span class="v">${((p.proforma_leverage || 0) * 100).toFixed(1)}%</span></div>
      <p class="moved">${esc(vtxt)}</p>
    </div>`;
  const btns = (p.can_fund && p.verdict !== 'locked')
    ? [['Open this branch', `closeText();act('open_branch',{market:${JSON.stringify(mid)}})`,
        (p.verdict === 'lethal' || p.verdict === 'stretch') ? 'danger' : 'primary']]
    : [];
  showHtml('Branch preview — ' + p.name, html, btns);
}

function confirmFire(role, count) {
  const last = count <= 1;
  const ok = confirm(last
    ? 'This is your last ' + (ROLE_LABELS[role] || role).toLowerCase()
      + '. Originations or controls in that seat will stall. Let them go?'
    : 'Let this person go? Severance hits earnings this month.');
  if (ok) act('fire', { role, count: 1 });
}
function confirmDigital() {
  const d = SEC.ops || {};
  const p = d.digital_preview || {};
  if (p.maxed) { toast('Digital is already best-in-class.'); return; }
  if (p.too_big) {
    toast('This build is ' + Math.round((p.pct_tbv || 0) * 100)
      + '% of tangible book — raise or wait.', true);
    return;
  }
  const ok = confirm('Upgrade digital for ' + fm(p.cost || d.digital_next_cost || 0)
    + '? Monthly run-rate goes up about ' + fm(p.monthly || 2500000)
    + '. That is an expense, not an asset — it leaves the vault.');
  if (ok) act('invest_digital');
}

function listingBlock(d) {
  if (d.listed) {
    return `<div class="helptip">Listed. Buybacks hit the last print. Private deals can take 40% in new stock.</div>`;
  }
  const p = d.listing;
  if (typeof p === 'string') {
    return `<div class="helptip">Listing: ${esc(p)}.</div>`;
  }
  if (p && p.can_list) {
    return `<div class="ctl" style="margin-top:8px">
      <button class="small" onclick="confirmListCommon()">List the common (${fm(p.fees)} fees · ${fm(p.px)}/sh)</button>
    </div>`;
  }
  return '';
}
async function confirmListCommon() {
  try {
    const r = await api('/api/action', { action: 'preview_list_common', payload: {} });
    const p = r.result || r;
    if (p.error || p.message && !p.can_list) { toast(p.error || p.message, true); return; }
    const ok = confirm('List the common stock? Fees ' + fm(p.fees)
      + '. Opening print about ' + fm(p.px) + ' (' + (p.price_to_book || 0).toFixed(2)
      + '× book). Buybacks and stock deals will use this price.');
    if (ok) act('list_common', {});
  } catch (e) { toast(String(e), true); }
}
function confirmRaiseCommon() {
  const amt = moneyIn('cap-amt');
  if (!amt) return;
  try {
    const r = await api('/api/action', { action: 'preview_raise_common', payload: { amount: amt } });
    const t = r.result || {};
    const ok = confirm('Raise ' + fm(amt) + ' of common at ' + (t.price_to_book || '?')
      + '× book (' + (t.shares_issued || 0).toLocaleString() + ' shares, '
      + fm(t.fees || 0) + ' fee). Pro-forma CET1 '
      + ((t.proforma_cet1 || 0) * 100).toFixed(1) + '%. Proceed?');
    if (ok) act('raise_common', { amount: amt });
  } catch (e) { toast(String(e), true); }
}
function confirmCore() {
  const d = SEC.ops || {};
  const ok = confirm('Replace the core system for ' + fm(d.core_cost || 0) + '?');
  if (ok) act('upgrade_core');
}
function confirmCloseBranch(id, name) {
  const ok = confirm('Close the ' + name + ' branch? This costs '
    + fm(35000000) + ' and you cannot close your last office.');
  if (ok) act('close_branch', { branch_id: id });
}
function confirmOpenBranch(market, source) {
  const mid = market || ($('br-mkt') && $('br-mkt').value);
  if (!mid) return;
  const src = source || 'ops';
  const p = ((SEC[src] || SEC.ops || {}).previews || {})[mid];
  if (!p) return;
  if (!p.can_fund) {
    toast('Not enough cash to open this branch ($' + Math.round(p.cost / 100).toLocaleString() + ' needed).', true);
    return;
  }
  const vtxt = VERDICT_TEXT[p.verdict] || p.verdict;
  const html = `<div class="memoform">
      <div class="who-name">${esc(p.name)}</div>
      <div class="sub">${esc(KIND_LABELS[p.kind] || p.kind || '')}</div>
      <div class="memorow"><span class="k">Open cost</span><span class="v">${fm(p.cost)}</span></div>
      <div class="memorow"><span class="k">Monthly</span><span class="v">${fm(p.monthly)}/mo</span></div>
      <div class="memorow"><span class="k">Year-1 gather</span><span class="v">≈ ${fm(p.year1_gather)}</span></div>
      <div class="memorow"><span class="k">Pro-forma leverage</span>
        <span class="v">${((p.proforma_leverage || 0) * 100).toFixed(1)}%</span></div>
      <p class="moved">${esc(vtxt)}</p>
    </div>`;
  const danger = (p.verdict === 'lethal' || p.verdict === 'stretch');
  showHtml('Branch preview — ' + p.name, html, [
    ['Open this branch', `closeText();act('open_branch',{market:${JSON.stringify(mid)}})`,
     danger ? 'danger' : 'primary']
  ]);
}

function pipelineBanner(pipe) {
  if (!pipe || !pipe.length) return '';
  return pipe.map(item => {
    const deal = item.deal || {};
    const who = item.rival_name || 'A rival';
    const mo = item.months_left == null ? '?' : item.months_left;
    return `<div class="banner" style="margin-bottom:10px;border-color:var(--warn)">
      <b>${esc(deal.name || 'A book')} is in diligence.</b>
      ${esc(who)} is circling — about ${mo} month${mo === 1 ? '' : 's'} left.
      <div class="btnrow" style="margin-top:6px">
        <button class="small primary" onclick="act('close_pipeline',{pipeline_id:${item.id}})">Buy it</button>
        <button class="small" onclick="act('drop_pipeline',{pipeline_id:${item.id}})">Pass</button>
      </div>
    </div>`;
  }).join('');
}

function mraBanner(d) {
  const live = (d.mras || []).filter(m => m.status === 'open' || m.status === 'missed');
  if (!live.length) return '';
  return `<div class="banner" style="border-color:var(--warn)">
    <b>Matters requiring attention</b>
    ${live.map(m => {
      const line = MODE === 'owner' ? (m.owner || m.text) : m.text;
      const tag = m.status === 'missed' ? 'MISSED — ' : '';
      return `<div class="sub">${tag}${esc(line)}</div>`;
    }).join('')}
  </div>`;
}

/* ---------------- Risk & Reg ---------------- */
async function tabRisk(m) {
  const d = await section('risk');
  const c = d.capital;
  const camels = d.camels;
  m.innerHTML = `
    <h2>Risk & Regulation</h2>
    <div class="cards">
      ${card(dt('cet1'), pct(c.cet1_ratio), 'well-cap needs 6.5%', c.cet1_ratio < 0.065 ? 'neg' : 'pos')}
      ${card('Tier 1 / Total', pct(c.tier1_ratio, 1) + ' / ' + pct(c.total_ratio, 1))}
      ${card(dt('leverage'), pct(c.leverage_ratio), 'tangible equity ' + pct(c.tang_equity_ratio))}
      ${card(dt('pca'), d.pca.toUpperCase(), '', d.pca === 'well' ? 'pos' : 'neg')}
      ${card(dt('camels'), String(camels.composite),
        `C${camels.C} A${camels.A} M${camels.M} E${camels.E} L${camels.L} S${camels.S}`,
        camels.composite <= 2 ? 'pos' : camels.composite === 3 ? 'warn' : 'neg')}
      ${card('Next exam', '~' + d.months_to_exam + ' mo')}
      ${card(dt('cra'), d.cra, '', d.cra === 'Needs to Improve' ? 'neg' : 'pos')}
    </div>
    ${d.orders.length ? `<div class="banner amber">Active enforcement: ${esc(d.orders.join(' · '))}</div>` : ''}
    ${d.exam_path ? `<div class="banner" style="border-color:${camels.composite >= 4 ? 'var(--red)' : 'var(--warn)'}">
      <b>${esc(d.exam_path.needed || '')}</b>
      ${(d.exam_path.actions || []).map(a => `<div class="sub">${esc(a)}</div>`).join('')}
    </div>` : ''}
    ${mraBanner(d)}
    ${d.thresholds.durbin ? '<div class="sub">Regulatory tier: ' +
      ['$10B+ (Durbin/CFPB)', d.thresholds.enhanced ? '$50B+ (stress tests)' : '',
       d.thresholds.lcr ? '$100B+ (LCR)' : '', d.thresholds.gsib ? 'G-SIB' : '']
      .filter(Boolean).join(' · ') + '</div>' : ''}
    <div class="grid g3" style="margin-top:10px">
    <div class="panel">
      <h3>Interest-rate risk</h3>
      <div class="kv">
        <span class="k">Securities duration</span><span class="v">${d.sec_duration}y</span>
        <span class="k">AOCI (AFS marks)</span><span class="v ${cls(d.aoci)}">${fm(d.aoci)}</span>
        <span class="k">HTM unrealized</span><span class="v ${cls(d.htm_unrealized)}">${fm(d.htm_unrealized)}</span>
        <span class="k">Unrealized vs CET1</span>
        <span class="v ${(-(Math.min(0, d.aoci) + Math.min(0, d.htm_unrealized)) / Math.max(1, c.cet1)) > 0.25 ? 'neg' : ''}">
          ${pct(-(Math.min(0, d.aoci) + Math.min(0, d.htm_unrealized)) / Math.max(1, c.cet1), 0)}</span>
      </div>
      <div class="helptip">${durationTrapCopy()}</div>
      ${d.eve ? `<div class="sub" style="margin-top:6px">${esc(d.eve.owner)} Open Treasury for the ±100/200/300 bp table.</div>` : ''}
      <h3>Liquidity & funding</h3>
      <div class="kv">
        <span class="k">Liquid assets / assets</span><span class="v">${pct(d.liquidity_ratio, 1)}</span>
        <span class="k">Wholesale dependence</span><span class="v">${pct(d.wholesale_dependence, 1)}</span>
        <span class="k">Uninsured deposits</span><span class="v">${pct(d.uninsured, 0)}</span>
        <span class="k">Run rumor level</span>
        <span class="v ${d.crisis.rumor > 0.3 ? 'neg' : ''}">${pct(d.crisis.rumor, 0)}</span>
      </div>
    </div>
    <div class="panel">
      <h3>Fraud command center</h3>
      <div class="kv">
        <span class="k">Detection rate</span><span class="v">${pct(d.fraud.detection, 0)}</span>
        <span class="k">Fraud environment</span><span class="v">${d.fraud.env.toFixed(2)}x</span>
        <span class="k">False-positive drag on deposits</span><span class="v">${pct(d.fraud.false_positive_drag, 2)}</span>
      </div>
      <div class="ctl" style="margin-top:6px"><label>Prevention $/mo</label>
        <input type="number" value="${d.fraud.prevention_spend / 100}"
          onchange="setPol('fraud.prevention_spend', Math.round(parseFloat(this.value)*100))"></div>
      <div class="ctl"><label>Detection thresholds</label>
        <select onchange="setPol('fraud.threshold', parseInt(this.value))">
          ${[0,1,2,3,4].map(t => `<option value="${t}" ${d.fraud.threshold===t?'selected':''}>${['Wide open','Loose','Balanced','Tight','Paranoid'][t]}</option>`).join('')}
        </select></div>
      <h3>Losses by channel (lifetime)</h3>
      <table>${Object.entries(d.fraud.losses_by_channel).sort((a,b)=>b[1]-a[1]).map(([k, v]) =>
        `<tr><td>${esc(k)}</td><td class="r">${fm(v)}</td></tr>`).join('')}</table>
      <h3>Open cases</h3>
      ${d.fraud.cases.filter(cse => cse.status === 'open').map(cse =>
        `<div class="newsitem">#${cse.id} ${esc(cse.kind)} — ${esc(cse.name)} (${fm(cse.amount)})
          <button class="small primary" onclick="act('resolve_fraud_case',{case_id:${cse.id},choice:'act'})">Act now</button>
          <button class="small" onclick="act('resolve_fraud_case',{case_id:${cse.id},choice:'monitor'})">Monitor</button>
        </div>`).join('') || '<span class="sub">No open cases.</span>'}
    </div>
    <div class="panel">
      <h3>BSA / AML program</h3>
      <div class="kv">
        <span class="k">Program score</span>
        <span class="v ${d.bsa.score < 0.6 ? 'neg' : 'pos'}">${pct(d.bsa.score, 0)}</span>
        <span class="k">Weak months</span><span class="v ${d.bsa.weak_months > 5 ? 'neg' : ''}">${d.bsa.weak_months}</span>
        <span class="k">SARs filed</span><span class="v">${d.bsa.sars_filed}</span>
        <span class="k">CTRs filed</span><span class="v">${d.bsa.ctrs_filed}</span>
      </div>
      <div class="ctl" style="margin-top:6px"><label>BSA program $/mo</label>
        <input type="number" value="${d.bsa.program_spend / 100}"
          onchange="setPol('regulation.bsa.program_spend', Math.round(parseFloat(this.value)*100))"></div>
      <div class="helptip">Underinvest for years and the fine has nine figures in it. Staffing compliance officers matters too.</div>
      <h3>Exam history</h3>
      ${d.exam_reports.slice().reverse().map(r =>
        `<div class="newsitem"><span class="nd">${esc(r.date)}</span>
          ${MODE === 'owner' ? 'Report card' : 'Composite'} ${r.composite}
          <a onclick='showExam(${JSON.stringify(esc(r.date))}, ${r.composite}, ${JSON.stringify(esc(r.text))})'>read report</a>
        </div>`).join('') || '<span class="sub">Not yet examined. They will come.</span>'}
    </div>
    </div>`;
}

/* ---------------- Markets ---------------- */
async function tabMarkets(m) {
  const d = await section('markets');
  m.innerHTML = `
    <h2>Markets & Competition</h2>
    <div class="grid g2">
      <div class="panel"><canvas id="ch-ff" class="chart"></canvas></div>
      <div class="panel"><canvas id="ch-macro" class="chart"></canvas></div>
    </div>
    <div class="panel" style="margin-top:12px">
      <h3>Geography — peer towns first, money centers last</h3>
      <div class="helptip">A $25 million bank cannot take a real slice of Dallas. The ceiling is the honest share of that pool. Open preview before you spend the capital.</div>
      ${marketGroups(d)}
    </div>
    <div class="grid g2" style="margin-top:12px">
    <div class="panel">
      <h3>Rival banks</h3>
      <div class="helptip">Click any bank to open its full call-report books — the same shape as your Reports tab.</div>
      <table><tr><th>Bank</th><th>Strategy</th><th class="r">Assets</th>
        <th class="r">${dt('cet1', MODE === 'owner' ? 'Capital' : 'Capital')}</th>
        <th class="r">${dt('npa')}</th><th class="r">${dt('roa')}</th><th></th></tr>
      ${(d.competitors || []).filter(b => b.id).map(b => `<tr class="click ${b.alive ? '' : 'sub'}" onclick='openRival(${jattr(b.id)})'>
        <td>${esc(b.name)}${b.alive ? '' : ' †'}</td><td>${esc(rivalStratLabel(b.strategy))}</td>
        <td class="r">${fmc(b.assets)}</td>
        <td class="r ${b.equity_ratio < 0.06 ? 'neg' : ''}">${pct(b.equity_ratio, 1)}</td>
        <td class="r ${b.npa_ratio > 0.04 ? 'neg' : ''}">${pct(b.npa_ratio, 1)}</td>
        <td class="r ${cls(b.roa)}">${pct(b.roa)}</td>
        <td><button class="small" onclick='event.stopPropagation();openRival(${jattr(b.id)})'>Books</button></td></tr>`).join('')}
      </table>
      ${d.failed.length ? `<div class="sub" style="margin-top:6px">Failures: ${d.failed.map(f => esc(f.name)).join(', ')}</div>` : ''}
    </div>
    <div class="panel">
      <h3>Peer comparison (banks your size)</h3>
      <table><tr><th>Bank</th><th class="r">Assets</th>
        <th class="r">${dt('roa')}</th><th class="r">${dt('nim')}</th>
        <th class="r">${dt('eff')}</th><th class="r">${dt('npa')}</th></tr>
      <tr style="color:#fff;font-weight:700"><td>YOU</td>
        <td class="r">${fmc(d.me.assets)}</td><td class="r">${pct(d.me.roa)}</td>
        <td class="r">${pct(d.me.nim)}</td><td class="r">${pct(d.me.efficiency, 0)}</td>
        <td class="r">${pct(d.me.npa_ratio)}</td></tr>
      ${(d.peers || []).filter(b => b.id).map(b => `<tr class="click" onclick='openRival(${jattr(b.id)})'>
        <td>${esc(b.name)}</td><td class="r">${fmc(b.assets)}</td>
        <td class="r">${pct(b.roa)}</td><td class="r">${pct(b.nim)}</td>
        <td class="r">${pct(b.efficiency, 0)}</td><td class="r">${pct(b.npa_ratio)}</td></tr>`).join('')}
      </table>
    </div>
    </div>`;
  const h = d.econ_history;
  drawChart($('ch-ff'), [
    { name: 'fed funds', color: '#e0b050', data: h.map(x => ({ x: x.m, y: x.ff * 100 })) },
    { name: '10y', color: '#58a6ff', data: h.map(x => ({ x: x.m, y: x.y10 * 100 })) },
    { name: '2y', color: '#46c78c', data: h.map(x => ({ x: x.m, y: x.y2 * 100 })) },
  ], { title: 'Rates', yfmt: v => v.toFixed(1) + '%', xfmt: v => 'm' + Math.round(v) });
  drawChart($('ch-macro'), [
    { name: 'output gap', color: '#46c78c', data: h.map(x => ({ x: x.m, y: x.gap })) },
    { name: 'unemployment', color: '#e06060', data: h.map(x => ({ x: x.m, y: x.unemp })) },
    { name: 'inflation', color: '#e0b050', data: h.map(x => ({ x: x.m, y: x.infl })) },
  ], { title: 'Macro', xfmt: v => 'm' + Math.round(v), zero: true });
}

/* ---------------- Rival call-report books ---------------- */
const RIVAL_STRAT = {
  rate_leader: { b: 'Rate leader', o: 'Pays up for deposits' },
  relationship: { b: 'Relationship', o: 'Knows its customers' },
  aggressive_lender: { b: 'Aggressive lender', o: 'Grows loans fast' },
  conservative: { b: 'Conservative', o: 'Fortress / cautious' },
  roll_up: { b: 'Roll-up', o: 'Buys other banks' },
  digital: { b: 'Digital', o: 'Online / few branches' },
};
const RIVAL_LINE = {
  'Cash and due from banks': { b: 'Cash and due from banks', o: 'Cash in the vault' },
  'Interest-bearing balances at Fed': { b: 'Interest-bearing balances at Fed', o: 'Cash at the Fed' },
  'Fed funds sold': { b: 'Fed funds sold', o: 'Overnight loans to other banks' },
  'Securities available-for-sale (fair value)': { b: 'Securities available-for-sale (fair value)', o: 'Sellable bonds' },
  'Securities held-to-maturity (amortized cost)': { b: 'Securities held-to-maturity (amortized cost)', o: 'Locked-away bonds' },
  'Loans, gross': { b: 'Loans, gross', o: 'Loans outstanding' },
  '  less: allowance for credit losses': { b: '  less: allowance for credit losses', o: '  less: loss reserve' },
  'Loans, net': { b: 'Loans, net', o: 'Loans after reserve' },
  'Premises and equipment': { b: 'Premises and equipment', o: 'Buildings and equipment' },
  'Other real estate owned': { b: 'Other real estate owned', o: 'Foreclosed property' },
  'Other assets': { b: 'Other assets', o: 'Everything else they own' },
  'Noninterest-bearing demand deposits': { b: 'Noninterest-bearing demand deposits', o: 'Free checking' },
  'Interest checking (NOW)': { b: 'Interest checking (NOW)', o: 'Interest checking' },
  'Savings deposits': { b: 'Savings deposits', o: 'Savings' },
  'Money market deposits': { b: 'Money market deposits', o: 'Money market' },
  'Time deposits (CDs)': { b: 'Time deposits (CDs)', o: 'CDs' },
  'Brokered deposits': { b: 'Brokered deposits', o: 'Bought (brokered) deposits' },
  'Total deposits': { b: 'Total deposits', o: 'Total deposits' },
  'FHLB advances': { b: 'FHLB advances', o: 'FHLB borrowings' },
  'Other liabilities': { b: 'Other liabilities', o: 'Other amounts they owe' },
  'Common stock and surplus': { b: 'Common stock and surplus', o: "Owners' capital" },
  'Retained earnings': { b: 'Retained earnings', o: 'Profits kept in the bank' },
  'Accumulated other comprehensive income': { b: 'Accumulated other comprehensive income', o: 'Paper gain/loss on bonds' },
  'Interest income': { b: 'Interest income', o: 'What loans and bonds earned' },
  'Interest expense': { b: 'Interest expense', o: 'What they paid depositors' },
  'NET INTEREST INCOME': { b: 'NET INTEREST INCOME', o: 'LENDING MARGIN' },
  'Provision for credit losses': { b: 'Provision for credit losses', o: 'Money set aside for bad loans' },
  'Noninterest income': { b: 'Noninterest income', o: 'Fees' },
  'Securities gains (losses)': { b: 'Securities gains (losses)', o: 'Bond sale gains (losses)' },
  'Noninterest expense': { b: 'Noninterest expense', o: 'Operating costs' },
  'PRETAX INCOME': { b: 'PRETAX INCOME', o: 'PROFIT BEFORE TAX' },
  'Income tax': { b: 'Income tax', o: 'Taxes' },
  'NET INCOME': { b: 'NET INCOME', o: 'PROFIT' },
  'Interest income — loans': { b: 'Interest income — loans', o: 'Interest from loans' },
  'Interest income — securities': { b: 'Interest income — securities', o: 'Interest from bonds' },
  'Interest income — other': { b: 'Interest income — other', o: 'Other interest earned' },
  'Interest expense — deposits': { b: 'Interest expense — deposits', o: 'Interest paid on deposits' },
  'Interest expense — wholesale': { b: 'Interest expense — wholesale', o: 'Interest on borrowed money' },
  'Service charges on deposits': { b: 'Service charges on deposits', o: 'Account fees' },
  'Card interchange': { b: 'Card interchange', o: 'Card swipe income' },
  'Salaries and benefits': { b: 'Salaries and benefits', o: 'Pay and benefits' },
  'Occupancy and equipment': { b: 'Occupancy and equipment', o: 'Buildings and gear' },
  'Technology': { b: 'Technology', o: 'Technology' },
  'Marketing': { b: 'Marketing', o: 'Marketing' },
  'FDIC assessment': { b: 'FDIC assessment', o: 'FDIC insurance bill' },
  'Other expense': { b: 'Other expense', o: 'Other costs' },
};
const LOAN_PROD = {
  auto: 'Auto', mortgage: 'Mortgage', heloc: 'HELOC', credit_card: 'Card',
  small_business: 'Small business', ci: 'C&I', cre: 'CRE',
  construction: 'Construction', ag: 'Ag', sba: 'SBA',
};
const DEP_PROD = {
  checking: 'Checking', checking_int: 'NOW', savings: 'Savings',
  money_market: 'Money market', time: 'CDs', brokered: 'Brokered',
};

function rivalStratLabel(strat) {
  const e = RIVAL_STRAT[strat];
  if (!e) return String(strat || '').replace(/_/g, ' ');
  return MODE === 'owner' ? e.o : e.b;
}
function rivalLine(label) {
  const e = RIVAL_LINE[label];
  if (!e) return esc(label);
  return esc(MODE === 'owner' ? e.o : e.b);
}

async function openRival(id) {
  if (!id) { toast('That bank has no books.', true); return; }
  try {
    const d = await api('/api/section?name=rival&id=' + encodeURIComponent(id));
    if (!d || !d.balance_sheet) throw d && d.error ? d.error : 'no books returned';
    showRivalBooks(d);
  } catch (e) { toast(String(e), true); }
}

let RIVAL_OPEN = null;
function rivalNeighbor(dir) {
  const d = RIVAL_OPEN;
  if (!d) return;
  const sibs = d.siblings || [];
  const i = sibs.findIndex(x => x.id === d.id);
  if (i < 0 || !sibs.length) return;
  const n = sibs[(i + dir + sibs.length) % sibs.length];
  if (n) openRival(n.id);
}

function showRivalBooks(d) {
  RIVAL_OPEN = d;
  const bs = d.balance_sheet;
  const isRow = (label, v, strong) =>
    `<tr class="${strong ? 'total' : ''}"><td>${rivalLine(label)}</td><td class="r ${cls(v)}">${fm(v)}</td></tr>`;
  const status = d.alive
    ? ''
    : (MODE === 'owner'
      ? ' <span class="neg">— closed by regulators</span>'
      : ' <span class="neg">— CLOSED</span>');
  const towns = (d.markets || []).map(m => m.name).join(', ') || '—';
  const depRates = (d.posted_rates && d.posted_rates.deposit) || {};
  const loanRates = (d.posted_rates && d.posted_rates.loan) || {};
  const r = d.ratios || {};
  const q = d.quality || {};
  const loanMix = Object.entries(d.mix && d.mix.loans || {})
    .filter(([, v]) => v)
    .sort((a, b) => b[1] - a[1]);
  const depMix = Object.entries(d.mix && d.mix.deposits || {})
    .filter(([, v]) => v)
    .sort((a, b) => b[1] - a[1]);
  const html = `
    <div class="sub" style="margin-bottom:8px">
      ${esc(rivalStratLabel(d.strategy))}
      · ${esc(towns)}
      · ~${d.branches_est || 0} ${MODE === 'owner' ? 'branches (size estimate)' : 'branches est.'}
      ${status}
    </div>
    <div class="cards">
      ${card(dt('roa'), pct(r.roa), 'TTM profit / assets')}
      ${card(dt('nim'), pct(r.nim), MODE === 'owner' ? 'lending margin' : 'NII / assets')}
      ${card(dt('eff'), pct(r.efficiency, 0), 'opex / revenue')}
      ${card(dt('npa'), pct(r.npa_ratio), fm(q.npa) + ' not paying')}
      ${card(dt('cet1'), pct(r.cet1, 1), dt('leverage') + ' ' + pct(r.leverage, 1))}
      ${card(dt('ldr'), r.ldr != null ? r.ldr.toFixed(2) : '—', dt('uninsured') + ' ' + pct(r.uninsured, 0))}
    </div>
    <div class="grid g2">
    <div class="panel tight">
      <h3>${MODE === 'owner' ? 'What they own and owe' : 'Balance sheet'}</h3>
      <table>
        <tr class="section"><td colspan="2">${MODE === 'owner' ? 'What they own' : 'Assets'}</td></tr>
        ${bs.assets.map(([l, v]) => isRow(l, v)).join('')}
        ${isRow('TOTAL ASSETS', bs.total_assets, true)}
        <tr class="section"><td colspan="2">${MODE === 'owner' ? 'What they owe' : 'Liabilities'}</td></tr>
        ${bs.liabilities.map(([l, v]) => isRow(l, v, l === 'Total deposits')).join('')}
        ${isRow('TOTAL LIABILITIES', bs.total_liabilities, true)}
        <tr class="section"><td colspan="2">${MODE === 'owner' ? "Owners' money" : 'Equity'}</td></tr>
        ${bs.equity.map(([l, v]) => isRow(l, v)).join('')}
        ${isRow('TOTAL EQUITY', bs.total_equity, true)}
      </table>
    </div>
    <div class="panel tight">
      <h3>${MODE === 'owner' ? 'Last twelve months' : 'Income statement (TTM)'}</h3>
      <table>
        ${d.income_ttm.lines.map(([l, v]) => isRow(l, v, l === l.toUpperCase())).join('')}
      </table>
      <h3>${MODE === 'owner' ? 'Line detail' : 'P&L line detail'}</h3>
      <table>${d.income_ttm.detail.filter(x => x[1] !== 0).map(([l, v]) =>
        `<tr><td>${rivalLine(l)}</td><td class="r">${fm(v)}</td></tr>`).join('')}</table>
    </div>
    </div>
    <div class="grid g2" style="margin-top:10px">
    <div class="panel tight">
      <h3>${MODE === 'owner' ? 'Loan book' : 'Loan mix'}</h3>
      <table>${loanMix.map(([k, v]) =>
        `<tr><td>${esc(LOAN_PROD[k] || k)}</td><td class="r">${fmc(v)}</td></tr>`).join('')}</table>
    </div>
    <div class="panel tight">
      <h3>${MODE === 'owner' ? 'Deposit book' : 'Deposit mix'}</h3>
      <table>${depMix.map(([k, v]) =>
        `<tr><td>${esc(DEP_PROD[k] || k)}</td><td class="r">${fmc(v)}</td></tr>`).join('')}
        <tr><td>${MODE === 'owner' ? 'Uninsured (est.)' : 'Uninsured (est.)'}</td>
          <td class="r">${fmc(r.uninsured_dollars)}</td></tr></table>
    </div>
    </div>
    <div class="grid g2" style="margin-top:10px">
    <div class="panel tight">
      <h3>${MODE === 'owner' ? 'What they pay for money' : 'Posted deposit rates'}</h3>
      <table>${[['checking','Checking'],['savings','Savings'],['money_market','Money market'],
        ['cd_1y','1-year CD'],['cd_5y','5-year CD']].map(([k, lab]) =>
        `<tr><td>${esc(lab)}</td><td class="r">${pct(depRates[k])}</td></tr>`).join('')}</table>
    </div>
    <div class="panel tight">
      <h3>${MODE === 'owner' ? 'What they charge' : 'Posted loan rates'}</h3>
      <table>${[['mortgage','Mortgage'],['auto','Auto'],['ci','C&I'],['cre','CRE'],
        ['small_business','Small business'],['ag','Ag']].map(([k, lab]) =>
        `<tr><td>${esc(lab)}</td><td class="r">${pct(loanRates[k])}</td></tr>`).join('')}</table>
    </div>
    </div>
    <div class="helptip" style="margin-top:10px">${esc(d.note || '')}</div>`;
  const prev = (d.siblings || []).length > 1
    ? [['← Prev', 'rivalNeighbor(-1)'], ['Next →', 'rivalNeighbor(1)']]
    : [];
  showHtml((d.name || 'Rival') + (d.alive ? '' : ' †'), html, prev, 'books');
}

/* ---------------- Reports ---------------- */
async function tabReports(m) {
  const d = await section('reports');
  const bs = d.balance_sheet;
  const isRow = (label, v, strong) =>
    `<tr class="${strong ? 'total' : ''}"><td>${label}</td><td class="r ${cls(v)}">${fm(v)}</td></tr>`;
  m.innerHTML = `
    <h2>Reports</h2>
    <div class="grid g3">
      <div class="panel"><canvas id="rc-roa" class="chart"></canvas></div>
      <div class="panel"><canvas id="rc-nim" class="chart"></canvas></div>
      <div class="panel"><canvas id="rc-npa" class="chart"></canvas></div>
    </div>
    <div class="grid g3" style="margin-top:10px">
      <div class="panel"><canvas id="rc-dep" class="chart"></canvas></div>
      <div class="panel"><canvas id="rc-eq" class="chart"></canvas></div>
      <div class="panel"><canvas id="rc-eff" class="chart"></canvas></div>
    </div>
    <div class="grid g2" style="margin-top:12px">
    <div class="panel">
      <h3>Balance sheet</h3>
      <table>
        <tr class="section"><td colspan="2">Assets</td></tr>
        ${bs.assets.map(([l, v]) => isRow(esc(l), v)).join('')}
        ${isRow('TOTAL ASSETS', bs.total_assets, true)}
        <tr class="section"><td colspan="2">Liabilities</td></tr>
        ${bs.liabilities.map(([l, v]) => isRow(esc(l), v, l === 'Total deposits')).join('')}
        ${isRow('TOTAL LIABILITIES', bs.total_liabilities, true)}
        <tr class="section"><td colspan="2">Equity</td></tr>
        ${bs.equity.map(([l, v]) => isRow(esc(l), v)).join('')}
        ${isRow('TOTAL EQUITY', bs.total_equity, true)}
      </table>
    </div>
    <div class="panel">
      <h3>Income statement</h3>
      <table><tr><th></th><th class="r">Month to date</th><th class="r">Last quarter</th><th class="r">Trailing 12m</th></tr>
      ${d.income_mtd.lines.map((row, i) => {
        const [label] = row;
        const q = d.income_q.lines[i], y = d.income_ttm.lines[i];
        const strong = label === label.toUpperCase();
        return `<tr class="${strong ? 'total' : ''}"><td>${esc(label)}</td>
          <td class="r ${cls(row[1])}">${fm(row[1])}</td>
          <td class="r ${cls(q[1])}">${fm(q[1])}</td>
          <td class="r ${cls(y[1])}">${fm(y[1])}</td></tr>`;
      }).join('')}
      </table>
      <h3>Full P&amp;L line detail (trailing 12m)</h3>
      <table>${d.income_ttm.detail.filter(x => x[1] !== 0).map(([l, v]) =>
        `<tr><td>${esc(l)}</td><td class="r">${fm(v)}</td></tr>`).join('')}</table>
      <h3>Call reports filed</h3>
      <div class="sub">${d.call_reports.length ? d.call_reports.map(cr =>
        `${esc(cr.date)} (${MODE === 'owner' ? 'report card' : 'CAMELS'} ${cr.camels}, ${esc(cr.pca)})`).join(' · ') : 'none yet'}</div>
    </div>
    </div>`;
  const h = d.metrics_history;
  metricChart('rc-roa', h, 'roa', { title: 'ROA', map: v => v * 100, yfmt: v => v.toFixed(1) + '%', color: '#46c78c', zero: true });
  metricChart('rc-nim', h, 'nim', { title: 'Net interest margin', map: v => v * 100, yfmt: v => v.toFixed(1) + '%', color: '#58a6ff' });
  metricChart('rc-npa', h, 'npa_ratio', { title: 'Nonperforming assets', map: v => v * 100, yfmt: v => v.toFixed(2) + '%', color: '#e06060', zero: true });
  metricChart('rc-dep', h, 'deposits', { title: 'Deposits', map: v => v / 100, yfmt: v => '$' + fmtCompact(v), color: '#e0b050' });
  metricChart('rc-eq', h, 'equity', { title: 'Equity', map: v => v / 100, yfmt: v => '$' + fmtCompact(v), color: '#46c78c' });
  metricChart('rc-eff', h, 'efficiency', { title: 'Efficiency ratio', map: v => v * 100, yfmt: v => v.toFixed(0) + '%', color: '#e06060' });
}

/* ---------------- Ledger ---------------- */
let LEDGER_FILTER = '';
async function tabLedger(m) {
  const d = await section('ledger');
  const entries = d.entries.slice().reverse().filter(e =>
    !LEDGER_FILTER || e.lines.some(l => l[0] === LEDGER_FILTER));
  m.innerHTML = `
    <h2>General ledger <span class="sub">— trial balance: ${d.trial_balance === 0 ?
      '<span class="pos">BALANCED (0)</span>' : `<span class="neg">OFF BY ${d.trial_balance}¢</span>`}</span></h2>
    <div class="grid g2">
    <div class="panel">
      <h3>Chart of accounts (click to filter journal)</h3>
      <table><tr><th>Code</th><th>Account</th><th class="r">Balance</th></tr>
      ${Object.entries(d.balances).map(([code, a]) => `
        <tr class="click ${LEDGER_FILTER === code ? 'total' : ''}" onclick="LEDGER_FILTER=LEDGER_FILTER==='${code}'?'':'${code}';renderTab()">
          <td class="mono">${code}</td><td>${esc(a.name)}</td>
          <td class="r ${cls(a.balance)}">${fm(a.balance)}</td></tr>`).join('')}
      </table>
    </div>
    <div class="panel">
      <h3>Journal ${LEDGER_FILTER ? `— filtered to ${LEDGER_FILTER} <button class="small" onclick="LEDGER_FILTER='';renderTab()">clear</button>` : '(most recent first)'}</h3>
      ${entries.slice(0, 120).map(e => `
        <div class="newsitem"><span class="nd">${esc(e.date)}</span> ${esc(e.memo)}
          <table style="margin:2px 0 4px 60px;width:auto">${e.lines.map(l =>
            `<tr><td class="mono">${l[0]}</td>
             <td class="r mono" style="min-width:90px">${l[1] ? fm(l[1]) : ''}</td>
             <td class="r mono" style="min-width:90px">${l[2] ? fm(l[2]) : ''}</td></tr>`).join('')}
          </table></div>`).join('') || '<span class="sub">No entries match.</span>'}
    </div>
    </div>`;
}

/* ---------------- Events ---------------- */
async function tabEvents(m) {
  const d = await section('events');
  m.innerHTML = `
    <h2>Events & news</h2>
    ${d.pending.length ? `<div class="panel"><h3>Needs attention</h3>
      ${d.pending.map(ev => `<div class="newsitem block">
        <span class="nd">${esc(ev.date)}</span><b>${esc(ev.title)}</b>
        <button class="small" onclick="openEvent(${ev.id})">Open</button>
      </div>`).join('')}</div>` : ''}
    <div class="panel" style="margin-top:10px"><h3>Full log</h3>
      ${newsList(d.log)}
    </div>`;
}

/* ---------------- Event modal ---------------- */
function renderEventModal() {
  const pend = (SUM.pending || []).filter(e => e.blocking);
  const box = $('eventmodal');
  if (!pend.length) { box.classList.add('hidden'); box.innerHTML = ''; return; }
  const ev = pend[0];
  box.classList.remove('hidden');
  let controls = '';
  if (ev.type === 'fdic_auction') {
    const pf = ev.proforma || {};
    const blocked = pf.can_bid === false;
    const why = (pf.blockers || []).join('; ');
    controls = `<div class="ctl"><label>Your bid: deposit premium (bp)</label>
        <input type="number" id="bid-bp" value="80" min="0" max="1000" ${blocked ? 'disabled' : ''}></div>
      <div class="btnrow">
        <button class="primary" ${blocked ? 'disabled title="' + esc(why) + '"' : ''}
          onclick="eventChoice(${ev.id}, 'bid', {premium_bp: numIn('bid-bp')})">${blocked ? 'Cannot close' : 'Submit bid'}</button>
        <button onclick="eventChoice(${ev.id}, 'pass')">Pass</button></div>
      ${blocked ? `<div class="helptip">${esc(why)}</div>` : ''}`;
  } else if (ev.type === 'bank_for_sale') {
    const pf = (ev.deal && ev.deal.proforma) || {};
    const blocked = pf.can_buy === false;
    const why = (pf.blockers || []).join('; ');
    const listed = !!(SUM.treasury && SUM.treasury.listed) || !!(ev.choices || []).includes('buy_stock');
    controls = `<div class="btnrow">
      <button class="primary" ${blocked ? 'disabled title="' + esc(why) + '"' : ''}
        onclick="eventChoice(${ev.id}, 'buy')">${blocked ? 'Cannot close' : 'Buy it (cash)'}</button>
      ${listed && !blocked ? `<button onclick="eventChoice(${ev.id}, 'buy_stock')">Buy 60% cash / 40% stock</button>` : ''}
      <button onclick="eventChoice(${ev.id}, 'hold')">Hold in diligence</button>
      <button onclick="eventChoice(${ev.id}, 'pass')">Pass</button></div>
      ${blocked ? `<div class="helptip">${esc(why)} Hold parks the book so you can raise; a rival may close it.</div>` : ''}`;
  } else if (ev.type === 'exam') {
    const comp = ev.composite || 3;
    const owner = MODE === 'owner' && ev.owner_title;
    controls = `<div class="btnrow">
      <button class="primary" onclick="dismissEvent(${ev.id})">Acknowledged</button></div>`;
    box.innerHTML = `<div class="modalbox exam-modal c${comp}">
      <h2>${esc(owner || ev.title)}</h2>
      <div class="sub">${esc(ev.date)}${pend.length > 1 ? ` · ${pend.length - 1} more waiting` : ''}</div>
      ${ev.owner_summary && MODE === 'owner' ? `<p style="margin:8px 0">${esc(ev.owner_summary)}</p>` : ''}
      <pre>${esc(ev.text || '')}</pre>
      ${controls}
    </div>`;
    return;
  } else if (ev.type === 'quarter_close') {
    controls = `<div class="btnrow">
      <button class="primary" onclick="dismissEvent(${ev.id})">File it</button></div>`;
  } else if (ev.type === 'goal_won') {
    controls = `<div class="btnrow">
      <button class="primary" onclick="eventChoice(${ev.id}, 'keep')">Keep playing</button>
      <button onclick="eventChoice(${ev.id}, 'retire')">Retire to the title screen</button></div>`;
  } else if (ev.type === 'overnight_shortfall') {
    controls = `<div class="btnrow">
      <button class="primary" onclick="eventChoice(${ev.id}, 'fhlb')">Draw 3-month FHLB</button>
      <button onclick="eventChoice(${ev.id}, 'fed_funds')">Borrow fed funds</button>
      <button class="danger" onclick="eventChoice(${ev.id}, 'window')">Use the discount window</button>
      <button onclick="eventChoice(${ev.id}, 'wait')">Wait — shrink originations</button></div>`;
  } else if (ev.type === 'buyout_offer') {
    controls = `<div class="btnrow">
      <button class="danger" onclick="eventChoice(${ev.id}, 'accept')">Sell the bank</button>
      <button class="primary" onclick="eventChoice(${ev.id}, 'decline')">Decline</button></div>`;
  } else if (ev.type === 'fraud_case') {
    controls = `<div class="btnrow">
      <button class="primary" onclick="eventChoice(${ev.id}, 'act')">Act now (freeze / intervene)</button>
      <button onclick="eventChoice(${ev.id}, 'monitor')">Keep monitoring</button></div>`;
  } else {
    controls = `<div class="btnrow">
      <button class="primary" onclick="dismissEvent(${ev.id})">Acknowledged</button></div>`;
  }
  box.innerHTML = `<div class="modalbox">
    <h2>${esc(ev.title)}</h2>
    <div class="sub">${esc(ev.date)}${pend.length > 1 ? ` · ${pend.length - 1} more waiting` : ''}</div>
    <pre>${esc(ev.text || '')}</pre>
    ${controls}
  </div>`;
}

async function eventChoice(id, choice, extra) {
  try {
    const payload = Object.assign({ event_id: id, choice }, extra || {});
    const r = await api('/api/action', { action: 'event_choice', payload });
    if (r.result && r.result.message) toast(r.result.message);
    await refresh();
  } catch (e) { toast(String(e), true); }
}
async function dismissEvent(id) {
  try {
    await api('/api/action', { action: 'dismiss_event', payload: { event_id: id } });
    await refresh();
  } catch (e) { toast(String(e), true); }
}
function openEvent(id) {
  const ev = (SUM.pending || []).find(e => e.id === id) ||
             (SUM.log || []).find(e => e.id === id);
  if (!ev) return;
  if (ev.blocking || ev.choices) {
    SUM.pending = [ev].concat((SUM.pending || []).filter(e => e.id !== id));
    renderEventModal();
  } else showText(ev.title, ev.text || '');
}

/* ---------------- text modal ---------------- */
function showModal(title, bodyHtml, buttons, klass) {
  const box = $('textmodal');
  box.classList.remove('hidden');
  const btns = (buttons || []).map(([label, code, k]) =>
    `<button class="${k || ''}" onclick="${code}">${label}</button>`).join('');
  box.innerHTML = `<div class="modalbox ${klass || ''}" onclick="event.stopPropagation()">
    <h2>${esc(title)}<button class="modal-x" onclick="closeText()" title="Close (Esc)">×</button></h2>
    ${bodyHtml}
    <div class="btnrow">${btns}<button class="primary" onclick="closeText()">Close</button></div>
  </div>`;
  box.onclick = () => closeText();
}
function showText(title, text, buttons) {
  showModal(title, `<pre>${text}</pre>`, buttons);
}
function showHtml(title, html, buttons, klass) {
  showModal(title, `<div class="modalbody">${html}</div>`, buttons, klass);
}
function closeText() {
  const box = $('textmodal');
  box.classList.add('hidden');
  box.innerHTML = '';
  box.onclick = null;
}

function showExam(date, composite, text) {
  const tone = composite <= 2 ? 'they are calm'
    : composite === 3 ? 'they are watching' : 'they are not happy';
  const head = MODE === 'owner'
    ? `Report card: ${composite} — ${tone}.\n\nThe official letter is below.\n\n`
    : '';
  showText((MODE === 'owner' ? 'Report card — ' : 'Report of Examination — ') + date,
           head + (text || ''));
}

/* ---------------- saves ---------------- */
async function showSaves() {
  const d = await api('/api/saves');
  $('topbar').classList.add('hidden');
  $('layout').classList.add('hidden');
  const sc = $('savescreen');
  sc.classList.remove('hidden');
  const latest = (d.saves || [])[0];
  sc.innerHTML = `
    <h2 style="font-size:22px;margin-bottom:4px">🏦 Bank Game</h2>
    <p class="sub" style="margin-bottom:16px">A courthouse square in West Texas. $20 million in assets. Three employees. Your move.</p>
    ${latest ? `<div class="panel">
      <h3>Continue</h3>
      <p>${esc(latest.name)} — ${esc(latest.display_date || latest.date || 'just chartered')}
        · ${latest.assets != null ? fmc(latest.assets) : ''}
        ${latest.goal_label ? `<span class="sub"> · ${esc(latest.goal_label)}</span>` : ''}
        <span class="sub"> · seed ${latest.seed}</span></p>
      <div style="margin-top:8px">
        <button class="primary" onclick='loadSave(${jattr(latest.name)})'>Continue this bank</button>
      </div>
    </div>` : ''}
    <div class="panel">
      <h3>New bank</h3>
      <div class="ctl"><label>Bank name</label>
        <input type="text" id="new-name" class="wide" value="First National Bank of Caprock"></div>
      <div class="ctl"><label>Seed (optional — same seed, same world)</label>
        <input type="text" id="new-seed" placeholder="random"></div>
      <div class="ctl"><label>Home market</label>
        <select id="new-home">
          <option value="caprock" selected>Caprock City, TX</option>
          <option value="verhalen">Verhalen, TX</option>
          <option value="plainview">Plainview, TX</option>
          <option value="lubbock">Lubbock, TX</option>
        </select></div>
      <div class="ctl"><label>Era</label>
        <select id="new-era">
          <option value="sandbox" selected>Sandbox clock (Year 1, Year 2…)</option>
          <option value="historical">Historical 2000</option>
        </select></div>
      <div class="ctl"><label>Difficulty</label>
        <select id="new-diff">
          <option value="easy">Easy — extra $1M capital, slower examiners</option>
          <option value="standard" selected>Standard</option>
          <option value="hard">Hard — thinner cash, hotter competition</option>
        </select></div>
      <div class="ctl"><label>Goal</label>
        <select id="new-goal">
          <option value="world" selected>Biggest bank in the world</option>
          <option value="independent">Stay independent 20 years</option>
          <option value="square">Best bank on the square</option>
          <option value="headline">Don't be the next headline</option>
          <option value="regional">Regional, not reckless</option>
          <option value="sell">Sell well</option>
        </select></div>
      <div class="ctl"><label><input type="checkbox" id="new-guided" checked style="width:auto">
        Guided first year (a tour + advisor nudges — recommended if banking is new to you)</label></div>
      <div style="margin-top:8px"><button class="primary" onclick="newGame()">Charter the bank</button></div>
    </div>
    <div class="panel">
      <h3>Saved banks</h3>
      ${d.saves.length ? `<table><tr><th>Name</th><th>When</th><th class="r">Year</th>
        <th class="r">Assets</th><th>Report card</th><th>Capital</th><th>Goal</th><th></th></tr>
        ${d.saves.map(s => `<tr>
          <td>${esc(s.name)}</td>
          <td>${esc(s.display_date || s.date)}</td>
          <td class="r">${s.year || '—'}</td>
          <td class="r">${s.assets != null ? fmc(s.assets) : '—'}</td>
          <td>${s.camels != null ? (MODE === 'owner' ? 'Report card ' : 'CAMELS ') + s.camels : '—'}</td>
          <td>${esc(s.pca || '—')}</td>
          <td>${esc(s.goal_label || '')}</td>
          <td><button class="small primary" onclick='loadSave(${jattr(s.name)})'>Load</button>
              <button class="small danger" onclick='if(confirm("Delete this save?"))deleteSave(${jattr(s.name)})'>Delete</button></td>
        </tr>`).join('')}</table>` : '<span class="sub">No saved banks yet.</span>'}
    </div>
    ${d.current ? `<div class="panel">
      <h3>Roll back "${esc(d.current)}"</h3>
      <div class="helptip">Return to an earlier autosave. Everything after it is discarded.</div>
      <table><tr><th>Day</th><th>Date</th><th></th></tr>
      ${d.snapshots.slice(0, 25).map(s => `<tr>
        <td class="mono">#${s.day_index}</td><td>${esc(s.date)} ${s.quarter_end ? '<span class="pill b">Q-END</span>' : ''}</td>
        <td><button class="small" onclick="rollback(${s.day_index})">Roll back here</button></td></tr>`).join('')}
      </table></div>` : ''}`;
}
async function newGame() {
  try {
    const seedRaw = $('new-seed').value.trim();
    const body = { name: $('new-name').value.trim() || 'First National Bank of Caprock' };
    if (seedRaw) body.seed = parseInt(seedRaw) || 0;
    body.guided = $('new-guided') ? $('new-guided').checked : true;
    if ($('new-home')) body.home = $('new-home').value;
    if ($('new-era')) body.era = $('new-era').value;
    if ($('new-diff')) body.difficulty = $('new-diff').value;
    if ($('new-goal')) body.goal = $('new-goal').value;
    const r = await api('/api/new', body);
    toast('Charter granted. Seed: ' + r.seed);
    await refresh();
  } catch (e) { toast(String(e), true); }
}
async function loadSave(name) {
  try { await api('/api/load', { name }); await refresh(); }
  catch (e) { toast(String(e), true); }
}
async function deleteSave(name) {
  try { await api('/api/delete_save', { name }); await showSaves(); }
  catch (e) { toast(String(e), true); }
}
async function rollback(day) {
  try { await api('/api/rollback', { day_index: day }); toast('Rolled back.'); await refresh(); }
  catch (e) { toast(String(e), true); }
}

/* ---------------- keyboard ---------------- */
function modalOpen() {
  const t = $('textmodal'), ev = $('eventmodal');
  return (t && !t.classList.contains('hidden')) || (ev && !ev.classList.contains('hidden'));
}

document.addEventListener('keydown', e => {
  if (e.target.tagName === 'INPUT' || e.target.tagName === 'SELECT') return;
  const savesOpen = $('savescreen') && !$('savescreen').classList.contains('hidden');
  if (savesOpen) return;
  const textOpen = $('textmodal') && !$('textmodal').classList.contains('hidden');
  if ((e.key === 'Escape' || e.key === 'Esc') && textOpen) {
    e.preventDefault();
    closeText();
    return;
  }
  if (modalOpen()) return;
  if (e.key === ' ') { e.preventDefault(); advance('day'); }
  else if (e.key === 'w') advance('week');
  else if (e.key === 'm') advance('month');
  else if (e.key === 'q') advance('quarter');
  else if (e.key === 'u') advance('until');
});

refresh().catch(e => {
  document.body.innerHTML = '<div class="banner red" style="margin:40px">Cannot reach the game server: '
    + esc(e) + '</div>';
});
