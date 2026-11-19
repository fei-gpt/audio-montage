let sortingSource = '';
function sortingHome(){
  const p=P();
  if(p)wid=defaultWorkspace(p,wid,accountPreferences);
  const w=W(), originals=(w?.assets||[]).filter(a=>a.kind==='raw');
  const source=originals.find(a=>a.id===sortingSource)||originals[0];
  const job=w?.sorting?.find(j=>j.asset_id===source?.id&&j.sha256===source?.sha256);
  const rows=job?.segments||[];
  $('#crumb').textContent='素材整理'+(p?' / '+p.name:'')+(w?' / '+w.name:'');
  $('#main').innerHTML=`<div class="heading"><h1>素材整理</h1></div>
    <section class="panel form-panel"><label class="field">产品<select id="sortProduct"><option value="">选择产品</option>${state.products.map(item=>`<option value="${esc(item.id)}" ${item.id===pid?'selected':''}>${esc(item.name)}</option>`).join('')}</select></label>${p?accountSelector():''}
    <p class="small muted"><strong>使用说明</strong>　接入原片文件夹，选择一条原片开始识别。Hypit 提取画面，视觉模型按动作建议片段和产品标签。不足 1 秒的片段自动跳过。连续动作超过 4 秒时会随机切分，每段约 1.5 至 4 秒，每段单独审核。逐段试看，可修改起止时间和标签，也可手动补段。确认后生成独立 MP4，加入当前账号的剪辑素材库。</p></section>
    ${w?.assigned?`<section class="panel form-panel"><div class="section-heading"><h2>选择原片</h2><button id="sortAttach">接入原片文件夹</button></div>
    ${originals.length?`<label class="field">未剪原片<select id="sortSource">${originals.map(a=>`<option value="${esc(a.id)}" ${a.id===source.id?'selected':''}>${esc(a.name)} · ${a.duration.toFixed(2)} 秒</option>`).join('')}</select></label>`:'<p>当前账号还没有原片。接入后即可选择。</p>'}
    ${source&&(!job||job.status==='failed'&&!rows.length)?`<button id="sortStart" class="primary">${job?'重新识别':'识别有效片段'}</button>`:''}</section>`:''}
    ${job?`<section class="panel form-panel"><div class="section-heading"><h2>片段审核</h2>${job.status!=='running'?'<button id="sortManual">手动补段</button>':''}</div>
    ${job.status==='running'?'<p role="status">正在提取画面并识别动作…</p>':job.status==='failed'?`<p class="error">未识别 · ${esc(job.error)}</p>`:!rows.length?'<p>没有识别到可用片段，可查看原片并手动补段。</p>':''}
    ${rows.map(r=>`<div class="reference"><div class="section-heading"><strong>${r.start.toFixed(2)} – ${r.end.toFixed(2)} 秒</strong>${r.status==='pending'?`<button data-sort-review="${esc(r.id)}">试看与审核</button>`:badge(r.status==='fault'?'故障 · 四把旋转时熄灯':r.status==='confirmed'?'已入库':'已跳过')}</div><div>${esc(r.labels.join('、')||'未识别类别，请人工核对')}</div><div class="small muted">${esc(r.reason)}</div></div>`).join('')}</section>`:''}`;
  $('#sortProduct').onchange=e=>{pid=e.target.value;wid=null;render()};
  if(p)bindAccounts();
  if($('#sortSource'))$('#sortSource').onchange=e=>{sortingSource=e.target.value;render()};
  if($('#sortAttach'))$('#sortAttach').onclick=()=>{attachDialog();const field=$('#attachForm select[name="kind"]');field.value='raw';field.querySelector('[value="prepared"]').remove()};
  if($('#sortStart'))$('#sortStart').onclick=()=>confirmRun(b=>api(wb()+'/sorting','POST',{asset_id:source.id,allow_paid:b.allow_paid,retry:!!job}));
  const open=row=>sortingReview(source,job,row,p.shot_categories||[]);
  if($('#sortManual'))$('#sortManual').onclick=()=>open(null);
  document.querySelectorAll('[data-sort-review]').forEach(btn=>btn.onclick=()=>open(rows.find(r=>r.id===btn.dataset.sortReview)));
}

function sortingReview(source,job,row,categories){
  const url=wb()+'/sorting/'+job.id+'/review';
  dialog(row?'审核片段':'手动补段',`<video class="preview-video" controls playsinline src="${esc(source.media_url)}"></video>
    <form id="sortReview"><div class="inline"><label>开始（秒）<input name="start" type="number" min="0" step="any" required value="${row?.start??0}"></label>
    <label>结束（秒）<input name="end" type="number" max="${source.duration}" step="any" required value="${row?.end??source.duration}"></label><button type="button" id="sortPlay">试看选区</button></div>
    ${categories.length?`<fieldset><legend>展示类别（可多选）</legend>${categories.map(label=>`<label class="check-label"><input type="checkbox" name="tag" value="${esc(label)}" ${row?.labels.includes(label)?'checked':''}>${esc(label)}</label>`).join('')}</fieldset>`:`<label class="field">展示标签（用顿号分隔）<input name="customTags" value="${esc(row?.labels.join('、')||'')}"></label>`}
    <div class="inline"><button class="primary">确认并入库</button>${row?'<button type="button" id="sortSkip">跳过片段</button>':''}</div></form>`);
  const form=$('#sortReview'),video=$('#dialog video'),start=form.elements.start,end=form.elements.end;
  video.onloadedmetadata=()=>{video.currentTime=Number(start.value)};
  video.ontimeupdate=()=>{if(!video.paused&&video.currentTime>=Number(end.value))video.pause()};
  $('#sortPlay').onclick=()=>{video.currentTime=Number(start.value);video.play().catch(e=>toast(e.message))};
  const needsSplit=()=>end.valueAsNumber>start.valueAsNumber+4;
  function updateButton(){form.querySelector('button.primary').textContent=needsSplit()?'拆分后逐段审核':'确认并入库'}
  start.oninput=end.oninput=updateButton;updateButton();
  function save(decision){action(async()=>{
    const result=await api(url,'POST',{decision,segment_id:row?.id,start:start.valueAsNumber,end:end.valueAsNumber,labels:categories.length?new FormData(form).getAll('tag'):form.elements.customTags.value.split(/[、,，]/).map(x=>x.trim()).filter(Boolean)});
    $('#dialog').close();toast(result.skipped_short?'片段不足 1 秒，已跳过':decision==='skip'?'片段已跳过':needsSplit()?'已拆分，请逐段审核':'已加入当前账号剪辑素材库');
  })}
  form.onsubmit=e=>{e.preventDefault();save('confirm')};
  if($('#sortSkip'))$('#sortSkip').onclick=()=>save('skip');
}
