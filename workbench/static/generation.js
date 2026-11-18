let generationPage=1;
const generationLabels={draft:'待生成',queued:'等待执行',running:'处理中',video_pending:'即梦生成中',awaiting_intro_review:'待确认AI开头',editing_ready:'已进入剪辑',interrupted:'已中断',needs_attention:'需要处理',awaiting_sample_approval:'待确认样片报价',sample_ready:'样片已生成'};
function generationHome(){
  const product=P();
  if(product)wid=defaultWorkspace(product,wid,accountPreferences);
  const workspace=W(), previousForm=$('#generationCreate');
  const keepDraft=workspace?.assigned&&previousForm?.dataset?.workspace===workspace.id;
  $('#crumb').textContent='AI 视频生成'+(product?' / '+product.name:'')+(workspace?' / '+workspace.name:'');
  $('#main').innerHTML=`<div class="heading"><h1>AI 视频生成</h1><button id="generationSettings">生成服务设置</button></div>
    <section class="panel form-panel"><label class="field"><span>产品</span>
      <select id="generationProduct"><option value="">选择产品</option>${state.products.map(item=>
        `<option value="${esc(item.id)}" ${item.id===pid?'selected':''}>${esc(item.name)}</option>`).join('')}</select>
    </label>${product?accountSelector():''}</section>
    ${workspace?.assigned?generationFormHTML(workspace):'<p class="muted">选择产品和已分配的账号后，即可填写样片文稿。</p>'}
    ${generationSection()}`;
  $('#generationProduct').onchange=event=>{pid=event.target.value||null;wid=null;generationPage=1;render();};
  if(product)bindAccounts();
  if(workspace?.assigned){
    if(keepDraft)$('#generationCreate').replaceWith(previousForm);
    bindGenerationForm();
  }
  bindGeneration();
}
function generationSection(){
  const items=[...(W()?.generations||[])].reverse().sort((a,b)=>(b.created_at||'').localeCompare(a.created_at||''));
  const data=editingRows(items,generationPage);generationPage=data.page;
  return `<section class="panel recent"><h2>生成任务</h2><p class="small muted">样片生成后在即梦画布查看。</p>${items.length?`<div class="asset-table-wrap"><table class="asset-table"><thead><tr><th>要求</th><th>状态</th><th>操作</th></tr></thead><tbody>${data.rows.map(g=>`<tr><td>${esc(g.brief.slice(0,80))}</td><td>${badge(generationLabels[g.status]||g.status)}<div class="small muted">${esc(g.stage)}</div></td><td><button data-generation-detail="${g.id}">查看 / 继续</button></td></tr>`).join('')}</tbody></table></div><div class="inline" style="justify-content:flex-end;margin-top:12px"><button id="generationPrev" ${data.page===1?'disabled':''}>上一页</button><span>${data.page} / ${data.pages}</span><button id="generationNext" ${data.page===data.pages?'disabled':''}>下一页</button></div>`:'<p class="muted">还没有 AI 生成任务。</p>'}</section>`;
}
function bindGeneration(){
  $('#generationSettings')?.addEventListener('click',()=>generationSettings());
  $('#generationPrev')?.addEventListener('click',()=>{generationPage--;render()});$('#generationNext')?.addEventListener('click',()=>{generationPage++;render()});
  document.querySelectorAll('[data-generation-detail]').forEach(b=>b.onclick=()=>generationDetail(b.dataset.generationDetail));
}
function generationFormHTML(workspace){
  const defaultDuration=Math.min(30,Math.max(4,state.generation_config?.duration||5));
  return `<section class="panel form-panel recent"><h2>Seedance 2.5 样片 · 全能参考</h2>
  <form id="generationCreate" data-workspace="${esc(workspace.id)}">
    <div class="inline">
      <label class="field"><span>时长</span><select name="duration">
        ${Array.from({length:27},(_,i)=>i+4).map(n=>`<option value="${n}" ${n===defaultDuration?'selected':''}>${n} 秒</option>`).join('')}
      </select></label>
      <label class="field"><span>画面比例</span><select name="ratio">
        ${['9:16','16:9','1:1','3:4','4:3','21:9'].map(ratio=>`<option>${ratio}</option>`).join('')}
      </select></label>
    </div>
    <label class="field"><span>文稿（必填）</span><textarea name="manuscript" rows="3" maxlength="14999" required></textarea></label>
    <div class="refbox">
      <label class="field"><span>参考图片</span><input type="file" id="generationReferenceImages" accept=".png,.jpg,.jpeg,.webp" multiple></label>
      <label class="field"><span>参考音频</span><input type="file" id="generationReferenceAudio" accept=".mp3,.wav,.m4a" multiple></label>
      <p class="small muted">至少选一种参考素材。图片最多 30 张，音频最多 10 段，每段至少 2 秒、合计最多 30 秒。全部文件合计最大 30 MB。</p>
    </div>
    <label class="check-label"><input name="rights_allowed" type="checkbox" required>已确认文稿和参考素材可用于本次制作</label>
    <button class="primary">保存生成任务</button>
  </form></section>`;
}
function bindGenerationForm(){
  const form=$('#generationCreate'), endpoint=`${wb()}/generation`;
  form.onsubmit=event=>{
    event.preventDefault();
    if(!state.editing_capabilities?.canvas_sample)return toast('重启工作台后即可使用新版样片表单。');
    const data=new FormData(form), manuscript=String(data.get('manuscript')||'').trim();
    if(!manuscript)return toast('请填写样片文稿');
    const refs=[...Array.from($('#generationReferenceImages').files,file=>({kind:'image',file})),
                ...Array.from($('#generationReferenceAudio').files,file=>({kind:'audio',file}))];
    if(!refs.length)return toast('请至少选择一张参考图片或一段参考音频');
    if(refs.reduce((bytes,ref)=>bytes+ref.file.size,0)>30000000)return toast('参考素材合计最大 30 MB');
    if(refs.some(ref=>ref.kind==='image'&&ref.file.size>10000000))return toast('每张参考图片最大 10 MB');
    const body={sample:true,video_mode:'multimodal',duration:Number(data.get('duration')),
      ratio:data.get('ratio'),manuscript,rights_allowed:data.has('rights_allowed'),references:[]};
    return action(async()=>{
      for(const {kind,file} of refs){
        const url=await new Promise((resolve,reject)=>{
          const reader=new FileReader();
          reader.onload=()=>resolve(reader.result);
          reader.onerror=()=>reject(new Error('读取参考素材失败：'+file.name));
          reader.readAsDataURL(file);
        });
        body.references.push({kind,name:file.name,base64:url.slice(url.indexOf(',')+1)});
      }
      await api(endpoint,'POST',body);
      form.reset();
      generationPage=1;
      toast('生成任务已保存，可在下方查看');
    });
  };
}
function generationDetail(id){
  const g=W().generations.find(x=>x.id===id);if(!g)return;
  dialog('AI视频生成',`<div style="max-height:72vh;overflow:auto"><p>${badge(generationLabels[g.status]||g.status)} ${esc(g.stage)}</p>${g.error?`<p class="error">${esc(g.error)}</p>`:''}<p>${esc(g.brief)}</p>
  ${g.references?.length?`<details><summary>全能参考 · ${g.references.length} 个素材</summary><ul>${g.references.map(ref=>`<li>${esc(ref.name)}</li>`).join('')}</ul></details>`:''}
  ${g.first_frame?`<p class="small">首帧图片 · ${esc(g.first_frame.name)}</p>`:''}
  ${g.manuscript?`<details><summary>原始文稿</summary><p class="result-note">${esc(g.manuscript)}</p></details>`:''}
  ${g.script?`<details><summary>两层文案</summary><h3>即梦开头口播</h3><p class="result-note">${esc(g.script.ai_copy)}</p><h3>即梦画面提示词</h3><p class="result-note">${esc(g.script.jimeng_prompt)}</p><h3>实拍续接配音稿</h3><p class="result-note">${esc(g.script.continuation_copy)}</p><h3>实拍画面要求</h3><p>${esc(g.script.visual_requirements)}</p></details>`:''}
  ${g.sample?`<p>Seedance 2.5 样片 · ${esc(g.settings.duration)} 秒 · ${esc(g.ratio)}</p>
    ${g.sample_canvas_url?`<a href="${esc(g.sample_canvas_url)}" target="_blank" rel="noopener noreferrer">打开即梦画布</a>`:''}
    ${g.status==='awaiting_sample_approval'?`<p>本次最多消耗 ${esc(g.sample_credits)} 积分。</p><button id="approveCanvasSample" class="primary">确认并生成样片</button>`:''}
    ${!g.submit_id&&['draft','interrupted','needs_attention'].includes(g.status)?'<button id="prepareCanvasSample" class="primary">创建画布并查看报价</button>':''}
    ${g.submit_id&&['video_pending','interrupted','needs_attention'].includes(g.status)?'<button id="pollCanvasSample">查询样片</button>':''}`:''}
  ${g.submit_id?`<p class="small">即梦任务：${esc(g.submit_id)}</p>`:''}
  ${g.intro?`<video class="preview-video" controls playsinline preload="metadata" src="${esc(g.intro.media_url)}"></video>`:''}
  ${g.status==='awaiting_intro_review'?`<label class="check-label"><input id="generationApproved" type="checkbox">已播放当前AI开头，确认画面、产品、口播和音画效果</label><label class="check-label"><input id="generationTtsPaid" type="checkbox">允许ElevenLabs生成续接配音及后续选片API调用，可能产生费用</label><button id="generationApprove" class="primary">确认开头，生成续接配音并合成</button>`:''}
  ${g.editing_batch_id?'<button id="generationOpenEdit" class="primary">查看续接剪辑与成片</button>':''}
  ${!g.sample&&!['queued','running','editing_ready','awaiting_intro_review'].includes(g.status)?`<div style="margin-top:14px">${g.intro_approval?'<label class="check-label"><input id="generationResumePaid" type="checkbox">允许继续续接配音与选片阶段（缓存优先，不重复提交不明请求）</label><button id="generationResume">继续续接配音与合成</button>':g.submit_id?'<button id="generationPoll">查询原即梦任务并取回视频</button>':'<label class="check-label"><input id="generationPaid" type="checkbox">允许本次文案调用及即梦生成消耗额度</label><button id="generationStart" class="primary">生成两层文案与AI开头</button>'}</div>`:''}</div>`);
  $('#generationResume')?.addEventListener('click',()=>{if(!$('#generationResumePaid').checked)return toast('请允许继续续接阶段');action(async()=>{await api(`${wb()}/generation/${id}/resume`,'POST',{allow_paid:true});$('#dialog').close()})});
  const sampleAction=(op,body={})=>action(async()=>{
    await api(`${wb()}/generation/${id}/${op}`,'POST',body);
    $('#dialog').close();
  });
  $('#prepareCanvasSample')?.addEventListener('click',()=>sampleAction('start'));
  $('#pollCanvasSample')?.addEventListener('click',()=>sampleAction('poll'));
  $('#approveCanvasSample')?.addEventListener('click',()=>sampleAction('approve-sample',{credits:g.sample_credits,allow_paid:true}));
  $('#generationStart')?.addEventListener('click',()=>{if(!$('#generationPaid').checked)return toast('请允许本阶段服务调用与费用');action(async()=>{await api(`${wb()}/generation/${id}/start`,'POST',{allow_paid:true});$('#dialog').close()})});
  $('#generationPoll')?.addEventListener('click',()=>action(async()=>{await api(`${wb()}/generation/${id}/poll`,'POST',{});$('#dialog').close()}));
  $('#generationApprove')?.addEventListener('click',()=>{if(!$('#generationApproved').checked||!$('#generationTtsPaid').checked)return toast('请确认当前AI开头及后续调用');action(async()=>{await api(`${wb()}/generation/${id}/approve-intro`,'POST',{content_confirmed:true,intro_sha256:g.intro.sha256,allow_paid:true});$('#dialog').close()})});
  $('#generationOpenEdit')?.addEventListener('click',()=>{
    if(!W().editing_batches.some(batch=>batch.id===g.editing_batch_id))return toast('对应的剪辑记录已不可用');
    editingBatchId=g.editing_batch_id;editingPage=1;
    $('#dialog').close();
    location.hash='editing';
  });
}
function generationSettings({voiceOnly=false}={}){
  const c=state.generation_config||{};
  dialog(voiceOnly?'ElevenLabs 配音设置':'生成服务设置',`<form id="generationConfig"><p class="small muted">设置保存在本机。密钥不会回显，保存不会调用生成。</p><p>${voiceOnly?badge(c.elevenlabs_key_ready?'ElevenLabs密钥已保存':'ElevenLabs待配置'):`${badge(c.dreamina_installed?'即梦CLI已安装':'即梦CLI待配置')} ${badge(c.codex_installed?'Codex CLI已安装':'Codex CLI待配置')}`}</p>
  ${voiceOnly?`<label class="field"><span>ElevenLabs API密钥（留空保留现有值）</span><input type="password" name="elevenlabs_api_key" autocomplete="new-password"></label><label class="field"><span>ElevenLabs声音ID</span><input name="voice_id" id="generationVoice" value="${esc(c.voice_id||'')}"><button type="button" id="generationVoices">保存密钥并获取声音列表</button><select id="generationVoiceList" hidden style="display:none"></select></label><label class="field"><span>ElevenLabs模型</span><input name="tts_model" value="${esc(c.tts_model||'eleven_multilingual_v2')}"></label>`:
  `<label class="field"><span>AI开头时长（秒）</span><input name="duration" type="number" min="4" max="30" value="${c.duration||5}"></label><details><summary>CLI及模型设置</summary>
    <p><button type="button" id="copyCanvasInstall">复制即梦画布 CLI 安装命令（PowerShell）</button></p>
    <p class="small muted">画布 CLI 安装后可在终端运行 dreamina-canvas auth login。下方路径供现有 AI 开头生成流程使用。</p><label class="field"><span>即梦CLI路径</span><input name="dreamina_bin" value="${esc(c.dreamina_bin||'')}"></label><p class="small muted">首次使用需在本机完成 dreamina login；网页登录不等于CLI已登录。程序不会自动替你同意模型协议。</p><button type="button" id="copyDreaminaLogin">复制即梦CLI登录命令</button><label class="field"><span>Codex CLI路径</span><input name="codex_bin" value="${esc(c.codex_bin||'')}"></label><label class="field"><span>即梦模型（留空沿用CLI默认）</span><input name="jimeng_model" value="${esc(c.jimeng_model||'')}"></label><label class="field"><span>即梦生成分辨率</span><select name="video_resolution">${['480p','720p','1080p','4k'].map(v=>`<option value="${v}" ${v===c.video_resolution?'selected':''}>${v}</option>`).join('')}</select></label></details>`}<button class="primary">保存设置</button></form>`);
  const settingsForm=$('#generationConfig');
  const save=async(showList=false)=>{
    const body=Object.fromEntries(new FormData(settingsForm));
    if(!voiceOnly)body.duration=Number(body.duration);
    const previous=state.generation_config||{};
    const config=await api('/api/generation/settings','POST',body);
    state.generation_config=config;
    if(!voiceOnly)return;
    settingsForm.elements.elevenlabs_api_key.value='';
    const form=$('#narrationForm');
    const refreshForm=form&&W()&&config.elevenlabs_key_ready&&(body.elevenlabs_api_key?.trim()||previous.voice_id!==config.voice_id);
    if(showList||refreshForm){
      const voices=api('/api/generation/voices');
      if(refreshForm)bindNarrationForm(W(),true,voices);
      if(showList)return voices;
    }
  };
  if(!voiceOnly)$('#copyCanvasInstall').onclick=async()=>{
    const command='irm https://jimeng.jianying.com/canvas-cli/install.ps1 | iex';
    try{await navigator.clipboard.writeText(command);toast('安装命令已复制');}
    catch{toast(command);}
  };
  if(!voiceOnly)$('#copyDreaminaLogin').onclick=async()=>{try{const executable=$('#generationConfig').elements.dreamina_bin.value.replace(/'/g,"''");await navigator.clipboard.writeText("& '"+executable+"' login");toast('登录命令已复制，在PowerShell中执行并完成授权')}catch(e){toast('请使用上方CLI路径执行 login')}};
  $('#generationConfig').onsubmit=e=>{e.preventDefault();action(async()=>{await save();$('#dialog').close()})};
  if(voiceOnly)$('#generationVoices').onclick=async()=>{try{const r=await save(true);if(!settingsForm.isConnected)return;const select=$('#generationVoiceList');select.hidden=false;select.style.display='block';select.innerHTML='<option value="">选择声音</option>'+r.voices.map(v=>`<option value="${esc(v.id)}">${esc(v.name)}</option>`).join('');select.onchange=()=>{$('#generationVoice').value=select.value}}catch(e){toast(e.message)}};
}
