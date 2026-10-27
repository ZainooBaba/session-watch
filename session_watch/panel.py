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
.capture-card{border:1px solid var(--line);border-radius:14px;overflow:hidden;background:var(--panel)}.capture-head{padding:21px 24px;display:flex;justify-content:space-between;align-items:flex-start;gap:20px}.eyebrow{color:var(--muted);text-transform:uppercase;font-size:10px;letter-spacing:1.5px;font-weight:600;margin:0 0 5px}h2{font-weight:550;letter-spacing:-.4px;font-size:17px;margin:0}.capture-clock{text-align:right;color:var(--muted);font-size:12px;font-variant-numeric:tabular-nums}.capture-clock strong{color:var(--white);font-weight:500;display:block;margin-bottom:2px}.image-shell{position:relative;background:#0a1117;min-height:200px}.countdown-track{position:absolute;z-index:2;top:0;left:0;right:0;height:3px;background:#ffffff1a;overflow:hidden;pointer-events:none}.countdown-fill{height:100%;background:#fff;width:100%;transform-origin:left center;transform:scaleX(0);will-change:transform;box-shadow:0 0 10px #ffffff75}#full-screenshot{display:block}#latest-screenshot{display:block;width:100%;height:auto}#latest-screenshot[hidden]{display:none}.empty{display:grid;place-items:center;min-height:240px;color:var(--muted);font-size:13px}.capture-foot{padding:12px 24px;display:flex;align-items:center;justify-content:space-between;gap:15px;color:var(--muted);font-size:11px;border-top:1px solid var(--line)}#countdown-label{font-variant-numeric:tabular-nums;color:#d8e3eb}.session{display:flex;align-items:center;justify-content:space-between;gap:24px;padding:25px 0 0}.session h2{font-size:14px}.session p{font-size:12px;color:var(--muted);margin:5px 0 0}.actions{display:flex;flex-wrap:wrap;gap:8px}.bottom{margin-top:26px;padding-top:17px;border-top:1px solid var(--line);display:flex;justify-content:space-between;gap:20px;font-size:11px;color:var(--muted)}#result:empty,#message:empty{display:none}#result,#message{color:#e5c791;font-size:12px}time{font-variant-numeric:tabular-nums}.app-actions{display:flex;gap:8px}.app-actions button{padding:6px 10px;font-size:11px;color:var(--muted)}.app-actions .stop-button{color:#ffb4b4}.bottom{align-items:center}a{color:inherit;text-decoration:none}@media(max-width:720px){main{padding:22px 16px}.summary,.session{align-items:flex-start;flex-direction:column}.summary button{width:100%}.capture-head{padding:18px 16px}.capture-clock{font-size:10px}.capture-foot{padding:12px 16px;font-size:10px}.actions{width:100%}.actions button{flex:1}.bottom{flex-direction:column;gap:6px}header p{font-size:10px}.badge{font-size:10px;padding:6px 9px}}
@media(prefers-reduced-motion:reduce){*{transition:none!important;animation:none!important}}
</style>
</head>
<body><main>
<header><div class="brand"><span class="mark" aria-hidden="true">◷</span><div><h1>Session Watch</h1><p>A quiet eye on your dashboard</p></div></div><span class="badge" id="status-badge" data-state="idle" role="status" aria-live="polite"><span class="dot"></span><span id="status">Connecting</span></span></header>
<div class="summary"><div><p id="alert">Checking monitor status…</p><p class="subtle" id="alert-detail">Distinct sound alerts, until you acknowledge.</p><p id="message"></p></div><button id="acknowledge" onclick="act('acknowledge')">Silence & acknowledge</button></div>
<section class="capture-card" aria-label="Latest dashboard screenshot">
<div class="capture-head"><div><p class="eyebrow">Live dashboard</p><h2>Latest dashboard screenshot</h2></div><div class="capture-clock"><strong id="capture-status">Awaiting first capture</strong><time id="capture-time"></time></div></div>
<div class="image-shell"><div class="countdown-track" id="capture-progress" role="progressbar" aria-label="Time remaining until next screenshot" aria-valuemin="0" aria-valuemax="100"><div class="countdown-fill" id="countdown-fill"></div></div><a id="full-screenshot" target="_blank" rel="noopener"><img id="latest-screenshot" hidden alt="Most recent authenticated dashboard screenshot"></a><div id="empty-image" class="empty">Your next dashboard capture will appear here.</div></div>
<div class="capture-foot"><span id="countdown-label">Waiting for monitor…</span><span>Open image for full size ↗</span></div>
</section>
<section class="session"><div><h2>Sign-in</h2><p id="session-instruction">Checking your session…</p></div><div class="actions"><button class="primary" id="session-button" onclick="act('session')">Sign in</button></div></section>
<p id="result" role="status"></p><footer class="bottom"><span>Local only · Captures every 1–2 minutes</span><span>Basso: login required · Glass: change detected</span><div class="app-actions"><button id="signout-button" onclick="act('signout')">Sign out</button><button class="stop-button" onclick="act('stop')">Stop app</button></div></footer>
</main>
<script>
const token='__TOKEN__';
let version=null,busy=false,screenshotVersion=null,monitor=null,serverOffset=0,receivedAt=0,appStopped=false;
const $=id=>document.getElementById(id);
const centralTime=value=>new Date(value).toLocaleString('en-US',{timeZone:'America/Chicago',dateStyle:'medium',timeStyle:'medium'})+' Central';
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
 $('status').textContent=s.indicator.label;
 $('status-badge').dataset.state=s.indicator.state;
 $('alert').textContent=s.indicator.state==='change'?'A dashboard change was detected':s.indicator.state==='action'?(s.indicator.label==='Sign-in needed'?'Finish sign-in to continue':'Your attention is needed'):s.monitoring?'All quiet. We’re keeping watch.':'Monitoring is paused';
 $('alert-detail').textContent=s.alert?'Your alert will repeat until acknowledged.':'You’ll hear a distinct sound when something needs you.';
 $('message').textContent=s.message||s.timing?.last_error||'';
 $('session-instruction').textContent=s.session.instruction;
 if(!busy){$('session-button').textContent=s.session.label;$('signout-button').disabled=s.signed_out;}
 $('empty-image').textContent=s.signed_out?'Signed out. Sign in to see your dashboard.':'Your next dashboard capture will appear here.';
 if(s.screenshot){
  const shot=s.screenshot,image=$('latest-screenshot');
  $('capture-status').textContent='Last captured';$('capture-time').dateTime=shot.captured_at;$('capture-time').textContent=centralTime(shot.captured_at);
  if(screenshotVersion!==shot.version){image.src=shot.url;$('full-screenshot').href=shot.url;screenshotVersion=shot.version}
  image.hidden=false;$('empty-image').style.display='none';
 }else{$('capture-status').textContent='Awaiting first capture';$('latest-screenshot').hidden=true;$('capture-time').textContent='';$('empty-image').style.display='grid';screenshotVersion=null}
 paintCountdown();
}
async function act(action){
 if(busy||appStopped)return;if(action==='signout'&&!confirm('Sign out of Session Watch? Monitoring and sounds will stop, and the login saved on this Mac will be removed. Existing logs stay on this Mac.'))return;if(action==='stop'&&!confirm('Stop Session Watch? Monitoring, alert sounds, and this control service will stop. Your saved login will be kept.'))return;const step=monitor?.session?.step;if(action==='session'&&!step)return;busy=true;document.querySelectorAll('button').forEach(b=>b.disabled=true);$('result').textContent=action==='session'?(step==='finish'?'Checking your sign-in and starting monitoring…':step==='resume'?'Resuming monitoring…':'Opening the sign-in browser…'):action==='signout'?'Signing out…':action==='stop'?'Stopping Session Watch…':'Acknowledging alert…';
 try{
  const response=await fetch('/'+action,{method:'POST',headers:{'Content-Type':'application/json','X-Session-Watch-Token':token},body:JSON.stringify({version,step})});
  const data=await response.json();if(!response.ok)throw Error(data.error);
  if(action==='stop'){appStopped=true;monitor=null;$('status').textContent='Stopped';$('status-badge').dataset.state='idle';$('alert').textContent='Session Watch has stopped';$('alert-detail').textContent='Monitoring and sounds are off. Your saved login is kept.';$('countdown-fill').style.transform='scaleX(0)';$('countdown-label').textContent='App stopped';$('result').textContent='You can close this page. Ask me to start Session Watch when you need it again.';return}
  if(action==='signout'){$('result').textContent='Signed out. Your saved local login was removed.';await refresh();return}
  $('result').textContent=action==='acknowledge'?'Alert acknowledged.':step==='signin'?'Sign in in the opened browser. When finished, click “I’m signed in” here.':step==='finish'?'Session saved. Monitoring has resumed.':'Monitoring has resumed.';
 }catch(error){$('result').textContent=error.message}
 finally{busy=false;if(!appStopped){document.querySelectorAll('button').forEach(b=>b.disabled=false);await refresh().catch(disconnected)}}
}
function disconnected(){if(appStopped)return;const state=monitor?.indicator?.state;const latched=state==='change'||state==='action';$('status').textContent=latched?monitor.indicator.label+' · offline':'Disconnected';$('status-badge').dataset.state=latched?state:'idle';receivedAt=Date.now()-11000;paintCountdown()}
refresh().catch(disconnected);setInterval(()=>refresh().catch(disconnected),2000);setInterval(paintCountdown,100);
</script>
</body></html>'''
