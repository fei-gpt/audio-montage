function activeModule(){return location.hash==='#editing'?'editing':'materials'}
function renderModuleNavigation(){
  const editing=activeModule()==='editing';
  for(const [id,selected] of [['homeNav',!editing],['editingNav',editing]]){
    const button=$('#'+id);button.classList.toggle('active',selected);
    if(selected)button.setAttribute('aria-current','page');else button.removeAttribute('aria-current');
  }
}
let editingBatchId=null,editingPage=1;

function editOutputName(output){return output?.path?.split(/[\\/]/).pop()||''}
function editDownloadLink(output){
  const name=editOutputName(output);
  return `<a href="${esc(output.media_url)}" download="${esc(name)}">下载成片</a>`;
}
const editLabels={ready:'待规划',timing_ready:'配音时间轴已识别',invalid:'输入无效',queued:'等待执行',running:'处理中',planned:'已规划',awaiting_review:'待审预览',completed:'已输出',needs_attention:'需要处理',paused:'已暂停',cancelled:'已取消',interrupted:'已中断'};
function editingRows(tasks,page){const pages=Math.max(1,Math.ceil(tasks.length/20));page=Math.max(1,Math.min(page,pages));return {page,pages,rows:tasks.slice((page-1)*20,page*20)}}
const closedEditStatuses=new Set(['completed','cancelled','invalid']);
function editBatchLabel(batch){
  const first=batch.tasks[0],date=String(batch.created_at||'').replace('T',' ').slice(0,16);
  const statuses=[...new Set(batch.tasks.map(t=>editLabels[t.status]||t.status))];
  const name=batch.tasks.length===1?first.name:`批量 · ${batch.tasks.length} 条`;
  return [name,statuses.join(' / '),date].filter(Boolean).join(' · ');
}
function canRegenerate(t){return Boolean(t.plan)&&!['queued','running','invalid'].includes(t.status)}
function editingHistory(batches,batch,data){
  if(!batch)return '<section class="panel recent"><h2>剪辑历史</h2><p class="muted">还没有剪辑记录。</p></section>';
  const active=batch.tasks.filter(t=>!closedEditStatuses.has(t.status));
  const busy=active.some(t=>['queued','running'].includes(t.status));
  const canPlan=!busy&&active.some(t=>['ready','timing_ready'].includes(t.status));
  const canPreview=!busy&&active.some(t=>t.plan&&!t.preview);
  const completed=batch.tasks.filter(t=>t.output).length;
  return `<section class="panel recent">
    <div class="section-heading"><h2>剪辑历史</h2><label class="field"><span>查看记录</span><select id="editBatch" aria-label="查看剪辑记录">${[...batches].reverse().map(b=>`<option value="${esc(b.id)}" ${b.id===batch.id?'selected':''}>${esc(editBatchLabel(b))}</option>`).join('')}</select></label></div>
    <p class="small muted">${batch.rules.mode==='direct'?'直接输出':'先预览再确认'} · ${batch.tasks.length} 条 · 已有成片 ${completed} 条</p>
    ${active.length&&batch.tasks.length>1?`<div class="inline">
      ${canPlan?'<button data-edit-batch-action="plan">开始规划</button>':''}
      ${canPreview?'<button data-edit-batch-action="preview">生成预览</button>':''}
      ${busy?'<button data-edit-batch-action="pause">暂停本批</button>':''}
      <button data-edit-batch-action="cancel">取消本批</button></div>`:''}
    <div class="asset-table-wrap" style="margin-top:12px;max-height:650px"><table class="asset-table">
      <thead><tr><th>输入文件</th><th>音频时长</th><th>状态</th><th>成片文件名</th><th>结果</th></tr></thead>
      <tbody>${data.rows.map(t=>`<tr><td>${esc(t.name)}${t.variant?`<div class="small muted">候选 ${t.variant} / ${batch.variant_count}</div>`:''}</td><td>${t.audio_duration==null?'—':t.audio_duration.toFixed(2)+' 秒'}</td><td>${badge(editLabels[t.status]||t.status)}${t.error||['queued','running'].includes(t.status)?`<div class="small muted">${esc(t.error||t.stage)}</div>`:''}</td>
        <td class="file-path">${esc(editOutputName(t.output)||'—')}</td>
        <td><div class="inline">${t.output?.media_url?editDownloadLink(t.output):''}
        <button data-edit-detail="${esc(t.id)}">${t.output?'查看成片':t.preview?'查看预览':closedEditStatuses.has(t.status)?'查看记录':'查看任务'}</button>
        ${canRegenerate(t)?`<button data-edit-regenerate="${esc(t.id)}">沿用要求，重新选片</button>`:''}</div></td></tr>`).join('')}</tbody>
    </table></div>
    ${data.pages>1?`<div class="inline" style="justify-content:flex-end;margin-top:12px"><button id="editPrev" ${data.page===1?'disabled':''}>上一页</button><span>${data.page} / ${data.pages}</span><button id="editNext" ${data.page===data.pages?'disabled':''}>下一页</button></div>`:''}
    <details class="reference"><summary>保存位置</summary><p class="file-path">${esc(batch.output_path||'—')}</p></details>
  </section>`;
}
function editingHome(){
  const p=P();if(p)wid=defaultWorkspace(p,wid,accountPreferences);const w=W(),batches=w?.editing_batches||[];
  if(!batches.some(b=>b.id===editingBatchId))editingBatchId=batches.at(-1)?.id||null;
  const batch=batches.find(b=>b.id===editingBatchId),data=editingRows(batch?.tasks||[],editingPage);editingPage=data.page;
  const readyShots=w?.shots?.filter(s=>s.review_decision==='keep'&&s.human_confirmed&&!s.stale&&w.assets.some(a=>a.id===s.asset_id)).length||0;
  const disabled=w?.assigned?'':'disabled';
  $('#crumb').textContent='视频剪辑制作'+(p?' / '+p.name:'')+(w?' / '+w.name:'');
  $('#main').innerHTML=`<div class="heading"><div><h1>视频剪辑制作</h1><div class="muted">选择手头已有的文件，开始剪辑</div></div><button id="editRefresh">刷新</button></div>
  <section class="panel form-panel"><label class="field"><span>产品</span><select id="editProduct"><option value="">选择产品</option>${state.products.map(x=>`<option value="${x.id}" ${x.id===pid?'selected':''}>${esc(x.name)}</option>`).join('')}</select></label>${p?accountSelector():''}
  <p class="small muted">${w?.assigned?'自动使用当前账号的素材库 · '+readyShots+' 个已确认镜头':'请先在「素材处理」中为当前账号接入素材库。'}</p>
  <div class="edit-entry-options">
    <div><button id="newPairBatch" ${disabled}>批量导入视频＋配音</button><p class="small muted">已有多组同名 MP4 和 MP3，例如 001.mp4 和 001.mp3。选一个文件夹，按文件名配对后批量创建任务。</p></div>
    <div><button id="newReferenceBatch" ${disabled}>按参考视频剪辑</button><p class="small muted">已有想参考的成片。上传参考视频，用素材库里的画面匹配它的镜头和节奏，配音可选。</p></div>
    <div><button id="newEditBatch" ${disabled}>用配音或音乐剪辑</button><p class="small muted">上传一条配音或音乐，从当前素材库选画面。音乐按整曲时长规划。</p></div>
  </div></section>
  ${typeof p?.editing_guidelines==='string'?`<section class="panel form-panel" style="margin-top:24px"><h2>剪辑总纲</h2><label class="field"><span>同产品共用 · 用于语义选片和参考剪辑</span><textarea id="editingGuidelines" rows="8" maxlength="10000">${esc(p.editing_guidelines)}</textarea></label><button id="saveEditingGuidelines" type="button">保存剪辑总纲</button></section>`:''}${w?editingHistory(batches,batch,data):''}${w?generationSection():''}`;
  $('#editProduct').onchange=e=>{pid=e.target.value||null;wid=null;editingBatchId=null;render()};
  $('#saveEditingGuidelines')?.addEventListener('click',()=>action(async()=>{await api(`/api/products/${p.id}/editing-guidelines`,'POST',{text:$('#editingGuidelines').value});toast('剪辑总纲已保存，同产品共用')}));
  if(p)bindAccounts();$('#editRefresh').onclick=()=>refresh();
  $('#newEditBatch').onclick=()=>editBatchDialog();$('#newReferenceBatch').onclick=()=>editBatchDialog(true);$('#newPairBatch').onclick=editPairBatchDialog;bindGeneration();
  $('#editBatch')?.addEventListener('change',e=>{editingBatchId=e.target.value;editingPage=1;render()});
  $('#editPrev')?.addEventListener('click',()=>{editingPage--;render()});$('#editNext')?.addEventListener('click',()=>{editingPage++;render()});
  document.querySelectorAll('[data-edit-regenerate]').forEach(b=>b.onclick=()=>regenerateEdit(b.dataset.editRegenerate));
  document.querySelectorAll('[data-edit-detail]').forEach(b=>b.onclick=()=>editTaskDialog(b.dataset.editDetail));
  document.querySelectorAll('[data-edit-batch-action]').forEach(b=>b.onclick=()=>editOperation(b.dataset.editBatchAction));
}
async function editUploadFile(file,kind){
  if(file.size>500000000)throw Error('单个文件不能超过500MB');
  const response=await fetch(`${wb()}/editing/uploads`,{method:'POST',headers:{'X-Workbench-Token':window.WORKBENCH_TOKEN,'X-File-Name':encodeURIComponent(file.name),'X-Upload-Kind':kind,'Content-Type':'application/octet-stream'},body:file});
  const result=await response.json();if(!response.ok)throw Error(result.error||'上传失败');return result;
}
function editBatchDialog(referenceMode=false){
  const w=W(),count=w.shots.filter(s=>s.review_decision==='keep'&&s.human_confirmed&&!s.stale&&w.assets.some(a=>a.id===s.asset_id)).length;
  const uploaded=new Map();
  dialog(referenceMode?'参考视频匹配镜头':'用配音或音乐剪辑',`<form id="editCreate"><div class="meta-box">使用 ${esc(P().name)} / ${esc(w.name)} 已确认素材库 · ${count} 个已确认镜头。无需重新上传素材。</div>
  ${referenceMode?'':'<label class="field"><span>主音频</span><select id="editAudioKind"><option value="narration">配音</option><option value="music">音乐</option></select></label>'}
  <div class="refbox" style="margin-top:16px"><label class="field"><span id="editNarrationLabel">上传配音</span><input id="editNarration" type="file" accept="audio/*,.mp3,.wav,.m4a,.aac,.flac" required></label><p class="small muted" id="editAudioHint">画面使用当前账号素材库。</p></div>
  <div id="editBackgroundMusic" class="refbox" style="margin-top:12px"><label class="field"><span>背景音乐（可选）</span><input id="editMusic" type="file" accept="audio/*,.mp3,.wav,.m4a,.aac,.flac"></label><label class="field"><span>音乐音量（%）</span><input type="number" name="music_volume" min="0" max="100" value="15"></label><p class="small muted">仅混入配音对应的主体部分。音乐不足时不自动循环，剩余部分继续保留配音。</p></div>
  ${referenceMode?`<label class="field"><span>参考视频（竖屏 9:16，最多 120 秒）</span><input id="editReference" type="file" accept=".mp4,.mov,.mkv,.webm" required></label><p class="small muted">可只传参考片做无配音预览。</p>`:''}<div id="editScripts"><label class="field"><span>整段配音文案（可选）</span><textarea name="script_0" placeholder="粘贴与配音对应的整段文案，无需提供字幕文件"></textarea></label></div>
  <label class="field"><span>使用哪一种素材识别结果？</span><select name="analysis_mode"><option value="simple" ${P().analysis_mode==='simple'?'selected':''}>简单展示结果</option><option value="standard" ${P().analysis_mode!=='simple'?'selected':''}>明确标准结果（含旧版记录）</option></select></label><label class="field"><span>剪辑匹配方式</span><select name="matching_mode"><option value="duration">时长匹配 · 按断句长度选素材（不调用模型）</option><option value="semantic">语义匹配 · 按文案意思选画面（调用模型）</option></select></label><label class="field" id="editSemanticRequest"><span>剪辑要求（语义模式使用）</span><textarea name="request" placeholder="例如：先展示握持动作，再展示灯效；不使用包装画面"></textarea></label>
  <label class="field"><span>候选数量</span><select name="variant_count"><option value="1">1 条</option><option value="5">5 条</option><option value="10">10 条</option><option value="15">15 条</option></select><small>多条候选沿用同一要求，先生成预览供你选择。只统计正式导出的素材引用。</small></label>
  <label class="field"><span>输出方式</span><select name="mode"><option value="preview">先预览再确认成片</option><option value="direct">直接输出（未人工审片）</option></select></label>
  <label class="field" id="editLanguage"><span>配音语言</span><select name="language"><option value="auto">自动检测</option><option value="en">英语</option><option value="es">西班牙语</option><option value="zh">中文</option></select></label>
  ${referenceMode?'':`<label class="field"><span>必切时间点（可选）</span><textarea name="required_cuts" rows="2" maxlength="2000" placeholder="00:00:04:16"></textarea><small>按成片时间填写，每行一个。格式为 时:分:秒:帧（30 fps），例如 00:00:04:16 是 4 秒 16 帧。</small></label>`}
  ${referenceMode?'':`<div id="editMusicCues" hidden><label class="check-label"><input type="checkbox" name="music_cue_assist">音乐卡点（可选）</label><small>未填必切时间点时，尝试在明显重拍或能量上升处安排少量切镜。可用镜头不合适时，按普通时长规划。</small></div>`}
  <label class="check-label"><input type="checkbox" name="keep_original_audio">保留素材库画面的原声</label>
  <label class="check-label"><input type="checkbox" name="rights_allowed" required>已确认本次上传文件和账号素材的使用范围</label>
  <details><summary>输出位置与本地语音识别设置</summary><label class="field"><span>输出父目录（留空则保存到本机账号工作区）</span><div class="inline"><input id="editOutput" name="output_path" style="flex:1"><button type="button" data-edit-folder="editOutput">选择文件夹</button></div></label><label class="field" id="editAsrModel"><span>自定义模型目录（可留空，默认使用内置模型）</span><input name="model_path" id="editModel"><button type="button" data-edit-folder="editModel">选择模型文件夹</button></label><p class="small muted" id="editAsrHint">时间来自实际音频识别，整段文案用于核对和选片，不按文字长度猜时间。${state.editing_capabilities?.local_asr?.ready?'本地识别已就绪，自动获取时间轴。':'本地识别环境准备中；不要求上传字幕文件。'}</p></details>
  <div id="editPlanConsent" hidden><label class="check-label"><input type="checkbox" name="allow_paid">允许本次使用 ${esc(state.capabilities?.config?.model||'已配置模型')} 规划镜头，使用模型额度</label></div><p id="editUploadProgress" class="small muted" role="status"></p><button id="editCreateSubmit" class="primary">上传并开始剪辑</button></form>`);
  const audioKind=$('#editAudioKind'), narrator=$('#editNarration');
  const matching=$('[name="matching_mode"]'), mode=$('[name="mode"]');
  const paidConsent=$('[name="allow_paid"]'),variants=$('[name="variant_count"]');
  function updateExecution(){
    const multiple=Number(variants.value)>1;
    if(mode.options)mode.options[1].disabled=referenceMode||multiple;
    if(multiple)mode.value='preview';
    const paid=matching.value==='semantic';
    $('#editPlanConsent').hidden=!paid;
    paidConsent.required=paid;
    paidConsent.disabled=!paid;
    if(!paid)paidConsent.checked=false;
    $('#editCreateSubmit').textContent=mode.value==='direct'?'上传并直接输出':'上传并生成预览';
  }
  matching.onchange=mode.onchange=variants.onchange=updateExecution;
  function audioSettings(){
    const music=audioKind?.value==='music';
    narrator.required=!referenceMode;
    $('#editNarrationLabel').textContent=music?'上传音乐（必选）':referenceMode?'上传自己的配音（可选）':'上传配音（必选）';
    $('#editAudioHint').textContent=music?'按整首音乐的实际时长规划画面，使用原音乐作为成片音轨。':'画面使用当前账号素材库。';
    const cueBox=$('#editMusicCues'), cuts=$('[name="required_cuts"]');
    if(cueBox&&cuts){
      const showCues=()=>{cueBox.hidden=!music||Boolean(cuts.value?.trim())};
      cuts.oninput=showCues;showCues();
    }
    $('#editBackgroundMusic').hidden=music;
    for(const id of ['editScripts','editSemanticRequest','editLanguage','editAsrModel','editAsrHint'])$('#'+id).hidden=music;
    if(referenceMode){matching.value='semantic';mode.value='preview'}
    if(music)matching.value='duration';
    if(matching.options){matching.options[0].disabled=referenceMode;matching.options[1].disabled=music}
    if(mode.options)mode.options[1].disabled=referenceMode;
    $('#editUploadProgress').textContent=referenceMode?'上传后自动匹配参考镜头并生成预览。':music?'上传后按音乐时长自动选片，无需转写或调用模型。':'上传后自动识别配音时间轴并选片。';
    updateExecution();
  }
  if(audioKind)audioKind.onchange=()=>{narrator.value='';audioSettings()};
  audioSettings();
  document.querySelectorAll('[data-edit-folder]').forEach(b=>b.onclick=async()=>{try{const input=$('#'+b.dataset.editFolder);const r=await api('/api/choose-folder','POST',{initial:input.value});if(r.path)input.value=r.path}catch(e){toast(e.message)}});
  $('#editCreate').onsubmit=e=>{e.preventDefault();const f=new FormData(e.target),file=narrator.files[0],musicOnly=audioKind?.value==='music',music=$('#editMusic').files[0];
    const body={auto_preview:true,variant_count:Number(f.get('variant_count')),mode:f.get('mode'),language:f.get('language'),request:f.get('request'),output_path:f.get('output_path'),model_path:f.get('model_path'),music_volume:Number(f.get('music_volume')),rights_allowed:f.has('rights_allowed'),keep_original_audio:f.has('keep_original_audio')};
    action(async()=>{if(f.get('matching_mode')==='duration'){try{const capabilities=await api('/api/editing-modes');if(!capabilities.modes.includes('duration'))throw new Error('unsupported')}catch(e){throw new Error('时长匹配需要加载新版服务，请待当前任务结束后重启工作台')}}async function upload(file,kind){const key=JSON.stringify([kind,file.name,file.size,file.lastModified]);if(!uploaded.has(key)){ $('#editUploadProgress').textContent='正在上传并检查：'+file.name;uploaded.set(key,await editUploadFile(file,kind))}return uploaded.get(key)}
      body.narrations=[];
      if(file){
        if(musicOnly)body.primary_music_id=(await upload(file,'music')).id;
        else body.narrations.push({id:(await upload(file,'narration')).id,script:f.get('script_0')||''});
      }
      const reference=referenceMode?$('#editReference').files[0]:null;
      if(reference)body.reference_id=(await upload(reference,'reference')).id;
      if(music&&!musicOnly)body.music_id=(await upload(music,'music')).id;
      body.analysis_mode=f.get('analysis_mode');body.matching_mode=f.get('matching_mode');
      if(!referenceMode)body.required_cuts=f.get('required_cuts')||'';
      if(musicOnly&&!body.required_cuts.trim())body.music_cue_assist=f.has('music_cue_assist');
      const b=await api(`${wb()}/editing/batches`,'POST',body);
      editingBatchId=b.id;editingPage=1;$('#dialog').close();
      await api(`${wb()}/editing/batches/${b.id}/plan`,'POST',{allow_paid:body.matching_mode==='semantic'&&f.has('allow_paid')});
    });
  };
}
function currentEditBatch(){return W()?.editing_batches?.find(b=>b.id===editingBatchId)}
function editOperation(op,taskId,extra={}){
  if(op==='preview'&&!taskId){extra.task_ids=currentEditBatch().tasks.filter(t=>t.plan&&!['running','queued','completed','cancelled','invalid'].includes(t.status)).map(t=>t.id);if(!extra.task_ids.length)return toast('没有可生成预览的已规划任务')}
  const go=allow_paid=>action(async()=>{await api(`${wb()}/editing/batches/${editingBatchId}/${op}`,'POST',{...(taskId?{task_ids:[taskId]}:{}),...extra,allow_paid});$('#dialog').close()});
  if(['plan','resume'].includes(op)&&currentEditBatch()?.rules.matching_mode!=='duration'){
    dialog('规划剪辑',`<p>${currentEditBatch()?.reference?'将参考片采样图与已有镜头记录用于匹配，并用入选及备选区间的采样图复核是否同源。调用':'将配音文本、产品知识和已保存的素材分析发送给'} ${esc(state.capabilities.config.model)}，不重新发送整库视频。使用当前配置的模型额度。</p><label class="check-label"><input id="editPaid" type="checkbox">允许本次规划调用；未完整返回时不自动重试</label><button id="editGo" class="primary">开始规划${currentEditBatch()?.rules.mode==='direct'?'并直接输出':''}</button>`);
    $('#editGo').onclick=()=>{if(!$('#editPaid').checked)return toast('请明确允许本次模型调用');go(true)};
  }else go(false);
}
function regenerateEdit(id){
  const b=currentEditBatch();
  if(!b?.tasks.some(t=>t.id===id&&canRegenerate(t)))return;
  const launch=allowPaid=>action(async()=>{
    const result=await api(`${wb()}/editing/batches/${b.id}/regenerate`,'POST',{task_ids:[id],allow_paid:allowPaid});
    editingBatchId=result.id;editingPage=1;
    if($('#dialog').open)$('#dialog').close();
  });
  if(b.rules.matching_mode==='duration'){launch(false);return}
  dialog('沿用要求，重新选片',`<p>沿用原输入、必切点和剪辑要求。新结果会另存，原记录可继续查看。</p>
    <label class="check-label"><input id="regeneratePaid" type="checkbox">允许本次使用 ${esc(state.capabilities.config.model)} 重新选片，使用模型额度</label>
    <button id="regenerateSubmit" class="primary">开始重新选片</button>`);
  $('#regenerateSubmit').onclick=()=>{if(!$('#regeneratePaid').checked)return toast('请允许本次模型调用');launch(true)};
}
function editTaskDialog(id){
  const b=currentEditBatch(),t=b.tasks.find(t=>t.id===id);if(!t)return;
  const busy=['queued','running'].includes(t.status),off=closedEditStatuses.has(t.status);
  dialog(t.name,`<div style="max-height:72vh;overflow:auto"><p>${badge(editLabels[t.status])} ${esc(t.stage)}</p>${t.error?`<p class="error">${esc(t.error)}</p>`:''}
  <p class="small file-path">${b.rules.reference_only?'参考片（无配音）':b.rules.audio_kind==='music'?'音乐':'配音'}：${esc(t.name)}${t.intro?`<br>原批次前段：${esc(t.intro)}`:''}</p>${t.script?`<details><summary>用户提供的整段文案</summary><p class="result-note">${esc(t.script)}</p></details>`:''}
  ${t.output||t.preview?`<video class="preview-video" controls playsinline preload="metadata" src="${esc((t.output||t.preview).media_url)}"></video>${t.output?`<p>${editDownloadLink(t.output)} · ${t.human_reviewed?'已确认预览':'未人工审片'}</p>`:''}`:''}
  ${t.script_check&&!t.script_check.matched?'<p class="warning">整段文案与音频识别文字存在差异，请核对下方时间轴。</p>':''}${t.timeline?`<details><summary>音频时间轴（${t.timeline.segments.length}段，来源 ${esc(t.timeline.source)}）</summary>${t.timeline.segments.map(s=>`<p class="small">${s.start.toFixed(2)}–${s.end.toFixed(2)} · ${esc(s.text)}</p>`).join('')}</details>`:''}
  ${b.reference?'<button id="inspectReference">查看逐镜诊断与纠错</button>':''}
  ${referenceMatchPanel(b,t,busy||off)}
  ${t.reference_analysis?`<details><summary>参考视频结构（采样初审，非精确切点）</summary>${t.reference_analysis.beats.map(x=>`<p>${x.start}–${x.end}秒 · ${esc(x.purpose)} · ${esc(x.action)} · ${esc(x.composition)}</p>${x.must_see?`<p>必须看见 · ${esc(x.must_see.join('；'))}</p>${x.flexible?.length?`<p>允许变化 · ${esc(x.flexible.join('；'))}</p>`:''}`:''}`).join('')}</details>`:''}${t.plan?`<details><summary>剪辑清单（${t.plan.parts.length}段）</summary>${t.plan.parts.map(p=>`<p class="small">${p.timeline_start.toFixed(2)}–${p.timeline_end.toFixed(2)} · ${esc(p.reason)}</p>`).join('')}<label class="field"><span>修正清单 JSON（只能使用已确认镜头与安全区间）</span><textarea id="editPlanJson" style="min-height:180px">${esc(JSON.stringify(t.plan,null,2))}</textarea></label><button id="editSavePlan" ${busy||off?'disabled':''}>保存修改并重新预览</button></details>`:''}
  ${off?'':`<div class="inline" style="margin-top:16px"><button data-edit-op="${['ready','timing_ready'].includes(t.status)?'plan':'resume'}" ${busy||off?'disabled':''}>${t.plan?'继续任务':'规划选片'}</button><button data-edit-op="preview" ${!t.plan||busy||off?'disabled':''}>生成预览</button><button data-edit-op="pause" ${off?'disabled':''}>暂停</button><button data-edit-op="cancel" ${off?'disabled':''}>取消</button></div>`}
  ${t.plan&&!off?`<div style="margin-top:16px">${b.rules.mode==='preview'?'<label class="check-label"><input id="editReviewed" type="checkbox">已实际核对当前预览的内容、完整动作、配音时间轴和音画衔接</label>':''}<button class="primary" id="editFinal" ${busy||t.plan.reference_gaps?.length||b.rules.mode==='preview'&&!t.preview?'disabled':''}>${b.rules.mode==='direct'?'直接输出（未人工审片）':'确认并输出'}</button></div>`:''}</div>`);
  document.querySelectorAll('[data-edit-op]').forEach(button=>button.onclick=()=>editOperation(button.dataset.editOp,id));
  $('#inspectReference')?.addEventListener('click',()=>showReferenceReview(b,t));
  bindReferenceMatchPanel(b,t,busy||off);
  $('#editSavePlan')?.addEventListener('click',()=>{try{editOperation('save-plan',id,{plan:JSON.parse($('#editPlanJson').value),plan_revision:t.plan_revision})}catch(e){toast('JSON 格式错误：'+e.message)}});
  $('#editFinal')?.addEventListener('click',()=>{if(b.rules.mode==='preview'&&!$('#editReviewed').checked)return toast('请先核对当前预览');editOperation('output',id,{content_confirmed:$('#editReviewed')?.checked||false,preview_sha256:t.preview?.sha256})});
}

