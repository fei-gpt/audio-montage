const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const elements={};
const element=()=>({innerHTML:'',textContent:'',classList:{toggle(){}},setAttribute(){},removeAttribute(){},addEventListener(){},querySelectorAll(){return []}});
const workspace={id:'w',assigned:true,name:'Account',editing_batches:[]};
const product={id:'p',name:'Product',workspaces:[workspace]};
const context={location:{hash:'#editing'},$:key=>elements[key]??=element(),esc:String,badge:String,
  P:()=>product,W:()=>workspace,pid:'p',wid:'w',accountPreferences:{},state:{products:[product]},
  defaultWorkspace:()=>workspace.id,accountSelector:()=>'',bindAccounts(){},refresh(){},render(){},
  generationSection:()=>'',bindGeneration(){},document:{querySelectorAll:()=>[]}};
vm.createContext(context);vm.runInContext(fs.readFileSync('workbench/static/narration.js','utf8'),context);vm.runInContext(fs.readFileSync('workbench/static/editing-pairs.js','utf8'),context);vm.runInContext(fs.readFileSync('workbench/static/editing.js','utf8'),context);
const durationTask={audio_duration:34.011417,target_duration:25};
assert.equal(context.editMovieDuration(durationTask,{}),'预计 25.00 秒');
durationTask.preview={report:{duration:24.97}};
assert.equal(context.editMovieDuration(durationTask,{}),'预览 24.97 秒');
durationTask.output={report:{duration:24.93}};
assert.equal(context.editMovieDuration(durationTask,{}),'24.93 秒');
const rows=Array.from({length:123},(_,i)=>({id:String(i),name:String(i),status:'ready',audio_duration:2}));
rows[0].output={media_url:'/media/edit/task-1?sig=token',path:'C:\\outputs\\toy-152-165-6-97-215-1.mp4'};
let page=context.editingRows(rows,1);assert.equal(page.rows.length,20);assert.equal(page.pages,7);
page=context.editingRows(rows,99);assert.equal(page.rows.length,3);assert.equal(page.page,7);
workspace.editing_batches=[{id:'batch',created_at:'today',tasks:rows,rules:{mode:'preview'},input_path:'input',output_path:'output'}];
context.editingHome();assert.equal((elements['#main'].innerHTML.match(/data-edit-detail=/g)||[]).length,20);
assert.ok(elements['#main'].innerHTML.includes('download="toy-152-165-6-97-215-1.mp4"'));
assert.ok(elements['#main'].innerHTML.includes('>toy-152-165-6-97-215-1.mp4</td>'));
assert.ok(!elements['#main'].innerHTML.includes('<video'));assert.ok(elements['#main'].innerHTML.includes('先预览再确认'));
// A refresh can temporarily replace the loaded history with a loading message.
const originalLookup=context.$;
const previousTable={dataset:{batch:'batch',page:'1'},scrollLeft:45,scrollTop:120};
function renderHistoryWith(nextTable){
  let first=true;
  context.$=key=>{
    if(key!=='#editHistoryTable')return originalLookup(key);
    if(first){first=false;return previousTable}
    return nextTable;
  };
  try{context.editingHome()}finally{context.$=originalLookup}
}
renderHistoryWith(null);
const refreshedTable={};
renderHistoryWith(refreshedTable);
assert.equal(refreshedTable.scrollLeft,45);
assert.equal(refreshedTable.scrollTop,120);
console.log('Editing pagination (123 tasks), compact list and lazy video loading passed');
let modal='';context.dialog=(title,html)=>{modal=html};context.wb=()=>'/account';
vm.runInContext(fs.readFileSync('workbench/static/generation.js','utf8'),context);
context.location.hash='#generation';
assert.equal(context.activeModule(),'generation');
context.generationHome();
assert.ok(elements['#main'].innerHTML.includes('id="generationProduct"'));
const generationPageHTML=elements['#main'].innerHTML;
assert.ok(generationPageHTML.includes('id="generationCreate"'));
assert.ok(generationPageHTML.includes('generationReferenceImages'));
assert.ok(generationPageHTML.includes('generationReferenceAudio'));
assert.match(generationPageHTML,/<textarea name="manuscript"[^>]* required>/);
for(const removed of ['id="newGeneration"','name="brief"','generationManuscriptFile','generationReferenceVideos','generationFirstFrame'])
  assert.ok(!generationPageHTML.includes(removed));
