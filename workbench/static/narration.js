let narrationWorkspace, selectedNarrations = new Set();

function recentNarrations(workspace,now=new Date()) {
  const dayKey=date=>[date.getFullYear(),date.getMonth()+1,date.getDate()]
    .map(part=>String(part).padStart(2,'0')).join('-');
  const yesterday=new Date(now.getFullYear(),now.getMonth(),now.getDate()-1);
  const days=new Set([dayKey(now),dayKey(yesterday)]);
  return (workspace?.narrations||[]).filter(item=>days.has((item.created_at||'').slice(0,10)));
}

function readyNarrations(workspace) {
  return recentNarrations(workspace).filter(item=>item.status==='completed');
}

function narrationDate(item) {
  return (item.created_at || '').slice(0,16).replace('T',' ');
}

function narrationSearchText(item) {
  return [narrationDate(item),item.name,item.script,item.voice_name].join(' ');
}

function bindNarrationSearch(input,rows,empty) {
  const filter=()=>{
    const terms=input.value.trim().toLowerCase().split(/\s+/).filter(Boolean);
    let matches=0;
    for(const row of rows){
      row.hidden=!terms.every(term=>row.dataset.narrationSearch.toLowerCase().includes(term));
      if(!row.hidden)matches++;
    }
    empty.hidden=matches>0;
  };
  input.oninput=filter;
  filter();
}

function narrationHome() {
  const product=P();
  if(product)wid=defaultWorkspace(product,wid,accountPreferences);
  const workspace=W();
  const previousSearch=$('#narrationHistorySearch');
  const previousForm=$('#narrationForm');
  const keepDraft=previousForm?.dataset?.workspace===workspace?.id&&Boolean(workspace);
  $('#crumb').textContent='ElevenLabs 配音'+(product?' / '+product.name:'')+(workspace?' / '+workspace.name:'');
  $('#main').innerHTML=`<div class="heading"><h1>ElevenLabs 配音</h1></div>
    <section class="panel form-panel"><label class="field"><span>产品</span>
      <select id="narrationProduct"><option value="">选择产品</option>${state.products.map(item=>
        `<option value="${esc(item.id)}" ${item.id===pid?'selected':''}>${esc(item.name)}</option>`).join('')}</select>
    </label>${product?accountSelector():''}</section>
    ${workspace?narrationFormHTML(workspace)+narrationSection(workspace):''}`;
  $('#narrationProduct').onchange=event=>{pid=event.target.value||null;wid=null;render();};
  if(product)bindAccounts();
  if(workspace){
    if(keepDraft)$('#narrationForm').replaceWith(previousForm);
    bindNarrationForm(workspace,keepDraft);
    bindNarrations(workspace,keepDraft?previousSearch?.value:undefined);
  }
}

function narrationSection(workspace) {
  if (narrationWorkspace !== workspace.id) {
    narrationWorkspace = workspace.id;
    selectedNarrations = new Set();
  }
  const items=recentNarrations(workspace).reverse();
  const available=new Set(items.filter(item=>item.status==='completed').map(item=>item.upload_id));
  for(const id of selectedNarrations)if(!available.has(id))selectedNarrations.delete(id);
  const labels = {queued:'等待生成', running:'生成中', completed:'已生成', failed:'失败'};
  return `<section class="panel recent">
    <h2>配音列表</h2><p class="small muted">显示今天和昨天生成的配音。</p>
    ${items.length ? `<label class="field"><span>搜索配音历史</span><input id="narrationHistorySearch" type="search" placeholder="按文案、音色或日期搜索"></label>
      <p id="narrationHistoryEmpty" class="small muted" hidden>没有匹配的配音。</p>
      <div class="asset-table-wrap" style="max-height:360px"><table class="asset-table">
      <thead><tr><th>选择</th><th>配音名称</th><th>文案</th><th>生成时间</th><th>音色</th><th>状态</th><th>时长</th><th>试听</th></tr></thead>
      <tbody>${items.map(item => `<tr data-narration-search="${esc(narrationSearchText(item))}">
        <td>${item.upload_id ? `<input type="checkbox" aria-label="选择 ${esc(item.name)}" data-narration-select="${esc(item.upload_id)}" ${selectedNarrations.has(item.upload_id) ? 'checked' : ''}>` : '—'}</td>
        <td class="file-path">${esc(item.name||'—')}</td>
        <td><details><summary>${esc(item.script.slice(0,60))}${item.script.length>60?'…':''}</summary><p class="result-note">${esc(item.script)}</p></details></td>
        <td>${esc(narrationDate(item)||'—')}</td><td>${esc(item.voice_name)}</td><td>${badge(labels[item.status])}${item.used?' '+badge('已使用'):''}${item.error ? `<div class="small error">${esc(item.error)}</div>` : ''}</td>
        <td>${item.duration ? item.duration.toFixed(2)+' 秒' : '—'}</td>
        <td>${item.media_url ? `<button data-narration-play="${esc(item.upload_id)}">试听</button>` : '—'}</td>
      </tr>`).join('')}</tbody></table></div>
      <button id="useNarrations" ${selectedNarrations.size ? '' : 'disabled'}>用于剪辑</button>` : '<p class="small muted">今天和昨天暂无配音记录。</p>'}
  </section>`;
}

