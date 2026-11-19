function activeModule(){return ({'#sorting':'sorting','#editing':'editing','#narration':'narration','#generation':'generation'})[location.hash]||'materials'}
function renderModuleNavigation(){
  const module=activeModule();
  for(const [id,page] of [['homeNav','materials'],['sortingNav','sorting'],['narrationNav','narration'],['generationNav','generation'],['editingNav','editing']]){
    const selected=module===page;
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
const stoppedEditStatuses=new Set(['paused','interrupted']);
function editStatusLabel(task){return task.source_warning?'需重新选片':editLabels[task.status]||task.status}
function editBatchLabel(batch){
  const first=batch.tasks[0],date=String(batch.created_at||'').replace('T',' ').slice(0,16);
  const statuses=[...new Set(batch.tasks.map(editStatusLabel))];
  const name=batch.tasks.length===1?first.name:`批量 · ${batch.tasks.length} 条`;
  return [name,statuses.join(' / '),date].filter(Boolean).join(' · ');
}
function canRegenerate(t){return Boolean(t.plan)&&!['queued','running','invalid'].includes(t.status)}
function editingHistory(batches,batch,data){
  if(!batch)return '<section class="panel recent"><h2>剪辑历史</h2><p class="muted">还没有剪辑记录。</p></section>';
  const active=batch.tasks.filter(t=>!closedEditStatuses.has(t.status));
  const runnable=active.filter(t=>!t.source_warning);
  const busy=active.some(t=>['queued','running'].includes(t.status));
  const canPlan=!busy&&runnable.some(t=>['ready','timing_ready'].includes(t.status));
  const canPreview=!busy&&runnable.some(t=>t.plan&&!t.preview);
  const completed=batch.tasks.filter(t=>t.output).length;
  return `<section class="panel recent">
    <div class="section-heading"><h2>剪辑历史</h2><label class="field"><span>查看记录</span><select id="editBatch" aria-label="查看剪辑记录">${[...batches].reverse().map(b=>`<option value="${esc(b.id)}" ${b.id===batch.id?'selected':''}>${esc(editBatchLabel(b))}</option>`).join('')}</select></label></div>
    <p class="small muted">${batch.rules.mode==='direct'?'直接输出':'先预览再确认'} · ${batch.tasks.length} 条 · 已有成片 ${completed} 条</p>
    ${batch.tasks.length&&batch.tasks.every(t=>!t.output&&!['queued','running','completed'].includes(t.status))?'<button id="deleteEditRecord" type="button">删除此记录</button>':''}
    <div class="reference"><strong>本批剪辑要求</strong>
      <p class="result-note">${esc(batch.rules.request?.trim()?batch.rules.request:'本批未填写剪辑要求。')}</p>
    </div>
    ${active.length&&batch.tasks.length>1?`<div class="inline">
      ${!busy&&runnable.some(t=>t.status==='needs_attention')?'<button data-edit-batch-action="resume">重试失败任务</button>':''}
      ${!busy&&runnable.some(t=>stoppedEditStatuses.has(t.status))?'<button data-edit-batch-action="continue-stopped">继续暂停或中断的任务</button>':''}
      ${canPlan?'<button data-edit-batch-action="plan">开始规划</button>':''}
      ${canPreview?'<button data-edit-batch-action="preview">生成预览</button>':''}
      ${busy?'<button data-edit-batch-action="pause">暂停本批</button>':''}
      <button data-edit-batch-action="cancel">取消本批</button></div>`:''}
    <div id="editHistoryTable" data-batch="${esc(batch.id)}" data-page="${data.page}" class="asset-table-wrap" style="margin-top:12px;max-height:650px"><table class="asset-table">
      <thead><tr><th>输入文件</th><th>音频时长</th><th>状态</th><th>成片文件名</th><th>结果</th></tr></thead>
      <tbody>${data.rows.map(t=>`<tr><td>${esc(t.name)}${t.variant?`<div class="small muted">候选 ${t.variant} / ${batch.variant_count}</div>`:''}</td><td>${t.audio_duration==null?'—':t.audio_duration.toFixed(2)+' 秒'}</td><td>${badge(editStatusLabel(t))}${t.source_warning||t.error||['queued','running'].includes(t.status)?`<div class="small muted">${esc(t.source_warning||t.error||t.stage)}</div>`:''}</td>
        <td class="file-path">${esc(editOutputName(t.output)||'—')}</td>
        <td><div class="inline">${t.output?.media_url?editDownloadLink(t.output):t.preview&&!t.source_warning&&!closedEditStatuses.has(t.status)&&!['queued','running'].includes(t.status)?`<button data-edit-review="${esc(t.id)}">核对预览</button>`:'<button disabled>下载成片</button>'}
        ${t.output||!t.preview||t.source_warning||closedEditStatuses.has(t.status)||['queued','running'].includes(t.status)?`<button data-edit-detail="${esc(t.id)}">${t.output?'查看成片':t.preview?(t.source_warning?'查看旧预览':'查看预览'):closedEditStatuses.has(t.status)?'查看记录':'查看任务'}</button>`:''}
        ${!t.source_warning&&(t.status==='needs_attention'||stoppedEditStatuses.has(t.status))?`<button type="button" data-edit-retry="${esc(t.id)}">${t.status==='needs_attention'?'重试':'继续'}</button>`:''}
        ${canRegenerate(t)?`<button data-edit-regenerate="${esc(t.id)}">沿用要求，重新选片</button>`:''}</div></td></tr>`).join('')}</tbody>
    </table></div>
    ${data.pages>1?`<div class="inline" style="justify-content:flex-end;margin-top:12px"><button id="editPrev" ${data.page===1?'disabled':''}>上一页</button><span>${data.page} / ${data.pages}</span><button id="editNext" ${data.page===data.pages?'disabled':''}>下一页</button></div>`:''}
    <details class="reference"><summary>保存位置</summary><p class="file-path">${esc(batch.output_path||'—')}</p></details>
  </section>`;
}
function workspaceAssetCount(w){
  return w?.assets?.length||0;
}
function editingInventory(w){
  return `素材 ${workspaceAssetCount(w)} 条`;
}
function editingHome(){
  const p=P();if(p)wid=defaultWorkspace(p,wid,accountPreferences);const w=W(),batches=w?.editing_batches||[];
  if(!batches.some(b=>b.id===editingBatchId))editingBatchId=batches.at(-1)?.id||null;
  const batch=batches.find(b=>b.id===editingBatchId),data=editingRows(batch?.tasks||[],editingPage);editingPage=data.page;
  const previousTable=$('#editHistoryTable');
  const historyScroll=previousTable?.dataset?.batch===batch?.id&&previousTable?.dataset?.page===String(data.page)
    ? [previousTable.scrollLeft,previousTable.scrollTop] : null;
  const disabled=w?.assigned?'':'disabled';
  $('#crumb').textContent='视频剪辑制作'+(p?' / '+p.name:'')+(w?' / '+w.name:'');
  $('#main').innerHTML=`<div class="heading"><div><h1>视频剪辑制作</h1><div class="muted">选择手头已有的文件，开始剪辑</div></div>${p?'<button id="openEditingGuidelines" type="button">剪辑总纲</button>':''}<button id="editRefresh">刷新</button></div>
  <section class="panel form-panel"><label class="field"><span>产品</span><select id="editProduct"><option value="">选择产品</option>${state.products.map(x=>`<option value="${x.id}" ${x.id===pid?'selected':''}>${esc(x.name)}</option>`).join('')}</select></label>${p?accountSelector():''}
  <p class="small muted">${w?.assigned?'自动使用当前账号的素材库 · '+editingInventory(w):'请先在「素材处理」中为当前账号接入素材库。'}</p>
  <div class="edit-entry-options">
    <div><button id="newPairBatch" ${disabled}>批量导入视频＋配音</button><p class="small muted">已有多组同名 MP4 和 MP3，例如 001.mp4 和 001.mp3。选一个文件夹，按文件名配对后批量创建任务。</p></div>
    <div><button id="newReferenceBatch" ${p?.sentence_editing_only?'disabled':disabled}>按参考视频剪辑</button><p class="small muted">已有想参考的成片。上传参考视频，用素材库里的画面匹配它的镜头和节奏，配音可选。</p></div>
    <div><button id="newEditBatch" ${disabled}>用配音或音乐剪辑</button><p class="small muted">选择配音或音乐，从当前素材库选画面。音乐可使用整曲或指定时长。</p></div>
  </div></section>
  ${w?editingHistory(batches,batch,data):''}`;
  if(historyScroll){
    const table=$('#editHistoryTable');
    [table.scrollLeft,table.scrollTop]=historyScroll;
  }
  $('#editProduct').onchange=e=>{pid=e.target.value||null;wid=null;editingBatchId=null;render()};
  $('#openEditingGuidelines')?.addEventListener('click',()=>{
    dialog('剪辑总纲',`<form id="editingGuidelinesForm">
      <label class="field"><span>${esc(p.name)} · 同产品共用，参考视频剪辑除外</span>
        <textarea id="editingGuidelines" rows="12" maxlength="10000">${esc(p.editing_guidelines||'')}</textarea>
      </label>
      <button class="primary">保存剪辑总纲</button>
    </form>`);
    $('#editingGuidelinesForm').onsubmit=event=>{
      event.preventDefault();
      const text=$('#editingGuidelines').value;
      return action(async()=>{
        await api(`/api/products/${p.id}/editing-guidelines`,'POST',{text});
        $('#dialog').close();
        toast('剪辑总纲已保存，同产品共用');
      });
    };
  });
  if(p)bindAccounts();$('#editRefresh').onclick=()=>refresh();
  $('#newEditBatch').onclick=()=>editBatchDialog();$('#newReferenceBatch').onclick=()=>editBatchDialog(true);$('#newPairBatch').onclick=editPairBatchDialog;
  $('#deleteEditRecord')?.addEventListener('click',()=>{
    if(!window.confirm('删除当前批次记录，并清理该批次的预览视频？'))return;
    action(async()=>{
      await api(`${wb()}/editing/batches/${batch.id}/delete-record`,'POST',{delete_previews:true});
      editingBatchId=null;
      editingPage=1;
    });
  });
  $('#editBatch')?.addEventListener('change',e=>{editingBatchId=e.target.value;editingPage=1;render()});
  $('#editPrev')?.addEventListener('click',()=>{editingPage--;render()});$('#editNext')?.addEventListener('click',()=>{editingPage++;render()});
  document.querySelectorAll('[data-edit-regenerate]').forEach(b=>b.onclick=()=>regenerateEdit(b.dataset.editRegenerate));
  document.querySelectorAll('[data-edit-review]').forEach(b=>b.onclick=()=>editTaskDialog(b.dataset.editReview));
  document.querySelectorAll('[data-edit-detail]').forEach(b=>b.onclick=()=>editTaskDialog(b.dataset.editDetail));
  document.querySelectorAll('[data-edit-retry]').forEach(b=>b.onclick=event=>{event.preventDefault();editOperation('resume',b.dataset.editRetry)});
  document.querySelectorAll('[data-edit-batch-action]').forEach(b=>b.onclick=()=>editOperation(b.dataset.editBatchAction));
}
async function editUploadFile(file,kind,workspace){
  if(file.size>500000000)throw Error('单个文件不能超过500MB');
  const response=await fetch(`${workspace}/editing/uploads`,{method:'POST',headers:{'X-Workbench-Token':window.WORKBENCH_TOKEN,'X-File-Name':encodeURIComponent(file.name),'X-Upload-Kind':kind,'Content-Type':'application/octet-stream'},body:file});
  const result=await response.json();if(!response.ok)throw Error(result.error||'上传失败');return result;
}
function editBatchDialog(referenceMode=false, preselectedNarrations=[]){
  const w=W();
  const workspace=wb(),uploaded=new Map();
  const generated=referenceMode?[]:readyNarrations(w);
  const selected=new Set(preselectedNarrations.filter(id=>generated.some(item=>item.upload_id===id)));
  dialog(referenceMode?'参考视频匹配镜头':'用配音或音乐剪辑',`<form id="editCreate"><div class="meta-box">使用 ${esc(P().name)} / ${esc(w.name)} 素材库 · ${editingInventory(w)}。无需重新上传素材。</div>
  ${referenceMode?'':`<label class="field"><span>主音频</span><select id="editAudioKind"><option value="narration">配音</option>${P()?.sentence_editing_only?'':'<option value="music">音乐</option>'}</select></label>`}
  ${!referenceMode?`<label class="field" id="editNarrationSourceField"><span>配音来源</span>
    <select id="editNarrationSource"><option value="local">上传本地配音</option><option value="elevenlabs">使用 ElevenLabs 配音</option></select></label>
    <div id="editGeneratedNarrations" class="refbox" hidden><strong>选择已生成配音 <span id="editNarrationCount"></span></strong><p class="small muted">显示今天和昨天生成的配音。</p>
    ${generated.length?`<label class="field"><span>搜索配音</span><input id="editNarrationSearch" type="search" placeholder="按文案、音色或日期搜索"></label>
    <p id="editNarrationSearchEmpty" class="small muted" hidden>没有匹配的配音。</p>
    <div style="max-height:210px;overflow:auto">${[...generated].reverse().map(item=>`<div data-narration-search="${esc(narrationSearchText(item))}"><label class="check-label">
      <input type="checkbox" name="generated_narrations" value="${esc(item.upload_id)}" ${selected.has(item.upload_id)?'checked':''}>
      <span><strong>${esc(item.name)}</strong><br>${esc(item.script)} · ${esc(item.voice_name)} · ${item.duration.toFixed(2)} 秒${item.created_at?' · '+esc(narrationDate(item)):''}${item.used?' · 已使用':''}</span></label>
      <details data-individual-editor ${selected.has(item.upload_id)?'':'hidden'}>
        <summary>单条补充要求 <span data-individual-filled></span></summary>
        <label class="field"><span>只用于这条配音。多条要求用换行或分号分隔。</span><textarea name="request_${esc(item.upload_id)}" rows="2" maxlength="10000"></textarea></label>
        <button type="button" data-check-individual>检查识别结果</button>
        <p class="small" data-individual-result role="status"></p>
      </details></div>`).join('')}</div>`:`<p class="small muted">${!Array.isArray(w.narrations)
      ?'重启工作台后即可读取 ElevenLabs 配音历史。'
      :w.narrations.some(item=>['queued','running'].includes(item.status))
      ?'当前账号的配音仍在生成，完成后重新打开此窗口即可选择。'
      :'当前产品和账号今天和昨天没有生成成功的 ElevenLabs 配音。'}</p>
      <button type="button" id="openNarrationHistory">前往 ElevenLabs 配音</button>`}</div>`:''}
  <div id="editNarrationUpload" class="refbox" style="margin-top:16px"><label class="field"><span id="editNarrationLabel">上传配音</span><input id="editNarration" type="file" accept="audio/*,.mp3,.wav,.m4a,.aac,.flac" required><small id="editNarrationDuration" aria-live="polite"></small></label><p class="small muted" id="editAudioHint">画面使用当前账号素材库。</p></div>
  <div id="editBackgroundMusic" class="refbox" style="margin-top:12px"><label class="field"><span id="editMusicLabel">本批背景音乐（可选）</span><select name="history_music_id" aria-label="音乐历史"><option value="">从历史选择音乐</option>${(w.background_music_history||[]).map(m=>`<option value="${esc(m.id)}">${esc(m.name)} · ${m.duration.toFixed(2)} 秒</option>`).join('')}</select><input id="editMusic" type="file" accept="audio/*,.mp3,.wav,.m4a,.aac,.flac"><small id="editMusicDuration" aria-live="polite"></small></label><label id="editMusicVolume" class="field"><span>音乐音量（%）</span><input type="number" name="music_volume" min="0" max="100" value="15"></label><p id="editBatchMusicSummary" class="small muted" aria-live="polite"></p><p id="editBackgroundHint" class="small muted">音乐从每条视频的配音段开头播放，按各自时长裁切，播完后不循环。</p></div>
  ${referenceMode?`<label class="field"><span>参考视频（任意画幅，最多 120 秒）</span><input id="editReference" type="file" accept=".mp4,.mov,.mkv,.webm" required></label><p class="small muted">按参考片的主体、动作和节奏匹配素材库镜头。可只传参考片做无配音预览。</p>`:''}<div id="editScripts"><label class="field"><span>整段配音文案（可选）</span><textarea name="script_0" placeholder="粘贴与配音对应的整段文案，无需提供字幕文件"></textarea></label></div>
  <label class="field"><span>使用哪一种素材识别结果？</span><select name="analysis_mode"><option value="simple" ${P().analysis_mode==='simple'?'selected':''}>简单展示结果</option><option value="standard" ${P().analysis_mode!=='simple'?'selected':''}>明确标准结果（含旧版记录）</option></select></label><label class="field"><span>剪辑匹配方式</span><select name="matching_mode"><option value="duration">时长匹配 · 按断句长度选素材（不调用模型）</option>${P()?.sentence_editing_only?'':`<option value="semantic">语义匹配 · 按文案意思选画面（调用模型）</option>`}</select></label><label class="field" id="editSemanticRequest"><span>本批通用剪辑要求（可选）</span><textarea name="request" placeholder="第一镜必须用四把光剑旋转&#10;最后一镜优先用带货指引"></textarea><small>按时长选片时，用素材类别名称指定第几镜、最后一镜或时间码。多条要求用换行或分号分隔。<br><strong>必须</strong>：第一镜必须用四把光剑旋转，只接受这个标签。最后一镜必须用四把光剑旋转+旋转到停下，先找恰好带这两个标签的素材。素材不足时，可用只带其中一个标签的素材补上。<br><strong>优先</strong>：最后一镜优先用带货指引。找不到合适镜头时可以换别的类别。<br><strong>排除</strong>：第三镜必须用单把光剑旋转，排除静止到旋转。</small></label>
  ${referenceMode?'':'<label class="field" id="editTargetDuration"><span>成片时长</span><select name="length_mode"><option value="voice">跟随配音</option><option value="music">跟随背景音乐</option><option value="custom">自定义秒数</option></select><input name="target_duration" aria-label="自定义成片秒数" placeholder="自定义秒数" type="number" min="0.1" max="600" step="0.001"></label>'}
  <label class="field" id="editVariantField"><span>候选数量</span><select name="variant_count"><option value="1">1 条</option><option value="5">5 条</option><option value="10">10 条</option><option value="15">15 条</option></select><small>多条候选沿用同一要求，先生成预览供你选择。只统计正式导出的素材引用。</small></label>
  <label class="field"><span>输出方式</span><select name="mode"><option value="preview">先预览再确认成片</option><option value="direct">直接输出（未人工审片）</option></select></label>
  <label class="field" id="editLanguage"><span>配音语言</span><select name="language"><option value="auto">自动检测</option><option value="en">英语</option><option value="es">西班牙语</option><option value="zh">中文</option></select></label>
  ${referenceMode?'':`<label class="field" id="editRequiredCuts"><span>必切时间点（可选）</span><textarea name="required_cuts" rows="2" maxlength="2000" placeholder="00:00:04:16"></textarea><small>按成片时间填写，每行一个。格式为 时:分:秒:帧（30 fps），例如 00:00:04:16 是 4 秒 16 帧。</small></label>`}
  ${referenceMode?'':`<div id="editMusicCues" hidden><label class="check-label"><input type="checkbox" name="music_cue_assist">音乐卡点（可选）</label><small>未填必切时间点时，尝试在明显重拍或能量上升处安排少量切镜。可用镜头不合适时，按普通时长规划。</small></div>`}
  <label class="check-label"><input type="checkbox" name="keep_original_audio">保留素材库画面的原声</label>
  <label class="check-label"><input type="checkbox" name="rights_allowed" required>已确认本次所选音频和账号素材的使用范围</label>
  <details><summary>输出位置与本地语音识别设置</summary><label class="field"><span>输出父目录（留空则保存到本机账号工作区）</span><div class="inline"><input id="editOutput" name="output_path" style="flex:1"><button type="button" data-edit-folder="editOutput">选择文件夹</button></div></label><label class="field" id="editAsrModel"><span>自定义模型目录（可留空，默认使用内置模型）</span><input name="model_path" id="editModel"><button type="button" data-edit-folder="editModel">选择模型文件夹</button></label><p class="small muted" id="editAsrHint">时间来自实际音频识别，整段文案用于核对和选片，不按文字长度猜时间。${state.editing_capabilities?.local_asr?.ready?'本地识别已就绪，自动获取时间轴。':'本地识别环境准备中；不要求上传字幕文件。'}</p></details>
  <div id="editPlanConsent" hidden><label class="check-label"><input type="checkbox" name="allow_paid">允许本次使用 ${esc(state.capabilities?.config?.model||'已配置模型')} 规划镜头，使用模型额度</label></div><p id="editUploadProgress" class="small muted" role="status"></p><button id="editCreateSubmit" class="primary">上传并开始剪辑</button></form>`);
  for(const id of ['editNarration','editMusic']){
    const input=$('#'+id), status=$('#'+id+'Duration');
    input.addEventListener('change',()=>{
      const file=input.files[0];
      status.textContent=file?'正在读取音频时长…':'';
      if(!file)return;
      const media=document.createElement('audio'), url=URL.createObjectURL(file);
      const done=text=>{
        URL.revokeObjectURL(url);
        if(input.files[0]===file)status.textContent=text;
      };
      media.onloadedmetadata=()=>done(Number.isFinite(media.duration)?'音频时长 '+media.duration.toFixed(2)+' 秒':'提交后检测音频时长');
      media.onerror=()=>done('提交后检测音频时长');
      media.preload='metadata';
      media.src=url;
    });
  }
  const form=$('#editCreate'),progress=$('#editUploadProgress');
  const musicHistory=$('[name="history_music_id"]'), musicInput=$('#editMusic');
  const lengthMode=referenceMode?null:$('[name="length_mode"]'),seconds=referenceMode?null:$('[name="target_duration"]');
  const resetInspectors=[];
  function clearInspections(){for(const reset of resetInspectors)reset()}
  function upload(file,kind){
    if(!uploaded.has(kind))uploaded.set(kind,new WeakMap());
    const files=uploaded.get(kind);
    if(!files.has(file)){
      progress.textContent='正在上传并检查：'+file.name;
      files.set(file,editUploadFile(file,kind,workspace).catch(error=>{files.delete(file);throw error}));
    }
    return files.get(file);
  }
  async function backgroundId(file,historyId){
    return file?(await upload(file,'music')).id:historyId;
  }
  function lengthSettings(f){
    if(!lengthMode||lengthMode.disabled)return {};
    if(f.get('length_mode')==='music')return {follow_music:true};
    if(f.get('length_mode')==='custom')return {target_duration:Number(f.get('target_duration'))};
    return {};
  }
  const musicLibrary=w.background_music_history||[];
  function updateBatchMusic(){
    const selectedMusic=musicInput.files?.[0]||musicLibrary.find(item=>item.id===musicHistory.value);
    const musicOnly=audioKind?.value==='music';
    musicInput.required=musicOnly&&!musicHistory.value;
    $('#editBatchMusicSummary').hidden=musicOnly;
    const count=usesHistory()?selected.size:0;
    const summary=$('#editBatchMusicSummary');
    summary.textContent=count>1
      ? `已选 ${count} 条配音，将生成 ${count} 条视频。${selectedMusic?`整批共用「${selectedMusic.name}」及设定的音量。`:'选一次背景音乐即可应用到整批，留空则整批无背景音乐。'}`
      : selectedMusic?`已选背景音乐「${selectedMusic.name}」。`:'选择一首背景音乐，应用于本次生成的视频。';
  }
  musicHistory.addEventListener('change',()=>{
    clearInspections();
    if(musicHistory.value){
      musicInput.value='';
      $('#editMusicDuration').textContent='';
    }
    updateBatchMusic();
  });
  musicInput.addEventListener('change',()=>{
    clearInspections();
    if(musicInput.files.length)musicHistory.value='';
    updateBatchMusic();
  });
  const audioKind=$('#editAudioKind'), narrator=$('#editNarration');
  const matching=$('[name="matching_mode"]'), mode=$('[name="mode"]');
  const paidConsent=$('[name="allow_paid"]'),variants=$('[name="variant_count"]');
  const generatedPicker=referenceMode?null:$('#editGeneratedNarrations');
  const commonRequest=$('[name="request"]');
  const individualEditors=Array.from(generatedPicker?.querySelectorAll('[data-individual-editor]')||[]);
  const narrationSource=referenceMode?null:$('#editNarrationSource');
  if(narrationSource)narrationSource.value='elevenlabs';
  const usesHistory=()=>audioKind?.value!=='music'&&narrationSource?.value==='elevenlabs';
  $('#openNarrationHistory')?.addEventListener('click',()=>{
    $('#dialog').close();
    location.hash='narration';
    render();
  });
  function updateExecution(){
    const hasGenerated=usesHistory();
    if(generatedPicker){
      generatedPicker.hidden=!hasGenerated;
      $('#editNarrationCount').textContent=selected.size?`（已选 ${selected.size} 条）`:'';
    }
    for(const editor of individualEditors)
      editor.querySelector('[data-check-individual]').hidden=matching.value==='semantic';
    $('#editCreateSubmit').disabled=hasGenerated&&selected.size===0;
    narrator.disabled=hasGenerated||audioKind?.value==='music';
    narrator.required=!referenceMode&&!narrator.disabled;
    $('#editNarrationUpload').hidden=narrator.disabled;
    $('#editScripts').hidden=audioKind?.value==='music'||hasGenerated;
    variants.disabled=hasGenerated&&selected.size>1;
    if(variants.disabled)variants.value='1';
    $('#editVariantField').hidden=variants.disabled;
    updateBatchMusic();
    if(!referenceMode){
      lengthMode.disabled=variants.disabled||matching.value==='semantic';
      $('#editTargetDuration').hidden=lengthMode.disabled;
      seconds.disabled=lengthMode.disabled||lengthMode.value!=='custom';
      seconds.hidden=seconds.disabled;
      seconds.required=!seconds.disabled;
      $('#editRequiredCuts').hidden=variants.disabled;
    }
    const multiple=Number(variants.value)>1;
    if(mode.options)mode.options[1].disabled=referenceMode||multiple;
    if(multiple)mode.value='preview';
    const paid=matching.value==='semantic';
    $('#editPlanConsent').hidden=!paid;
    paidConsent.required=paid;
    paidConsent.disabled=!paid;
    if(!paid)paidConsent.checked=false;
    $('#editCreateSubmit').textContent=mode.value==='direct'
      ?(hasGenerated||audioKind?.value==='music'?'直接输出':'上传并直接输出')
      :(hasGenerated||audioKind?.value==='music'?'生成预览':'上传并生成预览');
    if(variants.disabled)$('#editCreateSubmit').textContent=mode.value==='direct'?`输出 ${selected.size} 条视频`:`生成 ${selected.size} 条预览`;
    if(hasGenerated)$('#editUploadProgress').textContent=selected.size?'已带入所选配音及文案。':generated.length?'请至少选择一条配音。':'';
  }
  mode.onchange=variants.onchange=updateExecution;
  matching.onchange=()=>{clearInspections();updateExecution()};
  if(lengthMode)lengthMode.onchange=()=>{clearInspections();updateExecution()};
  if(seconds)seconds.oninput=clearInspections;
  commonRequest.oninput=clearInspections;
  function audioSettings(){
    clearInspections();
    const music=audioKind?.value==='music';
    if(narrationSource)$('#editNarrationSourceField').hidden=music;
    $('#editNarrationLabel').textContent=music?'上传音乐（必选）':referenceMode?'上传自己的配音（可选）':'上传配音（必选）';
    $('#editAudioHint').textContent=music?'按整首音乐的实际时长规划画面，使用原音乐作为成片音轨。':'画面使用当前账号素材库。';
    const cueBox=$('#editMusicCues'), cuts=$('[name="required_cuts"]');
    if(cueBox&&cuts){
      const showCues=()=>{cueBox.hidden=!music||Boolean(cuts.value?.trim())};
      cuts.oninput=showCues;showCues();
    }
    $('#editMusicLabel').textContent=music?'主音乐（从历史选择或上传）':'本批背景音乐（可选）';
    $('#editMusicVolume').hidden=music;
    $('#editBackgroundHint').hidden=music;
    if(lengthMode?.options){
      lengthMode.options[0].textContent=music?'跟随整首音乐':'跟随配音';
      lengthMode.options[1].hidden=lengthMode.options[1].disabled=music;
    }
    for(const id of ['editLanguage','editAsrModel','editAsrHint'])$('#'+id).hidden=music;
    if(referenceMode){matching.value='semantic';mode.value='preview'}
    if(music)matching.value='duration';
    if(matching.options){matching.options[0].disabled=referenceMode;if(matching.options[1])matching.options[1].disabled=music}
    if(mode.options)mode.options[1].disabled=referenceMode;
    $('#editUploadProgress').textContent=referenceMode?'上传后自动匹配参考镜头并生成预览。':music?'从音乐开头按所选时长剪辑。':'按配音时间轴选片。';
    updateExecution();
  }
  if(audioKind)audioKind.onchange=()=>{narrator.value='';lengthMode.value='voice';audioSettings()};
  if(narrationSource)narrationSource.onchange=audioSettings;
  if(generated.length)bindNarrationSearch($('#editNarrationSearch'),generatedPicker.querySelectorAll('[data-narration-search]'),$('#editNarrationSearchEmpty'));
  generatedPicker?.querySelectorAll('[name="generated_narrations"]').forEach(input=>input.onchange=()=>{
    if(input.checked)selected.add(input.value);
    else selected.delete(input.value);
    input.closest('[data-narration-search]').querySelector('[data-individual-editor]').hidden=!input.checked;
    audioSettings();
  });
  for(const editor of individualEditors){
    const field=editor.querySelector('textarea'), result=editor.querySelector('[data-individual-result]');
    const button=editor.querySelector('[data-check-individual]');
    let revision=0;
    const reset=()=>{revision++;result.textContent='';button.disabled=false};
    resetInspectors.push(reset);
    field.oninput=()=>{
      editor.querySelector('[data-individual-filled]').textContent=field.value.trim()?'· 已填写':'';
      reset();
    };
    button.onclick=async()=>{
      const request=field.value, common=commonRequest.value;
      const id=editor.parentElement.querySelector('input[type="checkbox"]').value;
      const check=++revision,f=new FormData(form),length=lengthSettings(f);
      button.disabled=true;
      result.textContent='正在检查…';
      try{
        const body={id,request,common,...length};
        if(length.follow_music||'target_duration' in length)
          body.music_id=await backgroundId(musicInput.files[0],f.get('history_music_id'));
        if(check!==revision)return;
        const response=await api(`${workspace}/editing/narration-request/inspect`,'POST',body);
        if(check!==revision)return;
        result.textContent=response.requirements.length
          ? '已识别 '+response.requirements.length+' 条（含通用要求） · '+response.requirements.map(rule=>`${rule.text} → ${rule.labels.join('＋')}${rule.excluded.length?'（排除 '+rule.excluded.join('、')+'）':''}`).join(' / ')
          : '本条将按产品总纲自动选片。';
      }catch(error){if(check===revision)result.textContent=error.message;}
      finally{if(check===revision)button.disabled=false;}
    };
  }
  audioSettings();
  document.querySelectorAll('[data-edit-folder]').forEach(b=>b.onclick=async()=>{try{const input=$('#'+b.dataset.editFolder);const r=await api('/api/choose-folder','POST',{initial:input.value});if(r.path)input.value=r.path}catch(e){toast(e.message)}});
  form.onsubmit=e=>{e.preventDefault();const f=new FormData(form),file=narrator.files[0],musicOnly=audioKind?.value==='music',music=musicInput.files[0];
    const body={auto_preview:true,variant_count:Number(f.get('variant_count')||1),mode:f.get('mode'),language:f.get('language'),request:f.get('request'),output_path:f.get('output_path'),model_path:f.get('model_path'),music_volume:Number(f.get('music_volume')),rights_allowed:f.has('rights_allowed'),keep_original_audio:f.has('keep_original_audio')};
    const history=usesHistory();
    if(history&&selected.size===0)return toast('请至少选择一条配音');
    if(history&&selected.size>100)return toast('每批最多选择 100 条配音');
    const reference=referenceMode?$('#editReference').files[0]:null;
    body.narrations=history?generated.filter(item=>selected.has(item.upload_id)).map(item=>({id:item.upload_id,script:item.script,request:f.get('request_'+item.upload_id)||''})):[];
    Object.assign(body,lengthSettings(f));
    if(!referenceMode)body.required_cuts=body.narrations.length<2?(f.get('required_cuts')||''):'';
    return action(async()=>{
      if(f.get('matching_mode')==='duration'){try{const capabilities=await api('/api/editing-modes');if(!capabilities.modes.includes('duration'))throw new Error('unsupported')}catch(e){throw new Error('时长匹配需要加载新版服务，请待当前任务结束后重启工作台')}}
      if(musicOnly){
        body.primary_music_id=await backgroundId(music,f.get('history_music_id'));
        if(!body.primary_music_id)throw new Error('请选择历史音乐或上传音乐文件');
      }else if(file&&!history){
        body.narrations.push({id:(await upload(file,'narration')).id,script:f.get('script_0')||''});
      }
      if(reference)body.reference_id=(await upload(reference,'reference')).id;
      if(!musicOnly){
        const id=await backgroundId(music,f.get('history_music_id'));
        if(id)body.music_id=id;
      }
      body.analysis_mode=f.get('analysis_mode');body.matching_mode=f.get('matching_mode');
      if(musicOnly&&!body.required_cuts.trim())body.music_cue_assist=f.has('music_cue_assist');
      const b=await api(`${workspace}/editing/batches`,'POST',body);
      if(wb()===workspace&&$('#editCreate')===form){editingBatchId=b.id;editingPage=1;$('#dialog').close();}
      await api(`${workspace}/editing/batches/${b.id}/plan`,'POST',{allow_paid:body.matching_mode==='semantic'&&f.has('allow_paid')});
    });
  };
}
function currentEditBatch(){return W()?.editing_batches?.find(b=>b.id===editingBatchId)}
function editOperation(op,taskId,extra={}){
  const batch=currentEditBatch();
  if(!batch)return;
  const runnable=batch.tasks.filter(t=>!t.source_warning);
  if((op==='resume'||op==='continue-stopped')&&!taskId){
    const stopped=op==='continue-stopped';
    extra.task_ids=runnable.filter(t=>stopped?stoppedEditStatuses.has(t.status):t.status==='needs_attention').map(t=>t.id);
    if(!extra.task_ids.length)return toast('没有符合条件的任务');
    op='resume';
  }
  const endpoint=`${wb()}/editing/batches/${batch.id}/${op}`;
  if(op==='preview'&&!taskId){extra.task_ids=runnable.filter(t=>t.plan&&!t.preview&&!closedEditStatuses.has(t.status)&&!['running','queued'].includes(t.status)).map(t=>t.id);if(!extra.task_ids.length)return toast('没有可生成预览的已规划任务')}
  if(op==='plan'&&!taskId){extra.task_ids=runnable.filter(t=>['ready','timing_ready'].includes(t.status)).map(t=>t.id);if(!extra.task_ids.length)return toast('没有等待规划的任务')}
  const go=allow_paid=>action(async()=>{await api(endpoint,'POST',{...(taskId?{task_ids:[taskId]}:{}),...extra,allow_paid});if($('#dialog').open)$('#dialog').close()});
  const targets=new Set(taskId?[taskId]:extra.task_ids);
  if(batch.rules.matching_mode!=='duration'&&batch.tasks.some(t=>targets.has(t.id)&&!t.plan&&
      (op==='plan'||op==='resume'&&(t.operation||'plan')==='plan'))){
    dialog('规划剪辑',`<p>${batch.reference?'将参考片采样图与已有镜头记录用于匹配，并用入选及备选区间的采样图复核是否同源。调用':'将配音文本、产品知识和已保存的素材分析发送给'} ${esc(state.capabilities.config.model)}，不重新发送整库视频。使用当前配置的模型额度。</p><label class="check-label"><input id="editPaid" type="checkbox">允许本次规划调用；未完整返回时不自动重试</label><button id="editGo" class="primary">开始规划${batch.rules.mode==='direct'?'并直接输出':''}</button>`);
    $('#editGo').onclick=()=>{if(!$('#editPaid').checked)return toast('请明确允许本次模型调用');go(true)};
  }else return go(false);
}
function regenerateEdit(id){
  const b=currentEditBatch();
  if(!b?.tasks.some(t=>t.id===id&&canRegenerate(t)))return;
  const launch=allowPaid=>action(async()=>{
    const result=await api(`${wb()}/editing/batches/${b.id}/regenerate`,'POST',{task_ids:[id],allow_paid:allowPaid});
    editingBatchId=result.id;editingPage=1;
    if($('#dialog').open)$('#dialog').close();
  });
  if(b.rules.matching_mode==='duration'||P()?.sentence_editing_only){launch(false);return}
  dialog('沿用要求，重新选片',`<p>沿用原输入、必切点和剪辑要求。新结果会另存，原记录可继续查看。</p>
    <label class="check-label"><input id="regeneratePaid" type="checkbox">允许本次使用 ${esc(state.capabilities.config.model)} 重新选片，使用模型额度</label>
    <button id="regenerateSubmit" class="primary">开始重新选片</button>`);
  $('#regenerateSubmit').onclick=()=>{if(!$('#regeneratePaid').checked)return toast('请允许本次模型调用');launch(true)};
}
function editReplacementPicker(panel,issues,batch,submit){
  const selected=new Map();
  const unique=batch.variant_count>1||Boolean(batch.pairing_report)||batch.rules.distinct_variant_sources||batch.rules.use_prepared_files;
  const media=new Map((W()?.assets||[]).map(asset=>[asset.id,asset.media_url]));
  panel.innerHTML=issues.map(issue=>`<fieldset class="refbox"><legend>第 ${issue.index+1} 镜 · 替换 ${esc(issue.name)}</legend>
    <label class="field">搜索备选素材<input type="search" placeholder="文件名、编号或类别"></label>
    <label class="field">备选素材<select></select></label><span class="small muted" data-count></span>
    <div data-player></div></fieldset>`).join('')+'<button class="primary" type="button" data-submit disabled></button><p data-result role="status"></p>';
  const fields=Array.from(panel.querySelectorAll('fieldset'));
  const button=panel.querySelector('[data-submit]'),result=panel.querySelector('[data-result]');
  function redrawField(field,i){
      const query=field.querySelector('input').value.trim().toLowerCase();
      const select=field.querySelector('select'),current=selected.get(i);
      const rows=issues[i].options.map((part,index)=>({part,index})).filter(({part})=>{
        if(part===current)return true;
        if(![part.source_name,...(part.labels||[])].join(' ').toLowerCase().includes(query))return false;
        return !Array.from(selected.entries()).some(([other,chosen])=>other!==i&&part.asset_sha256===chosen.asset_sha256&&
          (unique||Math.min(part.start+part.frames/30,chosen.start+chosen.frames/30)>Math.max(part.start,chosen.start)+1e-6));
      });
      select.innerHTML='<option value="">请选择素材</option>'+rows.map(({part,index})=>`<option value="${index}">${esc(part.source_name)} · ${part.start.toFixed(2)}–${(part.start+part.frames/30).toFixed(2)} 秒 ${esc((part.labels||[]).join('、'))}</option>`).join('');
      select.value=current?String(issues[i].options.indexOf(current)):'';
      field.querySelector('[data-count]').textContent=rows.length?`可选 ${rows.length} 个区间`:'没有匹配的备选，请调整搜索词或其他镜头的选择';
  }
  function redraw(){
    fields.forEach(redrawField);
    button.disabled=selected.size!==issues.length;
    button.textContent=`替换并重新生成预览（${selected.size}/${issues.length}）`;
  }
  fields.forEach((field,i)=>{
    field.querySelector('input').oninput=()=>redrawField(field,i);
    field.querySelector('select').onchange=event=>{
      const value=event.target.value,part=value===''?null:issues[i].options[Number(value)];
      const player=field.querySelector('[data-player]');player.replaceChildren();
      if(part){
        selected.set(i,part);
        const url=media.get(part.asset_id);
        if(url)player.innerHTML=`<video class="preview-video" aria-label="第 ${issues[i].index+1} 镜备选片段" controls playsinline preload="metadata" src="${esc(url)}#t=${part.start},${part.start+part.frames/30}"></video>`;
      }else selected.delete(i);
      result.textContent='';
      redraw();
    };
  });
  button.onclick=async()=>{
    button.disabled=true;
    fields.forEach(field=>field.disabled=true);
    button.textContent='正在提交替换…';
    try{
      const changes={};
      for(const [i,part] of selected)changes[issues[i].index]=[part.shot_id,part.asset_sha256,part.start];
      await submit(changes);
    }catch(error){result.textContent=error.message}
    finally{fields.forEach(field=>field.disabled=false);redraw()}
  };
  redraw();
}
async function inspectEditPreview(batch,task,panel,finalButton,workspace){
  const wasDisabled=finalButton?.disabled;
  if(finalButton)finalButton.disabled=true;
  const endpoint=workspace+'/editing/batches/'+batch.id+'/';
  function reselect(){
    if(!canRegenerate(task))return;
    panel.insertAdjacentHTML('beforeend','<button type="button" data-reselect>沿用要求，重新选片</button>');
    panel.querySelector('[data-reselect]').onclick=()=>regenerateEdit(task.id);
  }
  async function check(showOptions){
    try{await loadOptions(showOptions)}catch(error){
      panel.textContent='检查未完成：'+error.message+' ';
      panel.insertAdjacentHTML('beforeend','<button type="button">重新检查</button>');
      panel.querySelector('button').onclick=()=>check(showOptions);
    }
  }
  async function loadOptions(showOptions){
    panel.textContent=showOptions?'正在查找等长备选镜头…':'正在检查输入文件、素材版本和引用次数…';
    const report=await api(endpoint+(showOptions?'replacement-options':'preview-check'),'POST',{task_id:task.id});
    if(!panel.isConnected)return;
    const blocked=report.fixed.length||report.issues.length;
    if(finalButton)finalButton.disabled=wasDisabled||Boolean(blocked);
    if(!blocked){panel.textContent='输入文件与素材引用检查通过';return}
    panel.innerHTML=report.fixed.map(message=>`<p class="warning">${esc(message)}</p>`).join('')+
      report.issues.map(issue=>`<p class="warning">第 ${issue.index+1} 镜 · ${esc(issue.name)} · ${esc(issue.reason)}</p>`).join('');
    if(report.fixed.length||!report.issues.length)return;
    if(!report.issues.every(issue=>issue.replaceable)){
      panel.insertAdjacentHTML('beforeend','<p>镜头时长需要重新规划。</p>');reselect();return
    }
    if(!showOptions){
      panel.insertAdjacentHTML('beforeend','<button type="button">仅替换有问题的镜头</button>');
      panel.querySelector('button').onclick=()=>check(true);
      return;
    }
    if(report.issues.some(issue=>!issue.options.length)){
      panel.insertAdjacentHTML('beforeend',`<p>第 ${report.issues.filter(issue=>!issue.options.length).map(issue=>issue.index+1).join('、')} 镜缺少等长备选。</p>`);reselect();return
    }
    editReplacementPicker(panel,report.issues,batch,async changes=>{
      await api(endpoint+'repair-shots','POST',{task_ids:[task.id],plan_revision:task.plan_revision,changes});
      if(panel.isConnected&&$('#dialog').open)$('#dialog').close();
      toast('已提交换镜，可在原记录查看新预览的生成进度');
      await refresh();
    });
  }
  await check(false);
}
function editTaskDialog(id){
  const b=currentEditBatch(),t=b.tasks.find(t=>t.id===id);if(!t)return;
  const busy=['queued','running'].includes(t.status),off=closedEditStatuses.has(t.status);
  const ready=['ready','timing_ready'].includes(t.status),canContinue=stoppedEditStatuses.has(t.status)||t.status==='needs_attention';
  dialog(t.name,`<div style="max-height:72vh;overflow:auto"><p>${badge(editStatusLabel(t))} ${t.source_warning?'':esc(t.stage)}</p>${t.source_warning||t.error?`<p class="error">${esc(t.source_warning||t.error)}</p>`:''}
  <p class="small file-path">${b.rules.reference_only?'参考片（无配音）':b.rules.audio_kind==='music'?'音乐':'配音'}：${esc(t.name)}${t.intro?`<br>原批次前段：${esc(t.intro)}`:''}</p>${t.individual_request?`<details open><summary>单条补充要求</summary><p class="result-note">${esc(t.individual_request)}</p></details>`:''}${t.script?`<details><summary>用户提供的整段文案</summary><p class="result-note">${esc(t.script)}</p></details>`:''}
  ${t.output||t.preview?`<video class="preview-video" controls playsinline preload="metadata" src="${esc((t.output||t.preview).media_url)}"></video>${t.output?`<p>${editDownloadLink(t.output)} · ${t.human_reviewed?'已确认预览':'未人工审片'}</p>`:''}`:''}
  ${t.script_check&&!t.script_check.matched?'<p class="warning">整段文案与音频识别文字存在差异，请核对下方时间轴。</p>':''}${t.timeline?`<details><summary>音频时间轴（${t.timeline.segments.length}段，来源 ${esc(t.timeline.source)}）</summary>${t.timeline.segments.map(s=>`<p class="small">${s.start.toFixed(2)}–${s.end.toFixed(2)} · ${esc(s.text)}</p>`).join('')}</details>`:''}
  ${!busy&&!off&&(t.plan||t.status==='needs_attention')?'<div id="editPreviewCheck" aria-live="polite"></div>':''}
  ${b.reference?'<button id="inspectReference">查看逐镜诊断与纠错</button>':''}
  ${referenceMatchPanel(b,t,busy||off)}
  ${t.reference_analysis?`<details><summary>参考视频结构（采样初审，非精确切点）</summary>${t.reference_analysis.beats.map(x=>`<p>${x.start}–${x.end}秒 · ${esc(x.purpose)} · ${esc(x.action)} · ${esc(x.composition)}</p>${x.must_see?`<p>必须看见 · ${esc(x.must_see.join('；'))}</p>${x.flexible?.length?`<p>允许变化 · ${esc(x.flexible.join('；'))}</p>`:''}`:''}`).join('')}</details>`:''}${t.plan?`<details><summary>剪辑清单（${t.plan.parts.length}段）</summary>${t.plan.parts.map(p=>`<p class="small">${p.timeline_start.toFixed(2)}–${p.timeline_end.toFixed(2)} · ${esc(p.reason)}</p>`).join('')}<label class="field"><span>修正清单 JSON（只能使用已确认镜头与安全区间）</span><textarea id="editPlanJson" style="min-height:180px">${esc(JSON.stringify(t.plan,null,2))}</textarea></label><button id="editSavePlan" ${busy||off?'disabled':''}>保存修改并重新预览</button></details>`:''}
  ${off?'':`<div class="inline" style="margin-top:16px">${t.source_warning?'':ready?'<button data-edit-op="plan">规划选片</button>':canContinue?'<button data-edit-op="resume">继续任务</button>':''}<button data-edit-op="preview" ${!t.plan||busy||t.source_warning?'disabled':''}>生成预览</button><button data-edit-op="pause" ${busy||ready?'':'disabled'}>暂停</button><button data-edit-op="cancel">取消</button></div>`}
  ${t.plan&&!off?`<div style="margin-top:16px">${t.source_warning&&!busy?'<button id="editReselect">沿用要求，重新选片</button>':b.rules.mode==='preview'?'<p class="small muted">请先播放预览，核对内容、动作完整性、配音时间轴和音画衔接。</p>':''}<button class="primary" id="editFinal" ${busy||t.source_warning||t.plan.reference_gaps?.length||b.rules.mode==='preview'&&!t.preview?'disabled':''}>${b.rules.mode==='direct'?'直接输出（未人工审片）':'已核对，确认输出'}</button></div>`:''}</div>`);
  document.querySelectorAll('[data-edit-op]').forEach(button=>button.onclick=()=>editOperation(button.dataset.editOp,id));
  $('#inspectReference')?.addEventListener('click',()=>showReferenceReview(b,t));
  bindReferenceMatchPanel(b,t,busy||off);
  $('#editSavePlan')?.addEventListener('click',()=>{try{editOperation('save-plan',id,{plan:JSON.parse($('#editPlanJson').value),plan_revision:t.plan_revision})}catch(e){toast('JSON 格式错误：'+e.message)}});
  $('#editReselect')?.addEventListener('click',()=>regenerateEdit(id));
  const preflight=$('#editPreviewCheck');
  if(preflight)inspectEditPreview(b,t,preflight,$('#editFinal'),wb());
  $('#editFinal')?.addEventListener('click',()=>{editOperation('output',id,{content_confirmed:b.rules.mode==='preview',preview_sha256:t.preview?.sha256,plan_revision:t.plan_revision})});
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
    ${task.plan.reference_gaps?.length?`<p class="warning">旧预览含空缺，请重新生成预览以衔接实拍镜头</p>${task.plan.reference_gaps.map(g=>`<p class="small">第 ${g.beat} 段 · ${(g.start_frame/30).toFixed(2)}–${((g.start_frame+g.frames)/30).toFixed(2)} 秒 · ${esc(g.reason)}</p>`).join('')}`:''}
    ${omitted.length&&!task.plan.reference_gaps?.length?`<p class="warning">本次未采用的参考分镜：${omitted.join('、')}</p>`:''}
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