function referenceMatchPanel(batch, task, locked) {
  if (!batch.reference || !task.plan || !task.reference_analysis) return '';
  const beats = task.reference_analysis.beats;
  const omitted = beats.map((_, i) => i + 1).filter(n => !task.plan.parts.some(p => p.reference_beat === n));
  const rows = task.plan.parts.map((part, index) => {
    const beat = beats[part.reference_beat - 1];
    if (!beat) return '';
    const options = task.reference_choices?.[index] || [part];
    return `<details class="refbox" data-match-row="${index}">
      <summary>${part.timeline_start.toFixed(2)}–${part.timeline_end.toFixed(2)} 秒 · ${esc(part.source_name)} · 参考第 ${part.reference_beat} 段</summary>
      <p>参考 ${beat.start}–${beat.end} 秒 · ${esc(beat.purpose)} · ${esc(beat.action)}</p>
      <p>选片依据：${esc(part.reason)}</p>
      <label class="field">对照镜头<select data-match-option>${options.map((c,i)=>`<option value="${i}" ${c.shot_id===part.shot_id?'selected':''}>${esc(c.source_name)} · ${c.start.toFixed(2)}–${c.end.toFixed(2)} 秒</option>`).join('')}</select></label>
      <p class="small" data-match-reason></p><div data-match-videos></div>
      ${options.length>1&&!locked?'<button data-match-apply disabled>仅替换这一镜</button>':'<p class="small muted">当前没有可切换的同用途备选，或任务已锁定。</p>'}</details>`;
  }).join('');
  if (!rows) return '';
  return `<section><h3>参考分镜与实拍对照</h3>
    ${task.plan.reference_gaps?.length?`<p class="warning">待补区间（预览保留原时长，补齐后可输出）</p>${task.plan.reference_gaps.map(g=>`<p class="small">第 ${g.beat} 段 · ${(g.start_frame/30).toFixed(2)}–${((g.start_frame+g.frames)/30).toFixed(2)} 秒 · ${esc(g.reason)}</p>`).join('')}`:''}
    ${omitted.length&&!task.plan.reference_gaps?`<p class="warning">本次未采用的参考分镜：${omitted.join('、')}</p>`:''}
    ${(Array.isArray(task.reference_notes)?task.reference_notes:[]).map(n=>`<p class="small">${esc(typeof n==='string'?n:n.reason)}</p>`).join('')}
    ${task.reference_screen?`<p class="small">全库初筛排除 ${task.reference_screen.excluded.length} 个区间。入选与备选的拼图复核另排除 ${Object.values(task.reference_verdicts||{}).filter(v=>v.verdict!=='different_shoot').length} 个存疑选区。</p>`:''}${rows}</section>`;
}