context.editingHome();
assert.ok(!elements['#main'].innerHTML.includes('id="generationCreate"'));
context.location.hash='#editing';
context.generationSettings({voiceOnly:true});
assert.ok(modal.includes('name="elevenlabs_api_key"'));
assert.ok(modal.includes('name="tts_model"'));
assert.ok(!modal.includes('name="dreamina_bin"'));
assert.ok(!modal.includes('name="codex_bin"'));
context.generationSettings();
assert.ok(modal.includes('name="dreamina_bin"'));
assert.ok(!modal.includes('name="elevenlabs_api_key"'));
assert.ok(!modal.includes('name="voice_id"'));
assert.ok(!modal.includes('name="tts_model"'));
assert.ok(modal.includes('id="copyDreaminaLogin"'));
const gen={id:'g',brief:'toy demo',stage:'stage',status:'video_pending',submit_id:'external'};
workspace.generations=[gen];context.generationDetail('g');
assert.ok(modal.includes('generationPoll'));assert.ok(!modal.includes('generationApprove'));
gen.status='awaiting_intro_review';gen.intro={sha256:'hash',media_url:'/video'};context.generationDetail('g');
assert.ok(modal.includes('generationApprove'));assert.ok(modal.includes('generationTtsPaid'));
assert.ok(!context.generationSection().includes('<video'));
gen.status='needs_attention';gen.intro_approval={sha256:'hash'};context.generationDetail('g');
assert.ok(modal.includes('generationResume'));assert.ok(!modal.includes('id="generationPoll"'));
let openEdit;
elements['#generationOpenEdit'].addEventListener=(event,handler)=>{openEdit=handler};
elements['#dialog']=element();elements['#dialog'].close=()=>{};
gen.editing_batch_id='batch';context.location.hash='#generation';
context.generationDetail('g');openEdit();
assert.equal(context.location.hash,'editing');
assert.equal(context.currentEditBatch().id,'batch');
context.location.hash='#editing';
console.log('AI generation UI confirmation gate, pending-query and continuation recovery passed');

