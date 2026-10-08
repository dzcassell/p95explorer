'use strict';
const $ = id => document.getElementById(id);
const regions = ['Group 1','Group 2','China','Vietnam','Morocco','Unassigned'];
let state, result, assessment, scenario = {model:'site',growth:0,headroom:20,pools:{},sites:{}};
let requestVersion = 0, timer, poll;
const fmt = v => v == null ? 'Unverified' : Number(v).toLocaleString(undefined,{maximumFractionDigits:1});
const esc = s => String(s).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const text = (id, value) => { $(id).textContent = value; };
async function api(path, body) {
  const r = await fetch('/api/'+path,body === undefined ? {} : {method:'POST',headers:{'Content-Type':'application/json','X-P95-CSRF':state.csrf},body:JSON.stringify(body)});
  const data = await r.json();
  if (!r.ok) throw new Error(data.error || 'Request failed');
  return data;
}
function error(e){ text('status',e.message); }
async function refresh(month){
  state = await api('state');
  scenario = state.scenario || {name:'Working scenario',model:'site',growth:0,headroom:20,pools:{},sites:{},horizon:12,increment:10};
  normalizeScenario();
  scenario.pools ||= {}; scenario.sites ||= {};
  text('tenant',state.tenant === 'demo' ? 'Synthetic demo tenant' : 'Tenant '+state.tenant);
  $('month').innerHTML = state.months.map(m=>`<option>${esc(m)}</option>`).join('');
  if (month && state.months.includes(month)) $('month').value=month;
  for(const key of ['model','growth','headroom']) $(key).value=scenario[key] ?? (key === 'headroom' ? 20 : 0);
  result=null;$('sites').innerHTML='';
  populateAssessmentControls();
  if (state.env_configured) $('endpoint').value=state.endpoint;
  if (state.env_configured) text('connectStatus','Docker credentials available. Leave ID and key blank to use them.');
  if (state.months.length) await recalc();
  else {
    $('metrics').innerHTML='<div class="metric"><p>No data yet</p><h2>Start with a demo or connect your tenant.</h2></div>';
    $('chart').innerHTML=''; $('sites').innerHTML=''; $('pools').innerHTML='';
  }
}
function schedule(){ clearTimeout(timer);timer=setTimeout(()=>recalc().catch(error),300); }
async function recalc(){
  if (!$('month').value) return;
  const version=++requestVersion;
  $('comparison').innerHTML='';
  readAssessmentControls();
  scenario.model=$('model').value;
  scenario.growth=Number($('growth').value); scenario.headroom=Number($('headroom').value);
  text('growthValue',scenario.growth+'%');text('headroomValue',scenario.headroom+'%');
  const data=await api('analyze',{month:$('month').value,scenario});
  if(version!==requestVersion)return;
  result=data; render();
  const h=await api('history',{months:selectedMonths(),scenario});
  if(version!==requestVersion)return;assessment=h;renderHistory();
}
function svgChart(values, threshold, sorted=false){
  if(!values.length)return '<p class="muted">No observations in this month.</p>';
  const w=900,h=260,pad=42,max=Math.max(...values,threshold||0,1)*1.12;
  const x=i=>pad+i/Math.max(1,values.length-1)*(w-pad-15), y=v=>h-pad-v/max*(h-pad-16);
  const points=values.map((v,i)=>`${x(i).toFixed(1)},${y(v).toFixed(1)}`).join(' ');
  const grid=[0,.25,.5,.75,1].map(f=>`<line x1="${pad}" y1="${y(max*f)}" x2="${w-15}" y2="${y(max*f)}" stroke="#263346"/><text x="0" y="${y(max*f)+4}" fill="#99a8bd" font-size="10">${fmt(max*f)}</text>`).join('');
  const line=threshold===undefined?'':`<line x1="${pad}" x2="${w-15}" y1="${y(threshold)}" y2="${y(threshold)}" stroke="#ecb574" stroke-dasharray="5 5"/><text x="${pad+8}" y="${Math.max(14,y(threshold)-7)}" fill="#ecb574" font-size="11">P95 ${fmt(threshold)} Mbps</text>`;
  return `<svg role="img" aria-label="${sorted?'Sorted five-minute usage and P95 cutoff':'Aggregate bandwidth over the observation month'}" viewBox="0 0 ${w} ${h}">${grid}<polygon points="${pad},${h-pad} ${points} ${w-15},${h-pad}" fill="#68ddc11a"/><polyline points="${points}" stroke="#68ddc1" fill="none" stroke-width="1.8"/>${line}<text x="${pad}" y="${h-7}" fill="#99a8bd" font-size="11">${sorted?'Lowest bucket':'Start of month'}</text><text x="${w-125}" y="${h-7}" fill="#99a8bd" font-size="11">${sorted?'Highest bucket':'End of observations'}</text></svg>`;
}
function render(){
  const r=result;
  if(r.sites.some(s=>s.source.includes('synthetic-demo')))text('tenant','Synthetic demo assessment');
  const above = ['site','enforced-pool'].includes(scenario.model) ? r.sites.filter(s=>s.excess>0).length : r.pools.filter(p=>p.excess>0).length;
  const cov=r.sites.length ? r.sites.reduce((a,s)=>a+s.coverage,0)/r.sites.length : 0;
  const metric=(name,value,caption)=>`<div class="metric"><p>${name}</p><div class="value">${value}</div><p>${caption}</p></div>`;
  $('metrics').innerHTML=metric('Planning capacity',r.total_recommended==null?'Withheld':fmt(r.total_recommended)+' <small>Mbps</small>',r.ready?'Evidence checks passed':'Resolve missing data and assumptions')+metric('Simultaneous aggregate peak',fmt(r.peak)+' <small>Mbps</small>','Context only · not regional billing')+metric('Above modeled capacity',scenario.model_verified?above:'Not assessed',['site','enforced-pool'].includes(scenario.model)?'Confirmed sites above allocation':'Confirmed regions above capacity')+metric('Month coverage',fmt(cov)+'%','Known five-minute buckets / expected');
  // Preserve spikes when reducing the display data: use the maximum of each group.
  const values=r.series.map(s=>s.mbps), step=Math.max(1,Math.ceil(values.length/750));
  const display=[];for(let i=0;i<values.length;i+=step)display.push(Math.max(...values.slice(i,i+step)));
  $('chart').innerHTML=svgChart(display);
  $('warnings').innerHTML=r.warnings.map(w=>`<div class="warning">${esc(w)}</div>`).join('');
  const helps={
    'bursting-2027':'Daily site P95 → sum by region → highest daily aggregate in the month. For the January 2027 model; current documentation profile.',
    'enforced-pool':'A legacy pool funds fixed site allocations. Allocation totals must fit the pool, and each site limit must support its traffic.',
    'site':'Fixed site capacity is compared with observed peak throughput. Traffic already shaped by a license may conceal unmet demand.',
    'classic-p95':'Sort an entire month per site and exclude the top 5%. An educational alternative, not the Cato 2027 pool calculation.'};
  text('modelHelp',helps[scenario.model]);
  text('poolTitle',scenario.model==='site'?'Site capacity summarized by region':'How much is enough?');
  const poolKeys=r.pools.map(p=>p.region).join('|');
  if($('poolInputs').dataset.keys!==poolKeys){
    $('poolInputs').dataset.keys=poolKeys;
    $('poolInputs').innerHTML=r.pools.map((p,i)=>`<label>${esc(p.region)} pool · Mbps<input type="number" min="0" max="1000000" placeholder="Unverified" value="${scenario.pools[p.region]??''}" data-pool="${i}"></label>`).join('');
    $('poolInputs').querySelectorAll('input').forEach(el=>el.addEventListener('input',()=>{scenario.pools[result.pools[Number(el.dataset.pool)].region]=el.value===''?null:Number(el.value);schedule();}));
  }
  $('poolInputs').hidden=scenario.model==='site';
  $('pools').innerHTML=r.pools.map(p=>{
    const isSite=scenario.model==='site', capacity=isSite?p.allocation:p.capacity;
    const excess=p.excess, usage=capacity&&p.observed!=null ? Math.min(100,p.observed/capacity*100) : 0;
    return `<article class="poolcard"><h3>${esc(p.region)} ${!p.supported?'· model ineligible':''}</h3><span class="big">${fmt(p.observed)} <small>${p.observed==null?'':'Mbps'}</small></span><p class="muted">${scenario.model==='enforced-pool'?'Assigned allocations':isSite?'Sum of observed site peaks':'Complete-day observed usage'} / ${fmt(capacity)} capacity</p><p class="quality">${p.complete?'Full month':'Incomplete month'} · ${p.status==='ready'?'Inventory confirmed':'Inventory / model needs review'}</p><div class="track"><div class="fill" style="width:${usage}%"></div></div><p class="${excess>0?'danger':'muted'}">${excess==null?'Capacity comparison not verified':excess>0?fmt(excess)+' Mbps above capacity':'Within entered capacity'}</p>${p.enforced_minimum!=null?`<p class="quality">Enforced site-limit minimum: ${fmt(p.enforced_minimum)} Mbps</p>`:''}<p>Plan: <strong>${p.recommendation==null?'Withheld':fmt(p.recommendation)+' Mbps'}</strong></p><p class="muted">Determining day: ${esc(p.determining_day||'No complete regional day')} · ${p.excluded_days} partial days excluded</p><button data-evidence="${esc(p.region)}">Explain this number</button></article>`;
  }).join('');
  $('pools').querySelectorAll('[data-evidence]').forEach(el=>el.onclick=()=>openEvidence(el.dataset.evidence).catch(error));
  renderAssumptionFields();
  const focused=document.activeElement?.dataset.site !== undefined;
  if(!focused){
    $('sites').innerHTML=r.sites.map((s,i)=>`<tr><td>${esc(s.name)}<div class="quality">${esc(s.source)}<br>${s.missing_buckets} missing buckets<br>Longest gap: ${s.longest_gap_minutes} min</div></td><td><select aria-label="License region for ${esc(s.name)}" data-site="${i}" data-field="region">${regions.map(region=>`<option ${region===s.region?'selected':''}>${esc(region)}</option>`).join('')}</select></td><td><input aria-label="Allocation Mbps for ${esc(s.name)}" type="number" min="0" max="1000000" placeholder="Unverified" value="${s.capacity??''}" data-site="${i}" data-field="capacity"></td><td><select aria-label="Connection type for ${esc(s.name)}" data-site="${i}" data-field="type">${['Unknown','SOCKET_X1500','IPSEC_V2','CLOUD_INTERCONNECT',s.type].filter((v,i,a)=>a.indexOf(v)===i).map(t=>`<option ${t===s.type?'selected':''}>${esc(t)}</option>`).join('')}</select><label class="check"><input aria-label="Verify inventory for ${esc(s.name)}" type="checkbox" data-site="${i}" data-field="verified" ${s.verified?'checked':''}>Confirmed</label><label class="check"><input aria-label="Enforce site limit for ${esc(s.name)}" type="checkbox" data-site="${i}" data-field="enforced" ${scenario.sites[s.id]?.enforced?'checked':''}>Optional enforcement</label></td><td><input aria-label="Growth for ${esc(s.name)}" type="number" min="-90" max="1000" placeholder="Inherit" value="${scenario.sites[s.id]?.growth??''}" data-site="${i}" data-field="growth"></td><td>${fmt(s.p95)} Mbps</td><td>${fmt(s.peak)} Mbps</td><td>${s.recommendation==null?'Withheld':fmt(s.recommendation)+' Mbps'}${s.constrained?`<div class="quality">Fixed site limit: ${s.site_limit_recommendation==null?'Withheld':fmt(s.site_limit_recommendation)+' Mbps'}</div>`:''}</td><td class="${s.excess>0?'danger':''}">${s.over_minutes==null?'Unverified':fmt(s.over_minutes)}</td><td>${fmt(s.coverage)}%<div class="muted">${s.complete_days} complete days</div></td></tr>`).join('');
    $('sites').querySelectorAll('[data-site]').forEach(el=>el.addEventListener(el.type==='number'?'input':'change',(event)=>{
      const s=result.sites[Number(el.dataset.site)];
      scenario.sites[s.id] ||= {region:s.region,capacity:s.capacity,type:s.type,verified:s.verified,enforced:false};
      const field=el.dataset.field;scenario.sites[s.id][field]=['verified','enforced'].includes(field)?el.checked:['capacity','growth'].includes(field)?(el.value===''?null:Number(el.value)):el.value;
      if(event.type==='change')el.blur(); schedule();
    }));
  }
  $('sites').querySelectorAll('input[type=number]').forEach(el=>el.addEventListener('blur',schedule));
  $('export').href='/api/export?month='+encodeURIComponent(r.month);
}
function lesson(){
  const count=Number($('spike').value)/5, values=Array(288-count).fill(50).concat(Array(count).fill(200));
  const cutoff=values[273];
  text('spikeValue',$('spike').value+' min');
  $('lessonChart').innerHTML=svgChart(values,cutoff,true);
  text('lessonResult',`Daily P95: ${cutoff} Mbps · ${count<=14?'the burst fits in the 14 excluded buckets':'the burst lasts beyond the 14 excluded buckets'}`);
}
function creds(){return {account:$('account').value.trim(),key:$('key').value,endpoint:$('endpoint').value.trim()};}
$('connect').onclick=()=>$('connection').showModal();$('close').onclick=()=>$('connection').close();
$('model').onchange=schedule;$('growth').oninput=schedule;$('headroom').oninput=schedule;
$('month').onchange=()=>recalc().catch(error);$('spike').oninput=lesson;
$('demo').onclick=async()=>{try{const month=$('month').value||previousMonth();text('status','Preparing synthetic observations…');await api('demo',{month,months:3});$('poolInputs').dataset.keys='';await refresh(month);text('status','Demo data loaded. All tenant usage is synthetic.');}catch(e){error(e);}};
$('save').onclick=async()=>{try{readAssessmentControls();await api('scenario',{scenario});text('status','Scenario and verified site mapping saved locally.');}catch(e){error(e);}};
$('import').onclick=()=>$('file').click();
$('file').onchange=async()=>{const file=$('file').files[0];if(!file)return;try{if(file.size>10_000_000)throw new Error('CSV must be below 10 MB.');await api('import',{tenant:'imported',csv:await file.text()});$('poolInputs').dataset.keys='';await refresh();text('status','CSV imported into the local workspace.');}catch(e){error(e);}finally{$('file').value='';}};
$('discover').onclick=async()=>{const btn=$('discover');btn.disabled=true;try{text('connectStatus','Discovering sites…');const data=await api('discover',creds());$('discovered').innerHTML=data.sites.map(s=>`<label><input type="checkbox" value="${esc(s.id)}"> ${esc(s.name)} · ${esc(s.info?.countryCode||'Verify site')} · ${esc(s.info?.connType||'Unknown type')}</label>`).join('');text('connectStatus','Select physical or cloud sites. Leave remote users unchecked.');}catch(e){text('connectStatus',e.message);}finally{btn.disabled=false;}};
$('connectForm').onsubmit=async e=>{e.preventDefault();try{const ids=Array.from($('discovered').querySelectorAll('input:checked'),el=>el.value);await api('sync',{...creds(),site_ids:ids,start_month:$('collectStart').value,month:$('collectMonth').value});$('key').value='';text('connectStatus','Collection started. You can close this window.');text('status','Collecting five-minute peaks…');pollJob();}catch(e){text('connectStatus',e.message);}};
function pollJob(){clearTimeout(poll);poll=setTimeout(async()=>{try{const s=await api('state');if(s.job.state==='running'){text('status',`Collecting Cato usage: ${s.job.completed} / ${s.job.total||'?'} batches. Buckets are saved as they arrive.`);pollJob();}else if(s.job.state==='done'){$('poolInputs').dataset.keys='';await refresh($('collectMonth').value);text('status','Collection complete. Verify every site license region and allocation before evaluating a scenario.');}else{text('status',s.job.error||'Collection stopped.');}}catch(e){error(e);}},2500);}
function previousMonth(){const d=new Date();d.setUTCDate(1);d.setUTCMonth(d.getUTCMonth()-1);return d.toISOString().slice(0,7);}
$('collectStart').value=previousMonth();$('collectMonth').value=previousMonth();$('planStart').value=new Date().toISOString().slice(0,7);lesson();refresh().then(()=>{if(state.job.state==='running')pollJob();}).catch(error);
function normalizeScenario(){
  scenario.name ||= 'Working scenario';scenario.model ||= 'site';scenario.pools ||= {};scenario.sites ||= {};
  scenario.region_growth ||= {};scenario.cma ||= {};scenario.planned_sites ||= [];
  scenario.commercial ||= {currency:'USD',flat_monthly:0,expansion_fee:0,rates:{},overage_rates:{},verified:false};
  scenario.commercial.rates ||= {};scenario.commercial.overage_rates ||= {};
}
function selectedMonths(){
  const months=Array.from($('monthChecks').querySelectorAll('input:checked'),el=>el.value);
  return months.length?months:[$('month').value];
}
function populateAssessmentControls(){
  normalizeScenario();
  text('status','');
  $('scenarioName').value=scenario.name;$('modelVerified').checked=!!scenario.model_verified;
  $('increment').value=scenario.increment??10;$('monthlyGrowth').value=scenario.monthly_growth??0;
  $('horizon').value=scenario.horizon??12;$('currency').value=scenario.commercial.currency||'USD';
  $('flatMonthly').value=scenario.commercial.flat_monthly??0;$('expansionFee').value=scenario.commercial.expansion_fee??0;
  $('discount').value=scenario.commercial.discount??0;$('skuCatalog').value=scenario.commercial.catalog&&Object.keys(scenario.commercial.catalog).length?JSON.stringify(scenario.commercial.catalog,null,2):'';
  $('pricesVerified').checked=!!scenario.commercial.verified;
  $('savedScenario').innerHTML='<option value="">Working scenario</option>'+Object.entries(state.scenarios||{}).map(([id,s])=>`<option value="${esc(id)}">${esc(s.name)}</option>`).join('');
  $('monthChecks').innerHTML=state.months.slice(0,24).map((m,i)=>`<label><input type="checkbox" value="${m}" ${scenario.months?.length?(scenario.months.includes(m)?'checked':''):(i<3?'checked':'')}> ${m}</label>`).join('');
  $('monthChecks').querySelectorAll('input').forEach(el=>el.onchange=schedule);
  $('poolInputs').dataset.keys='';$('poolInputs').innerHTML='';$('regionGrowth').dataset.keys='';$('regionGrowth').innerHTML='';$('rates').innerHTML='';$('cmaInputs').dataset.keys='';$('cmaInputs').innerHTML='';
  renderCompareChoices();renderPlans();
}
function readAssessmentControls(){
  normalizeScenario();
  scenario.model=$('model').value;scenario.growth=Number($('growth').value);scenario.headroom=Number($('headroom').value);scenario.months=selectedMonths();
  scenario.name=$('scenarioName').value.trim()||'Working scenario';scenario.model_verified=$('modelVerified').checked;
  scenario.increment=Number($('increment').value);scenario.monthly_growth=Number($('monthlyGrowth').value);
  scenario.horizon=Number($('horizon').value);scenario.commercial.currency=$('currency').value;
  scenario.commercial.flat_monthly=Number($('flatMonthly').value);scenario.commercial.expansion_fee=Number($('expansionFee').value);
  scenario.commercial.verified=$('pricesVerified').checked;scenario.commercial.discount=Number($('discount').value);
  $('rates').querySelectorAll('input').forEach(el=>{if(el.value==='')delete scenario.commercial[el.dataset.rate][el.dataset.region];else scenario.commercial[el.dataset.rate][el.dataset.region]=Number(el.value);});
  $('regionGrowth').querySelectorAll('input').forEach(el=>{if(el.value==='')delete scenario.region_growth[el.dataset.growthRegion];else scenario.region_growth[el.dataset.growthRegion]=Number(el.value);});
  $('poolInputs').querySelectorAll('input').forEach(el=>{const pool=result?.pools[Number(el.dataset.pool)];if(pool)scenario.pools[pool.region]=el.value===''?null:Number(el.value);});
  try{scenario.commercial.catalog=$('skuCatalog').value.trim()?JSON.parse($('skuCatalog').value):{};}catch(e){throw new Error('SKU catalog must be valid JSON.');}
}
function renderAssumptionFields(){
  if($('regionGrowth').dataset.keys!=='all'){
    $('regionGrowth').dataset.keys='all';
    $('regionGrowth').innerHTML=regions.slice(0,5).map(r=>`<label>${esc(r)} growth %<input type="number" data-growth-region="${esc(r)}" min="-90" max="1000" placeholder="Inherit global" value="${scenario.region_growth[r]??''}"></label>`).join('');
    $('regionGrowth').querySelectorAll('input').forEach(el=>el.oninput=()=>{if(el.value==='')delete scenario.region_growth[el.dataset.growthRegion];else scenario.region_growth[el.dataset.growthRegion]=Number(el.value);schedule();});
    $('rates').innerHTML=regions.slice(0,5).map(r=>`<label>${esc(r)} monthly rate / Mbps<input type="number" min="0" step="0.01" data-rate="rates" data-region="${esc(r)}" placeholder="No price supplied" value="${scenario.commercial.rates[r]??''}"></label><label>${esc(r)} monthly excess rate / Mbps<input type="number" min="0" step="0.01" data-rate="overage_rates" data-region="${esc(r)}" placeholder="No price supplied" value="${scenario.commercial.overage_rates[r]??''}"></label>`).join('');
    $('rates').querySelectorAll('input').forEach(el=>el.oninput=()=>{if(el.value==='')delete scenario.commercial[el.dataset.rate][el.dataset.region];else scenario.commercial[el.dataset.rate][el.dataset.region]=Number(el.value);schedule();});
  }
  const key=result.month+'|'+result.pools.map(p=>p.region).join('|');
  if($('cmaInputs').dataset.keys!==key){
    $('cmaInputs').dataset.keys=key;
    $('cmaInputs').innerHTML=result.pools.filter(p=>p.region!=='Unassigned').map(p=>`<label>${esc(p.region)} CMA · Mbps<input type="number" min="0" data-cma="${esc(p.region)}" value="${scenario.cma[result.month]?.[p.region]??''}" placeholder="No report supplied"></label>`).join('');
    $('cmaInputs').querySelectorAll('input').forEach(el=>el.oninput=()=>{scenario.cma[result.month]||={};if(el.value==='')delete scenario.cma[result.month][el.dataset.cma];else scenario.cma[result.month][el.dataset.cma]=Number(el.value);schedule();});
  }
  $('reconciliation').innerHTML=result.pools.filter(p=>p.cma!=null).map(p=>`<p class="quality">${esc(p.region)}: CMA ${fmt(p.cma)} Mbps · ${p.reconciliation_delta==null?'comparison unavailable (requires complete bursting data and zero growth)':'modeled delta '+fmt(p.reconciliation_delta)+' Mbps'}</p>`).join('');
}
function renderHistory(){
  if(!assessment)return;
  const h=assessment;
  $('history').innerHTML=`<p class="${h.ready?'ready':'empty'}">${h.ready?'Complete observations and confirmed assumptions across the selected window.':'Final window sizing withheld until every selected month passes its evidence checks.'}</p><div class="tablewrap"><table><thead><tr><th>Region</th><th>Capacity + headroom</th><th>Determining month</th><th>Months above capacity</th></tr></thead><tbody>${h.regions.map(r=>`<tr><td>${esc(r.region)}</td><td>${r.recommendation==null?'Withheld':fmt(r.recommendation)+' Mbps'}</td><td>${esc(r.determining_month||'Unavailable')}</td><td>${r.months_above} / ${r.tested_months} verified comparisons</td></tr>`).join('')}</tbody></table></div>`;
  const c=h.commercial;
  const money=v=>v==null?'Unavailable':esc(c.currency)+' '+fmt(v);
  const forecastOpen=$('forecast').querySelector('details')?.open;
  $('forecast').innerHTML=`<details ${forecastOpen?'open':''}><summary>Projection and commercial comparison · ${h.forecast.length} months</summary><p class="assumption">${esc(h.assumptions[0])} Forecasts are deterministic assumptions, not a probability of avoiding overusage.</p>${c.available?`<div class="poolgrid"><div class="poolcard"><h3>Adjust capacity monthly</h3><p class="big">${money(c.total)}</p></div><div class="poolcard"><h3>One term-sized expansion</h3><p class="big">${money(c.true_forward_total)}</p></div><div class="poolcard"><h3>Current capacity + excess</h3><p class="big">${money(c.true_up_total)}</p></div></div><p class="muted">${esc(c.note)} ${c.true_up_total==null?esc(c.true_up_reason):''}</p><p class="quality">Selected term SKUs: ${c.selected_skus.map(i=>`${esc(i.site||i.region)}: ${esc(i.sku)} (${fmt(i.capacity)} Mbps)`).join('; ')}</p>`:`<p class="muted">${esc(c.reason)}</p>`}<div class="tablewrap"><table><thead><tr><th>Forecast month</th><th>Regional planning capacity</th><th>Added sites</th></tr></thead><tbody>${h.forecast.map(f=>`<tr><td>${f.month}</td><td>${f.regions.map(p=>`${esc(p.region)}: ${p.recommendation==null?'Withheld':fmt(p.recommendation)+' Mbps'}`).join('<br>')}</td><td>${f.regions.flatMap(p=>p.additions).map(esc).join(', ')||'None'}</td></tr>`).join('')}</tbody></table></div></details>`;
}
function renderPlans(){
  $('plannedSites').innerHTML=scenario.planned_sites.map((s,i)=>`<p class="compact">${esc(s.name)} · ${esc(s.region)} · from ${s.start} · peak ${fmt(s.peak)} / daily P95 ${fmt(s.p95)} Mbps <button data-remove-plan="${i}">Remove assumption</button></p>`).join('');
  $('plannedSites').querySelectorAll('button').forEach(el=>el.onclick=()=>{scenario.planned_sites.splice(Number(el.dataset.removePlan),1);renderPlans();schedule();});
}
async function openEvidence(region){
  const pool=result.pools.find(p=>p.region===region);
  text('evidenceTitle',region+' · '+result.month+' evidence');
  $('evidenceContent').innerHTML=`<p>${pool.determining_day?'Determining complete day: '+esc(pool.determining_day):'No complete regional day is available.'}</p><p class="muted">${pool.excluded_days} observed partial days were excluded. Missing site days are never filled with zero.</p><div class="chart">${svgChart(pool.daily.map(d=>d.mbps))}</div><h3>Site daily P95 contributions</h3>${pool.contributors.map(s=>`<p>${esc(s.name)} · ${fmt(s.mbps)} Mbps <button data-buckets="${esc(s.id)}">Inspect discarded buckets</button></p>`).join('')}<div id="bucketDetails"></div>`;
  $('evidence').showModal();
  $('evidenceContent').querySelectorAll('[data-buckets]').forEach(el=>el.onclick=async()=>{try{
    const day=await api('day',{month:result.month,site:el.dataset.buckets,day:pool.determining_day,scenario});
    $('bucketDetails').innerHTML=`<h3>${esc(day.site)} · ${day.day}</h3><p>${day.buckets.length} buckets · ${day.excluded} excluded · daily P95 ${fmt(day.p95)} Mbps</p>${svgChart(day.buckets.map(b=>b.mbps),day.p95,true)}<p class="muted">The last ${day.excluded} sorted buckets are excluded. Complete days require all 288 samples.</p><div class="tablewrap"><table><thead><tr><th>Highest buckets (UTC)</th><th>Mbps</th><th>Decision</th></tr></thead><tbody>${day.buckets.slice(-20).reverse().map(b=>`<tr><td>${new Date(b.ts*1000).toISOString()}</td><td>${fmt(b.mbps)}</td><td>${b.excluded?'Excluded burst':'Retained'}</td></tr>`).join('')}</tbody></table></div>`;
  }catch(e){error(e);}});
}
function download(blob,name){const url=URL.createObjectURL(blob);const link=document.createElement('a');link.href=url;link.download=name;link.click();setTimeout(()=>URL.revokeObjectURL(url),10000);}
$('evidenceClose').onclick=()=>$('evidence').close();
for(const id of ['scenarioName','modelVerified','increment','monthlyGrowth','horizon','currency','flatMonthly','expansionFee','pricesVerified','discount','skuCatalog'])$(id).onchange=schedule;
$('saveNamed').onclick=async()=>{try{readAssessmentControls();await api('scenarios/save',{scenario});state=await api('state');$('savedScenario').innerHTML='<option value="">Working scenario</option>'+Object.entries(state.scenarios).map(([id,s])=>`<option value="${esc(id)}">${esc(s.name)}</option>`).join('');renderCompareChoices();text('status','Named option saved locally. Select up to four options for comparison.');}catch(e){error(e);}};
$('savedScenario').onchange=async()=>{const id=$('savedScenario').value;$('updateNamed').disabled=!id;if(!id)return;scenario=structuredClone(state.scenarios[id]);result=null;$('sites').innerHTML='';populateAssessmentControls();for(const key of ['model','growth','headroom'])$(key).value=scenario[key];$('savedScenario').value=id;await recalc().catch(error);};
$('compare').onclick=async()=>{try{const ids=Array.from($('comparisonChoices').querySelectorAll('input:checked'),el=>el.value);if(!ids.length||ids.length>4)throw new Error('Select between one and four named options for comparison.');const data=await api('compare',{ids,months:selectedMonths()});$('comparison').innerHTML='<h3>Saved option comparison</h3><div class="poolgrid">'+data.results.map(item=>{const a=item.assessment;return `<article class="comparison-card"><h3>${esc(a.name)}</h3><p class="${a.ready?'ready':'empty'}">${a.ready?'Evidence checks passed':'Needs review'}</p>${a.regions.map(r=>`<p>${esc(r.region)}: ${r.recommendation==null?'Withheld':fmt(r.recommendation)+' Mbps'}</p>`).join('')}<p class="muted">Term-sized expansion: ${a.commercial.available?esc(a.commercial.currency)+' '+fmt(a.commercial.true_forward_total):'Pricing not configured'}</p></article>`;}).join('')+'</div>';}catch(e){error(e);}};
$('addPlan').onclick=()=>{const s={name:$('planName').value.trim(),region:$('planRegion').value,start:$('planStart').value,peak:Number($('planPeak').value),p95:Number($('planP95').value)};if(!s.name||!s.start||!$('planPeak').value||!$('planP95').value||s.peak<0||s.p95<0||s.p95>s.peak)return error(new Error('Supply a site name, start month, peak and daily P95. P95 cannot exceed peak.'));scenario.planned_sites.push(s);renderPlans();schedule();};
$('assessmentExport').onclick=async()=>{try{readAssessmentControls();await api('scenario',{scenario});const data=await api('assessment');download(new Blob([JSON.stringify(data)],{type:'application/json'}),'p95-assessment.json');text('status','Assessment exported with observations and scenarios. Credentials are excluded.');}catch(e){error(e);}};
$('assessmentImport').onclick=()=>$('assessmentFile').click();
$('assessmentFile').onchange=async()=>{const file=$('assessmentFile').files[0];if(!file)return;try{if(file.size>60_000_000)throw new Error('Assessment file must be below 60 MB.');const data=JSON.parse(await file.text());await api('assessment/import',data);await refresh();text('status','Assessment restored into a new isolated workspace. Verify its source and assumptions before using it.');}catch(e){error(e);}finally{$('assessmentFile').value='';}};
$('report').onclick=async()=>{try{readAssessmentControls();const r=await fetch('/api/report',{method:'POST',headers:{'Content-Type':'application/json','X-P95-CSRF':state.csrf},body:JSON.stringify({scenario,months:selectedMonths()})});if(!r.ok)throw new Error((await r.json()).error);download(await r.blob(),'p95-licensing-assessment.pdf');text('status','Executive PDF and technical appendix generated locally.');}catch(e){error(e);}};

function renderCompareChoices(){
  $('comparisonChoices').innerHTML=Object.entries(state.scenarios||{}).map(([id,s],i)=>`<label><input type="checkbox" value="${esc(id)}" ${i<2?'checked':''}> ${esc(s.name)}</label>`).join('');
}
$('updateNamed').onclick=async()=>{try{const id=$('savedScenario').value;if(!id)return;readAssessmentControls();await api('scenarios/save',{id,scenario});state=await api('state');renderCompareChoices();text('status','Selected named option updated.');}catch(e){error(e);}};
