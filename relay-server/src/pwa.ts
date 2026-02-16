// PWA frontend — inline HTML/JS/CSS served from the Worker

export const APP_HTML = `<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,maximum-scale=1">
<meta name="theme-color" content="#1a1a2e">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
<title>Teams Mentions</title>
<link rel="manifest" href="/manifest.json">
<style>
*{box-sizing:border-box;margin:0;padding:0}
:root{--bg:#1a1a2e;--surface:#16213e;--card:#0f3460;--card-read:#16213e;--accent:#e94560;--text:#eee;--text-dim:#888;--border:#233554}
body{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;background:var(--bg);color:var(--text);min-height:100dvh;padding-bottom:env(safe-area-inset-bottom)}
header{position:sticky;top:0;z-index:10;background:var(--surface);border-bottom:1px solid var(--border);padding:12px 16px}
header h1{font-size:18px;font-weight:600}
.toolbar{display:flex;gap:8px;margin-top:8px;align-items:center;flex-wrap:wrap}
.toolbar select,.toolbar button{background:var(--card);color:var(--text);border:1px solid var(--border);border-radius:6px;padding:6px 10px;font-size:14px;cursor:pointer}
.toolbar button.active{background:var(--accent);border-color:var(--accent)}
.toolbar .spacer{flex:1}
#status{font-size:12px;color:var(--text-dim);padding:4px 16px;background:var(--surface)}
#list{padding:8px}
.notif{background:var(--card);border-radius:8px;padding:12px;margin-bottom:8px;border-left:4px solid var(--accent);cursor:pointer;transition:opacity .2s}
.notif.read{background:var(--card-read);border-left-color:var(--border);opacity:.6}
.notif-header{display:flex;justify-content:space-between;align-items:center;margin-bottom:4px}
.notif-pc{font-size:11px;background:var(--accent);color:#fff;border-radius:4px;padding:1px 6px;font-weight:600}
.notif.read .notif-pc{background:var(--text-dim)}
.notif-time{font-size:11px;color:var(--text-dim)}
.notif-sender{font-size:14px;font-weight:600;margin-bottom:2px}
.notif-channel{font-size:12px;color:var(--text-dim);margin-bottom:4px}
.notif-msg{font-size:13px;line-height:1.4;word-break:break-word}
.empty{text-align:center;color:var(--text-dim);padding:40px 16px;font-size:15px}
.badge{background:var(--accent);color:#fff;border-radius:10px;padding:1px 7px;font-size:12px;font-weight:600;margin-left:6px}
</style>
</head>
<body>
<header>
  <h1>Teams Mentions <span id="unreadBadge" class="badge" hidden>0</span></h1>
  <div class="toolbar">
    <select id="pcFilter"><option value="">\u3059\u3079\u3066</option></select>
    <button id="unreadBtn" class="active">\u672a\u8aad</button>
    <button id="allBtn">\u5168\u4ef6</button>
    <div class="spacer"></div>
    <button id="refreshBtn">\u26f3 \u66f4\u65b0</button>
  </div>
</header>
<div id="status">\u8d77\u52d5\u4e2d...</div>
<div id="list"></div>

<script>
(function(){
  const API_KEY = localStorage.getItem("api_key") || "";
  if(!API_KEY){
    const k = prompt("\u63a5\u7d9a\u7528API\u30ad\u30fc\u3092\u5165\u529b\u3057\u3066\u304f\u3060\u3055\u3044:");
    if(k){ localStorage.setItem("api_key",k); location.reload(); }
    return;
  }

  const $list = document.getElementById("list");
  const $status = document.getElementById("status");
  const $pcFilter = document.getElementById("pcFilter");
  const $unreadBtn = document.getElementById("unreadBtn");
  const $allBtn = document.getElementById("allBtn");
  const $refreshBtn = document.getElementById("refreshBtn");
  const $badge = document.getElementById("unreadBadge");

  let notifications = [];
  let filterUnread = true;
  let filterPc = "";
  let knownIds = new Set();
  let pollTimer = null;

  const headers = {"Authorization":"Bearer "+API_KEY,"Content-Type":"application/json"};

  $unreadBtn.onclick = ()=>{ filterUnread=true; $unreadBtn.classList.add("active"); $allBtn.classList.remove("active"); render(); };
  $allBtn.onclick = ()=>{ filterUnread=false; $allBtn.classList.add("active"); $unreadBtn.classList.remove("active"); render(); };
  $pcFilter.onchange = ()=>{ filterPc=$pcFilter.value; render(); };
  $refreshBtn.onclick = ()=>fetchNotifications();

  async function fetchNotifications(){
    try{
      const r = await fetch("/api/notifications",{headers});
      if(r.status===401){ localStorage.removeItem("api_key"); location.reload(); return; }
      const data = await r.json();
      const list = data.notifications || [];
      // detect new unreads
      const newUnreads = list.filter(n=>n.status==="unread"&&!knownIds.has(n.id));
      notifications = list;
      knownIds = new Set(list.map(n=>n.id));

      // update PC filter options
      const pcs = [...new Set(list.map(n=>n.pc_name))].sort();
      const cur = $pcFilter.value;
      $pcFilter.innerHTML = '<option value="">\\u3059\\u3079\\u3066</option>' + pcs.map(p=>'<option value="'+p+'">'+p+'</option>').join("");
      $pcFilter.value = cur;

      // badge
      const unreadCount = list.filter(n=>n.status==="unread").length;
      if(unreadCount>0){ $badge.textContent=unreadCount; $badge.hidden=false; } else { $badge.hidden=true; }

      // browser notification for new unreads
      if(newUnreads.length>0 && Notification.permission==="granted"){
        for(const n of newUnreads.slice(0,3)){
          new Notification("Teams: "+n.sender+" ("+n.pc_name+")",{body:n.channel?n.channel+"\\n"+n.message:n.message,icon:"/icon-192.png",tag:n.id});
        }
      }

      $status.textContent = "\\u901a\\u77e5: "+list.length+"\\u4ef6 (\\u672a\\u8aad: "+unreadCount+"\\u4ef6) \\u2014 "+new Date().toLocaleTimeString("ja-JP");
      render();
    }catch(e){
      $status.textContent = "\\u30a8\\u30e9\\u30fc: "+e.message;
    }
  }

  function render(){
    let filtered = notifications;
    if(filterUnread) filtered = filtered.filter(n=>n.status==="unread");
    if(filterPc) filtered = filtered.filter(n=>n.pc_name===filterPc);
    // newest first
    filtered.sort((a,b)=>b.timestamp.localeCompare(a.timestamp));

    if(filtered.length===0){
      $list.innerHTML = '<div class="empty">'+(filterUnread?"\\u672a\\u8aad\\u306e\\u901a\\u77e5\\u306f\\u3042\\u308a\\u307e\\u305b\\u3093":"\\u901a\\u77e5\\u306f\\u3042\\u308a\\u307e\\u305b\\u3093")+'</div>';
      return;
    }
    $list.innerHTML = filtered.map(n=>{
      const d = new Date(n.timestamp);
      const ts = (d.getMonth()+1)+"/"+d.getDate()+" "+d.toLocaleTimeString("ja-JP",{hour:"2-digit",minute:"2-digit"});
      const cls = n.status==="read"?"notif read":"notif";
      return '<div class="'+cls+'" data-id="'+n.id+'">'
        +'<div class="notif-header"><span class="notif-pc">'+esc(n.pc_name)+'</span><span class="notif-time">'+ts+'</span></div>'
        +(n.sender?'<div class="notif-sender">'+esc(n.sender)+'</div>':'')
        +(n.channel?'<div class="notif-channel">'+esc(n.channel)+'</div>':'')
        +'<div class="notif-msg">'+esc(n.message)+'</div>'
        +'</div>';
    }).join("");

    // click to mark read
    $list.querySelectorAll(".notif:not(.read)").forEach(el=>{
      el.onclick = async ()=>{
        const id=el.dataset.id;
        el.classList.add("read");
        el.style.opacity="0.4";
        try{
          await fetch("/api/notifications/"+id,{method:"PATCH",headers});
          const n=notifications.find(x=>x.id===id);
          if(n) n.status="read";
          const uc=notifications.filter(x=>x.status==="unread").length;
          if(uc>0){$badge.textContent=uc;$badge.hidden=false;}else{$badge.hidden=true;}
          if(filterUnread) render();
        }catch(e){}
      };
    });
  }

  function esc(s){return s.replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;").replace(/"/g,"&quot;");}

  // Request notification permission
  if("Notification" in window && Notification.permission==="default"){
    Notification.requestPermission();
  }

  // Register service worker
  if("serviceWorker" in navigator){
    navigator.serviceWorker.register("/sw.js").catch(()=>{});
  }

  // Initial fetch + polling
  fetchNotifications();
  pollTimer = setInterval(fetchNotifications, 10000);
})();
</script>
</body>
</html>`;

export const MANIFEST_JSON = JSON.stringify({
  name: "Teams Mentions",
  short_name: "Mentions",
  start_url: "/",
  display: "standalone",
  background_color: "#1a1a2e",
  theme_color: "#1a1a2e",
  icons: [
    { src: "/icon-192.png", sizes: "192x192", type: "image/png" },
    { src: "/icon-512.png", sizes: "512x512", type: "image/png" },
  ],
});

export const SW_JS = `
self.addEventListener("install", e => self.skipWaiting());
self.addEventListener("activate", e => e.waitUntil(self.clients.claim()));
`;

// Generate a simple colored circle PNG icon (uncompressed BMP-in-PNG is too complex,
// so we return an SVG-based data URI trick — but for /icon-*.png we return a minimal SVG served as image)
export function generateIconSvg(size: number): string {
  return `<svg xmlns="http://www.w3.org/2000/svg" width="${size}" height="${size}" viewBox="0 0 ${size} ${size}">
  <rect width="${size}" height="${size}" rx="${size * 0.2}" fill="#1a1a2e"/>
  <text x="50%" y="54%" dominant-baseline="middle" text-anchor="middle" font-size="${size * 0.5}" font-family="sans-serif" fill="#e94560">T</text>
</svg>`;
}
