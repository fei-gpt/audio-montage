const faultStages = {reference:'参考片理解',recognition:'自有素材识别',ranking:'候选检索与排序',trim:'实际裁切'};
const correctionScopes = {shot:'仅这一镜',product:'本产品',general:'通用标准建议'};

function reviewRange(start,end) {return `${Number(start).toFixed(2)}–${Number(end).toFixed(2)} 秒`}

function diagnosticRow(row,cases,revision,media) {
  const ref=row.reference, selected=new Set(row.selected.map(x=>x.shot_id));
  const candidates=row.candidates.map(c=>{
    const audit=c.audit?.verdict;
    const status=selected.has(c.shot_id)?'当前选用':audit==='possible_same'?'排除：疑似同源':audit==='uncertain'?'排除：同源依据不足':
      audit==='different_shoot'?'同源复核通过':c.recommendation?'模型推荐':c.rank?'入围，模型未列为推荐':'未记录';
    return `<li><strong>${esc(c.name||c.shot_id)}</strong> · ${c.rank?'候选第 '+esc(c.rank)+' 位 · ':''}${status}
      <p>${esc(c.facts||'缺少当时的素材事实快照')}${c.analysis_version?' · 识别版 '+esc(c.analysis_version.slice(0,8)):''}</p>
      ${c.temporal_observation?timedObservationHTML(c):''}
      ${c.recommendation?`<p>推荐依据 · ${esc(c.recommendation)}</p>`:''}
      ${c.audit?.evidence?`<p>同源复核 · ${esc(c.audit.evidence)}</p>`:''}</li>`;
  }).join('');
  const output=row.selected.map(c=>`<p>${esc(c.source_name)} · 源片 ${reviewRange(c.start,c.end)} ·
    主体时间轴 ${reviewRange(c.timeline_start,c.timeline_end)}
    ${c.rendered_interval?` · 预览／成片 ${reviewRange(...c.rendered_interval)}`:''}</p>
    ${c.rendered_interval&&media?`<video controls preload="none" class="preview-video" src="${esc(media)}#t=${c.rendered_interval.join(',')}"></video>`:''}`).join('');
  const excludedLabels={already_used:'其他分段已选用同源镜头',no_safe_fit:'时长或安全裁切条件不符',outside_shortlist:'排序未进入前 14'};
  const options=labels=>Object.entries(labels).map(([k,v])=>`<option value="${k}">${v}</option>`).join('');
  const samples=cases.filter(c=>row.cases.includes(c.id)).map(c=>{
    const check=c.checks.filter(x=>x.revision===revision&&x.beat===row.index).at(-1);
    return `<li>${esc(faultStages[c.stage])} · ${esc(correctionScopes[c.scope])} · 原参考区间 ${reviewRange(c.reference.start,c.reference.end)}
      ${c.target?`<p>纠正对象 · ${esc(c.target.name||c.target.shot_id)} · ${esc(c.target.facts||'缺少素材事实快照')}</p>`:''}
      <p>正确判断 · ${esc(c.expected)}</p>
      <details><summary>保存时的对照</summary><p>${esc(c.reference.action)} · ${esc(c.reference.purpose)}</p>
      ${(c.evidence.selected||[]).map(s=>`<p>${esc(s.source_name)} · ${reviewRange(s.start,s.end)} · ${esc(s.reason)}</p>`).join('')||'当时没有选区'}</details>
      <label>本次核对 · ${check?(check.outcome==='pass'?'已符合':'仍有偏差'):'待人工核对'}</label>
      <button data-case="${esc(c.id)}" data-check="pass">已符合</button><button data-case="${esc(c.id)}" data-check="fail">仍有偏差</button></li>`;
  }).join('');
  return `<details class="refbox" data-review-beat="${row.index}"><summary>第 ${row.index} 段 · ${reviewRange(ref.start,ref.end)} · ${esc(ref.purpose)}</summary>
    <p>参考画面 · ${esc(ref.action)} · ${esc(ref.subject)}</p>
    <p>必须看见 · ${esc(ref.must_see?.join('；')||'旧任务未单独记录')}</p>
    ${ref.flexible?.length?`<p>允许变化 · ${esc(ref.flexible.join('；'))}</p>`:''}
    <details><summary>素材事实与候选记录（${row.candidates.length}）</summary><ol>${candidates||'缺少逐候选记录'}</ol></details>
    ${row.excluded?.length?`<details><summary>本段初筛落选（${row.excluded.length}）</summary>
      ${row.excluded.map(x=>`<p>${esc(x.name)} · ${esc(excludedLabels[x.reason]||x.reason)}</p>`).join('')}</details>`:''}
    <h3>当前选区</h3>${output||'<p>尚无选区</p>'}
    ${row.gaps.map(g=>`<p class="warning">缺素材 · ${reviewRange(g.start_frame/30,(g.start_frame+g.frames)/30)}</p>`).join('')}
    ${row.notes.map(n=>`<p>${esc(n)}</p>`).join('')}
    ${samples?`<h3>同一参考片时段的纠错样本</h3><ul>${samples}</ul>`:''}
    <form data-case-form><label class="field">首次出错步骤<select name="stage">${options(faultStages)}</select></label>
    <label class="field">建议适用范围<select name="scope">${options(correctionScopes)}</select></label>
    ${row.candidates.length?`<label class="field">纠正对象<select name="shot_id"><option value="">本段整体</option>${row.candidates.map(c=>`<option value="${esc(c.shot_id)}">${esc(c.name||c.shot_id)}</option>`).join('')}</select></label>`:''}
    <label class="field">正确判断<textarea name="expected" required maxlength="2000"></textarea></label>
    <button>保存为纠错样本</button></form></details>`;
}

