// Test-window-only per-turn cap, composed with the existing privacy/rate hook.
const fs=require('node:fs');
const path=require('node:path');
const cp=require('node:child_process');
const root=path.resolve(__dirname,'..');
const base=path.join(root,'tulpa-tools-only.cjs');
const {decision}=require(base);
function reserve(prefix){
  const directory=path.join(root,'runtime','test','web-budgets');
  if(typeof prefix!=='string'||path.dirname(path.resolve(prefix))!==directory||!/^[a-f0-9]{32}$/.test(path.basename(prefix)))return false;
  fs.mkdirSync(directory,{recursive:true});
  for(let i=0;i<4;i++){
    try{const fd=fs.openSync(prefix+'.'+i+'.slot','wx');fs.closeSync(fd);return true;}
    catch(error){if(error.code!=='EEXIST')return false;}
  }
  return false;
}
function deny(reason){return {hookSpecificOutput:{hookEventName:'PreToolUse',permissionDecision:'deny',permissionDecisionReason:reason}};}
function handle(event){
  const allowed=decision(event);
  if(!allowed.allow)return deny(allowed.reason);
  if(!allowed.web)return deny('This isolated text window has no QQ send tools');
  if(!reserve(process.env.KALTSIT_TEST_WEB_BUDGET_FILE))return deny('Per-turn public lookup budget reached; answer from existing evidence or state the remaining gap');
  // Keep the original URL/privacy checks and minute/hour limits as well.
  const child=cp.spawnSync(process.execPath,[base],{input:JSON.stringify(event),encoding:'utf8',timeout:4000,windowsHide:true});
  if(child.error||child.status!==0)return deny('Public lookup guard unavailable');
  try{return JSON.parse(child.stdout);}catch{return deny('Invalid public lookup guard result');}
}
module.exports={reserve,handle};
if(require.main===module){
  let input='';process.stdin.setEncoding('utf8');
  process.stdin.on('data',chunk=>{input+=chunk;if(input.length>1024*1024)process.exit(2);});
  process.stdin.on('end',()=>{let result;try{result=handle(JSON.parse(input));}catch{result=deny('Invalid lookup input');}process.stdout.write(JSON.stringify(result));});
}
