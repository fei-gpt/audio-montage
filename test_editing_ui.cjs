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
const rows=Array.from({length:123},(_,i)=>({id:String(i),name:String(i),status:'ready',audio_duration:2}));
rows[0].output={media_url:'/media/edit/task-1?sig=token',path:'C:\\outputs\\toy-152-165-6-97-215-1.mp4'};
let page=context.editingRows(rows,1);assert.equal(page.rows.length,20);assert.equal(page.pages,7);
page=context.editingRows(rows,99);assert.equal(page.rows.length,3);assert.equal(page.page,7);
workspace.editing_batches=[{id:'batch',created_at:'today',tasks:rows,rules:{mode:'preview'},input_path:'input',output_path:'output'}];
context.editingHome();assert.equal((elements['#main'].innerHTML.match(/data-edit-detail=/g)||[]).length,20);
assert.ok(elements['#main'].innerHTML.includes('download="toy-152-165-6-97-215-1.mp4"'));
assert.ok(elements['#main'].innerHTML.includes('>toy-152-165-6-97-215-1.mp4</td>'));
assert.ok(!elements['#main'].innerHTML.includes('<video'));assert.ok(elements['#main'].innerHTML.includes('先预览再确认'));
console.log('Editing pagination (123 tasks), compact list and lazy video loading passed');
let modal='';context.dialog=(title,html)=>{modal=html};context.wb=()=>'/account';
vm.runInContext(fs.readFileSync('workbench/static/generation.js','utf8'),context);
context.generationSettings({voiceOnly:true});
assert.ok(modal.includes('name="elevenlabs_api_key"'));
assert.ok(modal.includes('name="tts_model"'));
assert.ok(!modal.includes('name="dreamina_bin"'));
assert.ok(!modal.includes('name="codex_bin"'));
context.generationSettings();
assert.ok(modal.includes('name="dreamina_bin"'));
assert.ok(modal.includes('id="copyDreaminaLogin"'));
const gen={id:'g',brief:'toy demo',stage:'stage',status:'video_pending',submit_id:'external'};
workspace.generations=[gen];context.generationDetail('g');
assert.ok(modal.includes('generationPoll'));assert.ok(!modal.includes('generationApprove'));
gen.status='awaiting_intro_review';gen.intro={sha256:'hash',media_url:'/video'};context.generationDetail('g');
assert.ok(modal.includes('generationApprove'));assert.ok(modal.includes('generationTtsPaid'));
assert.ok(!context.generationSection().includes('<video'));
gen.status='needs_attention';gen.intro_approval={sha256:'hash'};context.generationDetail('g');
assert.ok(modal.includes('generationResume'));assert.ok(!modal.includes('id="generationPoll"'));
console.log('AI generation UI confirmation gate, pending-query and continuation recovery passed');

workspace.shots=[];workspace.assets=[];
context.editBatchDialog();
assert.ok(modal.includes('name="matching_mode"'));
assert.ok(modal.includes('value="duration"'));assert.ok(modal.includes('value="semantic"'));
assert.ok(!modal.includes('id="editClips"'));
assert.ok(!modal.includes('id="editReference"'));
elements['#editAudioKind'].value='music';
elements['#editAudioKind'].onchange();
assert.equal(elements['[name="matching_mode"]'].value,'duration');
assert.equal(elements['#editScripts'].hidden,true);
assert.equal(elements['#editBackgroundMusic'].hidden,true);
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
}).catch(error=>{console.error(error);process.exitCode=1});
