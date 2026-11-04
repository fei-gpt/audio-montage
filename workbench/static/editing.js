function activeModule(){return location.hash==='#editing'?'editing':'materials'}
function renderModuleNavigation(){
  const editing=activeModule()==='editing';
  for(const [id,selected] of [['homeNav',!editing],['editingNav',editing]]){
    const button=$('#'+id);button.classList.toggle('active',selected);
    if(selected)button.setAttribute('aria-current','page');else button.removeAttribute('aria-current');
  }
}
let editingBatchId=null,editingPage=1;
const editLabels={ready:'待规划',invalid:'输入无效',queued:'等待执行',running:'处理中',planned:'已规划',awaiting_review:'待审预览',completed:'已输出',needs_attention:'需要处理',paused:'已暂停',cancelled:'已取消',interrupted:'已中断'};
function editingRows(tasks,page){const pages=Math.max(1,Math.ceil(tasks.length/20));page=Math.max(1,Math.min(page,pages));return {page,pages,rows:tasks.slice((page-1)*20,page*20)}}
function editingHome(){
  const p=P();if(p)wid=defaultWorkspace(p,wid,accountPreferences);const w=W(),batches=w?.editing_batches||[];
  if(!batches.some(b=>b.id===editingBatchId))editingBatchId=batches.at(-1)?.id||null;
  const batch=batches.find(b=>b.id===editingBatchId),data=editingRows(batch?.tasks||[],editingPage);editingPage=data.page;
  $('#crumb').textContent='视频剪辑制作'+(p?' / '+p.name:'')+(w?' / '+w.name:'');
  $('#main').innerHTML=`<div class="heading"><div><h1>视频剪辑制作</h1><div class="muted">前段完整保留 · 后段按配音匹配账号素材 · 1080×1920</div></div><button id="editRefresh">刷新</button></div>
  <section class="panel form-panel"><label class="field"><span>产品</span><select id="editProduct"><option value="">选择产品</option>${state.products.map(x=>`<option value="${x.id}" ${x.id===pid?'selected':''}>${esc(x.name)}</option>`).join('')}</select></label>${p?accountSelector():''}
  <div class="inline"><button id="editingMaterials">前往素材处理</button><button class="primary" id="newEditBatch" ${w?.assigned?'':'disabled'}>新建剪辑批次</button></div><p class="small muted">复用已保存的产品知识与素材分析。仅使用当前账号已确认的有效区间；即梦和 ElevenLabs 不参与本版流程。</p></section>
  ${w?`<section class="panel recent"><div class="section-heading"><h2>剪辑任务</h2>${batches.length?`<select id="editBatch" aria-label="选择剪辑批次">${batches.map(b=>`<option value="${b.id}" ${b.id===editingBatchId?'selected':''}>${esc(b.created_at)} · ${b.tasks.length} 条</option>`).join('')}</select>`:''}</div>${batch?`<p class="file-path">输入：${esc(batch.input_path)}<br>输出：${esc(batch.output_path)}</p><p>${badge(batch.rules.mode==='direct'?'直接输出，未人工审片':'先预览再确认')} ${badge('批内不重复区间')}</p><div class="inline"><button data-edit-batch-action="plan">规划本批任务</button><button data-edit-batch-action="preview">预览本批已规划任务</button><button data-edit-batch-action="pause">暂停本批</button><button data-edit-batch-action="cancel">取消本批</button></div>
  <div class="asset-table-wrap" style="margin-top:16px;max-height:650px"><table class="asset-table"><thead><tr><th>配对名称</th><th>后段配音</th><th>状态 / 进度</th><th>操作</th></tr></thead><tbody>${data.rows.map(t=>`<tr><td>${esc(t.name)}</td><td>${t.audio_duration?.toFixed(2)||'—'} 秒</td><td>${badge(editLabels[t.status]||t.status)}<div class="small muted">${esc(t.error||t.stage)}</div></td><td><button data-edit-detail="${t.id}">查看 / 操作</button></td></tr>`).join('')}</tbody></table></div><div class="inline" style="justify-content:flex-end;margin-top:12px"><span>共 ${batch.tasks.length} 条 · 每页20条</span><button id="editPrev" ${data.page===1?'disabled':''}>上一页</button><span>${data.page} / ${data.pages}</span><button id="editNext" ${data.page===data.pages?'disabled':''}>下一页</button></div>`:'<p class="muted">还没有剪辑批次。先选择输入文件夹，检查同名 MP4＋MP3 配对。</p>'}</section>`:''}`;
  $('#editProduct').onchange=e=>{pid=e.target.value||null;wid=null;editingBatchId=null;render()};
  if(p)bindAccounts();$('#editRefresh').onclick=()=>refresh();
  $('#editingMaterials').onclick=()=>{location.hash='materials';if(pid)step=3;render()};
  $('#newEditBatch').onclick=editBatchDialog;
  $('#editBatch')?.addEventListener('change',e=>{editingBatchId=e.target.value;editingPage=1;render()});
  $('#editPrev')?.addEventListener('click',()=>{editingPage--;render()});$('#editNext')?.addEventListener('click',()=>{editingPage++;render()});
  document.querySelectorAll('[data-edit-detail]').forEach(b=>b.onclick=()=>editTaskDialog(b.dataset.editDetail));
  document.querySelectorAll('[data-edit-batch-action]').forEach(b=>b.onclick=()=>editOperation(b.dataset.editBatchAction));
}
function editBatchDialog(){
  dialog('新建剪辑批次',`<form id="editCreate"><label class="field"><span>本次输入文件夹（当前层同名 MP4＋MP3）</span><div class="inline"><input id="editInput" name="input_path" required style="flex:1"><button type="button" data-edit-folder="editInput">选择文件夹</button></div></label>
  <label class="field"><span>输出父文件夹（留空则在输入目录下新建）</span><div class="inline"><input id="editOutput" name="output_path" style="flex:1"><button type="button" data-edit-folder="editOutput">选择文件夹</button></div></label>
  <label class="field"><span>输出方式</span><select name="mode"><option value="preview">先预览再确认成片</option><option value="direct">直接批量输出（未人工审片）</option></select></label>
  <label class="field"><span>配音语言</span><select name="language"><option value="auto">自动检测</option><option value="en">英语</option><option value="es">西班牙语</option><option value="zh">中文</option></select></label>
  <label class="field"><span>剪辑要求</span><textarea name="request" placeholder="例如：先展示握持动作，再展示灯效；不使用包装画面"></textarea></label>
  <label class="check-label"><input type="checkbox" name="keep_original_audio">保留后段素材原声（前段始终保留原声）</label>
  <label class="check-label"><input type="checkbox" name="rights_allowed" required>已确认这些输入和账号素材可用于本次制作</label>
  <label class="check-label"><input type="checkbox" name="timing_confirmed">输入目录中的同名 SRT / JSON 确实对应当前 MP3</label>
  <details><summary>没有字幕时使用本地转写</summary><label class="field"><span>已有 Whisper 模型目录（不自动下载）</span><input name="model_path" id="editModel"><button type="button" data-edit-folder="editModel">选择模型文件夹</button></label></details>
  <p class="small muted">创建批次只检查文件，不调用付费 API。已有时间轴按音频指纹复用。</p><button class="primary">检查配对并创建</button></form>`);
  document.querySelectorAll('[data-edit-folder]').forEach(b=>b.onclick=async()=>{try{const input=$('#'+b.dataset.editFolder);const r=await api('/api/choose-folder','POST',{initial:input.value});if(r.path)input.value=r.path}catch(e){toast(e.message)}});
  $('#editCreate').onsubmit=e=>{e.preventDefault();const f=new FormData(e.target),body=Object.fromEntries(f);for(const k of ['rights_allowed','timing_confirmed','keep_original_audio'])body[k]=f.has(k);action(async()=>{const b=await api(`${wb()}/editing/batches`,'POST',body);editingBatchId=b.id;editingPage=1;$('#dialog').close()})};
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
  <p class="small file-path">前段：${esc(t.intro||'缺失')}<br>后段配音：${esc(t.audio||'缺失')}</p>
  ${t.output||t.preview?`<video class="preview-video" controls playsinline preload="metadata" src="${esc((t.output||t.preview).media_url)}"></video>${t.output?`<p><a href="${esc(t.output.media_url)}" download>下载成片</a> · ${t.human_reviewed?'已确认预览':'未人工审片'}</p>`:''}`:''}
  ${t.timeline?`<details><summary>配音时间轴（${t.timeline.segments.length}段，来源 ${esc(t.timeline.source)}）</summary>${t.timeline.segments.map(s=>`<p class="small">${s.start.toFixed(2)}–${s.end.toFixed(2)} · ${esc(s.text)}</p>`).join('')}</details>`:''}
  ${t.plan?`<details><summary>剪辑清单（${t.plan.parts.length}段）</summary>${t.plan.parts.map(p=>`<p class="small">${p.timeline_start.toFixed(2)}–${p.timeline_end.toFixed(2)} · ${esc(p.reason)}</p>`).join('')}<label class="field"><span>修正清单 JSON（只能使用已确认镜头与安全区间）</span><textarea id="editPlanJson" style="min-height:180px">${esc(JSON.stringify(t.plan,null,2))}</textarea></label><button id="editSavePlan" ${busy||off?'disabled':''}>保存修改并重新预览</button></details>`:''}
  <div class="inline" style="margin-top:16px"><button data-edit-op="resume" ${busy||off?'disabled':''}>${t.plan?'继续任务':'规划选片'}</button><button data-edit-op="preview" ${!t.plan||busy||off?'disabled':''}>生成预览</button><button data-edit-op="pause" ${off?'disabled':''}>暂停</button><button data-edit-op="cancel" ${off?'disabled':''}>取消</button></div>
  ${t.plan&&!off?`<div style="margin-top:16px">${b.rules.mode==='preview'?'<label class="check-label"><input id="editReviewed" type="checkbox">已实际核对当前预览的内容、完整动作、配音时间轴和音画衔接</label>':''}<button class="primary" id="editFinal" ${busy||b.rules.mode==='preview'&&!t.preview?'disabled':''}>${b.rules.mode==='direct'?'直接输出（未人工审片）':'确认并输出'}</button></div>`:''}</div>`);
  document.querySelectorAll('[data-edit-op]').forEach(button=>button.onclick=()=>editOperation(button.dataset.editOp,id));
  $('#editSavePlan')?.addEventListener('click',()=>{try{editOperation('save-plan',id,{plan:JSON.parse($('#editPlanJson').value)})}catch(e){toast('JSON 格式错误：'+e.message)}});
  $('#editFinal')?.addEventListener('click',()=>{if(b.rules.mode==='preview'&&!$('#editReviewed').checked)return toast('请先核对当前预览');editOperation('output',id,{content_confirmed:$('#editReviewed')?.checked||false,preview_sha256:t.preview?.sha256})});
}
