let shotView={workspace:null,query:'',filter:'all',page:1,size:20};
function shortShotText(value,limit=85){return String(value||'').replace(/\s+/g,' ').slice(0,limit)}
function shotPage(rows,query,filter,page,size=20){
  const filtered=rows.filter(s=>(filter==='all'||(filter==='stale'?s.stale:!s.stale&&(s.review_decision||'uncertain')===filter))&&JSON.stringify([s.facts,s.reason,s.visual_details]).toLowerCase().includes(query.toLowerCase()));
  const pages=Math.max(1,Math.ceil(filtered.length/size)),current=Math.max(1,Math.min(page,pages));
  return {total:filtered.length,pages,page:current,rows:filtered.slice((current-1)*size,current*size)};
}
function renderShots(query){
  const w=W();if(!w)return;
  if(shotView.workspace!==w.id)shotView={workspace:w.id,query:'',filter:'all',page:1,size:20};
  if(query!==undefined&&query!==shotView.query){shotView.query=query;shotView.page=1}
  if($('#shotSearch'))$('#shotSearch').value=shotView.query;
  const assetIds=new Set(w.assets.map(asset=>asset.id));
  const currentShots=w.shots.filter(shot=>assetIds.has(shot.asset_id));
  const visible=currentShots.filter(s=>!$('#resultMode')||$('#resultMode').value==='all'||s.analysis_mode=== $('#resultMode').value||(!s.analysis_mode&&$('#resultMode').value==='standard'));
  const data=shotPage(visible,shotView.query,shotView.filter,shotView.page,shotView.size);shotView.page=data.page;
  const statuses={keep:'已确认保留',uncertain:'待审核',reject:'已排除'};
  $('#shots').innerHTML=`<div class="inline" style="justify-content:space-between;margin-bottom:12px"><span class="muted">共 ${currentShots.length} 条 · 当前筛选 ${data.total} 条 · 每页 ${shotView.size} 条</span><button type="button" class="primary" id="reviewAllShots">全部通过审核</button><select id="shotStatus" aria-label="筛选审核状态">${[['all','全部'],['uncertain','待审核'],['keep','已确认保留'],['reject','已排除'],['stale','版本失效']].map(([v,label])=>`<option value="${v}" ${v===shotView.filter?'selected':''}>${label}</option>`).join('')}</select></div><div class="asset-table-wrap" style="max-height:650px"><table class="asset-table"><thead><tr><th>视频 / 时长</th><th>画面摘要</th><th>状态</th><th>操作</th></tr></thead><tbody>${data.rows.map(s=>{const a=w.assets.find(a=>a.id===s.asset_id),d=s.visual_details||{};return `<tr><td style="min-width:140px"><strong>${esc(a?.name||'原视频已移除')}</strong><br><span class="muted small">${(s.end-s.start).toFixed(2)} 秒 · ${s.start.toFixed(2)}–${s.end.toFixed(2)}</span></td><td><div class="shot-summary">${esc(shortShotText(d.actions||s.facts))}</div><div class="muted small shot-summary">${esc(shortShotText([d.shot_size,d.background].filter(Boolean).join(' · '),95))}</div></td><td style="white-space:nowrap">${badge(s.stale?'版本失效':statuses[s.review_decision]||'待审核',s.stale?'red':'')}</td><td><button data-shot-detail="${s.id}">查看 / 审核</button></td></tr>`}).join('')||'<tr><td colspan="4">没有符合条件的整理结果。</td></tr>'}</tbody></table></div><div class="inline" style="justify-content:flex-end;margin:12px 0 22px"><button id="shotPrev" ${data.page===1?'disabled':''}>上一页</button><span>第 ${data.page} / ${data.pages} 页</span><button id="shotNext" ${data.page===data.pages?'disabled':''}>下一页</button></div>`;
  $('#reviewAllShots').onclick=()=>{const count=w.shots.filter(s=>!s.stale&&(s.review_decision||'uncertain')==='uncertain').length;if(!count){toast('没有待审核记录');return}if(!confirm(`确认已核对当前账号全部 ${count} 条待审核记录的内容、切镜及展示效果，并全部通过？包含其他分页，已排除和失效记录不变。`))return;action(async()=>{const r=await api(`${wb()}/shots/review-all`,'POST',{content_confirmed:true});toast(`已通过 ${r.passed} 条，跳过 ${r.skipped.length} 条`)})};
  $('#shotStatus').onchange=e=>{shotView.filter=e.target.value;shotView.page=1;renderShots()};
  $('#shotPrev').onclick=()=>{shotView.page--;renderShots()};$('#shotNext').onclick=()=>{shotView.page++;renderShots()};
  document.querySelectorAll('[data-shot-detail]').forEach(b=>b.onclick=()=>showShotDetail(b.dataset.shotDetail));
}
function timedObservationHTML(shot) {
  const observation = shot.temporal_observation;
  if (!observation || !Array.isArray(observation.points) || !Array.isArray(observation.unknowns)) return '';
  const points = observation.points.map(p => `<li>${esc(p.time)} 秒 · ${esc(p.fact)}</li>`).join('');
  return `<section><h3>展示用途与时间证据</h3><p>${esc(observation.purpose)}</p>
    <p>必要区间 ${esc(observation.required_start)}–${esc(observation.required_end)} 秒</p>
    <ul>${points}</ul>${observation.unknowns.length ? `<p>待确认 · ${esc(observation.unknowns.join('；'))}</p>` : ''}</section>`;
}
function showShotDetail(id){
  const w=W(),s=w.shots.find(s=>s.id===id);if(!s)return;const a=w.assets.find(a=>a.id===s.asset_id);
  const versions=[...new Set(w.shots.filter(x=>a && x.asset_id===a.id && x.asset_sha256===a.sha256 && !x.stale && (x.analysis_mode||'standard')==='standard').map(x=>x.analysis_version||x.job_id||'legacy'))];
  const versionLabel=v=>v==='legacy'?'旧版':((w.jobs||[]).find(j=>j.id===v)?.created_at||'识别版')+' · '+v.slice(0,8);
  const versionSelector=versions.length>1 && (s.analysis_mode||'standard')==='standard' ? `<label class="field">语义选片使用的识别版（本素材）
    <select id="activeStandardVersion"><option value="">所有已确认版本</option>${versions.map(v=>`<option value="${esc(v)}" ${a.active_standard_version===v?'selected':''}>${esc(versionLabel(v))}</option>`).join('')}</select></label>
    <button id="saveStandardVersion">保存选片版本</button>`:'';
  dialog(a?.name||'镜头详情',`<div style="max-height:70vh;overflow:auto"><p>${s.start.toFixed(3)}–${s.end.toFixed(3)} 秒 · ${s.kind==='prepared'?'已有片段，保留原边界':'原视频候选区间'}</p>${a?.available?`<video controls playsinline preload="metadata" class="preview-video" src="${esc(a.media_url)}#t=${s.start},${s.end}"></video>`:''}${versionSelector}${s.analysis_version?`<p class="small">当前查看 · ${esc(versionLabel(s.analysis_version))}</p>`:''}<h3>画面事实</h3><p class="result-note">${esc(s.facts||'待核实')}</p><p class="muted">${esc(s.reason||'')}</p>${timedObservationHTML(s)}${(s.candidate_reviews||[]).map(timedObservationHTML).join('')}${visualDetailsHTML(s.visual_details)}${s.review_reason?`<p class="warning">${esc(s.review_reason)}</p>`:''}<div class="decision">${[['keep','保留'],['uncertain','待审'],['reject','排除']].map(([value,label])=>`<button data-review="${s.id}" data-value="${value}" class="${s.review_decision===value?'chosen':''}">${label}</button>`).join('')}</div><p class="small muted">审核：${esc(s.review_note||'尚无意见')}</p></div>`);
  $('#saveStandardVersion')?.addEventListener('click',()=>action(async()=>{
    await api(`${wb()}/assets/${a.id}/standard-version`,'POST',{sha256:a.sha256,previous:a.active_standard_version||null,version:$('#activeStandardVersion').value||null});
    $('#dialog').close();toast('已保存本素材的语义选片版本');
  }));
  bindShotReviewButtons();
}
