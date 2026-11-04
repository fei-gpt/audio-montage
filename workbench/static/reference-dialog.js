function knowledgeSummary(p){
  const profile=p.profile||{};
  const appearance=(profile.appearance||[]).find(x=>typeof x==='string')||'产品文字资料已整理';
  return ((profile.suggested_name||p.name)+' · '+appearance).slice(0,160);
}
function knowledgeChoices(products){
  const unique=new Map();
  products.filter(p=>p.profile?.understood_at).forEach(p=>{const key=p.knowledge_product_id||p.id;if(!unique.has(key)||p.id===key)unique.set(key,p)});
  return [...unique.values()];
}
function referenceDialog(){
  const target=pid,current=P(),owner=current.knowledge_product_id||current.id;
  const groups=knowledgeChoices(state.products);
  dialog('选择产品语料包',`<p class="muted">同一产品共用一份已理解的文字语料，无需重新上传或调用 API。</p><form id="referenceForm"><div style="max-height:380px;overflow:auto">${groups.map((p,i)=>{const selected=(p.knowledge_product_id||p.id)===owner;return `<label class="check-label" style="padding:14px;border:1px solid var(--line);border-radius:8px"><input type="radio" name="bundle" value="${i}" ${selected?'checked':''}><span><strong>${esc(p.knowledge_product_name||p.name)} · 产品语料包</strong> ${selected?badge('当前使用'):badge('已理解')}<br><span class="small muted">${esc(knowledgeSummary(p))}</span></span></label>`}).join('')||'<p class="muted">尚无已理解的产品语料包。</p>'}</div><button class="primary" ${groups.length?'':'disabled'}>确认使用</button></form>`);
  $('#referenceForm').onsubmit=e=>{e.preventDefault();const value=new FormData(e.target).get('bundle');if(value===null){toast('请先选择产品语料包');return}const selected=groups[Number(value)];if((selected.knowledge_product_id||selected.id)===owner){$('#dialog').close();toast('当前已使用这份语料，无需重复关联。');return}action(async()=>{await api(`/api/products/${target}/knowledge/reference`,'POST',{product_ids:[selected.id]});$('#dialog').close();toast('已关联同一份产品语料，未调用 API。')})};
}
function knowledgeCard(p){
  if(!p.profile?.understood_at)return '<p class="muted">尚未选择产品语料包，可选择已有语料或理解新上传资料。</p>';
  const profile=p.profile;
  return `<section class="reference" style="padding:16px;border:1px solid var(--line);border-radius:10px;margin-top:14px"><div class="inline"><h3 style="margin:0">${esc(p.knowledge_product_name||p.name)} · 产品语料包</h3>${badge('使用中')}</div><p class="muted">${esc(knowledgeSummary(p))}</p><p class="small muted">外观 ${(profile.appearance||[]).length} 项 · 功能主张 ${(profile.claims||[]).length} 项 · 展示方式 ${(profile.demonstrations||[]).length} 项 · 同产品账号共用</p><details><summary>查看语料详情</summary>${profileHTML(p)}</details></section>`;
}
