const form=document.getElementById('predict-form');
const results=document.getElementById('results');
const errorBox=document.getElementById('error');
const btn=document.getElementById('submit-btn');

form.addEventListener('submit',async e=>{
  e.preventDefault(); errorBox.textContent=''; btn.disabled=true; btn.textContent='جاري التحليل...';
  const fd=new FormData(form), data=Object.fromEntries(fd.entries());
  for(const k of ['home_scored','home_conceded','away_scored','away_conceded']) data[k]=Number(data[k]);
  try{
    const r=await fetch('/api/predict',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)});
    const body=await r.json(); if(!r.ok) throw new Error(body.error||'تعذر التحليل');
    results.classList.remove('hidden');
    results.innerHTML=`<div class="result-head">تم تحليل <strong>${esc(body.home)}</strong> ضد <strong>${esc(body.away)}</strong> بواسطة 8 محركات مستقلة</div>`+
      body.bots.map(b=>`<article class="bot-result"><div class="bot-result-top"><h3>${esc(b.name)}</h3><span class="pick">توقع ${b.pick}</span></div><div class="scoreline">النتيجة الأقرب: <b>${b.score}</b> · xG: ${b.home_xg} - ${b.away_xg}</div><div class="metrics"><div class="metric"><b>${b.p_home}%</b><small>فوز المستضيف</small></div><div class="metric"><b>${b.p_draw}%</b><small>تعادل</small></div><div class="metric"><b>${b.p_away}%</b><small>فوز الضيف</small></div></div><div class="scoreline">Over 2.5: ${b.over25}% · BTTS: ${b.btts}% · نتائج محتملة: ${b.top_scores.join(' / ')}</div></article>`).join('');
    results.scrollIntoView({behavior:'smooth',block:'start'}); loadHistory();
  }catch(err){errorBox.textContent=err.message}
  finally{btn.disabled=false;btn.textContent='⚡ حلّل المباراة بواسطة 8 بوتات'}
});
function esc(v){return String(v).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]))}
async function loadHistory(){
 const box=document.getElementById('history-list');
 try{
  const rows=await (await fetch('/api/history')).json();
  if(!rows.length){box.innerHTML='<div class="empty">لا توجد توقعات بعد. حلّل أول مباراة للبدء.</div>';return}
  box.innerHTML=rows.map(r=>`<div class="history-item"><div><b>${esc(r.home)} - ${esc(r.away)}</b><small>${esc(r.bot_name)} · ${r.pick} · ${r.score}</small></div><div><span class="status ${r.status}">${r.status==='PENDING'?'قيد الانتظار':r.status==='WON'?'رابح':'خاسر'}</span>${r.status==='PENDING'?`<div style="margin-top:6px;direction:ltr"><input class="result-input" id="h${r.id}" type="number" min="0" max="30" placeholder="0"> : <input class="result-input" id="a${r.id}" type="number" min="0" max="30" placeholder="0"> <button class="save-result" onclick="saveResult(${r.id})">حفظ</button></div>`:''}</div></div>`).join('');
 }catch(e){box.innerHTML='<div class="empty">تعذر تحميل السجل.</div>'}
}
async function saveResult(id){
 const h=document.getElementById('h'+id).value,a=document.getElementById('a'+id).value;
 if(h===''||a===''){alert('أدخل النتيجة النهائية');return}
 const r=await fetch('/api/result/'+id,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({home:h,away:a})});
 const d=await r.json(); if(!r.ok){alert(d.error);return} loadHistory();
}
document.getElementById('refresh').addEventListener('click',loadHistory);
loadHistory();


