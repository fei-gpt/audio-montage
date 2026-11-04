function referenceDialog(){
  const target=pid,current=P().sources;
  const linked=new Set(current.filter(s=>s.kind==='knowledge').map(s=>s.knowledge_origin));
  const groups=state.products.filter(p=>p.id!==target&&p.profile?.understood_at&&!linked.has(p.id)).map(product=>({product}));
  dialog('选择共用产品知识',`<p class="muted">选择相同产品，直接关联其已有知识。各账号共用一份文字资料，不复制、不重新理解。</p><form id="referenceForm"><div style="max-height:380px;overflow:auto">${groups.map((g,i)=>`<label class="check-label"><input type="radio" name="bundle" value="${i}"><span><strong>${esc(g.product.name)}</strong> · 共用产品知识<br><span class="small">${esc((g.product.profile.appearance||[]).slice(0,2).map(x=>typeof x==='string'?x:JSON.stringify(x)).join('；'))}</span></span></label>`).join('')||'<p class="muted">没有可新增引用的已理解资料包。</p>'}</div><button class="primary" ${groups.length?'':'disabled'}>使用此产品知识</button></form>`);
  $('#referenceForm').onsubmit=e=>{e.preventDefault();const product_ids=new FormData(e.target).getAll('bundle').map(value=>groups[Number(value)].product.id);if(!product_ids.length){toast('请先选择资料包');return}action(async()=>{const r=await api(`/api/products/${target}/knowledge/reference`,'POST',{product_ids});$('#dialog').close();toast(`已关联共用产品知识，未调用 API。`)})};
}

function knowledgeCard(p){return p.profile?.understood_at?`<section class="reference"><h3>${esc(p.name)} · 产品知识</h3><p class="muted">此产品下所有账号共用同一份文字资料。${p.knowledge_product_name?'关联：'+esc(p.knowledge_product_name):''}</p>${profileHTML(p)}</section>`:'<p class="muted">尚无产品知识，可选择相同产品的已有知识，或理解新上传资料。</p>'}
