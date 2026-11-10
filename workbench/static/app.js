const $=s=>document.querySelector(s),esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
let state={products:[],capabilities:{}},pid=null,wid=null,step=1,loading=false,poller;
let accountPreferences={};
let referenceMode='new';
try { const saved=JSON.parse(localStorage.getItem('montage-account-preferences')||'{}'); if(saved && typeof saved==='object' && !Array.isArray(saved)) accountPreferences=saved; } catch {}
function rememberAccount(productId,workspaceId){accountPreferences[productId]=workspaceId||'';try{localStorage.setItem('montage-account-preferences',JSON.stringify(accountPreferences))}catch{}}
const P=()=>state.products.find(p=>p.id===pid),W=()=>P()?.workspaces.find(w=>w.id===wid);
const base=()=>`/api/products/${pid}`,wb=()=>`${base()}/workspaces/${wid}`;
const labels={queued:'等待执行',running:'处理中',interrupted:'已中断，可继续',requires_configuration:'待配置识别服务',requires_consent:'待允许本次调用',awaiting_review:'处理完成，待审核',completed:'资料理解完成',failed:'失败，记录已保留',partial_failure:'部分完成，错误已隔离'};
async function api(url,method='GET',body){let r;try{r=await fetch(url,{method,headers:{'X-Workbench-Token':window.WORKBENCH_TOKEN,...(body?{'Content-Type':'application/json'}:{})},body:body?JSON.stringify(body):undefined})}catch(e){throw Error('无法连接本机工作台，请刷新后检查任务或资料记录；不自动重试外部生成。')}const d=await r.json();if(!r.ok)throw Error(d.error||'请求失败');return d}
function toast(text){if($('#dialog').open){let box=$('#dialog').querySelector('.dialogMessage');if(!box){box=document.createElement('div');box.className='dialogMessage error';box.setAttribute('role','status');$('#dialog .dialog-inner').append(box)}box.textContent=text;return}$('#toast').textContent=text;$('#toast').hidden=false;clearTimeout(toast.timer);toast.timer=setTimeout(()=>$('#toast').hidden=true,6000)}
async function action(fn){if(loading)return;loading=true;try{await fn();await refresh()}catch(e){toast(e.message)}finally{loading=false}}
async function refresh(renderPage=true){state=await api('/api/state');if(pid&&!P())pid=null;if(wid&&!W())wid=null;$('#engineStatus').textContent=`${state.capabilities.hypit?'Hypit已就绪':'FFmpeg证据准备'} · ${state.capabilities.vision_ready?'视觉服务可用':'视觉服务待配置'}`;if(renderPage)render();schedulePoll()}
function schedulePoll(){clearTimeout(poller);const jobs=state.products.flatMap(p=>[...p.jobs,...p.workspaces.flatMap(w=>[...w.jobs,...(w.generations||[]),...(w.editing_batches||[]).flatMap(b=>b.tasks)])]);if(jobs.some(j=>['queued','running','video_pending'].includes(j.status)))poller=setTimeout(()=>refresh(!document.activeElement?.matches('input,textarea,select')).catch(e=>toast(e.message)),2500)}
function dialog(title,html){$('#dialog').innerHTML=`<div class="dialog-inner"><div class="dialog-head"><h2>${esc(title)}</h2><button id="closeDialog" aria-label="关闭">×</button></div>${html}</div>`;$('#closeDialog').onclick=()=>$('#dialog').close();$('#dialog').showModal()}
function badge(text,kind=''){return `<span class="badge ${kind}">${esc(text)}</span>`}
function visualDetailsHTML(details){if(!details||!Object.keys(details).length)return '';const labels={shot_size:'景别与主体占比',subject:'主体与配色',people_hands:'人物与手部',actions:'动作过程',background:'背景',objects:'画面元素',camera:'机位与运镜',lighting:'光效与光线',composition:'构图',distinctive_features:'区分特征',temporal_events:'时间事件',unknowns:'未确认项'};return `<details open><summary>画面特征与区别</summary><dl>${Object.entries(labels).filter(([key])=>details[key]!=null).map(([key,label])=>`<dt><strong>${label}</strong></dt><dd class="result-note">${esc(typeof details[key]==='string'?details[key]:JSON.stringify(details[key],null,2))}</dd>`).join('')}</dl></details>`}
function jobHTML(j){return `<div class="job"><div class="inline"><strong>${esc(j.kind==='understand'?'产品资料理解':'账号素材整理')}</strong>${badge(labels[j.status]||j.status,j.status==='failed'?'red':'')}</div><p>${esc(j.stage)}</p>${['queued','running'].includes(j.status)?`<progress value="${j.progress}" max="100"></progress>`:''}${j.error?`<div class="error">${esc(j.error)}</div>`:''}${(j.kind==='understand'||state.capabilities.asset_recognition_enabled)&&['failed','partial_failure','interrupted','requires_configuration','requires_consent'].includes(j.status)?`<button data-resume="${j.id}" data-workspace="${j.workspace_id||''}">继续任务</button>`:''}</div>`}
function accountJobsHTML(jobs){const active=jobs.filter(j=>['queued','running'].includes(j.status));const history=jobs.filter(j=>!active.includes(j)).reverse();return active.map(jobHTML).join('')+(history.length?`<details class="reference"><summary>任务记录（${history.length}）</summary>${history.map(jobHTML).join('')}</details>`:'')}
function bindJobs(){document.querySelectorAll('[data-resume]').forEach(b=>b.onclick=()=>{const j=[...(P()?.jobs||[]),...(P()?.workspaces||[]).flatMap(w=>w.jobs||[])].find(j=>j.id===b.dataset.resume);const cfg=j?.analysis_config;return confirmRun(async consent=>{await api(b.dataset.workspace?`${base()}/workspaces/${b.dataset.workspace}/jobs/${b.dataset.resume}/resume`:`${base()}/jobs/${b.dataset.resume}/resume`,'POST',consent)},false,true,cfg?.provider==='codex'?{model:cfg.model,base_url:'Codex CLI · ChatGPT 登录'}:null)})}
function render(){renderModuleNavigation();if(activeModule()==='editing')return editingHome();if(!pid)return home();if(step===3&&!state.capabilities.asset_recognition_enabled)step=2;const p=P();wid=defaultWorkspace(p,wid,accountPreferences);const w=W();$('#crumb').textContent='产品 / '+p.name+(w?' / '+w.name:'');$('#main').innerHTML=`<button class="back" id="back">← 所有产品</button><div class="heading"><div><h1>${esc(p.name)}</h1><div class="muted">给资料、接入账号素材库，剩下的交给系统整理。</div></div><button id="renameProduct">修改名称</button></div><div class="stepbar">${[[1,'添加产品资料'],[2,'账号与素材库'],...(state.capabilities.asset_recognition_enabled?[[3,'整理结果']]:[])].map(([i,t])=>`<button data-step="${i}" class="${step===i?'active':''}"><span class="num">${i}</span>${t}</button>`).join('')}</div><div id="content"></div>`;$('#back').onclick=()=>{pid=null;wid=null;render()};$('#renameProduct').onclick=()=>{dialog('修改产品名称',`<form id="rename"><label class="field"><span>产品名称</span><input name="name" required value="${esc(p.name)}"></label><button class="primary">保存</button></form>`);$('#rename').onsubmit=e=>{e.preventDefault();action(async()=>{await api(base(),'PATCH',{name:new FormData(e.target).get('name')});$('#dialog').close()})}};document.querySelectorAll('[data-step]').forEach(b=>b.onclick=()=>{step=+b.dataset.step;render()});if(step===1)references();if(step===2)libraries();if(step===3&&state.capabilities.asset_recognition_enabled)results()}
function home(){wid=null;$('#crumb').textContent='素材处理 / 产品项目';$('#main').innerHTML=`<div class="heading"><div><h1>素材处理</h1><div class="muted">同一产品共用知识，每个账号使用自己的素材。</div></div><button class="primary" id="newProduct">＋ 添加产品</button></div>${!state.capabilities.vision_ready?`<div class="meta-box">尚未配置视觉识别服务。可以先整理资料和接入素材库，任务不会假装完成。<button id="setup">配置服务</button></div>`:''}<div class="cards">${state.products.map(p=>{const assets=p.workspaces.reduce((n,w)=>n+w.assets.length,0),pending=p.workspaces.reduce((n,w)=>n+w.shots.filter(s=>s.review_decision==='uncertain').length,0);return `<article class="panel project"><div class="cover">${esc(p.name.slice(0,6))}</div><div class="project-content"><h2>${esc(p.name)}</h2><p class="muted">${p.sources.length} 份参考资料 · ${p.workspaces.length} 个账号</p><div class="metrics"><div>素材<strong>${assets}</strong></div><div>待审镜头<strong>${pending}</strong></div><div>资料理解<strong>${p.profile?.understood_at?'已整理':'待理解'}</strong></div></div><button data-open="${p.id}" style="width:100%;margin-top:18px">进入产品</button></div></article>`}).join('')||`<div class="panel empty-state"><h3>从一份产品资料开始</h3>添加PDF、图片或产品链接，不需要先填写复杂表格。</div>`}</div>`;$('#newProduct').onclick=()=>{dialog('添加产品',`<form id="productForm"><label class="field"><span>产品名称（可先用临时名称）</span><input name="name" required maxlength="100" placeholder="例如：指尖光剑"></label><button class="primary">创建并添加资料</button></form>`);$('#productForm').onsubmit=e=>{e.preventDefault();action(async()=>{const p=await api('/api/products','POST',{name:new FormData(e.target).get('name')});pid=p.id;step=1;$('#dialog').close()})}};$('#setup')?.addEventListener('click',settings);document.querySelectorAll('[data-open]').forEach(b=>b.onclick=()=>{pid=b.dataset.open;wid=null;step=1;render()})}
function profileHTML(p){const profile=p.profile||{};if(!profile.understood_at)return '<div class="muted">系统会先理解产品身份、外观和展示意图；尚未形成理解结果。</div>';return `${productTemplateHTML(p)}<div class="profile"><h3>系统整理的产品资料</h3>${profile.suggested_name?`<p>建议名称：${esc(profile.suggested_name)}</p>`:''}${[['appearance','外观特征'],['demonstrations','展示方式']].map(([key,title])=>`<h4>${title}</h4><ul>${(profile[key]||[]).map(x=>`<li>${esc(typeof x==='string'?x:x.text||JSON.stringify(x))}${x.source_id?` <span class="small muted">来源 ${esc(p.sources.find(s=>s.id===x.source_id)?.name||x.source_id)}${x.page?' · 第'+x.page+'页':''}</span>`:''}</li>`).join('')||'<li class="muted">没有记录</li>'}</ul>`).join('')}</div>`}
function references(){const p=P();$('#content').innerHTML=`<div class="layout"><section class="panel form-panel"><h2>把产品资料给我</h2><p class="muted">PDF说明书、产品图片、TikTok或亚马逊链接，都可以补充。系统自动整理，未知信息单独列出。</p><div class="inline" role="tablist" style="margin:16px 0"><button id="newSourcesTab" class="${referenceMode==='new'?'primary':''}" role="tab" aria-selected="${referenceMode==='new'}">新上传资料</button><button id="existingSourcesTab" class="${referenceMode==='existing'?'primary':''}" role="tab" aria-selected="${referenceMode==='existing'}">已有资料</button></div><div class="refbox" ${referenceMode==='new'?'':'hidden'}><label class="field"><span>添加PDF或产品图片（每份不超过30MB）</span><input id="references" type="file" multiple accept=".pdf,.png,.jpg,.jpeg,.webp"></label><div class="inline"><input id="refUrl" aria-label="产品链接" placeholder="粘贴 TikTok / 亚马逊产品链接" style="flex:1;padding:10px;border:1px solid var(--line);border-radius:7px"><button id="addUrl">添加链接</button></div></div><div ${referenceMode==='existing'?'':'hidden'}><button type="button" id="reuseSources">选择同一产品的已有知识</button><p class="small muted">使用已保存的理解结论，不重新读取原图或调用 API。</p></div>${referenceMode==='existing'?knowledgeCard(p):''}<div class="source-list" ${referenceMode==='new'?'':'hidden'}>${p.sources.filter(s=>referenceMode==='existing'?s.status==='understood':s.status!=='understood').map(s=>`<div class="reference"><strong>${esc(s.name)}</strong> ${badge(s.status==='failed'?'读取失败':s.status==='understood'?'已理解':'待理解',s.status==='failed'?'red':'')}<div class="file-path">${esc(s.url||s.kind||'')}</div>${s.reference?`<div class="small muted">引用自：${esc(s.reference.product_name)}</div>`:''}${s.error?`<div class="error">${esc(s.error)}</div>`:''}${s.note?`<p class="small warning">${esc(s.note)}</p>`:''}${s.pages?.length?`<details><summary>PDF文字与页码 · ${s.pages.length}页</summary>${s.pages.map(x=>`<p class="small"><strong>第${x.page}页</strong><br>${esc(x.text.slice(0,1600)||'扫描页：需要视觉观察')}</p>`).join('')}</details>`:''}</div>`).join('')||'<p class="muted">还没有参考资料。</p>'}</div><details><summary>补充要求（可选）</summary><label class="field"><span>例如：保留按压后的结果，不混用不同型号</span><textarea id="extra">${esc(p.extra_request)}</textarea></label><button id="saveExtra">保存补充要求</button></details><div class="form-actions"><button id="toLibraries">去接入账号素材库</button><button class="primary" id="understand" ${referenceMode==='new'?'':'hidden'} ${p.sources.some(s=>s.status==='awaiting_understanding')?'':'disabled'}>理解新上传资料</button></div>${p.jobs.map(jobHTML).join('')}<div style="margin-top:18px"></div></section><aside class="panel rules"><h2>资料先行</h2><p>产品资料在同一产品下共用。视频与审核结论属于各自账号。</p><div class="rule">PDF保留引用页码</div><div class="rule">图片交给视觉模型</div><div class="rule">链接失败明确提示</div><div class="rule">宣传主张不当实测</div><div class="notice">Hypit负责准备媒体证据，产品及镜头语义由已配置的视觉服务判断。</div></aside></div>`;$('#newSourcesTab').onclick=()=>{referenceMode='new';references()};$('#existingSourcesTab').onclick=()=>{referenceMode='existing';references()};$('#reuseSources').onclick=referenceDialog;$('#references').onchange=e=>action(async()=>{for(const file of e.target.files){if(file.size>30_000_000)throw Error('单份资料不得超过30MB');const content=await readFile(file);const s=await api(`${base()}/sources`,'POST',{name:file.name,data:content});if(s.status==='failed')throw Error(s.error||'资料读取失败')}toast('资料已保存，点击“理解产品资料”生成产品知识。')});$('#addUrl').onclick=()=>action(async()=>{const url=$('#refUrl').value.trim();if(!url)throw Error('请填写产品链接');const s=await api(`${base()}/sources`,'POST',{name:'产品链接',url});toast(s.status==='failed'?s.error:'网页资料已保存，等待理解')});$('#saveExtra').onclick=()=>action(()=>api(base(),'PATCH',{extra_request:$('#extra').value}));$('#toLibraries').onclick=()=>{step=2;render()};$('#understand').onclick=()=>confirmRun(async consent=>{await api(`${base()}/understand`,'POST',consent)});bindJobs()}
function readFile(file){return new Promise((resolve,reject)=>{const r=new FileReader();r.onload=()=>resolve(r.result.split(',')[1]);r.onerror=()=>reject(Error('文件读取失败'));r.readAsDataURL(file)})}
function accountSelector(){return `<div class="account-banner"><div class="inline"><strong>当前账号</strong><select class="account-select" id="accounts"><option value="">选择账号工作区</option>${P().workspaces.map(w=>`<option value="${w.id}" ${w.id===wid?'selected':''}>${esc(w.name)}${w.assigned?'':'（待分配）'}</option>`).join('')}</select><button id="newAccount">＋ 添加账号</button></div><div class="small muted" style="margin-top:8px">只使用当前账号的素材、镜头、审核意见和导出结果，不跨账号混用。</div></div>`}
function bindAccounts(){const p=P();$('#accounts').onchange=e=>{wid=e.target.value||null;rememberAccount(pid,wid);render()};$('#newAccount').onclick=()=>{dialog('添加账号工作区',`<form id="accountForm"><label class="field"><span>账号名称（不需要平台登录）</span><input name="name" required placeholder="例如：账号A / 英语号 / 备用号"></label><button class="primary">创建账号</button></form>`);$('#accountForm').onsubmit=e=>{e.preventDefault();action(async()=>{const w=await api(`${base()}/workspaces`,'POST',{name:new FormData(e.target).get('name')});wid=w.id;rememberAccount(pid,wid);$('#dialog').close()})}}}
const assetCategoryFilters=new Map();
function shortAssetNotice(assets){
  const short=assets.filter(a=>a.available&&Number.isFinite(a.duration)&&a.duration>0&&a.duration<1);
  if(!short.length)return '';
  return `<details class="warning" open><summary>${short.length} 个源视频不足 1 秒，可能拉低剪辑的单镜头时长下限</summary><ul>${short.map(a=>`<li>${esc(a.name)} · ${a.duration.toFixed(3)} 秒</li>`).join('')}</ul></details>`;
}
function libraries(){const w=W();
const showCategories=Boolean(P()?.shot_categories?.length);
const classified=new Map(),recognized=new Set();
if(showCategories){
  for(const shot of w?.shots||[]){
    if(!shot.stale&&shot.asset_sha256)recognized.add(shot.asset_id+':'+shot.asset_sha256);
    const labels=shot.visual_details?.display_categories;
    if(!shot.stale&&Array.isArray(labels))classified.set(shot.asset_id,{labels,status:'模型归类，待核对',evidence:shot.visual_details.light_sword?.evidence,sha:shot.asset_sha256});
  }
}
const originalCategory=a=>classified.get(a.id)?.sha===a.sha256?classified.get(a.id):a.category_review;
const categoryFor=a=>{
  const record=a.user_category||(a.category_review?.confirmed?a.category_review:originalCategory(a));
  if(!record)return null;
  const aliases=P()?.shot_category_aliases||{};
  return {...record,labels:[...new Set(record.labels.map(label=>Object.hasOwn(aliases,label)?aliases[label]:label))]};
};
const hasRecognition=a=>recognized.has(a.id+':'+a.sha256)||Boolean(a.category_review&&!a.category_review.confirmed&&a.category_review.status!=='缺完整分析，待分类');
const categories=[...new Set([...(P()?.shot_categories||[]),...(w?.assets||[]).flatMap(a=>categoryFor(a)?.labels||[])])];
const selectedCategory=assetCategoryFilters.get(w?.id)||'';
$('#content').innerHTML=accountSelector()+(!w?`<div class="panel empty-state"><h3>先选择这组素材属于哪个账号</h3>同一产品可以有多个账号；它们共用产品资料，但不会共享视频。</div>`:`<section class="panel form-panel"><div class="section-heading"><h2>${esc(w.name)}的素材库</h2><div class="inline"><button id="scan" ${w.libraries.length?'':'disabled'}>扫描新增视频</button><button class="primary" id="attach">接入已有素材库</button>${showCategories?'<button id="attachCategoryFolder">接入类别文件夹</button>':''}</div></div>${!w.assigned?`<div class="meta-box">旧版资料尚未分配账号，不能开始整理或导出。<button id="assign">分配账号</button></div>`:''}${w.libraries.map(l=>`<div class="reference"><strong>${esc(l.name)}</strong> ${badge(l.category?'类别文件夹 · '+(P().shot_category_aliases?.[l.category]||l.category):l.kind==='prepared'?'已剪好的素材':'待识别原视频')}<div class="file-path">${esc(l.path)}</div></div>`).join('')||'<p class="muted">接入本地已有视频文件夹，递归扫描，不搬动或修改原片。</p>'}${showCategories?`<label class="field"><span>按展示类别筛选</span><select id="assetCategory"><option value="">全部素材</option><option value="pending" ${selectedCategory==='pending'?'selected':''}>待分类</option>${categories.map(label=>`<option value="${esc(label)}" ${selectedCategory===label?'selected':''}>${esc(label)}</option>`).join('')}</select></label>`:''}${shortAssetNotice(w.assets)}<div class="asset-table-wrap"><table class="asset-table"><thead><tr><th scope="col">视频</th>${showCategories?'<th scope="col">展示类别</th>':''}${state.capabilities.asset_recognition_enabled?'<th scope="col">识别状态</th>':''}<th scope="col">时长</th><th scope="col" class="asset-action">预览</th></tr></thead><tbody>${w.assets.filter(a=>a.available&&(!showCategories||!selectedCategory||(selectedCategory==='pending'?!categoryFor(a)?.labels?.length:categoryFor(a)?.labels?.includes(selectedCategory)))).map(a=>`<tr><td>${esc(a.name)}</td>${showCategories?`<td><div class="asset-category-layout"><div><strong>${esc(categoryFor(a)?.labels?.join('、')||'待分类')}</strong><div class="small muted">${esc(categoryFor(a)?.status||'暂无类别记录')}</div></div><div><button type="button" data-change-category="${esc(a.id)}">改类别</button></div><div><button type="button" data-confirm-category="${esc(a.id)}" ${!categoryFor(a)?.labels.length||categoryFor(a).confirmed?'disabled':''}>确认类别</button></div></div></td>`:''}${state.capabilities.asset_recognition_enabled?`<td>${badge(hasRecognition(a)?'机器已识别':categoryFor(a)?.confirmed?'人工已归类':'未识别',hasRecognition(a)||categoryFor(a)?.confirmed?'':'red')}${hasRecognition(a)&&categoryFor(a)?.confirmed?'<div class="small muted">类别已人工确认</div>':''}</td>`:''}<td class="asset-duration">${Number.isFinite(a.duration)?a.duration.toFixed(2)+' 秒':'—'}</td><td class="asset-action">${a.available?`<button data-preview="${esc(a.media_url)}" aria-label="预览 ${esc(a.name)}">预览</button>`:badge('文件失效','red')}</td></tr>`).join('')||'<tr><td colspan="${3+Number(showCategories)+Number(Boolean(state.capabilities.asset_recognition_enabled))}" class="muted">没有符合条件的素材</td></tr>'}</tbody></table></div><div ${state.capabilities.asset_recognition_enabled?'':'hidden'}><label class="field"><span>本次素材识别服务</span><select id="analysisProvider">${state.capabilities.config.provider==='codex'?'':'<option value="vision">已配置的视觉 API</option>'}<option value="codex" ${state.capabilities.config.provider==='codex'||w.jobs.some(j=>j.analysis_config?.provider==='codex')?'selected':''}>Codex · GPT-6-Luna</option></select></label><label class="field"><span>本次识别标准（两种结果独立保留）</span><select id="recognitionMode"><option value="simple" ${P().analysis_mode==='simple'?'selected':''}>简单展示 · 轻量识别，供时长混剪</option><option value="standard" ${!P().recognition_template_ready?'disabled':P().analysis_mode!=='simple'?'selected':''}>明确标准 · 状态、动作与用途</option></select><small>${P().recognition_template_origin?'使用 '+esc(P().recognition_template_origin)+' 已确认的共用标准':P().recognition_template?.builtin?'可直接使用基础标准：数量、包装、灯光、运镜':P().recognition_template_ready?'已可使用本产品的识别标准':'明确标准暂不可用。请到「添加产品资料」生成并确认标准，或使用简单展示。'}</small></label><details><summary>本次补充一句话（可选）</summary><textarea id="runRequest" style="width:100%;min-height:75px" placeholder="例如：优先保留旋转和完整变色"></textarea></details><div class="form-actions"><button class="primary" id="start" ${!w.assigned?'disabled':''}>整理未完成素材</button><button id="reanalyze">重新识别全库（保留旧版本）</button></div></div><p class="footer-note">默认1–4秒；真实切镜拆分、连续运镜不拆；明确一镜到底完整展示允许例外。已剪素材不会自动再次切割。</p>${w.legacy_snapshot?`<details><summary>旧版记录（待重新定位原文件）</summary><pre class="result-note small">${esc(JSON.stringify(w.legacy_snapshot,null,2))}</pre></details>`:''}${accountJobsHTML(w.jobs)}</section>`);bindAccounts();if(!w)return;$('#assetCategory')?.addEventListener('change',e=>{assetCategoryFilters.set(w.id,e.target.value);libraries()});$('#attach').onclick=()=>attachDialog();
$('#attachCategoryFolder')?.addEventListener('click',()=>attachDialog(true));
document.querySelectorAll('[data-confirm-category]').forEach(button=>button.onclick=()=>{
  const a=w.assets.find(item=>item.id===button.dataset.confirmCategory);
  action(()=>api(`${wb()}/assets/${a.id}/category`,'POST',{labels:categoryFor(a).labels,confirmed:true}));
});
document.querySelectorAll('[data-change-category]').forEach(button=>button.onclick=()=>{
  const a=w.assets.find(item=>item.id===button.dataset.changeCategory);
  const productId=P().id;
  let categories=[...P().shot_categories];
  const chosen=new Set(categoryFor(a)?.labels||[]);
  dialog('改展示类别',`<form id="changeAssetCategory"><p>${esc(a.name)}</p>
    <fieldset><legend>展示类别（可多选）</legend><div id="assetCategoryChoices"></div></fieldset>
    <details><summary>管理类别</summary>
      <label class="field"><span>新类别名称</span><input id="assetCategoryName" maxlength="40"></label>
      <button type="button" id="assetCategoryAdd">新增类别</button>
      <label class="field"><span>要重命名或删除的类别</span><select id="assetCategoryManage"></select></label>
      <div class="inline"><button type="button" id="assetCategoryRename">重命名</button><button type="button" id="assetCategoryRemove">从类别清单移除</button></div>
      <div id="assetCategoryRenameEditor" hidden><label class="field"><span>改为</span><input id="assetCategoryRenameName" maxlength="40"></label><div class="inline"><button type="button" id="assetCategoryRenameSave">保存新名称</button><button type="button" id="assetCategoryRenameCancel">取消改名</button></div></div>
      <p class="small muted">清单改动立即保存。移除类别会保留历史归类记录。</p>
    </details><button class="primary">保存并确认类别</button></form>`);
  function renderCategoryChoices(){
    const selected=$('#assetCategoryManage').value;
    $('#assetCategoryChoices').innerHTML=categories.map(label=>`<label class="check-label"><input type="checkbox" name="labels" value="${esc(label)}" ${chosen.has(label)?'checked':''}>${esc(label)}</label>`).join('');
    $('#assetCategoryManage').innerHTML=categories.map(label=>`<option ${selected===label?'selected':''}>${esc(label)}</option>`).join('');
  }
  renderCategoryChoices();
  $('#assetCategoryChoices').onchange=e=>{
    if(e.target.checked)chosen.add(e.target.value);else chosen.delete(e.target.value);
  };
  let savingCategories=false;
  async function manageCategories(operation){
    if(savingCategories)return;
    const old=$('#assetCategoryManage').value;
    const input=operation==='rename'?$('#assetCategoryRenameName'):$('#assetCategoryName');
    const newName=input.value.trim();
    if(operation!=='remove'&&(!newName||categories.includes(newName))){
      input.focus();
      return toast(operation==='rename'&&newName===old?'请输入不同于原名称的新名称':'请输入尚未使用的类别名称');
    }
    if(operation==='remove'){
      if(categories.length<=1)return toast('请至少保留一个类别');
      if(!window.confirm(`将「${old}」从类别清单移除？历史归类记录会保留。`))return;
    }
    const controls=[...$('#changeAssetCategory').querySelectorAll('button')];
    savingCategories=true;
    controls.forEach(button=>button.disabled=true);
    try{
      const path=`/api/products/${productId}/shot-categories`;
      const result=operation==='rename'
        ?await api(path+'/rename','POST',{old,new:newName})
        :await api(path,'POST',{categories:(operation==='add'?[...categories,newName]:categories.filter(label=>label!==old)).join('\n')});
      if(operation==='rename'&&chosen.delete(old))chosen.add(newName);
      if(operation==='remove')chosen.delete(old);
      if(operation==='add')chosen.add(newName);
      categories=result.categories;
      input.value='';
      $('#assetCategoryRenameEditor').hidden=true;
      renderCategoryChoices();
      if(operation!=='remove')$('#assetCategoryManage').value=newName;
      await refresh(false);
      if(W()?.id===w.id)libraries();
      toast('类别清单已保存');
    }catch(e){toast(e.message)}finally{savingCategories=false;controls.forEach(button=>button.disabled=false)}
  }
  $('#assetCategoryAdd').onclick=()=>manageCategories('add');
  const renameEditor=$('#assetCategoryRenameEditor');
  $('#assetCategoryRename').onclick=()=>{
    renameEditor.hidden=false;
    const input=$('#assetCategoryRenameName');
    input.value=$('#assetCategoryManage').value;
    input.focus();input.select();
  };
  $('#assetCategoryManage').onchange=()=>{renameEditor.hidden=true};
  $('#assetCategoryRenameSave').onclick=()=>manageCategories('rename');
  $('#assetCategoryRenameCancel').onclick=()=>{renameEditor.hidden=true};
  for(const [id,operation] of [['assetCategoryName','add'],['assetCategoryRenameName','rename']]){
    $('#'+id).onkeydown=e=>{if(e.key==='Enter'){e.preventDefault();manageCategories(operation)}};
  }
  $('#assetCategoryRemove').onclick=()=>manageCategories('remove');
  $('#changeAssetCategory').onsubmit=event=>{event.preventDefault();if(savingCategories)return;const labels=new FormData(event.currentTarget).getAll('labels');action(async()=>{await api(`${wb()}/assets/${a.id}/category`,'POST',{labels,confirmed:true});$('#dialog').close()})};
});
$('#scan').onclick=()=>action(async()=>{
  const button=$('#scan');
  button.disabled=true;
  button.textContent='正在扫描…';
  try {
    const result=await api(`${wb()}/scan`,'POST',{});
    scanMessage(result,w);
  } finally {
    button.disabled=false;
    button.textContent='扫描新增视频';
  }
});$('#assign')?.addEventListener('click',()=>{dialog('分配账号',`<form id="assignForm"><label class="field"><span>这组旧资料属于哪个账号？</span><input name="name" required placeholder="请输入实际账号名称"></label><button class="primary">确认分配</button></form>`);$('#assignForm').onsubmit=e=>{e.preventDefault();action(async()=>{await api(wb(),'PATCH',{name:new FormData(e.target).get('name'),assigned:true});$('#dialog').close()})}});const launchRecognition=(force=false)=>{const request=$('#runRequest')?.value||'';const codex=$('#analysisProvider')?.value==='codex';confirmRun(async consent=>{await api(`${wb()}/start`,'POST',{...consent,request,analysis_mode:$('#recognitionMode').value,force_reanalysis:force,...(codex?{provider:'codex',model:'gpt-6-luna'}:{})});step=3},true,false,codex?{model:'gpt-6-luna',base_url:'Codex CLI · ChatGPT 登录'}:null)};$('#start').onclick=()=>launchRecognition(false);$('#reanalyze').onclick=()=>{if(window.confirm('重新识别全库会重新分析已有结果的素材，并使用模型额度。确定继续吗？'))launchRecognition(true)};bindPreviews();bindJobs()}
function scanMessage(result,workspace){
  if(!workspace){
    if(result.errors.length)dialog('扫描结果',`<p>已接入 ${result.count} 条可用素材。</p><div class="error result-note">${esc(result.errors.map(x=>(x.file||x.library)+': '+x.error).join('\n'))}</div>`);
    else toast('已扫描 '+result.count+' 条素材。');
    return;
  }
  const previous=new Map(workspace.assets.map(asset=>[asset.id,asset]));
  const found=new Set(result.assets.map(asset=>asset.id));
  const added=result.assets.filter(asset=>!previous.has(asset.id));
  const updated=result.assets.filter(asset=>{
    const old=previous.get(asset.id);
    return old&&(!old.available||old.sha256!==asset.sha256);
  });
  const unavailable=workspace.assets.filter(asset=>asset.available&&!found.has(asset.id));
  dialog('素材库扫描结果',`
    <p>已扫描 ${workspace.libraries.length} 个文件夹（含子文件夹），共 ${result.count} 条可用视频。</p>
    <p>新增 ${added.length} 条 · 更新或恢复 ${updated.length} 条 · 失效 ${unavailable.length} 条 · 跳过 ${result.errors.length} 项</p>
    ${added.length?`<ul>${added.map(asset=>`<li>${esc(asset.name)}</li>`).join('')}</ul>`:'<p class="small muted">本次没有找到新增的可用视频。</p>'}
    <p class="small muted">扫描位置</p>
    ${workspace.libraries.map(library=>`<div class="file-path">${esc(library.path)}</div>`).join('')}
    ${result.errors.length?`<details open><summary>查看跳过原因</summary><div class="error result-note">${esc(result.errors.map(x=>(x.file||x.library)+': '+x.error).join('\n'))}</div></details>`:''}
  `);
}
function attachDialog(categoryMode=false){dialog(categoryMode?'接入类别文件夹':'接入已有素材库',`<form id="attachForm"><label class="field"><span>素材文件夹</span><div class="inline"><input id="folderPath" name="path" required placeholder="选择文件夹或填写绝对路径" style="flex:1"><button type="button" id="chooseFolder">选择文件夹</button></div></label>${categoryMode?`<label class="field"><span>文件夹内素材的类别</span><select name="category" required><option value="">请选择已有类别</option>${P().shot_categories.map(label=>`<option>${esc(label)}</option>`).join('')}</select></label><p class="small muted">扫描后直接按所选类别入库，不调用模型。</p>`:'<label class="field"><span>文件夹里的视频是什么？</span><select name="kind"><option value="raw">待识别原视频</option><option value="prepared">已经剪好的素材（不自动重切）</option></select></label>'}<p class="small muted">此文件夹将归属 ${esc(W().name)}，不能再接入另一个账号。原文件不会搬动。</p><button class="primary">接入并扫描</button></form>`);$('#chooseFolder').onclick=()=>browseLocalFolder($('#folderPath'));$('#attachForm').onsubmit=e=>{e.preventDefault();const f=new FormData(e.target);action(async()=>{await api(`${wb()}/libraries`,'POST',{path:f.get('path'),kind:categoryMode?'prepared':f.get('kind'),category:f.get('category')});const r=await api(`${wb()}/scan`,'POST',{});$('#dialog').close();scanMessage(r)})}}
function confirmRun(fn,organize=false,retry=false,override=null){const cap=override?{...state.capabilities,vision_ready:true,config:override}:state.capabilities;if(!cap.vision_ready){dialog('识别服务尚未配置',`<p>需要补充：</p><ul>${cap.missing.map(x=>`<li>${esc(x)}</li>`).join('')}</ul><p>资料与素材库已保留，不会显示虚假的处理成功。</p><button id="goConfig" class="primary">配置识别服务</button>`);$('#goConfig').onclick=()=>{$('#dialog').close();settings()};return}dialog('开始'+(organize?'整理素材':'理解资料'),`<p>将资料${organize?'和视频抽帧':''}发送到你配置的模型：</p><p><strong>${esc(cap.config.model)}</strong><br><span class="file-path">${esc(cap.config.base_url)}</span></p><label class="check-label"><input id="allowPaid" type="checkbox">${cap.config.provider==='codex'||override?'允许本次使用Codex账号额度，不自动更换服务或模型。':'允许本次发送资料并可能产生API费用，不自动更换服务或模型。'}</label>${organize?`<label class="check-label"><input id="rights" type="checkbox">已确认这些素材可用于当前账号（未确认也可分析，但不能正式导出）。</label>`:''}${retry?`<label class="check-label"><input id="retryFailed" type="checkbox">重新发送未完成请求（可能再次计费；保留旧记录）</label>`:''}<button id="confirmStart" class="primary">确认开始</button>`);$('#confirmStart').onclick=()=>action(async()=>{if(!$('#allowPaid').checked)throw Error('请明确允许本次模型调用');await fn({allow_paid:true,rights_allowed:$('#rights')?.checked||false,retry_failed:$('#retryFailed')?.checked||false});$('#dialog').close();toast('后台任务已启动，进度会实际更新。')})}
function bindPreviews(){document.querySelectorAll('[data-preview]').forEach(b=>b.onclick=()=>dialog('当前账号素材预览',`<video controls playsinline autoplay class="preview-video" src="${esc(b.dataset.preview)}"></video>`))}
function results(){const w=W();$('#content').innerHTML=accountSelector()+(!w?'<div class="panel empty-state">选择账号查看该账号的整理结果。</div>':`<div class="section-heading"><h2>${esc(w.name)}的整理结果</h2><div class="inline"><button id="useInEditing">使用当前账号素材制作视频</button><button id="refreshResults">刷新结果</button></div></div>${accountJobsHTML(w.jobs)}<div class="meta-box">已剪好的片段：整理结果与审核意见保存到原视频旁的 JSON，无需再次导出。待处理原视频：确认镜头后导出片段，并为每个导出视频保存 JSON。</div><div class="toolbar"><label class="search"><input id="shotSearch" placeholder="在当前账号内搜索镜头"></label><select id="resultMode" aria-label="识别标准筛选"><option value="all">两种标准全部结果</option><option value="simple">简单展示结果</option><option value="standard">明确标准结果及旧记录</option></select>${w.assets.some(a=>a.kind==='raw')?'<button class="primary" id="exportShots">导出原片已确认镜头 + JSON</button>':''}</div><div id="shots" class="shot-list"></div>${w.exports.length||w.assets.some(a=>a.kind==='raw')?`<section class="panel recent"><h2>当前账号导出记录</h2>${w.exports.map(e=>`<div class="reference"><strong>${esc(e.created_at)}</strong><p>${e.files.map((f,i)=>`<a href="${esc(f.media_url)}" download>片段 ${i+1}</a>`).join('　')}</p></div>`).join('')||'<p class="muted">还没有导出文件。</p>'}</section>`:''}`);bindAccounts();if(!w)return;$('#useInEditing').onclick=()=>{location.hash='editing';render()};$('#refreshResults').onclick=()=>refresh();$('#shotSearch').oninput=e=>renderShots(e.target.value);$('#resultMode').onchange=()=>renderShots();$('#exportShots')?.addEventListener('click',()=>action(async()=>{const ids=w.shots.filter(s=>s.review_decision==='keep'&&!s.stale&&w.assets.some(a=>a.id===s.asset_id&&a.kind==='raw')).map(s=>s.id);await api(`${wb()}/export`,'POST',{shot_ids:ids});toast('原片镜头已导出，每条视频旁均已保存 JSON。')}));renderShots();bindJobs()}
function bindShotReviewButtons(){
 document.querySelectorAll('[data-review]').forEach(b=>b.onclick=()=>{
  const shot=W().shots.find(s=>s.id===b.dataset.review),keep=b.dataset.value==='keep';
  dialog('保存审核意见',`<form id="reviewForm">
   <label class="field"><span>意见或选区问题</span><textarea name="note">${esc(shot.review_note||'')}</textarea></label>
   <details><summary>修正事实或选区（可选，不跨切镜）</summary>
    <label class="field"><span>画面事实</span><textarea name="facts">${esc(shot.facts||'')}</textarea></label>
    <div class="inline"><label class="field"><span>起点（秒）</span><input name="start" type="number" step="0.001" required value="${shot.start}"></label><label class="field"><span>终点（秒）</span><input name="end" type="number" step="0.001" required value="${shot.end}"></label></div>
   </details>
   ${keep?`<fieldset><legend>允许裁切的时间区间（可选）</legend>
    <p class="small">填写原视频中的秒数。仅添加已核对、区间内裁切不会截断必要动作的范围；留空时只使用完整镜头。全部通过审核不会自动开放裁切。</p>
    <div id="trimRanges"></div><button type="button" id="addTrimRange">＋ 添加时间区间</button>
   </fieldset><label class="check-label"><input id="reviewConfirm" type="checkbox" required>我已实际核对本段内容、真实切镜、边界和展示效果；填写的区间可安全裁切。</label>`:''}
   <button class="primary">保存${keep?'保留':'意见'}</button></form>`);
  const form=$('#reviewForm');
  if(keep){
   const add=(range={})=>{
    if($('#trimRanges').children.length>=30){toast('最多添加30组时间区间');return}
    const row=document.createElement('div');row.className='inline';row.dataset.trimRow='';
    row.innerHTML=`<label class="field"><span>可裁切起点（秒）</span><input data-trim-start type="number" step="0.001" min="0" required value="${esc(range.start??'')}"></label><label class="field"><span>可裁切终点（秒）</span><input data-trim-end type="number" step="0.001" min="0" required value="${esc(range.end??'')}"></label><button type="button" data-remove-trim>删除区间</button>`;
    row.querySelector('[data-remove-trim]').onclick=()=>row.remove();$('#trimRanges').append(row);
   };
   (shot.safe_trim_ranges||[]).forEach(add);$('#addTrimRange').onclick=()=>add();
  }
  form.onsubmit=e=>{e.preventDefault();action(async()=>{
   const fields=new FormData(form),start=Number(fields.get('start')),end=Number(fields.get('end'));
   const body={decision:b.dataset.value,note:fields.get('note'),facts:fields.get('facts'),start,end,content_confirmed:$('#reviewConfirm')?.checked||false};
   if(keep){
    body.safe_trim_ranges=[...form.querySelectorAll('[data-trim-row]')].map(row=>({start:Number(row.querySelector('[data-trim-start]').value),end:Number(row.querySelector('[data-trim-end]').value)}));
    if(body.safe_trim_ranges.some(r=>!Number.isFinite(r.start)||!Number.isFinite(r.end)||r.start<start||r.start>=r.end||r.end>end))throw Error('裁切起止时间必须位于当前镜头内，且终点大于起点');
   }
   await api(`${wb()}/shots/${b.dataset.review}`,'PATCH',body);$('#dialog').close();
  })};
 });
}
function settings(){
const c=state.capabilities.config;
if(c.provider==='codex'){dialog('识别服务设置',`<div class="meta-box"><strong>Codex · GPT-6-Luna</strong><p>产品资料理解、素材分析和剪辑选片默认使用此模型。使用已登录的Codex账号额度，无需填写DeepSeek密钥。</p><p>连接失败或额度不足时保留任务，不自动更换服务或模型。</p></div><button id="keepCodex" class="primary">保存当前设置</button>`);$('#keepCodex').onclick=()=>action(async()=>{await api('/api/settings','POST',{provider:'codex',model:'gpt-6-luna'});$('#dialog').close()});return}
dialog('识别服务设置',`<form id="settingsForm">
<button type="button" id="deepseekPreset">使用 DeepSeek 视觉配置</button>
<label class="field"><span>API 地址</span><input name="base_url" required value="${esc(c.base_url)}"></label>
<label class="field"><span>支持图片的模型名称</span><input name="model" required value="${esc(c.model)}"></label>
<label class="field"><span>API 密钥</span><input type="password" name="api_key" autocomplete="new-password" placeholder="粘贴 sk- 开头的完整密钥；留空保留原密钥"></label>
<p class="small">密钥保存在本机工作台数据目录，保存后立即生效，重启后保留。已保存的密钥不会回显。配置保存不会调用模型。</p>
<details><summary>高级设置</summary><label class="field"><span>密钥环境变量名（可选）</span><input name="api_key_env" value="${esc(c.api_key_env)}"></label></details>
<button class="primary">保存配置</button></form>`);
$('#deepseekPreset').onclick=()=>{const f=$('#settingsForm');f.elements.base_url.value='https://api.deepseek.com';f.elements.model.value='deepseek-flash';f.elements.api_key_env.value='DEEPSEEK_API_KEY'};
$('#settingsForm').onsubmit=e=>{e.preventDefault();action(async()=>{const result=await api('/api/settings','POST',Object.fromEntries(new FormData(e.target)));e.target.elements.api_key.value='';$('#dialog').close();toast(result.vision_ready?'配置已保存，密钥已就绪（尚未验证联网）。':'配置已保存，请补充 API 密钥。')})};
}
function migration(){let data;try{data=JSON.parse(localStorage.getItem('montage-workbench-v1'))}catch{}dialog('导入旧版资料',`<p>产品资料、素材记录、任务与审核快照会保留，归入“待分配账号”，不会直接运行或导出。旧浏览器数据保持不变。</p>${data?'<button class="primary" id="migrateLocal">迁移此浏览器的旧版资料</button>':'<p class="muted">此地址没有旧版浏览器数据。请从旧页面导出资料，或使用下方迁移文件。</p>'}<label class="field" style="margin-top:18px"><span>旧版完整数据JSON或产品资料JSON</span><input type="file" id="migrationFile" accept=".json"></label>`);const run=d=>action(async()=>{if(d.product&&!d.products)d={products:[d.product],tasks:[],exports:[]};if(!Array.isArray(d.products))throw Error('迁移文件缺少产品列表');const result=await api('/api/migrate','POST',d);$('#dialog').close();toast(result.already_imported?'此版本已迁移，不重复导入':'资料已迁移，请为待分配工作区指定账号并重新接入原文件夹。')});$('#migrateLocal')?.addEventListener('click',()=>run(data));$('#migrationFile').onchange=async e=>{try{run(JSON.parse(await e.target.files[0].text()))}catch(err){toast(err.message)}}}
$('#homeNav').onclick=()=>{pid=null;wid=null;location.hash='materials';render()};$('#editingNav').onclick=()=>{location.hash='editing';render()};window.addEventListener('hashchange',()=>render());$('#settingsNav').onclick=settings;$('#migrationNav').onclick=migration;$('#dialog').addEventListener('close',()=>{$('#dialog').querySelectorAll('video').forEach(v=>v.pause())});refresh().catch(e=>{$('#main').textContent='工作台无法连接本地服务：'+e.message});