// Automatic fixtures from API-Football (API key remains on the server).
const fixtureDate=document.getElementById('fixtures-date');
const fixtureList=document.getElementById('fixtures-list');
const providerState=document.getElementById('provider-state');
if(fixtureDate){
  const localToday=new Date();
  fixtureDate.value=[localToday.getFullYear(),String(localToday.getMonth()+1).padStart(2,'0'),String(localToday.getDate()).padStart(2,'0')].join('-');
  checkProvider();
  loadFixtures();
  document.getElementById('fixtures-refresh').addEventListener('click',loadFixtures);
  fixtureDate.addEventListener('change',loadFixtures);
}
async function checkProvider(){
  try{
    const state=await (await fetch('/api/provider-status')).json();
    providerState.textContent=state.message;
    providerState.classList.toggle('needs-key',!state.configured);
  }catch(e){providerState.textContent='تعذر التحقق من مصدر البيانات.'}
}
async function loadFixtures(){
  fixtureList.innerHTML='<div class="empty">جاري جلب المباريات...</div>';
  try{
    const response=await fetch('/api/fixtures?date='+encodeURIComponent(fixtureDate.value));
    const rows=await response.json();
    if(!response.ok) throw new Error(rows.error||'تعذر جلب المباريات');
    if(!rows.length){fixtureList.innerHTML='<div class="empty">ما كايناش مباريات مسجلة فهاد التاريخ.</div>';return}
    fixtureList.innerHTML=rows.map(f=>{
      const played=f.home_goals!==null&&f.away_goals!==null;
      const status=f.status_long||f.status||'مجدولة';
      return `<article class="fixture-card">
        <div class="fixture-meta"><span>${esc(f.league||'دوري غير محدد')} · ${esc(f.country||'')}</span><span class="fixture-status">${esc(status)}${f.elapsed?` · ${f.elapsed}'`:''}</span></div>
        <div class="fixture-teams">
          <div class="fixture-team">${f.home_logo?`<img src="${esc(f.home_logo)}" alt="">`:''}<span>${esc(f.home)}</span></div>
          <div class="fixture-vs">VS</div>
          <div class="fixture-team">${f.away_logo?`<img src="${esc(f.away_logo)}" alt="">`:''}<span>${esc(f.away)}</span></div>
        </div>
        <div class="fixture-bottom"><span class="fixture-score">${played?`${f.home_goals} - ${f.away_goals}`:new Date(f.date).toLocaleTimeString([], {hour:'2-digit',minute:'2-digit'})}</span>
        <button class="analyze-fixture" onclick="analyzeFixture(${Number(f.id)},this)">حلّل بالذكاء الاصطناعي</button></div>
      </article>`;
    }).join('');
  }catch(err){
    fixtureList.innerHTML=`<div class="empty">${esc(err.message)}</div>`;
    if(err.message.includes('APISPORTS_KEY')) providerState.textContent='خاص إضافة مفتاح API لتفعيل المباريات التلقائية.';
  }
}
async function analyzeFixture(id,button){
  button.disabled=true;button.textContent='جاري جلب الإحصائيات...';
  try{
    const response=await fetch(`/api/fixture/${id}/analyze`,{method:'POST'});
    const body=await response.json();
    if(!response.ok) throw new Error(body.error||'تعذر تحليل المباراة');
    renderAnalysis(body);
    results.classList.remove('hidden');
    results.scrollIntoView({behavior:'smooth',block:'start'});
    loadHistory();
  }catch(err){alert(err.message)}
  finally{button.disabled=false;button.textContent='حلّل بالذكاء الاصطناعي'}
}
function renderAnalysis(body){
  results.innerHTML=`<div class="result-head">تحليل تلقائي: <strong>${esc(body.home)}</strong> ضد <strong>${esc(body.away)}</strong><br><small>مصدر الإحصائيات: ${esc(body.source)} · متوسطات الموسم</small></div>`+
  body.bots.map(b=>`<article class="bot-result"><div class="bot-result-top"><h3>${esc(b.name)}</h3><span class="pick">توقع ${b.pick}</span></div><div class="scoreline">النتيجة الأقرب: <b>${b.score}</b> · xG: ${b.home_xg} - ${b.away_xg}</div><div class="metrics"><div class="metric"><b>${b.p_home}%</b><small>فوز المستضيف</small></div><div class="metric"><b>${b.p_draw}%</b><small>تعادل</small></div><div class="metric"><b>${b.p_away}%</b><small>فوز الضيف</small></div></div><div class="scoreline">Over 2.5: ${b.over25}% · BTTS: ${b.btts}% · نتائج محتملة: ${b.top_scores.join(' / ')}</div></article>`).join('');
}