workspace.shots=[];workspace.assets=[];
workspace.background_music_history=[{id:'short',name:'Short.mp3',duration:21.4976}];
context.editBatchDialog();
assert.ok(modal.includes('name="matching_mode"'));
assert.ok(modal.includes('value="duration"'));assert.ok(modal.includes('value="semantic"'));
assert.ok(!modal.includes('id="editClips"'));
assert.match(modal, /class="request-categories" hidden/);
const categoryList=element(),categoryGroup={hidden:true,querySelector:()=>categoryList};
elements['#editCreate'].querySelector=()=>categoryGroup;
elements['#editCreate'].updateCategoryButtons(['New category']);
assert.equal(categoryGroup.hidden,false);
assert.match(categoryList.innerHTML,/data-insert-category="New category"/);
elements['#editCreate'].updateCategoryButtons([]);
assert.equal(categoryGroup.hidden,true);
assert.equal(categoryList.innerHTML,'');
assert.ok(!modal.includes('id="editReference"'));
elements['#editAudioKind'].value='music';
elements['#editAudioKind'].onchange();
assert.equal(elements['[name="matching_mode"]'].value,'duration');
assert.equal(elements['#editScripts'].hidden,true);
assert.match(modal,/<div id="editBackgroundMusic"[^>]*>/);
assert.equal(elements['#editMusic'].required,true);
assert.equal(elements['#editNarrationUpload'].hidden,true);
assert.equal(elements['#editGeneratedNarrations'].hidden,true);
assert.equal(elements['#editNarrationSourceField'].hidden,true);
assert.equal(elements['#editTargetDuration'].hidden,false);
elements['[name="history_music_id"]'].value='short';
elements['[name="length_mode"]'].value='custom';
elements['[name="length_mode"]'].onchange();
assert.equal(elements['[name="target_duration"]'].max,'21.497');
assert.equal(elements['#editDurationLimit'].hidden,false);
elements['#editAudioKind'].value='voice';
elements['#editAudioKind'].onchange();
assert.equal(elements['[name="target_duration"]'].max,'600');
elements['[name="history_music_id"]'].value='';
context.editBatchDialog(true);
assert.ok(modal.includes('id="editReference"'));
assert.ok(!modal.includes('id="editAudioKind"'));
const search={value:'2026-11-17 lights'};
const searchRows=[{dataset:{narrationSearch:'2026-11-17 Show the lights'}},{dataset:{narrationSearch:'2026-11-18 Show the lights'}}];
const searchEmpty={};
context.bindNarrationSearch(search,searchRows,searchEmpty);
assert.equal(searchRows[0].hidden,false);
assert.equal(searchRows[1].hidden,true);
search.value='missing';search.oninput();
assert.equal(searchEmpty.hidden,false);
const now=new Date(),today=[now.getFullYear(),now.getMonth()+1,now.getDate()].map(x=>String(x).padStart(2,'0')).join('-');
const january={narrations:[{created_at:'2026-01-01'},{created_at:'2025-12-31'},{created_at:'2025-12-30'}]};
assert.equal(context.recentNarrations(january,new Date(2026,0,1,12)).length,2);
workspace.narrations=[];
context.editBatchDialog();
assert.ok(modal.includes('选择已生成配音'));
assert.equal(elements['#editNarrationSource'].value,'elevenlabs');
elements['#editAudioKind'].value='narration';
elements['#editNarrationSource'].value='elevenlabs';
elements['#editNarrationSource'].onchange();
assert.equal(elements['#editGeneratedNarrations'].hidden,false);
assert.equal(elements['#editNarrationUpload'].hidden,true);
assert.equal(elements['#editCreateSubmit'].disabled,true);
elements['#editNarrationSource'].value='local';
elements['#editNarrationSource'].onchange();
assert.equal(elements['#editGeneratedNarrations'].hidden,true);
assert.equal(elements['#editNarrationUpload'].hidden,false);
assert.ok(modal.includes('当前产品和账号今天和昨天没有生成成功'));
workspace.narrations=[
  {created_at:today,used:true,status:'completed',upload_id:'one',name:'one.mp3',script:'Show the toy',voice_name:'Voice',duration:2,media_url:'/one'},
  {created_at:today,status:'completed',upload_id:'two',name:'two.mp3',script:'Show the lights',voice_name:'Voice',duration:3},
  {created_at:today,status:'failed',script:'Failed copy',voice_name:'Voice',error:'Unavailable'}
];
context.editingHome();
assert.ok(!elements['#main'].innerHTML.includes('id="narrationForm"'));
context.location.hash='#narration';
assert.equal(context.activeModule(),'narration');
context.bindNarrationForm=()=>{};
context.narrationHome();
assert.ok(elements['#main'].innerHTML.includes('id="narrationProduct"'));
assert.ok(elements['#main'].innerHTML.includes('id="narrationForm"'));
assert.ok(elements['#main'].innerHTML.includes('配音文案1'));
assert.ok(elements['#main'].innerHTML.includes('添加新文案'));
assert.ok(elements['#main'].innerHTML.includes('共用同一个音色')||elements['#main'].innerHTML.includes('使用同一个音色'));
assert.ok(context.narrationScriptHTML(2).includes('配音文案2'));
assert.ok(elements['#main'].innerHTML.includes('name="scripts" rows="2"'));
assert.ok(elements['#main'].innerHTML.includes('data-narration-play="one"'));
assert.ok(elements['#main'].innerHTML.includes('Unavailable'));
assert.ok(elements['#main'].innerHTML.includes('已使用'));
vm.runInContext("selectedNarrations.add('one'); selectedNarrations.add('two');",context);
elements['#editAudioKind'].value='narration';
context.$("#editNarrationSearch").value='';
elements['#useNarrations'].onclick();
assert.equal(context.location.hash,'editing');
assert.ok(modal.includes('value="one" checked')&&modal.includes('value="two" checked'));
assert.ok(modal.includes('Show the toy · Voice · 2.00 秒'));
assert.ok(modal.includes('已使用'));
assert.equal(elements['[name="variant_count"]'].disabled,true);
assert.equal(elements['#editNarration'].required,false);
context.editBatchDialog(false,['one']);
assert.equal(elements['[name="variant_count"]'].disabled,false);
console.log('Voice, music and reference modes are separated');

vm.runInContext(fs.readFileSync('workbench/static/reference-review.js','utf8'),context);
const diagnostic=context.diagnosticRow({index:1,reference:{start:0,end:1,action:'开盖',purpose:'展示打开过程',must_see:['盒盖移开']},
  candidates:[{shot_id:'x',name:'盒子',facts:'盒盖闭合',rank:1}],selected:[],cases:[],gaps:[{start_frame:0,frames:30}],notes:[],
  excluded:[{name:'长镜',reason:'no_safe_fit'}]},[],'r',null);
