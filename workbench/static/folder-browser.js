// Browse the local machine without waiting for a native window to gain focus.
async function browseLocalFolder(input) {
  const picker=document.createElement('dialog');
  picker.setAttribute('aria-label','选择素材文件夹');
  picker.innerHTML=`<div style="padding:22px;width:min(580px,calc(100vw - 80px))"><div class="section-heading"><h2>选择文件夹</h2><button type="button" data-close aria-label="关闭文件夹选择">×</button></div><form data-location class="inline"><input aria-label="当前系统路径" placeholder="此电脑，或填写完整路径" style="flex:1;min-width:0"><button>前往</button></form><div class="inline" style="margin:12px 0"><button type="button" data-roots>此电脑</button><button type="button" data-up>上一级</button></div><p data-error role="status" class="small"></p><div data-folders style="height:280px;overflow:auto;border:1px solid #dbe2ea;border-radius:8px;padding:8px"></div><p class="small muted">打开目标文件夹后，点击“选择此文件夹”，完整路径会自动填入。</p><div class="inline"><button type="button" data-cancel>取消</button><button type="button" class="primary" data-select disabled>选择此文件夹</button></div></div>`;
  document.body.append(picker);
  const q=s=>picker.querySelector(s),location=q('input'),list=q('[data-folders]'),select=q('[data-select]');
  let current='',parent=null,request=0;
  const close=()=>{picker.close();picker.remove();};
  picker.addEventListener('cancel',e=>{e.preventDefault();close();});
  q('[data-close]').onclick=q('[data-cancel]').onclick=close;
  async function open(path) {
    const serial=++request;
    select.disabled=true;q('[data-up]').disabled=true;list.replaceChildren();q('[data-error]').textContent='正在读取文件夹…';
    try {
      const result=await api('/api/browse-folders','POST',{path});
      if(serial!==request||!picker.isConnected)return;
      current=result.path;parent=result.parent;location.value=current;
      q('[data-up]').disabled=parent===null;select.disabled=!current;
      q('[data-error]').textContent=current||'此电脑 · 选择磁盘';
      for(const folder of result.folders) {
        const button=document.createElement('button');button.type='button';button.style.cssText='display:block;width:100%;text-align:left;margin:2px 0';
        button.textContent='📁 '+folder.name;button.title=folder.path;button.onclick=()=>open(folder.path);list.append(button);
      }
      if(!result.folders.length)list.textContent='此文件夹没有子文件夹';
    } catch(error) {
      if(serial!==request||!picker.isConnected)return;
      current='';parent=null;q('[data-error]').textContent=error.message;
    }
  }
  q('[data-location]').onsubmit=e=>{e.preventDefault();open(location.value.trim());};
  q('[data-roots]').onclick=()=>open('');q('[data-up]').onclick=()=>open(parent);
  select.onclick=()=>{if(current){input.value=current;input.dispatchEvent(new Event('input',{bubbles:true}));close();input.focus();}};
  picker.showModal();await open(input.value.trim());
}