async function showReferenceReview(batch,task) {
  const url=`${wb()}/editing/batches/${batch.id}/tasks/${task.id}`;
  try {
    const data=await api(url+'/diagnosis');
    const shown=task.output||task.preview;
    const media=shown?.sha256===data.media_sha256?shown?.media_url:null;
    const basis={exact_bytes:'与参考片字节相同',similar_sample_run:'连续采样相似',insufficient_detail:'画面细节不足',
      insufficient_samples:'采样不足',unreadable:'素材不可读取',prior_source_review:'此前同源复核存疑'};
    dialog('参考片逐镜诊断',`<div id="diagnosticRows" style="max-height:70vh;overflow:auto">
      ${data.error?`<p class="error">${esc(data.error)}</p>`:''}
      ${data.screen?`<details><summary>全库同源初筛排除 ${data.screen.excluded.length} 项</summary>
      ${data.screen.excluded.map(x=>`<p>${esc(x.name)} · ${esc(basis[x.basis]||x.basis)}</p>`).join('')}</details>`:''}
      ${data.rows.map(r=>diagnosticRow(r,data.cases,data.revision,media)).join('')||'<p>尚无可核对的参考分段。</p>'}
      <button id="diagnosticBack">返回任务</button></div>`);
    $('#diagnosticBack').onclick=()=>editTaskDialog(task.id);
    async function post(row,op,body) {
      const index=row.dataset.reviewBeat;
      try {
        await api(url+'/'+op,'POST',{...body,beat:Number(index),revision:data.revision});
        await showReferenceReview(batch,task);
        const reopened=document.querySelector(`[data-review-beat="${index}"]`);
        if(reopened) {reopened.open=true;reopened.scrollIntoView({block:'nearest'})}
      } catch(error) {toast(error.message)}
    }
    for(const row of document.querySelectorAll('[data-review-beat]')) {
      row.querySelector('form').onsubmit=e=>{e.preventDefault();post(row,'samples',Object.fromEntries(new FormData(e.target)))};
      for(const button of row.querySelectorAll('[data-check]'))
        button.onclick=()=>post(row,'checks',{case_id:button.dataset.case,outcome:button.dataset.check});
    }
  } catch(error) {toast(error.message)}
}
