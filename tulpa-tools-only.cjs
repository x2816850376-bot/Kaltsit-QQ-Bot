// Trusted dispatcher. Only public web reading and the existing chat tools.
const fs=require('node:fs');
const path=require('node:path');
function decision(event){
  const name=event?.tool_name??'';
  const names=['list_chat_groups','list_chat_sessions','get_chat_session','start_chat_session','wait_chat_messages','send_chat_message','stop_chat_session','read_chat_image','list_chat_stickers','read_chat_sticker','note_chat_sticker','send_chat_sticker','get_operator_knowledge','get_community_knowledge','get_world_knowledge','get_canonical_knowledge'];
  const allowed=new Set(names.map(n=>'mcp__kaltsit_bot__'+n));
  if(allowed.has(name))return {allow:true,web:false,reason:'Authorized Tulpa live chat tool'};
  if(!['web.run','web_search','web__run'].includes(name))return {allow:false,reason:'Only chat tools and public web reading are permitted'};
  let args=event.tool_input;
  if(typeof args==='string'){try{args=JSON.parse(args);}catch{return {allow:false,reason:'Invalid web arguments'};}}
  if(!args || typeof args!=='object' || Array.isArray(args))return {allow:false,reason:'Invalid web arguments'};
  // The search service is hosted; never direct it to private/local URLs or credentials.
  const encoded=JSON.stringify(args);
  if(encoded.length>12000 || /(?:file|ftp|data|javascript):|(?:localhost|127\.0\.0\.1|\[::1\])|(?:auth\.json|SESSDATA|OPENAI_API_KEY)/i.test(encoded))return {allow:false,reason:'Private data is not a web query'};
  for(const row of args.open??[]){
    const ref=row.ref_id??row.ref??'';
    if(/^https?:\/\//i.test(ref)){
      let u;try{u=new URL(ref);}catch{return {allow:false,reason:'Invalid URL'};}
      const h=u.hostname;
      if(u.username||u.password||!h.includes('.')||h.endsWith('.local')||h.endsWith('.internal')||/^(?:\d+\.){3}\d+$/.test(h)||h.includes(':'))return {allow:false,reason:'Only public hostname URLs'};
    }else if(!/^turn[\w-]+$/i.test(ref))return {allow:false,reason:'Invalid public reference'};
  }
  return {allow:true,web:true,reason:'Authorized public knowledge lookup'};
}
function budget(){
  const file=path.join(__dirname,'runtime','group-'+(process.env.KALTSIT_GROUP||'test'),'web-tool-budget.json');const now=Date.now();
  let stamps=[];try{stamps=JSON.parse(fs.readFileSync(file,'utf8')).stamps.filter(x=>Number.isFinite(x)&&now-x<3600000);}catch{}
  if(stamps.length>=40 || stamps.filter(x=>now-x<60000).length>=12)return false;
  fs.mkdirSync(path.dirname(file),{recursive:true});fs.writeFileSync(file,JSON.stringify({stamps:[...stamps,now]}));return true;
}
module.exports={decision};
if(require.main===module){
  let input='';process.stdin.setEncoding('utf8');
  process.stdin.on('data',chunk=>{input+=chunk;if(input.length>1024*1024)process.exit(2);});
  process.stdin.on('end',()=>{
    let result={allow:false,reason:'Invalid hook input'};try{result=decision(JSON.parse(input));if(result.allow&&result.web&&!budget())result={allow:false,reason:'Public lookup budget reached'};}catch{result={allow:false,reason:'Invalid web input or budget unavailable'};}
    console.log(JSON.stringify({hookSpecificOutput:{hookEventName:'PreToolUse',permissionDecision:result.allow?'allow':'deny',permissionDecisionReason:result.reason}}));
  });
}
