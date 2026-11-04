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
  <div class="inline"><button id="editingMaterials">前往素材处理</button><button class="primary" id="newEditBatch" ${w?.assigned?'':'disabled'}>新建剪辑批次</button></div><p class="small muted">复用已保存的产品知识与素材分析。仅使用当前账号已确认的有效区间；已有文件可直接上传，也可通过下方 AI 生成链路制作。</p></section>
  ${w?`<section class="panel recent"><div class="section-heading"><h2>剪辑任务</h2>${batches.length?`<select id="editBatch" aria-label="选择剪辑批次">${batches.map(b=>`<option value="${b.id}" ${b.id===editingBatchId?'selected':''}>${esc(b.created_at)} · ${b.tasks.length} 条</option>`).join('')}</select>`:''}</div>${batch?`<p class="file-path">输入：${batch.input_mode==='uploads'?'已上传配音及可选片段':esc(batch.input_path)}<br>输出：${esc(batch.output_path)}</p><p>${badge(batch.rules.mode==='direct'?'直接输出，未人工审片':'先预览再确认')} ${badge('批内不重复区间')}</p><div class="inline"><button data-edit-batch-action="plan">规划本批任务</button><button data-edit-batch-action="preview">预览本批已规划任务</button><button data-edit-batch-action="pause">暂停本批</button><button data-edit-batch-action="cancel">取消本批</button></div>
  <div class="asset-table-wrap" style="margin-top:16px;max-height:650px"><table class="asset-table"><thead><tr><th>配音文件</th><th>配音时长</th><th>状态 / 进度</th><th>操作</th></tr></thead><tbody>${data.rows.map(t=>`<tr><td>${esc(t.name)}</td><td>${t.audio_duration?.toFixed(2)||'—'} 秒</td><td>${badge(editLabels[t.status]||t.status)}<div class="small muted">${esc(t.error||t.stage)}</div></td><td><button data-edit-detail="${t.id}">查看 / 操作</button></td></tr>`).join('')}</tbody></table></div><div class="inline" style="justify-content:flex-end;margin-top:12px"><span>共 ${batch.tasks.length} 条 · 每页20条</span><button id="editPrev" ${data.page===1?'disabled':''}>上一页</button><span>${data.page} / ${data.pages}</span><button id="editNext" ${data.page===data.pages?'disabled':''}>下一页</button></div>`:'<p class="muted">还没有剪辑批次。上传配音，按需添加背景音乐和开头／结尾片段。</p>'}</section>`:''}${w?generationSection():''}`;
  $('#editProduct').onchange=e=>{pid=e.target.value||null;wid=null;editingBatchId=null;render()};
  if(p)bindAccounts();$('#editRefresh').onclick=()=>refresh();
  $('#editingMaterials').onclick=()=>{location.hash='materials';if(pid)step=3;render()};
  $('#newEditBatch').onclick=editBatchDialog;bindGeneration();
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
function editBatchDialog(){
  const w=W(),count=w.shots.filter(s=>s.review_decision==='keep'&&s.human_confirmed&&!s.stale&&w.assets.some(a=>a.id===s.asset_id)).length;
  const uploaded=new Map();
  dialog('新建剪辑任务',`<form id="editCreate"><div class="meta-box">使用 ${esc(P().name)} / ${esc(w.name)} 已确认素材库 · ${count} 个已确认镜头。无需重新上传素材。</div>
  <div class="refbox" style="margin-top:16px"><label class="field"><span>1 · 上传配音（必选）</span><input id="editNarration" type="file" accept="audio/*,.mp3,.wav,.m4a,.aac,.flac" multiple required></label><p class="small muted">每条配音生成一条视频，画面直接使用当前账号素材库。</p></div>
  <div class="refbox" style="margin-top:12px"><label class="field"><span>2 · 上传背景音乐（可选）</span><input id="editMusic" type="file" accept="audio/*,.mp3,.wav,.m4a,.aac,.flac"></label><label class="field"><span>音乐音量（%）</span><input type="number" name="music_volume" min="0" max="100" value="15"></label><p class="small muted">仅混入配音对应的主体部分。音乐不足时不自动循环，剩余部分继续保留配音。</p></div>
  <div class="refbox" style="margin-top:12px"><label class="field"><span>3 · 上传开头／结尾片段（可选）</span><input id="editClips" type="file" accept="video/*,.mp4,.mov,.mkv,.webm" multiple></label><div id="editClipPositions"></div><p class="small muted">整段保留画面、速度和原声，按选择顺序接入。不传也可以制作视频。</p></div>
  <div id="editScripts"><label class="field"><span>整段配音文案（可选）</span><textarea name="script_0" placeholder="粘贴与配音对应的整段文案，无需提供字幕文件"></textarea></label></div>
  <label class="field"><span>剪辑要求</span><textarea name="request" placeholder="例如：先展示握持动作，再展示灯效；不使用包装画面"></textarea></label>
  <label class="field"><span>输出方式</span><select name="mode"><option value="preview">先预览再确认成片</option><option value="direct">直接批量输出（未人工审片）</option></select></label>
  <label class="field"><span>配音语言</span><select name="language"><option value="auto">自动检测</option><option value="en">英语</option><option value="es">西班牙语</option><option value="zh">中文</option></select></label>
  <label class="check-label"><input type="checkbox" name="keep_original_audio">保留素材库画面的原声（开头／结尾片段始终保留原声）</label>
  <label class="check-label"><input type="checkbox" name="rights_allowed" required>已确认本次上传文件和账号素材的使用范围</label>
  <details><summary>输出位置与本地语音识别设置</summary><label class="field"><span>输出父目录（留空则保存到本机账号工作区）</span><div class="inline"><input id="editOutput" name="output_path" style="flex:1"><button type="button" data-edit-folder="editOutput">选择文件夹</button></div></label><label class="field"><span>自定义模型目录（可留空，默认使用内置模型）</span><input name="model_path" id="editModel"><button type="button" data-edit-folder="editModel">选择模型文件夹</button></label><p class="small muted">时间来自实际音频识别，整段文案用于核对和选片，不按文字长度猜时间。${state.editing_capabilities?.local_asr?.ready?'本地识别已就绪，自动获取时间轴。':'本地识别环境准备中；不要求上传字幕文件。'}</p></details>
  <p id="editUploadProgress" class="small muted" role="status">上传后自动在本机识别配音时间轴，不调用付费 API。</p><button class="primary">上传并创建剪辑任务</button></form>`);
  $('#editNarration').onchange=e=>{const files=[...e.target.files];$('#editScripts').innerHTML=files.map((file,i)=>`<label class="field"><span>${files.length>1?esc(file.name)+' · ':''}整段配音文案（可选）</span><textarea name="script_${i}" placeholder="粘贴与这条配音对应的整段文案，无需字幕文件"></textarea></label>`).join('')};
  $('#editClips').onchange=e=>{$('#editClipPositions').innerHTML=[...e.target.files].map((file,i)=>`<label class="field"><span>${esc(file.name)}</span><select name="clip_position_${i}"><option value="intro">放在开头</option><option value="outro">放在结尾</option></select></label>`).join('')};
  document.querySelectorAll('[data-edit-folder]').forEach(b=>b.onclick=async()=>{try{const input=$('#'+b.dataset.editFolder);const r=await api('/api/choose-folder','POST',{initial:input.value});if(r.path)input.value=r.path}catch(e){toast(e.message)}});
  $('#editCreate').onsubmit=e=>{e.preventDefault();const f=new FormData(e.target),files=[...$('#editNarration').files],music=$('#editMusic').files[0],clips=[...$('#editClips').files];
    const body={mode:f.get('mode'),language:f.get('language'),request:f.get('request'),output_path:f.get('output_path'),model_path:f.get('model_path'),music_volume:Number(f.get('music_volume')),rights_allowed:f.has('rights_allowed'),keep_original_audio:f.has('keep_original_audio')};
    action(async()=>{async function upload(file,kind){const key=JSON.stringify([kind,file.name,file.size,file.lastModified]);if(!uploaded.has(key)){ $('#editUploadProgress').textContent='正在上传并检查：'+file.name;uploaded.set(key,await editUploadFile(file,kind))}return uploaded.get(key)}
      body.narrations=[];for(const [i,file] of files.entries()){const u=await upload(file,'narration');body.narrations.push({id:u.id,script:f.get('script_'+i)||''})}
      if(music)body.music_id=(await upload(music,'music')).id;
      body.clips=[];for(const [i,file] of clips.entries()){const u=await upload(file,'clip');body.clips.push({id:u.id,position:f.get('clip_position_'+i)})}
      const b=await api(`${wb()}/editing/batches`,'POST',body);editingBatchId=b.id;editingPage=1;$('#dialog').close();await api(`${wb()}/editing/batches/${b.id}/timing`,'POST',{});
    });
  };
}
function currentEditBatch(){return W()?.editing_batches?.find(b=>b.id===editingBatchId)}
function editOperation(op,taskId,extra={}){
  if(op==='preview'&&!taskId){extra.task_ids=currentEditBatch().tasks.filter(t=>t.plan&&!['running','queued','completed','cancelled','invalid'].includes(t.status)).map(t=>t.id);if(!extra.task_ids.length)return toast('没有可生成预览的已规划任务')}
  const go=allow_paid=>action(async()=>{await api(`${wb()}/editing/batches/${editingBatchId}/${op}`,'POST',{...(taskId?{task_ids:[taskId]}:{}),...extra,allow_paid});$('#dialog').close()});
  if(['plan','resume'].includes(op)){
    dialog('规划剪辑',`<p>将配音文本、产品知识和已保存的素材分析发送给 ${esc(state.capabilities.config.model)}，不重新发送整库视频。可能产生 API 费用。</p><label class="check-label"><input id="editPaid" type="checkbox">允许本次规划调用；未完整返回时不自动重试</label><button id="editGo" class="primary">开始规划${currentEditBatch()?.rules.mode==='direct'?'并直接输出':''}</button>`);
    $('#editGo').onclick=()=>{if(!$('#editPaid').checked)return toast('请明确允许本次模型调用');go(true)};
  }else go(false);
}
function editTaskDialog(id){
  const b=currentEditBatch(),t=b.tasks.find(t=>t.id===id);if(!t)return;
  const busy=['queued','running'].includes(t.status),off=['invalid','cancelled','completed'].includes(t.status);
  dialog(t.name,`<div style="max-height:72vh;overflow:auto"><p>${badge(editLabels[t.status])} ${esc(t.stage)}</p>${t.error?`<p class="error">${esc(t.error)}</p>`:''}
  <p class="small file-path">配音：${esc(t.name)}${t.intro?`<br>原批次前段：${esc(t.intro)}`:''}</p>${t.script?`<details><summary>用户提供的整段文案</summary><p class="result-note">${esc(t.script)}</p></details>`:''}
  ${t.output||t.preview?`<video class="preview-video" controls playsinline preload="metadata" src="${esc((t.output||t.preview).media_url)}"></video>${t.output?`<p><a href="${esc(t.output.media_url)}" download>下载成片</a> · ${t.human_reviewed?'已确认预览':'未人工审片'}</p>`:''}`:''}
  ${t.script_check&&!t.script_check.matched?'<p class="warning">整段文案与音频识别文字存在差异，请核对下方时间轴。</p>':''}${t.timeline?`<details><summary>配音时间轴（${t.timeline.segments.length}段，来源 ${esc(t.timeline.source)}）</summary>${t.timeline.segments.map(s=>`<p class="small">${s.start.toFixed(2)}–${s.end.toFixed(2)} · ${esc(s.text)}</p>`).join('')}</details>`:''}
  ${t.plan?`<details><summary>剪辑清单（${t.plan.parts.length}段）</summary>${t.plan.parts.map(p=>`<p class="small">${p.timeline_start.toFixed(2)}–${p.timeline_end.toFixed(2)} · ${esc(p.reason)}</p>`).join('')}<label class="field"><span>修正清单 JSON（只能使用已确认镜头与安全区间）</span><textarea id="editPlanJson" style="min-height:180px">${esc(JSON.stringify(t.plan,null,2))}</textarea></label><button id="editSavePlan" ${busy||off?'disabled':''}>保存修改并重新预览</button></details>`:''}
  <div class="inline" style="margin-top:16px"><button data-edit-op="${['ready','timing_ready'].includes(t.status)?'plan':'resume'}" ${busy||off?'disabled':''}>${t.plan?'继续任务':'规划选片'}</button><button data-edit-op="preview" ${!t.plan||busy||off?'disabled':''}>生成预览</button><button data-edit-op="pause" ${off?'disabled':''}>暂停</button><button data-edit-op="cancel" ${off?'disabled':''}>取消</button></div>
  ${t.plan&&!off?`<div style="margin-top:16px">${b.rules.mode==='preview'?'<label class="check-label"><input id="editReviewed" type="checkbox">已实际核对当前预览的内容、完整动作、配音时间轴和音画衔接</label>':''}<button class="primary" id="editFinal" ${busy||b.rules.mode==='preview'&&!t.preview?'disabled':''}>${b.rules.mode==='direct'?'直接输出（未人工审片）':'确认并输出'}</button></div>`:''}</div>`);
  document.querySelectorAll('[data-edit-op]').forEach(button=>button.onclick=()=>editOperation(button.dataset.editOp,id));
  $('#editSavePlan')?.addEventListener('click',()=>{try{editOperation('save-plan',id,{plan:JSON.parse($('#editPlanJson').value)})}catch(e){toast('JSON 格式错误：'+e.message)}});
  $('#editFinal')?.addEventListener('click',()=>{if(b.rules.mode==='preview'&&!$('#editReviewed').checked)return toast('请先核对当前预览');editOperation('output',id,{content_confirmed:$('#editReviewed')?.checked||false,preview_sha256:t.preview?.sha256})});
}
