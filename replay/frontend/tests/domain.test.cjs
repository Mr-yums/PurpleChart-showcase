// Tests du domaine front (node:test) : sizing, marques, dominances, value area, études, timeframes.
// Les sources TypeScript sont transpilées à la volée (même approche que PurpleChart v2).
const { test } = require('node:test');
const assert = require('node:assert/strict');
const ts = require('../../../frontend/node_modules/typescript');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');

function load(rel, modules = {}) {
	const src = fs.readFileSync(path.join(__dirname, '..', 'lib', rel), 'utf8');
	const out = ts.transpileModule(src, { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 } }).outputText;
	const box = { exports: {}, require: (n) => { if (modules[n]) return modules[n]; const m = n.replace(/^\$replay\//, '').replace(/^\.\.?\//, ''); throw new Error('module non simulé: ' + n + ' (' + m + ')'); }, Date, Math, Number, JSON, Map, Set, Intl, localStorage: undefined, console, setTimeout, clearTimeout, setInterval, clearInterval, Promise };
	vm.createContext(box);
	vm.runInContext(out, box);
	return box.exports;
}

const { RiskCalculator } = load('domain/orders/RiskCalculator.ts');
const spec = { symbol: 'NQ', tick_size: 0.25, tick_value: 5, point_value: 20, fee_round_trip: 3.78, max_contracts: 20, min_bracket_ticks: 4, default_risk_usd: 250, dry_run: true };

test('sizing : contrats = floor(budget / (ticks × valeur)), plancher 1, plafond serveur, TP miroir', () => {
	const c = new RiskCalculator(spec);
	const z = c.evaluate({ side: 'buy', sl: 97, tp: 106 }, 100, 250);
	assert.equal(z.slTicks, 12); assert.equal(z.qty, 4); assert.equal(z.risk, 240); assert.equal(z.tpTicks, 24); assert.equal(z.gain, 480); assert.equal(z.rr, 2); assert.ok(z.valid);
	assert.equal(c.evaluate({ side: 'buy', sl: 99.75, tp: null }, 100, 250).tooClose, true);
	const floored = c.evaluate({ side: 'sell', sl: 200, tp: null }, 100, 250);
	assert.ok(floored.floored && !floored.valid && floored.qty === 1);
	assert.equal(c.evaluate({ side: 'buy', sl: 101, tp: null }, 100, 250).badSL, true);
	assert.equal(c.evaluate({ side: 'buy', sl: 99, tp: 98 }, 100, 250).badTP, true);
	assert.equal(c.autoStop('buy', 100, 1, 250), 87.5);      // 50 ticks × 5 $ = 250 $
	assert.equal(c.target('sell', 100, 102, 1.5), 97);
	assert.equal(c.snap(100.13), 100.25);
});

const { normalizeMark, MarkStore } = load('domain/marks/MarkStore.ts');
test('marques : normalisation, dédoublonnage, live TTL conservé, tri chronologique', async () => {
	const m = normalizeMark({ t: 10.7, price: 100, side: 'sell', kind: 'sweep', volume: 12, trigger_volume: 30, score: 55 });
	assert.equal([m.t, m.vol, m.side, m.kind].join(), '10,30,sell,sweep');
	assert.equal(normalizeMark({ price: null }), null);
	const store = new MarkStore(null);
	store.setSymbol('NQ');
	store.seed([{ t: 5, price: 1, side: 'buy', kind: 'block', volume: 20 }, { t: 3, price: 1, side: 'buy', kind: 'absorb', volume: 9 }]);
	store.pushTrades([{ t: 5, price: 1, side: 'buy', kind: 'block', volume: 20, symbol: 'NQ', timestamp: '', trigger_volume: 20 }, { t: 6, price: 2, side: 'sell', volume: 3, symbol: 'NQ', timestamp: '' }]);
	assert.equal(store.marks.map((x) => x.t).join(), '3,5');
	assert.ok(store.marks[1].liveUntil > 0, 'une marque revue en live garde son TTL');
	store.setSymbol('ES');
	assert.equal(store.marks.length, 0);
});

test('marques : chargement par tranches horaires borné au curseur, subdivision si tronqué', async () => {
	const calls = [];
	const fetcher = async (symbol, from, to, limit) => { calls.push([from, to]); return { big_prints: [{ t: from + 1, price: 1, side: 'buy', kind: 'block', volume: 1 }], truncated: from === 0 && to - from > 1000 }; };
	const store = new MarkStore(fetcher);
	store.setSymbol('NQ'); store.chunkSec = 3600; store.minChunkSec = 300;
	store.setCursorCap(7200);
	store.requestRange(100, 100000);
	await new Promise((r) => setTimeout(r, 400));
	assert.ok(calls.every(([, to]) => to <= 7200), 'aucune tranche au-delà du curseur');
	assert.ok(calls.some(([from, to]) => from === 0 && to - from < 3599), 'la tranche tronquée est subdivisée');
	assert.ok(store.marks.length >= 2);
});

const va = load('domain/profile/valueArea.ts');
test('value area 70 % depuis le POC, tick estimé, bins', () => {
	const map = new Map();
	for (const [p, v, side] of [[100, 10, 'buy'], [100.25, 50, 'sell'], [100.5, 30, 'buy'], [100.75, 5, 'buy'], [101, 5, 'sell']]) va.addCell(map, p, v, side);
	const st = va.profileStats(map);
	assert.equal(st.poc, 100.25); assert.equal(st.val, 100.25); assert.equal(st.vah, 100.5); assert.equal(st.total, 100); assert.equal(st.netDelta, 45 - 55);
	assert.equal(va.estimateTick([100, 100.25, 100.5]), 0.25);
	assert.equal(va.binLevels(map.values(), 0.5).length, 3);
	assert.equal(va.normalizeCell({ timestamp: '2026-08-27T13:00:00Z', price: 1, volume: 2 }).t, Date.parse('2026-08-27T13:00:00Z') / 1000);
	assert.equal(va.normalizeCell({ t: 0, price: 1, volume: 2 }), null);
});

const studies = load('domain/indicators/studies.ts');
test('EMA incrémentale et VWAP Globex/RTH', () => {
	const candles = Array.from({ length: 30 }, (_, i) => ({ time: 1787835600 + i * 60, open: 100, high: 101 + i, low: 99, close: 100 + i, volume: 10 }));
	const e = new studies.EmaTracker(20);
	const pts = e.seed(candles);
	assert.equal(pts.length, 11);
	const next = e.update({ time: candles[29].time + 60, open: 1, high: 1, low: 1, close: 200, volume: 1 });
	assert.ok(next.value > pts[pts.length - 1].value);
	assert.equal(e.update({ time: 0, open: 1, high: 1, low: 1, close: 1, volume: 1 }), null, 'une bougie passée ne réécrit pas l’EMA');
	const v = new studies.VwapTracker();
	const r = v.seed(candles);
	assert.equal(r.vwap.length, 30); assert.ok(r.up2[5].value > r.up1[5].value && r.dn1[5].value > r.dn2[5].value);
	v.mode = 'rth';
	assert.equal(studies.vwapSessionKey(1787835600 + 3600, 'rth') != null, true);   // 14:00 UTC = RTH
	assert.equal(studies.vwapSessionKey(1787835600 - 3600 * 2, 'rth'), null);       // 11:00 UTC = hors RTH
});

const tfs = load('domain/timeframes.ts');
test('timeframes alignés sur l’epoch, comme le backend', () => {
	assert.equal(tfs.tfSeconds('15s'), 15); assert.equal(tfs.tfSeconds('4h'), 14400); assert.equal(tfs.tfSeconds('1D'), 86400);
	assert.equal(tfs.bucketStart(1787835661, 300), 1787835600);
	assert.throws(() => tfs.tfSeconds('1W'));
});

const {sessionTime}=load('domain/replay/sessionTime.ts');
test('séance de nuit : 22h30 appartient à la veille, 15h30 au jour de clôture',()=>{
 const epoch=s=>Date.parse(s)/1000;
 const session={date:'2026-09-09',session_start:epoch('2026-09-08T22:00:00Z'),first_ts:epoch('2026-09-08T22:00:01Z'),last_ts:epoch('2026-09-09T21:00:00Z')};
 assert.equal(sessionTime(session,22,30),epoch('2026-09-08T22:30:00Z'));
 assert.equal(sessionTime(session,15,30),epoch('2026-09-09T15:30:00Z'));
 assert.equal(sessionTime(session,21,30),session.last_ts-60);
});

test('couches front : le domaine reste indépendant du transport et des composants', () => {
 const lib=path.join(__dirname,'..','lib');
 for (const layer of ['domain','api','websocket','application']) {
  for(const file of fs.readdirSync(path.join(lib,layer),{recursive:true}).filter(f=>f.endsWith('.ts'))) {
   const source=ts.createSourceFile(file,fs.readFileSync(path.join(lib,layer,file),'utf8'),ts.ScriptTarget.Latest,true);
   for(const node of source.statements.filter(ts.isImportDeclaration)) {
    const target=node.moduleSpecifier.text;
    if(layer==='domain') assert(!/svelte|\$replay\/(api|application|websocket|components)/.test(target),`${layer}/${file} -> ${target}`);
    if(layer==='api'||layer==='websocket') assert(!/\$replay\/(application|components)/.test(target),`${layer}/${file} -> ${target}`);
    if(layer==='application') assert(!target.includes('$replay/components'),`${layer}/${file} -> ${target}`);
   }
  }
 }
});

const {accountValue}=load('domain/account/valuation.ts');
test('compte : valeur = solde + résultat ouvert, sans compter les frais deux fois',()=>{
 const account={balance:49990,starting_balance:50000,fees_total:10};
 assert.equal(accountValue(account,[],null,'NQ').equity,49990);
 const position={symbol:'NQ',side:'LONG',entry:100,size:2,point_value:20,pnl:null};
 assert.equal(accountValue(account,[position],102,'NQ').equity,50070);
 assert.equal(accountValue(account,[{...position,side:'SHORT'}],102,'NQ').unrealized,-80);
 assert.equal(accountValue(account,[position],null,'NQ').equity,null);
 assert.equal(accountValue(account,[position],102,'ES').equity,null);
 assert.equal(accountValue(account,[{...position,pnl:12}],102,'ES').equity,50002);
});

const {createRequire}=require('node:module');
const {writable,get}=createRequire(path.resolve(__dirname,'../../../frontend/package.json'))('svelte/store');
const {GammaStore}=load('application/GammaStore.ts',{'svelte/store':{writable,get},'$replay/api/gex':{GexApi:{}},'./MarketStore':{market:{status:writable({loaded:false})}}});
const gammaLevel=(time,spot=100)=>({time,spot,netGamma:1,regime:'RANGE',cw_d:.01,pw_d:-.01,fl_d:0});
const statusAt=(symbol,cursor=1000)=>({loaded:true,symbol,cursor_ts:cursor,context_start:100,start_ts:500});
const flush=()=>new Promise(resolve=>setTimeout(resolve,0));

test('gamma : ES vers NQ puis MNQ à la même heure recharge immédiatement',async()=>{
 const status=writable(statusAt('ES'));const calls=[];
 const gamma=new GammaStore(status,async(symbol,from,to)=>{calls.push(symbol);return {levels:[gammaLevel(to)],stale:false}},()=>0);
 gamma.start();
 try {
  assert.equal(get(gamma).phase,'unsupported');
  status.set(statusAt('NQ'));await flush();assert.equal(get(gamma).phase,'ready');assert.equal(get(gamma).symbol,'NQ');
  status.set(statusAt('MNQ'));await flush();assert.equal(get(gamma).symbol,'MNQ');assert.deepEqual(calls,['NQ','MNQ']);
 } finally {gamma.stop();}
});

test('gamma : réponse ancienne ignorée et niveaux effacés au retour en arrière',async()=>{
 const status=writable(statusAt('NQ'));const pending=[];
 const gamma=new GammaStore(status,()=>new Promise(resolve=>pending.push(resolve)),()=>0);
 gamma.start();
 try {
  status.set(statusAt('MNQ'));
  pending[1]({levels:[gammaLevel(900,200)],stale:false});await flush();
  pending[0]({levels:[gammaLevel(900,100)],stale:false});await flush();assert.equal(get(gamma).level.spot,200);
  status.set(statusAt('MNQ',800));assert.equal(get(gamma).level,null);
  pending[2]({levels:[gammaLevel(900)],stale:false});await flush();assert.equal(get(gamma).phase,'empty');
 } finally {gamma.stop();}
});

test('gamma : nouvelle tentative après erreur même si le replay reste en pause',async()=>{
 const status=writable(statusAt('NQ'));let now=0,calls=0;
 const gamma=new GammaStore(status,async()=>{if(++calls===1)throw Error('indisponible');return {levels:[gammaLevel(900)],stale:false}},()=>now);
 gamma.start();
 try {await flush();assert.equal(get(gamma).phase,'error');now=4001;gamma.refresh();await flush();assert.equal(get(gamma).phase,'ready');} finally {gamma.stop();}
});