function bindNarrations(workspace,search='') {
  const searchInput=$('#narrationHistorySearch');
  if(searchInput){
    searchInput.value=search;
    bindNarrationSearch(searchInput,document.querySelectorAll('tr[data-narration-search]'),$('#narrationHistoryEmpty'));
  }
  const settings=$('#narrationSettings'), use=$('#useNarrations');
  if(settings)settings.onclick=()=>generationSettings({voiceOnly:true});
  if(use)use.onclick=()=>{
    const ids=[...selectedNarrations];
    location.hash='editing';
    render();
    editBatchDialog(false,ids);
  };
  document.querySelectorAll('[data-narration-select]').forEach(input=>input.onchange=()=>{
    if(input.checked)selectedNarrations.add(input.dataset.narrationSelect);
    else selectedNarrations.delete(input.dataset.narrationSelect);
    use.disabled=!selectedNarrations.size;
  });
  document.querySelectorAll('[data-narration-play]').forEach(button=>button.onclick=()=>{
    const item=readyNarrations(workspace).find(row=>row.upload_id===button.dataset.narrationPlay);
    if(item?.media_url)dialog(item.name,`<audio controls preload="metadata" src="${esc(item.media_url)}"></audio>`);
  });
}

function narrationFormHTML(workspace) {
  return `<section class="panel recent">
    <div class="section-heading"><h2>生成配音</h2><button id="narrationSettings">ElevenLabs 设置</button></div>
    <form id="narrationForm" data-workspace="${esc(workspace.id)}">
      <div id="narrationScripts" style="max-height:40vh;overflow-y:auto">
        ${narrationScriptHTML()}
      </div>
      <button type="button" id="addNarrationScript">添加新文案</button>
      <label class="field"><span>本批音色</span><small>本次添加的所有文案都会使用同一个音色。</small><select id="narrationVoice" required><option value="">请选择音色</option></select></label>
      <p id="narrationVoiceStatus" class="small" role="status"></p>
      <p id="narrationConsent" class="small muted"></p>
      <button class="primary" id="submitNarration" disabled>生成配音</button>
    </form>
  </section>`;
}

function narrationScriptHTML(number=1) {
  return `<div>
    <div class="inline">
      <label class="small" for="narrationScript${number}" data-narration-script-label>配音文案${number}</label>
      <button type="button" data-remove-narration-script hidden>删除</button>
    </div>
    <div class="field" style="margin-top:4px">
      <textarea id="narrationScript${number}" name="scripts" rows="2" style="min-height:0" maxlength="5000" required></textarea>
    </div>
  </div>`;
}

function bindNarrationForm(workspace,keepDraft) {
  const form=$('#narrationForm'), list=$('#narrationScripts'), add=$('#addNarrationScript');
  const voice=$('#narrationVoice'), submit=$('#submitNarration'), voiceStatus=$('#narrationVoiceStatus');
  const consent=$('#narrationConsent'), endpoint=`${wb()}/narrations`;
  const config=state.generation_config || {};
  const busy=(workspace.narrations||[]).some(item=>['queued','running'].includes(item.status));
  function update() {
    const count=list.children.length;
    add.disabled=count>=20;
    Array.from(list.children).forEach((row,index)=>{
      const label=row.querySelector('[data-narration-script-label]');
      const textarea=row.querySelector('textarea');
      const button=row.querySelector('[data-remove-narration-script]');
      label.textContent=`配音文案${index+1}`;
      textarea.id=`narrationScript${index+1}`;
      label.htmlFor=textarea.id;
      button.setAttribute('aria-label',`删除配音文案${index+1}`);
      button.hidden=count===1;
      button.onclick=()=>{row.remove();update();};
    });
    consent.textContent=`将向 ElevenLabs 发送 ${count} 条文案并生成配音，可能计费。`;
    submit.textContent=busy?'正在生成配音…':`生成 ${count} 条配音`;
    submit.disabled=busy||!workspace.assigned||!config.elevenlabs_key_ready||!voice.value||form.dataset.submitting==='true';
  }
  add.onclick=()=>{
    list.insertAdjacentHTML('beforeend',narrationScriptHTML(list.children.length+1));
    update();
    list.lastElementChild.querySelector('textarea').focus();
  };
  voice.onchange=update;
  if(!config.elevenlabs_key_ready)voiceStatus.textContent='请先在 ElevenLabs 设置中保存密钥。';
  else if(!keepDraft||!form.dataset.voicesLoaded){
    form.dataset.voicesLoaded='loading';
    voiceStatus.textContent='正在读取音色…';
    api('/api/generation/voices').then(result=>{
      if(!form.isConnected)return;
      voice.innerHTML='<option value="">请选择音色</option>'+result.voices.map(item=>
        `<option value="${esc(item.id)}">${esc(item.name)}</option>`).join('');
      if(result.voices.some(item=>item.id===config.voice_id))voice.value=config.voice_id;
      voiceStatus.textContent=result.voices.length?'':'当前密钥没有可选音色。';
      form.dataset.voicesLoaded='ready';
      voice.onchange();
    }).catch(error=>{
      if(!form.isConnected)return;
      voiceStatus.textContent=error.message;
      delete form.dataset.voicesLoaded;
    });
  }
  update();
  form.onsubmit=event=>{
    event.preventDefault();
    if(submit.disabled)return;
    const scripts=new FormData(form).getAll('scripts').map(text=>text.trim());
    if(scripts.some(text=>!text))return toast('请填写每条配音文案');
    const body={scripts,voice_id:voice.value,voice_name:voice.selectedOptions[0].textContent,allow_paid:true};
    return action(async()=>{
      form.dataset.submitting='true';
      update();
      try{
        await api(endpoint,'POST',body);
        list.innerHTML=narrationScriptHTML();
      }finally{
        delete form.dataset.submitting;
        update();
      }
    });
  };
}