function bindReferenceMatchPanel(batch, task, locked) {
  for (const row of document.querySelectorAll('[data-match-row]')) {
    const index = Number(row.dataset.matchRow);
    const part = task.plan.parts[index], beat = task.reference_analysis.beats[part.reference_beat-1];
    const options = task.reference_choices?.[index] || [part];
    const select = row.querySelector('[data-match-option]'), apply = row.querySelector('[data-match-apply]');
    const player = (label,url,start,end) => url ? `<label class="field">${label}<video controls muted playsinline preload="metadata" style="width:100%;max-height:240px" src="${esc(url)}#t=${start},${end}"></video></label>` : '';
    function show() {
      const choice = options[Number(select.value)], asset = W().assets.find(a => a.id===choice.asset_id);
      row.querySelector('[data-match-reason]').textContent = choice.reason;
      row.querySelector('[data-match-videos]').innerHTML = row.open ? `<div style="display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:8px">${player('参考片',batch.reference.media_url,beat.start,beat.end)}${player('自己的素材',asset?.media_url,choice.start,choice.end)}</div>` : '';
      if (apply) apply.disabled = locked || part.shot_id===choice.shot_id;
    }
    row.ontoggle = select.onchange = show;
    if (apply) apply.onclick = () => editOperation('replace-shot', task.id, {index,option:Number(select.value),plan_revision:task.plan_revision});
  }
}
