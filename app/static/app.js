'use strict';
const $ = id => document.getElementById(id);
const regions = ['Group 1','Group 2','China','Vietnam','Morocco','Unassigned'];
let state, result, scenario = {model:'bursting-2027',growth:0,headroom:20,pools:{},sites:{}};
let requestVersion = 0, timer, poll;
const fmt = v => Number(v || 0).toLocaleString(undefined,{maximumFractionDigits:1});
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
  scenario = state.scenario || {model:'bursting-2027',growth:0,headroom:20,pools:{},sites:{}};
  scenario.pools ||= {}; scenario.sites ||= {};
  text('tenant',state.tenant === 'demo' ? 'Synthetic demo tenant' : 'Tenant '+state.tenant);
  $('month').innerHTML = state.months.map(m=>`<option>${esc(m)}</option>`).join('');
  if (month && state.months.includes(month)) $('month').value=month;
  for(const key of ['model','growth','headroom']) $(key).value=scenario[key] ?? (key === 'headroom' ? 20 : 0);
  if (state.env_configured) text('connectStatus','Docker credentials available. Leave ID and key blank to use them.');
  if (state.months.length) await recalc();
  else {
    $('metrics').innerHTML='<div class="metric"><p>No data yet</p><h2>Start with a demo or connect your tenant.</h2></div>';
    $('chart').innerHTML=''; $('sites').innerHTML=''; $('pools').innerHTML='';
  }
}
function schedule(){ clearTimeout(timer);timer=setTimeout(()=>recalc().catch(error),140); }
async function recalc(){
  if (!$('month').value) return;
  const version=++requestVersion;
  scenario.model=$('model').value;
  scenario.growth=Number($('growth').value); scenario.headroom=Number($('headroom').value);
  text('growthValue',scenario.growth+'%');text('headroomValue',scenario.headroom+'%');
  const data=await api('analyze',{month:$('month').value,scenario});
  if(version!==requestVersion)return;
  result=data; render();
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
  const above = ['site','enforced-pool'].includes(scenario.model) ? r.sites.filter(s=>s.excess>0).length : r.pools.filter(p=>p.excess>0).length;
  const cov=r.sites.length ? r.sites.reduce((a,s)=>a+s.coverage,0)/r.sites.length : 0;
  const metric=(name,value,caption)=>`<div class="metric"><p>${name}</p><div class="value">${value}</div><p>${caption}</p></div>`;
  $('metrics').innerHTML=metric('Planning capacity',fmt(r.total_recommended)+' <small>Mbps</small>','Across regions · includes headroom')+metric('Simultaneous aggregate peak',fmt(r.peak)+' <small>Mbps</small>','Context only · not regional billing')+metric('Above modeled capacity',above,['site','enforced-pool'].includes(scenario.model)?'Sites above allocation':'Regions needing review')+metric('Month coverage',fmt(cov)+'%','Known five-minute buckets / expected');
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
    $('poolInputs').innerHTML=r.pools.map((p,i)=>`<label>${esc(p.region)} pool · Mbps<input type="number" min="0" max="1000000" value="${scenario.pools[p.region]??500}" data-pool="${i}"></label>`).join('');
    $('poolInputs').querySelectorAll('input').forEach(el=>el.addEventListener('input',()=>{scenario.pools[result.pools[Number(el.dataset.pool)].region]=Number(el.value);schedule();}));
  }
  $('poolInputs').hidden=scenario.model==='site';
  $('pools').innerHTML=r.pools.map(p=>{
    const isSite=scenario.model==='site', capacity=isSite?p.allocation:p.capacity;
    const excess=Math.max(0,p.measured-capacity), usage=capacity ? Math.min(100,p.measured/capacity*100) : 100;
    return `<article class="poolcard"><h3>${esc(p.region)} ${!p.supported?'· unsupported pool':''}</h3><span class="big">${fmt(p.measured)} <small>Mbps</small></span><p class="muted">${scenario.model==='enforced-pool'?'Assigned site allocations':isSite?'Sum of observed site peaks':'Modeled measured usage'} / ${fmt(capacity)} Mbps capacity</p><div class="track"><div class="fill" style="width:${usage}%"></div></div><p class="${excess?'danger':'muted'}">${excess?fmt(excess)+' Mbps above capacity':fmt(capacity-p.measured)+' Mbps available'}</p><p>Plan for <strong>${fmt(p.recommendation)} Mbps</strong></p>${scenario.model==='bursting-2027'&&p.daily.length?`<p class="muted">Highest daily sum: ${esc(p.daily.reduce((a,b)=>a.mbps>b.mbps?a:b).day)}</p>`:''}<p class="muted">${p.contributors.sort((a,b)=>b.mbps-a.mbps).slice(0,3).map(c=>`${esc(c.name)}: ${fmt(c.mbps)} Mbps`).join('<br>')}</p></article>`;
  }).join('');
  const focused=document.activeElement?.dataset.site !== undefined;
  if(!focused){
    $('sites').innerHTML=r.sites.map((s,i)=>`<tr><td>${esc(s.name)}<div class="muted">ID ${esc(s.id)}</div></td><td><select aria-label="License region for ${esc(s.name)}" data-site="${i}" data-field="region">${regions.map(region=>`<option ${region===s.region?'selected':''}>${esc(region)}</option>`).join('')}</select></td><td><input aria-label="Allocation Mbps for ${esc(s.name)}" type="number" min="0" max="1000000" value="${s.capacity}" data-site="${i}" data-field="capacity"></td><td>${fmt(s.p95)} Mbps</td><td>${fmt(s.peak)} Mbps</td><td class="${s.excess>0?'danger':''}">${fmt(s.recommendation)} Mbps</td><td>${fmt(s.over_minutes)}</td><td>${fmt(s.coverage)}%<div class="muted">${s.complete_days} complete days</div></td></tr>`).join('');
    $('sites').querySelectorAll('[data-site]').forEach(el=>el.addEventListener('change',()=>{
      const s=result.sites[Number(el.dataset.site)];
      scenario.sites[s.id] ||= {region:s.region,capacity:s.capacity};
      scenario.sites[s.id][el.dataset.field]=el.dataset.field==='capacity'?Number(el.value):el.value;
      el.blur(); schedule();
    }));
  }
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
$('demo').onclick=async()=>{try{const month=$('month').value||previousMonth();text('status','Preparing synthetic observations…');await api('demo',{month});$('poolInputs').dataset.keys='';await refresh(month);text('status','Demo data loaded. All tenant usage is synthetic.');}catch(e){error(e);}};
$('save').onclick=async()=>{try{await api('scenario',{scenario});text('status','Scenario and verified site mapping saved locally.');}catch(e){error(e);}};
$('import').onclick=()=>$('file').click();
$('file').onchange=async()=>{const file=$('file').files[0];if(!file)return;try{if(file.size>10_000_000)throw new Error('CSV must be below 10 MB.');await api('import',{tenant:'imported',csv:await file.text()});$('poolInputs').dataset.keys='';await refresh();text('status','CSV imported into the local workspace.');}catch(e){error(e);}finally{$('file').value='';}};
$('discover').onclick=async()=>{const btn=$('discover');btn.disabled=true;try{text('connectStatus','Discovering sites…');const data=await api('discover',creds());$('discovered').innerHTML=data.sites.map(s=>`<label><input type="checkbox" value="${esc(s.id)}"> ${esc(s.name)} · ${esc(s.info?.countryCode||'Verify site')} · ${esc(s.info?.connType||'Unknown type')}</label>`).join('');text('connectStatus','Select physical or cloud sites. Leave remote users unchecked.');}catch(e){text('connectStatus',e.message);}finally{btn.disabled=false;}};
$('connectForm').onsubmit=async e=>{e.preventDefault();try{const ids=Array.from($('discovered').querySelectorAll('input:checked'),el=>el.value);await api('sync',{...creds(),site_ids:ids,month:$('collectMonth').value});$('key').value='';text('connectStatus','Collection started. You can close this window.');text('status','Collecting five-minute peaks…');pollJob();}catch(e){text('connectStatus',e.message);}};
function pollJob(){clearTimeout(poll);poll=setTimeout(async()=>{try{const s=await api('state');if(s.job.state==='running'){text('status',`Collecting Cato usage: ${s.job.completed} / ${s.job.total||'?'} batches. Buckets are saved as they arrive.`);pollJob();}else if(s.job.state==='done'){$('poolInputs').dataset.keys='';await refresh($('collectMonth').value);text('status','Collection complete. Verify every site license region and allocation before evaluating a scenario.');}else{text('status',s.job.error||'Collection stopped.');}}catch(e){error(e);}},2500);}
function previousMonth(){const d=new Date();d.setUTCDate(1);d.setUTCMonth(d.getUTCMonth()-1);return d.toISOString().slice(0,7);}
$('collectMonth').value=previousMonth();lesson();refresh().then(()=>{if(state.job.state==='running')pollJob();}).catch(error);