for(const label of ['盒盖移开','盒盖闭合','缺素材','时长或安全裁切条件不符','保存为纠错样本'])assert.ok(diagnostic.includes(label));
assert.ok(!diagnostic.includes('<video'));console.log('Reference gap diagnosis and correction controls passed');

let retryRequest;
context.api=(url,method,body)=>{retryRequest={url,method,body}};
context.action=fn=>fn();
workspace.editing_batches[0].rules.matching_mode='duration';
workspace.editing_batches.push({...workspace.editing_batches[0],id:'newer'});
context.editingHome();
context.editOperation('resume','6').then(async()=>{
  assert.equal(retryRequest.url,'/account/editing/batches/batch/resume');
  assert.equal(retryRequest.method,'POST');
  assert.equal(JSON.stringify(retryRequest.body.task_ids),'["6"]');
  assert.equal(context.currentEditBatch().id,'batch');
  const batch=context.currentEditBatch(),savedTasks=batch.tasks;
  batch.tasks=[{id:'new',status:'ready'},{id:'pending',status:'planned',plan:{}},
    {id:'viewed',status:'awaiting_review',plan:{},preview:{}}];
  await context.editOperation('plan');
  assert.deepEqual(Array.from(retryRequest.body.task_ids),['new']);
  await context.editOperation('preview');
  assert.deepEqual(Array.from(retryRequest.body.task_ids),['pending']);
  batch.rules.matching_mode='semantic';
  batch.tasks=[
    {id:'paused',status:'paused',operation:'preview',plan:{}},
    {id:'interrupted',status:'interrupted',operation:'output',plan:{}},
    {id:'failed',status:'needs_attention',operation:'plan'},
    {id:'cancelled',status:'cancelled'},
    {id:'review',status:'awaiting_review',plan:{},preview:{}}
  ];
  const controls=context.editingHistory([batch],batch,context.editingRows(batch.tasks,1));
  assert.ok(controls.includes('data-edit-batch-action="continue-stopped"'));
  assert.ok(controls.includes('data-edit-retry="paused"'));
  assert.ok(!controls.includes('data-edit-retry="cancelled"'));
  await context.editOperation('continue-stopped');
  assert.deepEqual(Array.from(retryRequest.body.task_ids),['paused','interrupted']);
  assert.equal(retryRequest.url,'/account/editing/batches/batch/resume');
  assert.equal(retryRequest.body.allow_paid,false);
  context.state.capabilities={config:{model:'mock'}};
  const previousRequest=retryRequest;
  context.editOperation('resume');
  assert.equal(retryRequest,previousRequest);
  assert.ok(modal.includes('id="editPaid"'));
  elements['#editPaid']=Object.assign(element(),{checked:true});
  elements['#editGo'].onclick();
  assert.deepEqual(Array.from(retryRequest.body.task_ids),['failed']);
  assert.equal(retryRequest.body.allow_paid,true);
  batch.rules.matching_mode='duration';
  const stale={id:'stale',name:'素材替换测试',status:'awaiting_review',stage:'预览已生成',
    source_warning:'素材版本无法与剪辑方案核对，请重新选片并预览：视频078.mp4',
    plan:{parts:[]},preview:{media_url:'/old-preview'}};
  batch.tasks=[stale];
  const staleControls=context.editingHistory([batch],batch,context.editingRows(batch.tasks,1));
  assert.ok(staleControls.includes('视频078.mp4'));
  assert.ok(staleControls.includes('查看旧预览'));
  assert.ok(staleControls.includes('data-edit-regenerate="stale"'));
  assert.ok(!staleControls.includes('data-edit-review="stale"'));
  context.editTaskDialog('stale');
  assert.match(modal,/id="editFinal" disabled/);
  assert.ok(modal.includes('id="editReselect"'));
  assert.ok(modal.includes('src="/old-preview"'));
  batch.tasks=savedTasks;
  console.log('Editing retry keeps the selected history record and task');
  const calls=[];
  context.api=(url,method,body)=>{
    calls.push({url,method,body});
    if(url==='/api/editing-modes')return {modes:['duration']};
    if(url.endsWith('/editing/batches'))return {id:'from-narrations'};
  };
  context.FormData=class {
    get(name){return {matching_mode:'duration',mode:'preview',language:'auto',music_volume:'15',history_music_id:'shared-music',request_one:'第一镜必须用主体展示'}[name]??null;}
    has(name){return name==='rights_allowed';}
  };
  elements['#dialog'].close=()=>{};
  elements['#editNarration'].files=[];
  elements['#editMusic'].files=[];
  const extra=Array.from({length:8},(_,i)=>({...workspace.narrations[0],upload_id:'extra-'+i}));
  workspace.narrations.push(...extra);
  const ids=['one','two',...extra.map(item=>item.upload_id)];
  workspace.background_music_history=[{id:'shared-music',name:'Shared.mp3',duration:22}];
  context.$('[name="history_music_id"]').value='shared-music';
  context.editBatchDialog(false,ids);
  assert.equal(elements['#editCreateSubmit'].textContent,'生成 10 条预览');
  assert.ok(elements['#editBatchMusicSummary'].textContent.includes('整批共用「Shared.mp3」'));
  await elements['#editCreate'].onsubmit({preventDefault(){},target:elements['#editCreate']});
  assert.equal(calls.length,3);
  assert.equal(JSON.stringify(calls[1].body.narrations.map(item=>item.id)),JSON.stringify(ids));
  assert.equal(calls[1].body.music_id,'shared-music');
  assert.ok(modal.includes('name="request_one"'));
  assert.equal(calls[1].body.narrations[0].request,'第一镜必须用主体展示');
  assert.ok(calls[1].body.narrations.slice(1).every(item=>!item.request));
  assert.equal(calls[1].body.variant_count,1);
  assert.equal(calls[2].url,'/account/editing/batches/from-narrations/plan');
  console.log('Generated narrations submit as a single batch without uploading audio');
  const field={value:'00:00:11:00 必须用静态展示'},result={},check={},filled={};
  const editor={
    parentElement:{querySelector:()=>({value:'one'})},
    querySelector:key=>({'textarea':field,'[data-individual-result]':result,'[data-check-individual]':check,
      '[data-individual-filled]':filled}[key])
  };
  elements['#editGeneratedNarrations'].querySelectorAll=key=>key==='[data-individual-editor]'?[editor]:[];
  const values={matching_mode:'duration',mode:'preview',length_mode:'custom',target_duration:'16',history_music_id:'shared-music'};
  context.FormData=class {
    constructor(){this.values={...values};}
    get(name){return this.values[name]??null;}
    has(){return false;}
  };
  const requests=[];
  let finishCheck;
  context.api=(url,method,body)=>{
    requests.push({url,body});
    if(url.endsWith('/inspect'))return new Promise(resolve=>{finishCheck=resolve});
    if(url==='/api/editing-modes')return {modes:['duration']};
    if(url.endsWith('/editing/batches'))return {id:'saved'};
  };
  const matching=elements['[name="matching_mode"]'],lengthMode=elements['[name="length_mode"]'];
  matching.value='duration';lengthMode.value='custom';
  context.editBatchDialog(false,['one']);
  const outdated=check.onclick();
  await new Promise(setImmediate);
  assert.equal(requests.at(-1).body.target_duration,16);
  assert.equal(requests.at(-1).body.music_id,'shared-music');
  elements['[name="request"]'].value='最后一镜优先用静态展示';
  elements['[name="request"]'].oninput();
  finishCheck({requirements:[]});
  await outdated;
  assert.equal(result.textContent,'');
  let uploads=0,finishUpload,activeAccount='/account';
  context.editUploadFile=(file,kind,scope)=>{
    uploads++;
    assert.equal(kind,'music');assert.equal(scope,'/account');
    return new Promise(resolve=>{finishUpload=resolve});
  };
  context.wb=()=>activeAccount;
  elements['#editMusic'].files=[{name:'local.mp3'}];
  values.length_mode=lengthMode.value='music';lengthMode.onchange();
  const checking=check.onclick();
  const submitting=elements['#editCreate'].onsubmit({preventDefault(){}});
  await new Promise(setImmediate);
  assert.equal(uploads,1);
  activeAccount='/different-account';
  finishUpload({id:'local-music'});
  await submitting;
  finishCheck({requirements:[]});await checking;
  for(const {url,body} of requests.filter(r=>r.body?.follow_music)){
    assert.ok(url.startsWith('/account/'));assert.equal(body.music_id,'local-music');
  }
  assert.equal(requests.filter(r=>r.body?.follow_music).length,2);
  assert.equal(requests.at(-1).url,'/account/editing/batches/saved/plan');
  matching.value=values.matching_mode='semantic';matching.onchange();
  assert.equal(elements['#editTargetDuration'].hidden,true);
  assert.equal(elements['[name="target_duration"]'].disabled,true);
  assert.equal(result.textContent,'');
  elements['#editMusic'].files=[];
  await elements['#editCreate'].onsubmit({preventDefault(){}});
  assert.equal(requests.at(-2).body.follow_music,undefined);
  assert.equal(requests.at(-2).body.target_duration,undefined);
  console.log('Inspection and submission share the timeline, pending music upload and original account');
}).then(async()=>{
  const fields={};
  const field=id=>fields[id]??=(Object.assign(element(),{dataset:{},style:{},isConnected:true,value:''}));
  const script=field('script');script.value='Keep this draft';
  field('#narrationScripts').children=[{querySelector:selector=>selector==='textarea'?script:field(selector)}];
  const voice=field('#narrationVoice'),configForm=field('#generationConfig');
  configForm.elements={elevenlabs_api_key:field('key')};
  let settingsBody={voice_id:'new',elevenlabs_api_key:'changed'},finishList=[],saving;
  const state={generation_config:{elevenlabs_key_ready:true,voice_id:'old'}};
  const voicePage={state,$:field,W:()=>workspace,wb:()=>'/account',esc:String,badge:String,dialog(){},
    action:fn=>{saving=fn()},toast:message=>assert.fail(message),
    FormData:class {constructor(){return Object.entries(settingsBody)}},
    api:async(path,method,body)=>{
      if(path==='/api/generation/settings')return {elevenlabs_key_ready:true,voice_id:body.voice_id};
      assert.equal(path,'/api/generation/voices');
      return new Promise(resolve=>finishList.push(resolve));
    }};
  vm.createContext(voicePage);
  for(const file of ['narration','generation'])vm.runInContext(fs.readFileSync('workbench/static/'+file+'.js','utf8'),voicePage);
  voicePage.bindNarrationForm(workspace,false);
  finishList[0]({voices:[{id:'old',name:'Old'}]});await new Promise(setImmediate);
  assert.equal(voice.value,'old');
  voicePage.generationSettings({voiceOnly:true});
  const openingList=field('#generationVoices').onclick();
  await new Promise(setImmediate);
  assert.equal(finishList.length,2);
  assert.equal(voice.value,'');
  assert.equal(field('#submitNarration').disabled,true);
  settingsBody={voice_id:'latest',elevenlabs_api_key:''};
  field('#dialog').close=()=>{configForm.isConnected=false};
  configForm.onsubmit({preventDefault(){}});
  await saving;
  assert.equal(finishList.length,3);
  finishList[2]({voices:[{id:'latest',name:'Latest'}]});await new Promise(setImmediate);
  finishList[1]({voices:[{id:'new',name:'Earlier'}]});await openingList;
  assert.equal(voice.value,'latest');
  assert.equal(voice.disabled,false);
  assert.equal(field('#submitNarration').disabled,false);
  assert.equal(script.value,'Keep this draft');
  console.log('Voice settings refresh the active batch and preserve its script');
}).catch(error=>{console.error(error);process.exitCode=1});

