function activeModule(){return location.hash==='#editing'?'editing':'materials'}
function renderModuleNavigation(){
  const editing=activeModule()==='editing';
  for(const [id,selected] of [['homeNav',!editing],['editingNav',editing]]){
    const button=$('#'+id);button.classList.toggle('active',selected);
    if(selected)button.setAttribute('aria-current','page');else button.removeAttribute('aria-current');
  }
}
let editingBatchId=null,editingPage=1;
const editLabels={ready:'待规划',timing_ready:'配音时间轴已识别',invalid:'输入无效',queued:'等待执行',running:'处理中',planned:'已规划',awaiting_review:'待审预览',completed:'已输出',needs_attention:'需要处理',paused:'已暂停',cancelled:'已取消',interrupted:'已中断'};
function editingRows(tasks,page){const pages=Math.max(1,Math.ceil(tasks.length/20));page=Math.max(1,Math.min(page,pages));return {page,pages,rows:tasks.slice((page-1)*20,page*20)}}
function editingHome(){
  const p=P();if(p)wid=defaultWorkspace(p,wid,accountPreferences);const w=W(),batches=w?.editing_batches||[];
  if(!batches.some(b=>b.id===editingBatchId))editingBatchId=batches.at(-1)?.id||null;
  const batch=batches.find(b=>b.id===editingBatchId),data=editingRows(batch?.tasks||[],editingPage);editingPage=data.page;
  $('#crumb').textContent='视频剪辑制作'+(p?' / '+p.name:'')+(w?' / '+w.name:'');
  $('#main').innerHTML=`<div class="heading"><div><h1>视频剪辑制作</h1><div class="muted">已确认素材库自动复用 · 配音驱动剪辑 · 开头／结尾可选</div></div><button id="editRefresh">刷新</button></div>
  <section class="panel form-panel"><label class="field"><span>产品</span><select id="editProduct"><option value="">选择产品</option>${state.products.map(x=>`<option value="${x.id}" ${x.id===pid?'selected':''}>${esc(x.name)}</option>`).join('')}</select></label>${p?accountSelector():''}
  <div class="inline"><button id="editingMaterials">前往素材处理</button><button class="primary" id="newPairBatch" ${w?.assigned?'':'disabled'}>批量导入 MP4＋MP3 配对</button><button id="newReferenceBatch" ${w?.assigned?'':'disabled'}>参考视频匹配镜头</button><button id="newEditBatch" ${w?.assigned?'':'disabled'}>新建剪辑批次</button></div><p class="small muted">复用已保存的产品知识与素材分析。仅使用当前账号已确认的有效区间；已有文件可直接上传，也可通过下方 AI 生成链路制作。</p></section>
  ${w?`<section class="panel recent"><div class="section-heading"><h2>剪辑任务</h2>${batches.length?`<select id="editBatch" aria-label="选择剪辑批次">${batches.map(b=>`<option value="${b.id}" ${b.id===editingBatchId?'selected':''}>${esc(b.created_at)} · ${b.tasks.length} 条</option>`).join('')}</select>`:''}</div>${batch?`<p class="file-path">输入：${batch.input_mode==='uploads'?'已上传配音及可选片段':esc(batch.input_path)}<br>输出：${esc(batch.output_path)}</p><p>${badge(batch.rules.mode==='direct'?'直接输出，未人工审片':'先预览再确认')} ${badge('批内不重复区间')}</p><div class="inline"><button data-edit-batch-action="plan">规划本批任务</button><button data-edit-batch-action="preview">预览本批已规划任务</button><button data-edit-batch-action="pause">暂停本批</button><button data-edit-batch-action="cancel">取消本批</button></div>
  <div class="asset-table-wrap" style="margin-top:16px;max-height:650px"><table class="asset-table"><thead><tr><th>配音文件</th><th>配音时长</th><th>状态 / 进度</th><th>操作</th></tr></thead><tbody>${data.rows.map(t=>`<tr><td>${esc(t.name)}</td><td>${t.audio_duration?.toFixed(2)||'—'} 秒</td><td>${badge(editLabels[t.status]||t.status)}<div class="small muted">${esc(t.error||t.stage)}</div></td><td><button data-edit-detail="${t.id}">查看 / 操作</button></td></tr>`).join('')}</tbody></table></div><div class="inline" style="justify-content:flex-end;margin-top:12px"><span>共 ${batch.tasks.length} 条 · 每页20条</span><button id="editPrev" ${data.page===1?'disabled':''}>上一页</button><span>${data.page} / ${data.pages}</span><button id="editNext" ${data.page===data.pages?'disabled':''}>下一页</button></div>`:'<p class="muted">还没有剪辑批次。上传配音，按需添加背景音乐和开头／结尾片段。</p>'}</section>`:''}${w?generationSection():''}`;
  $('#editProduct').onchange=e=>{pid=e.target.value||null;wid=null;editingBatchId=null;render()};
  if(p)bindAccounts();$('#editRefresh').onclick=()=>refresh();
  $('#editingMaterials').onclick=()=>{location.hash='materials';if(pid)step=3;render()};
  $('#newEditBatch').onclick=()=>editBatchDialog();$('#newReferenceBatch').onclick=()=>editBatchDialog(true);$('#newPairBatch').onclick=editPairBatchDialog;bindGeneration();
  $('#editBatch')?.addEventListener('change',e=>{editingBatchId=e.target.value;editingPage=1;render()});
  $('#editPrev')?.addEventListener('click',()=>{editingPage--;render()});$('#editNext')?.addEventListener('click',()=>{editingPage++;render()});
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
  dialog(referenceMode?'参考视频匹配镜头':'新建剪辑任务',`<form id="editCreate"><div class="meta-box">使用 ${esc(P().name)} / ${esc(w.name)} 已确认素材库 · ${count} 个已确认镜头。无需重新上传素材。</div>
  <div class="refbox" style="margin-top:16px"><label class="field"><span id="editNarrationLabel">上传配音</span><input id="editNarration" type="file" accept="audio/*,.mp3,.wav,.m4a,.aac,.flac" multiple required></label><p class="small muted">每条配音生成一条视频，画面直接使用当前账号素材库。</p></div>
  <div class="refbox" style="margin-top:12px"><label class="field"><span>2 · 上传背景音乐（可选）</span><input id="editMusic" type="file" accept="audio/*,.mp3,.wav,.m4a,.aac,.flac"></label><label class="field"><span>音乐音量（%）</span><input type="number" name="music_volume" min="0" max="100" value="15"></label><p class="small muted">仅混入配音对应的主体部分。音乐不足时不自动循环，剩余部分继续保留配音。</p></div>
  <div class="refbox" style="margin-top:12px"><label class="field"><span>3 · 上传插入片段（可选，逐个选择开头或结尾）</span><input id="editClips" type="file" accept="video/*,.mp4,.mov,.mkv,.webm" multiple></label><div id="editClipPositions"><p class="small muted">上传后，为每个片段选择：放在开头 或 放在结尾。</p></div><p class="small muted">片头 → 素材库剪辑主体 → 片尾。同一位置的多个片段按上传顺序排列，整段保留画面、速度和原声。</p></div>
  <label class="field"><span>参考视频（竖屏 9:16，最多 120 秒）</span><input id="editReference" type="file" accept=".mp4,.mov,.mkv,.webm"></label><p id="referenceHint" class="small muted" hidden>从当前账号选择其他实拍镜头，排除参考原片及检测到的相同片段。可只传参考片做无配音预览。</p><div id="editScripts"><label class="field"><span>整段配音文案（可选）</span><textarea name="script_0" placeholder="粘贴与配音对应的整段文案，无需提供字幕文件"></textarea></label></div>
  <label class="field"><span>使用哪一种素材识别结果？</span><select name="analysis_mode"><option value="simple" ${P().analysis_mode==='simple'?'selected':''}>简单展示结果</option><option value="standard" ${P().analysis_mode!=='simple'?'selected':''}>明确标准结果（含旧版记录）</option></select></label><label class="field"><span>剪辑匹配方式</span><select name="matching_mode"><option value="duration">时长匹配 · 按断句长度选素材（不调用模型）</option><option value="semantic">语义匹配 · 按文案意思选画面（调用模型）</option></select></label><label class="field"><span>剪辑要求（语义模式使用）</span><textarea name="request" placeholder="例如：先展示握持动作，再展示灯效；不使用包装画面"></textarea></label>
  <label class="field"><span>输出方式</span><select name="mode"><option value="preview">先预览再确认成片</option><option value="direct">直接批量输出（未人工审片）</option></select></label>
  <label class="field"><span>配音语言</span><select name="language"><option value="auto">自动检测</option><option value="en">英语</option><option value="es">西班牙语</option><option value="zh">中文</option></select></label>
  <label class="check-label"><input type="checkbox" name="keep_original_audio">保留素材库画面的原声（开头／结尾片段始终保留原声）</label>
  <label class="check-label"><input type="checkbox" name="rights_allowed" required>已确认本次上传文件和账号素材的使用范围</label>
  <details><summary>输出位置与本地语音识别设置</summary><label class="field"><span>输出父目录（留空则保存到本机账号工作区）</span><div class="inline"><input id="editOutput" name="output_path" style="flex:1"><button type="button" data-edit-folder="editOutput">选择文件夹</button></div></label><label class="field"><span>自定义模型目录（可留空，默认使用内置模型）</span><input name="model_path" id="editModel"><button type="button" data-edit-folder="editModel">选择模型文件夹</button></label><p class="small muted">时间来自实际音频识别，整段文案用于核对和选片，不按文字长度猜时间。${state.editing_capabilities?.local_asr?.ready?'本地识别已就绪，自动获取时间轴。':'本地识别环境准备中；不要求上传字幕文件。'}</p></details>
  <p id="editUploadProgress" class="small muted" role="status">上传后自动在本机识别配音时间轴，不调用付费 API。</p><button class="primary">上传并创建剪辑任务</button></form>`);
  const referenceInput=$('#editReference'), narrator=$('#editNarration');
  function referenceSettings(){
    const active=referenceMode||Boolean(referenceInput.files?.length);
    referenceInput.required=referenceMode;
    narrator.required=!active;
    $('#editNarrationLabel').textContent=active?'上传自己的配音（可选）':'上传配音（必选）';
    $('#referenceHint').hidden=!active;
    const matching=$('[name="matching_mode"]'), mode=$('[name="mode"]');
    if(active){matching.value='semantic';mode.value='preview'}
    if(matching.options)matching.options[0].disabled=active;
    if(mode.options)mode.options[1].disabled=active;
    $('#editUploadProgress').textContent=active?'上传仅创建任务，规划时才调用 Codex 匹配镜头。':'上传后在本机识别配音时间轴。';
  }
  referenceInput.onchange=referenceSettings;
  referenceSettings();
  $('#editNarration').onchange=e=>{const files=[...e.target.files];$('#editScripts').innerHTML=files.map((file,i)=>`<label class="field"><span>${files.length>1?esc(file.name)+' · ':''}整段配音文案（可选）</span><textarea name="script_${i}" placeholder="粘贴与这条配音对应的整段文案，无需字幕文件"></textarea></label>`).join('')};
  $('#editClips').onchange=e=>{$('#editClipPositions').innerHTML=[...e.target.files].map((file,i)=>`<label class="field"><span>${esc(file.name)} · 插入位置</span><select name="clip_position_${i}" required><option value="" disabled selected>请选择放在开头还是结尾</option><option value="intro">放在开头</option><option value="outro">放在结尾</option></select></label>`).join('')};
  document.querySelectorAll('[data-edit-folder]').forEach(b=>b.onclick=async()=>{try{const input=$('#'+b.dataset.editFolder);const r=await api('/api/choose-folder','POST',{initial:input.value});if(r.path)input.value=r.path}catch(e){toast(e.message)}});
  $('#editCreate').onsubmit=e=>{e.preventDefault();const f=new FormData(e.target),files=[...$('#editNarration').files],music=$('#editMusic').files[0],clips=[...$('#editClips').files];
    const body={mode:f.get('mode'),language:f.get('language'),request:f.get('request'),output_path:f.get('output_path'),model_path:f.get('model_path'),music_volume:Number(f.get('music_volume')),rights_allowed:f.has('rights_allowed'),keep_original_audio:f.has('keep_original_audio')};
    action(async()=>{if(f.get('matching_mode')==='duration'){try{const capabilities=await api('/api/editing-modes');if(!capabilities.modes.includes('duration'))throw new Error('unsupported')}catch(e){throw new Error('时长匹配需要加载新版服务，请待当前任务结束后重启工作台')}}async function upload(file,kind){const key=JSON.stringify([kind,file.name,file.size,file.lastModified]);if(!uploaded.has(key)){ $('#editUploadProgress').textContent='正在上传并检查：'+file.name;uploaded.set(key,await editUploadFile(file,kind))}return uploaded.get(key)}
      body.narrations=[];for(const [i,file] of files.entries()){const u=await upload(file,'narration');body.narrations.push({id:u.id,script:f.get('script_'+i)||''})}
      const reference=$('#editReference').files[0];if(reference){if(f.get('matching_mode')!=='semantic'||f.get('mode')!=='preview')throw Error('参考混剪请选择语义匹配和先预览再确认');body.reference_id=(await upload(reference,'reference')).id;}
      if(music)body.music_id=(await upload(music,'music')).id;
      body.analysis_mode=f.get('analysis_mode');body.matching_mode=f.get('matching_mode');body.clips=[];for(const [i,file] of clips.entries()){const u=await upload(file,'clip');body.clips.push({id:u.id,position:f.get('clip_position_'+i)})}
      const b=await api(`${wb()}/editing/batches`,'POST',body);editingBatchId=b.id;editingPage=1;$('#dialog').close();if(files.length)await api(`${wb()}/editing/batches/${b.id}/timing`,'POST',{});
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
function editTaskDialog(id){
  const b=currentEditBatch(),t=b.tasks.find(t=>t.id===id);if(!t)return;
  const busy=['queued','running'].includes(t.status),off=['invalid','cancelled','completed'].includes(t.status);
  dialog(t.name,`<div style="max-height:72vh;overflow:auto"><p>${badge(editLabels[t.status])} ${esc(t.stage)}</p>${t.error?`<p class="error">${esc(t.error)}</p>`:''}
  <p class="small file-path">${b.rules.reference_only?'参考片（无配音）':'配音'}：${esc(t.name)}${t.intro?`<br>原批次前段：${esc(t.intro)}`:''}</p>${t.script?`<details><summary>用户提供的整段文案</summary><p class="result-note">${esc(t.script)}</p></details>`:''}
  ${t.output||t.preview?`<video class="preview-video" controls playsinline preload="metadata" src="${esc((t.output||t.preview).media_url)}"></video>${t.output?`<p><a href="${esc(t.output.media_url)}" download>下载成片</a> · ${t.human_reviewed?'已确认预览':'未人工审片'}</p>`:''}`:''}
  ${t.script_check&&!t.script_check.matched?'<p class="warning">整段文案与音频识别文字存在差异，请核对下方时间轴。</p>':''}${t.timeline?`<details><summary>配音时间轴（${t.timeline.segments.length}段，来源 ${esc(t.timeline.source)}）</summary>${t.timeline.segments.map(s=>`<p class="small">${s.start.toFixed(2)}–${s.end.toFixed(2)} · ${esc(s.text)}</p>`).join('')}</details>`:''}
  ${b.reference?'<button id="inspectReference">查看逐镜诊断与纠错</button>':''}
  ${referenceMatchPanel(b,t,busy||off)}
  ${t.reference_analysis?`<details><summary>参考视频结构（采样初审，非精确切点）</summary>${t.reference_analysis.beats.map(x=>`<p>${x.start}–${x.end}秒 · ${esc(x.purpose)} · ${esc(x.action)} · ${esc(x.composition)}</p>${x.must_see?`<p>必须看见 · ${esc(x.must_see.join('；'))}</p>${x.flexible?.length?`<p>允许变化 · ${esc(x.flexible.join('；'))}</p>`:''}`:''}`).join('')}</details>`:''}${t.plan?`<details><summary>剪辑清单（${t.plan.parts.length}段）</summary>${t.plan.parts.map(p=>`<p class="small">${p.timeline_start.toFixed(2)}–${p.timeline_end.toFixed(2)} · ${esc(p.reason)}</p>`).join('')}<label class="field"><span>修正清单 JSON（只能使用已确认镜头与安全区间）</span><textarea id="editPlanJson" style="min-height:180px">${esc(JSON.stringify(t.plan,null,2))}</textarea></label><button id="editSavePlan" ${busy||off?'disabled':''}>保存修改并重新预览</button></details>`:''}
  <div class="inline" style="margin-top:16px"><button data-edit-op="${['ready','timing_ready'].includes(t.status)?'plan':'resume'}" ${busy||off?'disabled':''}>${t.plan?'继续任务':'规划选片'}</button><button data-edit-op="preview" ${!t.plan||busy||off?'disabled':''}>生成预览</button><button data-edit-op="pause" ${off?'disabled':''}>暂停</button><button data-edit-op="cancel" ${off?'disabled':''}>取消</button></div>
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