function productTemplateHTML(p){if(p.shot_categories)return `<section class="meta-box"><h3>光剑展示类别</h3><p>新素材按这些类别归类，可同时归入多类。</p><p>${esc(p.shot_categories.join(' · '))}</p><button type="button" data-shot-categories>新增或编辑类别</button> <button type="button" data-rename-shot-category>重命名类别</button></section>`;const t=p.recognition_template;return `<section class="meta-box"><h3>本产品识别重点</h3><p>明确标准可以手动填写并确认，也可以根据产品资料生成。修改产品资料后需重新确认标准。</p><button type="button" data-template-manual>${t?.builtin?'修改基础标准':'手动填写识别标准'}</button> <button data-template-generate>根据产品资料生成标准</button>${t?`<p>${esc(t.definition.summary||'产品专属标准')} · ${t.confirmed?'已确认':'待确认'}</p><ul>${t.definition.dimensions.map(d=>`<li>${esc(d.label)}：${esc(d.evidence_rule)}</li>`).join('')}</ul>${t.builtin?'':p.recognition_template_origin?`<p>共用 ${esc(p.recognition_template_origin)} 的标准。修改共用标准请到来源产品。</p>`:'<button data-template-confirm>查看、修改并确认</button>'}`:''}</section>`}
document.addEventListener('click',e=>{if(e.target.closest('[data-rename-shot-category]')){
  const p=P();
  dialog('重命名展示类别',`<form id="renameShotCategory"><label class="field"><span>现有类别</span><select name="old">${p.shot_categories.map(label=>`<option>${esc(label)}</option>`).join('')}</select></label><label class="field"><span>新名称</span><input name="new" required maxlength="40"></label><button class="primary">保存名称</button></form>`);
  $('#renameShotCategory').onsubmit=event=>{event.preventDefault();const body=Object.fromEntries(new FormData(event.currentTarget));action(async()=>{await api(`/api/products/${p.id}/shot-categories/rename`,'POST',body);assetCategoryFilters.clear();$('#dialog').close()})};
}if(e.target.closest('[data-shot-categories]')){
  const p=P();
  dialog('编辑光剑展示类别',`<form id="shotCategoriesForm"><label class="field"><span>每行一个类别</span><textarea name="categories" rows="12" required maxlength="2000">${esc(p.shot_categories.join('\n'))}</textarea></label><button class="primary">保存类别</button></form>`);
  $('#shotCategoriesForm').onsubmit=event=>{event.preventDefault();const categories=new FormData(event.currentTarget).get('categories');action(async()=>{await api(`/api/products/${p.id}/shot-categories`,'POST',{categories});$('#dialog').close()})};
}if(e.target.closest('[data-template-manual]')){
  const p=P(),t=p.recognition_template;
  dialog('手动填写识别标准',`<form id="manualRecognitionTemplate"><label class="field"><span>每行写一条你希望识别的内容，最多 12 条。</span><textarea name="rules" required maxlength="6000" rows="7" placeholder="例如：记录画面里有无包装盒。&#10;例如：区分单把、四把组合和多把独立光剑。">${esc(p.recognition_template_origin?'':t?.manual_rules||'')}</textarea></label><p class="muted">保存后即可在本产品选用「明确标准」。已有整理结果会保留。${t?' 本次保存会设为当前产品的标准。':''}</p><button class="primary">保存并确认</button></form>`);
  $('#manualRecognitionTemplate').onsubmit=event=>{event.preventDefault();const rules=new FormData(event.currentTarget).get('rules');action(async()=>{await api(`/api/products/${p.id}/recognition-template/confirm`,'POST',{id:t?.id??null,manual_rules:rules});$('#dialog').close();toast('识别标准已确认')})};
}if(e.target.closest('[data-template-generate]'))confirmRun(async consent=>{await api(`/api/products/${pid}/recognition-template`,'POST',consent)});if(e.target.closest('[data-template-confirm]')){const t=P().recognition_template;dialog('确认产品识别标准',`<p>请核对产品身份和维度；未知功能不需要补成确定事实。确认仅影响后续任务，旧结果保留。</p><textarea id="templateDefinition" style="width:100%;min-height:260px">${esc(JSON.stringify(t.definition,null,2))}</textarea><button id="confirmProductTemplate" class="primary">保存并确认</button>`);$('#confirmProductTemplate').onclick=()=>action(async()=>{await api(`/api/products/${pid}/recognition-template/confirm`,'POST',{id:t.id,definition:JSON.parse($('#templateDefinition').value)});$('#dialog').close()})}});

$('#restartWorkbench').onclick=async event=>{
  const button=event.currentTarget;
  button.disabled=true;
  button.textContent='重启中…';
  try{
    await api('/api/restart','POST',{});
    for(let attempt=0;attempt<30;attempt++){
      await new Promise(resolve=>setTimeout(resolve,500));
      const page=await fetch('/',{cache:'no-store'}).then(r=>r.text()).catch(()=>'');
      const token=page.match(/window\.WORKBENCH_TOKEN\s*=\s*"([^"]+)"/)?.[1];
      if(token&&token!==window.WORKBENCH_TOKEN){location.reload();return}
    }
    throw Error('工作台尚未恢复，请稍后刷新');
  }catch(e){toast(e.message);button.disabled=false;button.textContent='重启工作台'}
};
