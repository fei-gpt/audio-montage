function activeModule(){return location.hash==='#editing'?'editing':'materials'}
function renderModuleNavigation(){
  const editing=activeModule()==='editing';
  for(const [id,selected] of [['homeNav',!editing],['editingNav',editing]]){
    const button=$('#'+id);button.classList.toggle('active',selected);
    if(selected)button.setAttribute('aria-current','page');else button.removeAttribute('aria-current');
  }
}
function editingHome(){
  $('#crumb').textContent='工作空间 / 视频剪辑制作';
  $('#main').innerHTML=`<div class="heading"><div><h1>视频剪辑制作</h1><div class="muted">使用已整理素材和产品知识，按制作规则完成视频。</div></div>${badge('待配置制作流程')}</div>
  <section class="panel form-panel"><h2>制作流程</h2><p class="muted">模块入口已建立，具体规则与执行功能待接入。</p>
  <div class="cards">${[
    ['1 · 制作规则','设定视频目标、文案、镜头顺序和画面要求。'],
    ['2 · 素材与生成','复用当前产品知识和账号素材；即梦生成、ElevenLabs 配音待接入工作台。'],
    ['3 · 编排与预览','根据配音时间轴安排画面，预览并调整。'],
    ['4 · 审核与成片','确认内容和时间边界后输出视频。']
  ].map(([title,text])=>`<article class="meta-box"><strong>${title}</strong><p>${text}</p></article>`).join('')}</div>
  <div class="form-actions"><button id="editingMaterials">前往素材处理</button></div></section>`;
  $('#editingMaterials').onclick=()=>{pid=null;wid=null;location.hash='materials';render()};
}
