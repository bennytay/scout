CSS = """
:root{--bg:#f7f7f5;--card:#fff;--ink:#16181d;--mute:#6b7280;--line:#e6e6e2;--acc:#2f5bea;--hot:#e4572e;--mid:#e8a33d;--low:#9aa3ae}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:14px/1.5 -apple-system,BlinkMacSystemFont,"Inter","Segoe UI",sans-serif}
a{color:var(--acc);text-decoration:none}a:hover{text-decoration:underline}
header{display:flex;gap:24px;align-items:center;padding:12px 28px;background:var(--ink);color:#fff;position:sticky;top:0;z-index:2}
header .logo{color:#fff;font-weight:700;font-size:16px}header nav a{color:#c9cdd4;margin-right:16px}header nav a.on{color:#fff;font-weight:600}
header .add{margin-left:auto;display:flex;gap:6px}header .add input{width:320px;background:#2a2d34;border:1px solid #3a3e46;color:#fff}
main{max-width:1280px;margin:0 auto;padding:20px 28px 60px}
input,select,button{font:inherit;border:1px solid var(--line);border-radius:8px;padding:7px 10px;background:#fff;color:var(--ink)}
button{background:var(--acc);color:#fff;border-color:var(--acc);cursor:pointer;font-weight:600}
button.ghost{background:#fff;color:var(--ink);border-color:var(--line);font-weight:500}button.danger{background:#fff;color:#b42318;border-color:#f1c0bb}
button:disabled{opacity:.4;cursor:default}
.search .q{width:100%;font-size:17px;padding:12px 14px;border-radius:10px;margin-bottom:10px}
.row{display:flex;flex-wrap:wrap;gap:8px;align-items:center;margin:6px 0}
.layout{display:grid;grid-template-columns:240px 1fr;gap:24px;margin-top:16px}
aside .facet{margin-bottom:18px}aside h4{margin:0 0 6px;font-size:11px;text-transform:uppercase;letter-spacing:.06em;color:var(--mute)}
aside .facet a{display:flex;justify-content:space-between;padding:3px 8px;border-radius:6px;color:var(--ink)}
aside .facet a:hover{background:#ecedea;text-decoration:none}aside .facet a.on{background:var(--acc);color:#fff}
aside em{font-style:normal;color:var(--mute);font-size:12px}aside a.on em{color:#dfe6ff}
.status{color:var(--mute);margin-bottom:10px}
.card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:14px 16px;margin-bottom:10px}
.card .top{display:flex;gap:10px;align-items:center}.card .title{font-weight:600;font-size:15px;color:var(--ink);flex:1}
.card h1{font-size:22px;margin:0;flex:1}.meta{color:var(--mute);font-size:12.5px;margin:4px 0}
.sum{margin:6px 0}.why{margin:4px 0;color:#7a3b16;font-size:13px}.why.big{display:flex;gap:10px;align-items:center;background:#fff6ef;padding:8px 10px;border-radius:8px}
.type{font-size:11px;text-transform:uppercase;letter-spacing:.04em;padding:2px 7px;border-radius:5px;background:#eef1f6;color:#374151;font-weight:600}
.t-paper{background:#e7efff;color:#2346b0}.t-repo{background:#e6f6ec;color:#166534}.t-post{background:#e6f4fb;color:#0b6a93}
.t-article{background:#f3ebfb;color:#6b21a8}.t-model{background:#fff3df;color:#92400e}.t-dataset{background:#fde8e8;color:#9b1c1c}
.rel{position:relative;display:inline-flex;align-items:center;width:84px;height:18px;background:#f0f0ec;border-radius:9px;overflow:hidden;flex:none}
.rel i{position:absolute;left:0;top:0;bottom:0}.rel b{position:relative;width:100%;text-align:center;font-size:11px}
.rel.hot i{background:#f8c4b4}.rel.mid i{background:#f6dfb2}.rel.low i{background:#e3e6ea}.rel.none{width:auto;padding:0 8px;color:var(--mute)}
.chip{display:inline-block;padding:2px 9px;margin:2px 4px 2px 0;border-radius:999px;background:#eef0f3;color:#374151;font-size:12px}
.chip.on{background:var(--acc);color:#fff}.chip em{font-style:normal;color:var(--mute)}
.src{font-size:11px;color:var(--mute);border:1px solid var(--line);border-radius:4px;padding:0 5px}
.kv>div{margin:6px 0}.kv b{display:inline-block;width:90px;color:var(--mute);font-weight:500}
.people{display:flex;flex-wrap:wrap;gap:6px}.person{display:flex;gap:8px;background:#fff;border:1px solid var(--line);border-radius:8px;padding:6px 10px;color:var(--ink)}
.person em{font-style:normal;color:var(--mute)}
.related{margin:0;padding-left:0;list-style:none}.related li{margin:6px 0}.related em{color:var(--mute);font-size:12px}
.boxes{display:flex;flex-wrap:wrap;gap:6px 14px;margin-bottom:8px}.boxes label{display:flex;gap:5px;align-items:center}
.maint form{display:inline}.hint{color:var(--mute);font-size:12px}.curated{color:#166534;font-size:13px}
.err{color:#b42318}.err.small{font-size:11.5px}.ok{color:#166534}.empty{color:var(--mute);padding:30px;text-align:center}
table{width:100%;border-collapse:collapse}td,th{text-align:left;padding:7px 8px;border-bottom:1px solid var(--line);vertical-align:top}
th{font-size:11px;text-transform:uppercase;color:var(--mute)}tr.off{opacity:.45}
.stats{display:flex;gap:12px;margin-bottom:14px}.stats div{background:#fff;border:1px solid var(--line);border-radius:12px;padding:12px 16px;flex:1}
.stats b{display:block;font-size:22px}
details pre{white-space:pre-wrap;background:#f6f6f3;padding:10px;border-radius:8px;max-height:420px;overflow:auto;font-size:12px}
@media(max-width:820px){.layout{grid-template-columns:1fr}header .add input{width:160px}}
"""
