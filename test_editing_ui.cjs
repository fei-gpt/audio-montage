const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const elements={};
const element=()=>({innerHTML:'',textContent:'',classList:{toggle(){}},setAttribute(){},removeAttribute(){},addEventListener(){}});
const workspace={id:'w',assigned:true,name:'Account',editing_batches:[]};
const product={id:'p',name:'Product',workspaces:[workspace]};
const context={location:{hash:'#editing'},$:key=>elements[key]??=element(),esc:String,badge:String,
  P:()=>product,W:()=>workspace,pid:'p',wid:'w',accountPreferences:{},state:{products:[product]},
  defaultWorkspace:()=>workspace.id,accountSelector:()=>'',bindAccounts(){},refresh(){},render(){},
  generationSection:()=>'',bindGeneration(){},document:{querySelectorAll:()=>[]}};
vm.createContext(context);vm.runInContext(fs.readFileSync('workbench/static/editing.js','utf8'),context);
const rows=Array.from({length:123},(_,i)=>({id:String(i),name:String(i),status:'ready',audio_duration:2}));
let page=context.editingRows(rows,1);assert.equal(page.rows.length,20);assert.equal(page.pages,7);
page=context.editingRows(rows,99);assert.equal(page.rows.length,3);assert.equal(page.page,7);
workspace.editing_batches=[{id:'batch',created_at:'today',tasks:rows,rules:{mode:'preview'},input_path:'input',output_path:'output'}];
context.editingHome();assert.equal((elements['#main'].innerHTML.match(/data-edit-detail=/g)||[]).length,20);
assert.ok(!elements['#main'].innerHTML.includes('<video'));assert.ok(elements['#main'].innerHTML.includes('先预览再确认'));
console.log('Editing pagination (123 tasks), compact list and lazy video loading passed');
let modal='';context.dialog=(title,html)=>{modal=html};context.wb=()=>'/account';
vm.runInContext(fs.readFileSync('workbench/static/generation.js','utf8'),context);
const gen={id:'g',brief:'toy demo',stage:'stage',status:'video_pending',submit_id:'external'};
workspace.generations=[gen];context.generationDetail('g');
assert.ok(modal.includes('generationPoll'));assert.ok(!modal.includes('generationApprove'));
gen.status='awaiting_intro_review';gen.intro={sha256:'hash',media_url:'/video'};context.generationDetail('g');
assert.ok(modal.includes('generationApprove'));assert.ok(modal.includes('generationTtsPaid'));
assert.ok(!context.generationSection().includes('<video'));
gen.status='needs_attention';gen.intro_approval={sha256:'hash'};context.generationDetail('g');
assert.ok(modal.includes('generationResume'));assert.ok(!modal.includes('id="generationPoll"'));
console.log('AI generation UI confirmation gate, pending-query and continuation recovery passed');
