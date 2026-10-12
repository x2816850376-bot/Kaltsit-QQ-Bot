const assert=require('node:assert/strict');
const guard=require('../tulpa-tools-only.cjs');
for(const name of ['exec_command','shell','apply_patch','functions.exec','mcp__other__read_file']) {
  assert.equal(guard.decision({tool_name:name,tool_input:{command:'whoami'}}).allow,false);
}
assert.equal(guard.decision({tool_name:'web.run',tool_input:{open:[{ref_id:'http://127.0.0.1:3000/token'}]}}).allow,false);
assert.equal(guard.decision({tool_name:'web.run',tool_input:{search_query:[{q:'明日方舟官方活动'}]}}).allow,true);
assert.equal(guard.decision({tool_name:'mcp__kaltsit_bot__get_world_knowledge',tool_input:{}}).allow,true);
console.log('Tool hook isolation passed');
