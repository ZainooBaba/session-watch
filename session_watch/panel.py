"""Local monitor control page."""
PAGE = '''<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Session Watch</title>
<style>
:root{color-scheme:dark;--bg:#0d1820;--panel:#14232e;--line:#ffffff12;--muted:#91a5b3;--mint:#b3e8dc;--white:#f4f7f9}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--white);font:15px/1.55 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;-webkit-font-smoothing:antialiased}
main{max-width:1240px;padding:38px 40px 32px;margin:auto}header{display:flex;align-items:center;justify-content:space-between;gap:20px;margin-bottom:30px}.brand{display:flex;align-items:center;gap:13px}.mark{display:grid;place-items:center;width:38px;height:38px;border:1px solid #ffffff24;border-radius:12px;color:var(--mint);font-size:20px}h1{font-size:21px;font-weight:600;letter-spacing:-.7px;margin:0}header p{color:var(--muted);font-size:12px;margin:2px 0 0}.badge{display:inline-flex;align-items:center;gap:9px;font-size:12px;letter-spacing:.2px;color:#b0bec8;background:#ffffff05;border:1px solid #ffffff10;border-radius:30px;padding:7px 12px}.dot{height:7px;width:7px;border-radius:50%;background:#85929b;flex-shrink:0}.badge[data-state="active"]{color:#edcf81;background:#b4871410;border-color:#e4bd4b25}.badge[data-state="active"] .dot{background:#f3cd57;animation:watch-pulse 2.2s ease-in-out infinite}.badge[data-state="change"]{color:#ffb4b4;background:#d84d4d12;border-color:#e6606028}.badge[data-state="change"] .dot{background:#ff6464;box-shadow:0 0 9px #ff646438}.badge[data-state="action"]{color:#a7e6c0;background:#479d6c12;border-color:#71c59425}.badge[data-state="action"] .dot{background:#77daa0;box-shadow:0 0 9px #77daa025}@keyframes watch-pulse{0%,100%{opacity:1;box-shadow:0 0 0 0 #f3cd5735}50%{opacity:.45;box-shadow:0 0 0 4px #f3cd5700}}

.summary{display:flex;justify-content:space-between;align-items:center;gap:20px;margin-bottom:22px;padding:18px 22px;background:var(--panel);border:1px solid var(--line);border-radius:12px}#alert{font-size:14px;margin:0;font-weight:500}.subtle{font-size:12px;color:var(--muted);margin:4px 0 0}button{font:inherit;font-size:12px;font-weight:550;padding:10px 15px;border:1px solid #ffffff21;border-radius:8px;background:#ffffff06;color:var(--white);cursor:pointer;transition:background .15s,border-color .15s}button:hover{background:#ffffff10;border-color:#ffffff40}button:focus-visible,a:focus-visible{outline:2px solid var(--mint);outline-offset:4px}button:disabled{opacity:.45;cursor:wait}.primary{background:var(--mint);border-color:var(--mint);color:#102c25}.primary:hover{background:#c9f3e9;border-color:#c9f3e9}
.capture-card{border:1px solid var(--line);border-radius:14px;overflow:hidden;background:var(--panel)}.capture-head{padding:21px 24px;display:flex;justify-content:space-between;align-items:flex-start;gap:20px}.eyebrow{color:var(--muted);text-transform:uppercase;font-size:10px;letter-spacing:1.5px;font-weight:600;margin:0 0 5px}h2{font-weight:550;letter-spacing:-.4px;font-size:17px;margin:0}.capture-clock{text-align:right;color:var(--muted);font-size:12px;font-variant-numeric:tabular-nums}.capture-clock strong{color:var(--white);font-weight:500;display:block;margin-bottom:2px}.image-shell{position:relative;background:#0a1117;min-height:200px}.countdown-track{position:absolute;z-index:2;top:0;left:0;right:0;height:3px;background:#ffffff1a;overflow:hidden;pointer-events:none}.countdown-fill{height:100%;background:#fff;width:100%;transform-origin:left center;transform:scaleX(0);will-change:transform;box-shadow:0 0 10px #ffffff75}#full-screenshot{display:block}#latest-screenshot{display:block;width:100%;height:auto}#latest-screenshot[hidden]{display:none}.empty{display:grid;place-items:center;min-height:240px;color:var(--muted);font-size:13px}.capture-foot{padding:12px 24px;display:flex;align-items:center;justify-content:space-between;gap:15px;color:var(--muted);font-size:11px;border-top:1px solid var(--line)}#countdown-label{font-variant-numeric:tabular-nums;color:#d8e3eb}.session{display:flex;align-items:center;justify-content:space-between;gap:24px;padding:25px 0 0}.session h2{font-size:14px}.session p{font-size:12px;color:var(--muted);margin:5px 0 0}.actions{display:flex;flex-wrap:wrap;gap:8px}.bottom{margin-top:26px;padding-top:17px;border-top:1px solid var(--line);display:flex;justify-content:space-between;gap:20px;font-size:11px;color:var(--muted)}#result:empty,#message:empty{display:none}#result,#message{color:#e5c791;font-size:12px}time{font-variant-numeric:tabular-nums}.analysis-card{border:1px solid var(--line);border-radius:14px;background:var(--panel);padding:22px 24px;margin-top:22px}.analysis-head{display:flex;align-items:center;justify-content:space-between;gap:16px;margin-bottom:18px}.analysis-head time{color:var(--muted);font-size:11px}.analysis-grid{display:grid;grid-template-columns:1fr 1fr;gap:22px}.review-label{font-size:10px;color:var(--muted);letter-spacing:1px;text-transform:uppercase;margin:0 0 8px}.review-verdict{font-size:15px;font-weight:550;margin:0 0 7px}.review-reason{font-size:12px;color:#becbd4;margin:0;white-space:pre-wrap;overflow-wrap:anywhere}.evidence-quote{border-left:2px solid #b3e8dc50;padding-left:12px;font-size:12px;color:var(--muted);margin:12px 0 0;white-space:pre-wrap}.pager-line{border-top:1px solid var(--line);margin-top:20px;padding-top:15px;display:flex;justify-content:space-between;gap:15px;font-size:12px}.pager-line span{color:var(--muted)}details{margin-top:12px}summary{cursor:pointer;font-size:12px;color:var(--mint)}.pager-settings{display:flex;flex-wrap:wrap;gap:8px;margin-top:12px}input[type=password]{min-width:200px;flex:1;border:1px solid #ffffff24;background:#0d1820;border-radius:8px;padding:11px 12px;color:var(--white);font:12px system-ui}.pager-help{font-size:12px;color:var(--muted);margin:12px 0}.pager-help a{text-decoration:underline}.analysis-grid [data-verdict=interview_invite],.analysis-grid [data-verdict=possible_invite]{color:#ffb4b4}#pager-disable[hidden],#invite-evidence[hidden]{display:none}@media(max-width:720px){.analysis-grid{grid-template-columns:1fr}.analysis-card{padding:20px 16px}.analysis-head{align-items:flex-start;flex-direction:column}.pager-line{flex-direction:column;gap:5px}}
.app-actions{display:flex;gap:8px}.app-actions button{padding:6px 10px;font-size:11px;color:var(--muted)}.app-actions .stop-button{color:#ffb4b4}.bottom{align-items:center}a{color:inherit;text-decoration:none}@media(max-width:720px){main{padding:22px 16px}.summary,.session{align-items:flex-start;flex-direction:column}.summary button{width:100%}.capture-head{padding:18px 16px}.capture-clock{font-size:10px}.capture-foot{padding:12px 16px;font-size:10px}.actions{width:100%}.actions button{flex:1}.bottom{flex-direction:column;gap:6px}header p{font-size:10px}.badge{font-size:10px;padding:6px 9px}}
@media(prefers-reduced-motion:reduce){*{transition:none!important;animation:none!important}}
.inbox{margin:22px 0}.inbox-heading{display:flex;justify-content:space-between;align-items:center;margin-bottom:12px}.alert-card{padding:18px 20px;margin:10px 0;background:var(--panel);border:1px solid var(--line);border-left:3px solid #ff7777;border-radius:12px}.alert-card[data-category=auth_needed]{border-left-color:#77daa0}.alert-card[data-status=dismissed],.alert-card[data-status=resolved]{opacity:.7;border-left-color:#85929b}.alert-top{display:flex;justify-content:space-between;gap:14px;align-items:flex-start}.alert-title{font-size:14px;font-weight:600;margin:0}.alert-time,.alert-meta{font-size:11px;color:var(--muted);margin:5px 0}.alert-card p{overflow-wrap:anywhere}.alert-check{margin-top:13px}.alert-check strong{font-size:12px}.inbox-empty{font-size:13px;color:var(--muted);padding:15px 0}.alert-count{font-size:12px;color:var(--muted)}
</style>
</head>
<body><main>
<header><div class="brand"><span class="mark" aria-hidden="true">◷</span><div><h1>Session Watch</h1><p>A quiet eye on your dashboard</p></div></div><span class="badge" id="status-badge" data-state="idle" role="status" aria-live="polite"><span class="dot"></span><span id="status">Connecting</span></span></header>
<div class="summary"><div><p id="alert">Checking monitor status…</p><p class="subtle" id="alert-detail">Distinct sound alerts, until you acknowledge.</p><p id="message"></p></div><a href="#alerts-inbox">Review alerts ↓</a></div>
<section class="inbox" id="alerts-inbox" aria-label="Alert inbox"><div class="inbox-heading"><h2>Alerts</h2><span class="alert-count" id="alert-count"></span></div><div id="open-alerts"></div><details id="alert-history"><summary id="history-summary">Dismissed & resolved</summary><div id="past-alerts"></div></details></section>
<section class="capture-card" aria-label="Latest dashboard screenshot">
<div class="capture-head"><div><p class="eyebrow">Live dashboard</p><h2>Latest dashboard screenshot</h2></div><div class="capture-clock"><strong id="capture-status">Awaiting first capture</strong><time id="capture-time"></time></div></div>
<div class="image-shell"><div class="countdown-track" id="capture-progress" role="progressbar" aria-label="Time remaining until next screenshot" aria-valuemin="0" aria-valuemax="100"><div class="countdown-fill" id="countdown-fill"></div></div><a id="full-screenshot" target="_blank" rel="noopener"><img id="latest-screenshot" hidden alt="Most recent authenticated dashboard screenshot"></a><div id="empty-image" class="empty">Your next dashboard capture will appear here.</div></div>
<div class="capture-foot"><span id="countdown-label">Waiting for monitor…</span><span>Open image for full size ↗</span></div>
</section>
<section class="analysis-card" aria-label="Interview invitation review"><div class="analysis-head"><div><p class="eyebrow">Two local checks · alerts favor caution</p><h2>Latest change review</h2></div><time id="analysis-time"></time></div><div class="analysis-grid"><div><p class="review-label">1 · Is this a real change?</p><p class="review-verdict" id="change-verdict">Waiting for a change</p><p class="review-reason" id="change-reason">The first check distinguishes dashboard changes from an expired login.</p></div><div><p class="review-label">2 · Did an interview invite appear?</p><p class="review-verdict" id="invite-verdict">Not checked yet</p><p class="review-reason" id="invite-reason">Confirmed changes and possible invitations create local alerts. Both checks must confirm a new invite before PagerDuty is sent.</p><blockquote class="evidence-quote" id="invite-evidence" hidden></blockquote></div></div><div class="pager-line"><strong>PagerDuty</strong><span id="pager-status">Checking setup…</span></div><details><summary>PagerDuty setup</summary><p class="pager-help">Use your PagerDuty service’s <a href="https://docs.pagerduty.com/developer/events-api-v2-overview" target="_blank" rel="noopener">Events API v2 integration key</a>. Enabling sends only confirmed new interview invitations, including queued confirmed invites, to that service. Possible invites and login requests stay local. No dashboard images or private page text are sent.</p><div class="pager-settings"><input id="pager-key" type="password" autocomplete="new-password" aria-label="PagerDuty integration routing key" placeholder="Integration routing key"><button onclick="act('pager-config')">Enable PagerDuty</button><button id="pager-disable" hidden onclick="act('pager-disable')">Disable</button></div><p class="pager-help">The key stays on this Mac. PagerDuty uses your service’s on-call and notification rules. Acknowledge PagerDuty incidents there; dismissing an alert here silences its local sound.</p></details></section>
<section class="session"><div><h2>Sign-in</h2><p id="session-instruction">Checking your session…</p></div><div class="actions"><button class="primary" id="session-button" onclick="act('session')">Sign in</button></div></section>
<p id="result" role="status"></p><footer class="bottom"><span>Local only · Captures every 1–2 minutes</span><span>Basso: sign-in · Glass: dashboard change or invite</span><div class="app-actions"><button id="signout-button" onclick="act('signout')">Sign out</button><button class="stop-button" onclick="act('stop')">Stop app</button></div></footer>
</main>
<script>
const token='__TOKEN__';
let inboxSignature='';
let version=null,busy=false,screenshotVersion=null,monitor=null,serverOffset=0,receivedAt=0,appStopped=false;
const $=id=>document.getElementById(id);
const labels={auth_expired:'Sign-in required',content_change:'Dashboard changed',uncertain:'Change needs review',baseline_created:'Baseline saved',unchanged:'No dashboard change',interview_invite:'New interview invite',possible_invite:'Possible invite — review needed',not_interview_invite:'Not a new interview invite',not_run:'Not checked'};
function reviewText(element,result){element.textContent=(labels[result?.classification]||'Waiting for a change')+(result?.classification==='possible_invite'?' · uncertainty alert':typeof result?.confidence==='number'?' · '+Math.round(result.confidence*100)+'% confidence':'');element.dataset.verdict=result?.classification||''}
const centralTime=value=>new Date(value).toLocaleString('en-US',{timeZone:'America/Chicago',dateStyle:'medium',timeStyle:'medium'})+' Central';
function renderInbox(alerts){
 const signature=JSON.stringify(alerts);if(signature===inboxSignature)return;inboxSignature=signature;
 const opened=alerts.filter(a=>a.status==='open'),past=alerts.filter(a=>a.status!=='open');
 $('alert-count').textContent=opened.length+' open';$('history-summary').textContent='Dismissed & resolved · '+past.length;
 for(const [container,items] of [[$('open-alerts'),opened],[$('past-alerts'),past]]){
  container.replaceChildren();
  if(!items.length){const p=document.createElement('p');p.className='inbox-empty';p.textContent=container.id==='open-alerts'?'No open alerts.':'No alert history yet.';container.append(p)}
  for(const a of items){
   const card=document.createElement('article');card.className='alert-card';card.dataset.category=a.category;card.dataset.status=a.status;
   const top=document.createElement('div');top.className='alert-top';const heading=document.createElement('div');
   const title=document.createElement('h3');title.className='alert-title';title.textContent=({auth_needed:'Auth Needed',change:'Dashboard change',interview_invite:'New interview invite',review_needed:'Change needs review'})[a.category]||'Alert';
   const time=document.createElement('p');time.className='alert-time';time.textContent=centralTime(a.created_at);heading.append(title,time);top.append(heading);
   if(a.status==='open'){const button=document.createElement('button');button.textContent='Dismiss';button.onclick=()=>act('dismiss',{id:a.id,revision:a.revision});top.append(button)}
   card.append(top);
   const reason=document.createElement('p');reason.className='review-reason';reason.textContent=a.reason;card.append(reason);
   if(a.category!=='auth_needed'){
    for(const [label,check] of [['1 · Change check',a.stage1],['2 · Invite check',a.stage2]]){
     const block=document.createElement('div');block.className='alert-check';const verdict=document.createElement('strong');verdict.textContent=label+' — '+(labels[check.classification]||'Waiting')+(typeof check.confidence==='number'?' · '+Math.round(check.confidence*100)+'%':'');
     const detail=document.createElement('p');detail.className='review-reason';detail.textContent=check.reason||'No additional explanation.';block.append(verdict,detail);card.append(block);
    }
    if(a.stage2.evidence){const quote=document.createElement('blockquote');quote.className='evidence-quote';quote.textContent=a.stage2.evidence;card.append(quote)}
   }
   const meta=document.createElement('p');meta.className='alert-meta';meta.textContent=a.category==='auth_needed'?'Monitoring and further notifications are paused until sign-in succeeds.':a.checking_invite?'Second check is in progress…':a.pager_event_id?'PagerDuty: '+(a.pager_delivery?.status==='accepted'?'accepted':a.pager_delivery?.error||'queued for delivery'):'Local alert · no PagerDuty notification';
   if(a.status==='dismissed')meta.textContent+=' · Dismissed '+centralTime(a.dismissed_at);
   if(a.status==='resolved')meta.textContent+=' · Sign-in restored '+centralTime(a.resolved_at);
   card.append(meta);container.append(card);
  }
 }
}
function paintCountdown(){
 if(appStopped)return;
 const fill=$('countdown-fill'),bar=$('capture-progress'),label=$('countdown-label');
 let fraction=0,text='Monitoring paused';
 if(receivedAt&&Date.now()-receivedAt>10000){text='Connection lost — countdown paused'}
 else if(monitor?.login_open){text='Waiting for sign-in'}
 else if(monitor?.monitoring){
  const timing=monitor.timing;
  if(timing?.phase==='waiting'&&timing.next_capture_at){
   const remaining=Math.max(0,timing.next_capture_at*1000-(Date.now()+serverOffset));
   fraction=Math.min(1,remaining/(timing.interval_seconds*1000));
   const seconds=Math.ceil(remaining/1000);
   text=seconds>0?(timing.last_error?'Retrying capture in ':'Next screenshot in ')+Math.floor(seconds/60)+':'+String(seconds%60).padStart(2,'0'):'Starting next capture…';
  }else if(timing?.phase==='analyzing'){text='Comparing latest capture…'}
  else if(timing?.phase==='classifying_invite'){text='Checking for interview invitations…'}
  else{text='Capturing dashboard…'}
 }
 fill.style.transform='scaleX('+fraction+')';bar.setAttribute('aria-valuenow',String(Math.round(fraction*100)));bar.setAttribute('aria-valuetext',text);label.textContent=text;
}
async function refresh(){
 if(appStopped)return;
 const start=Date.now(),response=await fetch('/status',{cache:'no-store'});
 if(!response.ok)throw Error('Status unavailable');
 const s=await response.json();if(appStopped)return;monitor=s;receivedAt=Date.now();serverOffset=s.server_time*1000-(start+receivedAt)/2;
 version=s.alert?.version??null;
 renderInbox(s.alerts||[]);
 $('status').textContent=s.indicator.label;
 $('status-badge').dataset.state=s.indicator.state;
 $('alert').textContent=s.indicator.state==='change'?(s.indicator.label==='Interview invite'?'A new interview invitation was detected':s.indicator.label==='Possible invite'?'Possible interview invitation — review your dashboard':'A dashboard change was detected'):s.indicator.state==='action'?(s.indicator.label==='Sign-in needed'?'Finish sign-in to continue':'Your attention is needed'):s.monitoring?'All quiet. We’re keeping watch.':'Monitoring is paused';
 $('alert-detail').textContent=s.auth_paused?'Sign-in is required. Dismiss the auth alert to silence it; sign in to resume.':s.alert?'Sound repeats while alerts remain open. Review and dismiss each item below.':'You’ll hear a distinct sound when something needs you.';
 $('message').textContent=s.message||s.timing?.last_error||'';
 $('session-instruction').textContent=s.session.instruction;
 if(!busy){$('session-button').textContent=s.session.label;$('signout-button').disabled=s.signed_out;}
 $('empty-image').textContent=s.signed_out?'Signed out. Sign in to see your dashboard.':'Your next dashboard capture will appear here.';
 if(s.analysis){reviewText($('change-verdict'),s.analysis.stage1);reviewText($('invite-verdict'),s.analysis.stage2);$('change-reason').textContent=s.analysis.stage1.reason||'No extra explanation.';$('invite-reason').textContent=s.analysis.stage2.reason||'No extra explanation.';$('analysis-time').textContent=centralTime(s.analysis.time);$('analysis-time').dateTime=s.analysis.time;$('invite-evidence').textContent=s.analysis.stage2.evidence||'';$('invite-evidence').hidden=!s.analysis.stage2.evidence}
 else if(s.signed_out){$('change-verdict').textContent='Signed out';$('invite-verdict').textContent='Not checked';$('change-reason').textContent='Sign in to review dashboard changes.';$('invite-reason').textContent='';$('invite-evidence').hidden=true;$('analysis-time').textContent=''}
 const delivery=s.pager.delivery;
 $('pager-status').textContent=!s.pager.configured?(s.pager.has_key?'Disabled':'Setup needed')+(s.pager.pending_count?' · '+s.pager.pending_count+' alert(s) queued':''):delivery?.status==='accepted'?'Latest invite alert accepted by PagerDuty':s.pager.pending_count?s.pager.pending_count+' confirmed invite alert(s) queued for delivery':s.analysis?.stage2?.classification==='possible_invite'?'Possible invite stays local · only confirmed new invites page you':'Enabled · confirmed new invites only';
 $('pager-disable').hidden=!s.pager.enabled;$('pager-key').placeholder=s.pager.has_key?'Key saved locally — enter only to replace':'Integration routing key';
 if(s.screenshot){
  const shot=s.screenshot,image=$('latest-screenshot');
  $('capture-status').textContent='Last captured';$('capture-time').dateTime=shot.captured_at;$('capture-time').textContent=centralTime(shot.captured_at);
  if(screenshotVersion!==shot.version){image.src=shot.url;$('full-screenshot').href=shot.url;screenshotVersion=shot.version}
  image.hidden=false;$('empty-image').style.display='none';
 }else{$('capture-status').textContent='Awaiting first capture';$('latest-screenshot').hidden=true;$('capture-time').textContent='';$('empty-image').style.display='grid';screenshotVersion=null}
 paintCountdown();
}
async function act(action,extra={}){
 if(busy||appStopped)return;if(action==='signout'&&!confirm('Sign out of Session Watch? Monitoring and sounds will stop, and the login saved on this Mac will be removed. Existing logs stay on this Mac.'))return;if(action==='stop'&&!confirm('Stop Session Watch? Monitoring, alert sounds, and this control service will stop. Your saved login will be kept.'))return;const step=monitor?.session?.step;if(action==='session'&&!step)return;busy=true;document.querySelectorAll('button').forEach(b=>b.disabled=true);$('result').textContent=action==='session'?(step==='finish'?'Checking your sign-in and starting monitoring…':step==='resume'?'Resuming monitoring…':'Opening the sign-in browser…'):(action==='pager-config'||action==='pager-disable')?'Saving PagerDuty settings…':action==='signout'?'Signing out…':action==='stop'?'Stopping Session Watch…':'Acknowledging alert…';
 try{
  const endpoint=action==='pager-disable'?'pager-config':action;const response=await fetch('/'+endpoint,{method:'POST',headers:{'Content-Type':'application/json','X-Session-Watch-Token':token},body:JSON.stringify({version,step,...extra,...(action==='pager-config'?{enabled:true,routing_key:$('pager-key').value}:action==='pager-disable'?{enabled:false}:{})})});
  const data=await response.json();if(!response.ok)throw Error(data.error);
  if(action==='pager-config'||action==='pager-disable'){$('pager-key').value='';$('result').textContent=action==='pager-config'?'PagerDuty enabled. Queued alerts will be delivered.':'PagerDuty disabled. Local monitoring continues.';await refresh();return}
  if(action==='stop'){appStopped=true;monitor=null;$('status').textContent='Stopped';$('status-badge').dataset.state='idle';$('alert').textContent='Session Watch has stopped';$('alert-detail').textContent='Monitoring and sounds are off. Your saved login is kept.';$('countdown-fill').style.transform='scaleX(0)';$('countdown-label').textContent='App stopped';$('result').textContent='You can close this page. Ask me to start Session Watch when you need it again.';return}
  if(action==='signout'){$('result').textContent='Signed out. Your saved local login was removed.';await refresh();return}
  $('result').textContent=action==='dismiss'?'Alert dismissed.':action==='acknowledge'?'Alert acknowledged.':step==='signin'?'Sign in in the opened browser. When finished, click “I’m signed in” here.':step==='finish'?'Session saved. Monitoring has resumed.':'Monitoring has resumed.';
 }catch(error){$('result').textContent=error.message}
 finally{busy=false;if(!appStopped){document.querySelectorAll('button').forEach(b=>b.disabled=false);await refresh().catch(disconnected)}}
}
function disconnected(){if(appStopped)return;const state=monitor?.indicator?.state;const latched=state==='change'||state==='action';$('status').textContent=latched?monitor.indicator.label+' · offline':'Disconnected';$('status-badge').dataset.state=latched?state:'idle';receivedAt=Date.now()-11000;paintCountdown()}
refresh().catch(disconnected);setInterval(()=>refresh().catch(disconnected),2000);setInterval(paintCountdown,100);
</script>
</body></html>'''
