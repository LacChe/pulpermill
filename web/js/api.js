/* Pulpermill page: Talking to the backend: requests with a deadline, job polling, schema and limits, connection test. */
const base=()=>$('#base').value.trim().replace(/\/+$/,'');
/* Every request has a deadline: a connection that stalls (a tunnel hiccup, a laptop waking up) would otherwise never fail,
   and the page would wait forever with no notice. A timeout is an ordinary failure, so polling rides it out like any other. */
let API_TIMEOUT_MS=30000;
const apiSignal=()=>typeof AbortSignal!=='undefined'&&AbortSignal.timeout?AbortSignal.timeout(API_TIMEOUT_MS):undefined;
async function api(path,opt={}){
  if(!base())throw fail('Enter the backend URL first.');
  try{
    const r=await fetch(base()+path,{...opt,signal:apiSignal(),headers:{'ngrok-skip-browser-warning':'1',...(opt.body?{'Content-Type':'application/json'}:{})}});
    if(!r.ok)throw Object.assign(fail('Backend returned {status}: {body}',{status:r.status,body:(await r.text()).slice(0,300)}),{status:r.status});
    return await r.json();
  }catch(e){
    if(e&&(e.name==='TimeoutError'||e.name==='AbortError'))throw fail('The backend did not answer within {s} seconds.',{s:Math.round(API_TIMEOUT_MS/1000)});
    throw e;
  }
}
/* what the backend said went wrong, as something msg() can show */
const apiErr=r=>r.error_msg||r.error;

/* Asks how a job is going. A dropped connection is ridden out: the page shows a "Lost contact" notice and keeps asking until the
   backend answers again. After POLL_GIVEUP_MS without an answer it throws an error marked gaveUp (the job may still be running there). */
let POLL_GIVEUP_MS=5*60*1000;
/* Answers that mean "nothing is listening there" rather than "the backend refused": the tunnel's own error pages (404 when the tunnel
   is offline, 502/503/504 when it cannot reach the backend). Anything else, like a 500 or a 422, is a real error and is not retried. */
const OUTAGE_STATUS=[404,502,503,504];
const LOST_CONTACT='Lost contact with the backend. Retrying… (a running job keeps going there)';
async function pollJob(id){
  let since=null;
  for(;;){
    try{
      const r=await api('/job/'+id);
      if(since!==null&&st.banner&&st.banner.t===LOST_CONTACT){st.banner='';drawTop()}
      return r;
    }catch(e){
      if(!base())throw e;                          // no address at all is not an outage
      if(e&&e.status&&!OUTAGE_STATUS.includes(e.status)){          // the backend answered with a real error: show it now, do not retry
        if(st.banner&&st.banner.t===LOST_CONTACT){st.banner='';drawTop()}
        throw e;
      }
      if(since===null)since=Date.now();
      if(Date.now()-since>=POLL_GIVEUP_MS){
        if(st.banner&&st.banner.t===LOST_CONTACT){st.banner='';drawTop()}
        throw Object.assign(new Error('lost contact'),{gaveUp:true});
      }
      if(!st.banner||st.banner.t!==LOST_CONTACT){st.banner=mk(LOST_CONTACT);drawTop()}
      await sleep(2500);
    }
  }
}
/* These two throw when the backend cannot answer; the callers show it (testConnection shows it in the connection area). */
async function loadSchema(){
  SCH=await api('/schema');
  try{localStorage.setItem('pmcg_schema',JSON.stringify(SCH))}catch(e){/* only a cache so saved cards still edit while offline; losing it is harmless */}
}
async function loadLimits(){st.limits=await api('/limits');await loadSchema();if(!st.busy)draw();else updateCounters()}

/* Checks the backend and its settings; whatever goes wrong is shown in the connection area, never swallowed. */
async function testConnection(){
  st.conn={k:'checking'};drawConn();
  try{const r=await api('/health');await loadLimits();st.conn={k:'ok',model:r.model};drawConn()}
  catch(e){st.conn={k:'fail',why:e.m||e.message};drawConn()}
}