{
  const library={assets:[{id:'a'},{id:'b',kind:'prepared'}],shots:[{asset_id:'a'},{asset_id:'a'}]};
  assert.equal(context.editingInventory(library),'素材 2 条');
  library.shots.push({asset_id:'b'});
  assert.equal(context.editingInventory(library),'素材 2 条');
  library.assets.pop();
  assert.equal(context.editingInventory(library),'素材 1 条');
}

{
  const calls=[];
  const ui={wb:()=>'/original-workspace',W:()=>({editing_batches:[]}),P:()=>({}),
    action:fn=>fn(),api:async(url,method,body)=>{calls.push({url,body});return {id:'new'}},
    $:()=>({open:false}),document:{querySelectorAll:()=>[]}};
  vm.createContext(ui);
  vm.runInContext(fs.readFileSync('workbench/static/editing.js','utf8'),ui);
  const task={id:'original-task',status:'awaiting_review',plan:{}};
  const batch={id:'original-batch',rules:{matching_mode:'duration'},tasks:[task]};
  ui.regenerateEdit(task.id,batch);
  assert.equal(calls[0].url,'/original-workspace/editing/batches/original-batch/regenerate');
  assert.deepEqual(Array.from(calls[0].body.task_ids),[task.id]);
  console.log('Open preview retains its batch while history detail is reloading');
}
