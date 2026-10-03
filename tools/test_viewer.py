#!/usr/bin/env python3
"""Open opencl-explorer.html in headless Chromium, visit every tab and the workbench,
fail on any JavaScript error or any suspiciously empty view.

The snap Chromium cannot read /tmp, so the test page is written next to the viewer and removed.
"""
import re, subprocess, sys, html, json, os
from common import ROOT

h = open(os.path.join(ROOT, "opencl-explorer.html")).read()
h = h.replace("<head>", '<head><script>window.__early=[];window.addEventListener("error",e=>__early.push(String(e.message)+" @"+e.lineno));</script>', 1)
js = """
setTimeout(()=>{const res={};try{
 for(const [id] of TABS){show(id);res[id]=main.innerText.length;}
 show('bench');STATE.picks=new Set(['cl_khr_command_buffer','cl_khr_semaphore','cl_khr_subgroup_ballot']);STATE.optpick='Sub-groups';show('bench');
 res.bench_report=document.getElementById('brep').innerText.length;
 STATE.res=(M.results[1]||M.results[0]).id;show('results');res.results_detail=document.getElementById('rdet').innerText.length;
 show('concerns');res.concerns_high=document.querySelectorAll('#cbody .chip.removed').length;res.concerns_sources=/tested/.test(main.innerText)&&/not knowable/.test(main.innerText);
 show('bench');STATE.picks=new Set(['cl_khr_command_buffer']);STATE.optpick=null;show('bench');res.bench_links_stored=/Already tested/.test(document.getElementById('brep').innerText);
 STATE.arg='v3.1.1';show('versions');res.v311_has_revert=/CL_COMPLETE/.test(main.innerText);
 STATE.arg='OpenCL 3.1';show('versions');res.v31_entries=+((main.innerText.match(/Spec changelog entries \\((\\d+)\\)/)||[])[1]||0);
 show('structure');for(const d of ['API','C','Env','Ext']){const s=document.getElementById('sd');s.value=d;s.onchange();res['structure_'+d]=document.getElementById('sout').innerText.length;}
 document.getElementById('sd').value='API';document.getElementById('sr').checked=true;document.getElementById('sr').onchange();res.refpages=document.getElementById('sout').innerText.length;
 STATE.ext='cl_khr_unified_svm';show('extensions');res.ext_detail=document.getElementById('edet').innerText.length;

 // deep links: a pasted hash must reproduce the view
 location.hash='#compare?ca=v3.0.19&cb=v3.1.0';route();res.dl_compare=(document.getElementById('ca').value==='v3.0.19'&&document.getElementById('cb').value==='v3.1.0'&&/v3\\.0\\.19 → v3\\.1\\.0/.test(main.innerText));
 res.compare_has_31_summary=/adds the OpenCL 3\\.1 C kernel language/.test(main.innerText);
 location.hash='#bench?picks=cl_khr_command_buffer';route();res.dl_bench=/Already tested/.test(document.getElementById('brep').innerText);
 location.hash='#extensions?ext=cl_khr_unified_svm';route();res.dl_ext=/cl_khr_unified_svm/.test(document.getElementById('edet').innerText);
 location.hash='#concerns?lv=high';route();res.dl_concerns=(STATE.cl.size===1&&!/\\binfo\\b\\s+\\d/.test(main.querySelector('.card .small')?'':'')&&document.querySelectorAll('#cbody .chip.removed').length>0);
 location.hash='#structure?sd=C&sq=sub-group';route();res.dl_structure=(document.getElementById('sd').value==='C'&&document.getElementById('sq').value==='sub-group');
 // round trip: change a control, the URL must follow
 show('compare');const ca=document.getElementById('ca');ca.value='v3.0.5';ca.dispatchEvent(new Event('change',{bubbles:true}));res.roundtrip=/ca=v3\\.0\\.5/.test(location.hash);
 // plain-language layer
 show('overview');res.plain_box=!!document.querySelector('.plain');
 show('optional');res.apph_attribution=main.innerText.includes('Creative Commons Attribution 4.0')&&main.innerText.includes('Changes:')&&main.innerText.includes('Khronos does not endorse');res.apph_rows=main.innerText.includes('indicating that device does not support Shared Virtual Memory');res.glossary_marks=document.querySelectorAll('.gl').length;
 const g=document.querySelector('.gl');if(g){g.click();}res.popup=!!document.getElementById('gpop');
 show('propose');show('propose');document.querySelector('[data-add=commands]').click();res.propose_no_stacking=(document.querySelectorAll('#wform [data-del^="commands"]').length===1);
 document.getElementById('wex').click();{const j=JSON.parse(document.getElementById('wjson').value);res.propose_example=(j.extension.name==='cl_zzdemo_wizard_query'&&j.commands.length===1&&j.feature.absent.clGetDemoInfoZZDEMO==='CL_INVALID_OPERATION');res.propose_clean=!/problem/.test(document.getElementById('wcheck').innerText);}
 res.propose_hash=/spec=/.test(location.hash);const h0=location.hash;show('overview');location.hash=h0;route();res.propose_restore=(document.querySelector('[data-k="extension.name"]').value==='cl_zzdemo_wizard_query');
 {const f=document.querySelector('[data-k="enums.0.name"]');f.value='CL_DEVICE_TYPE';f.dispatchEvent(new Event('input',{bubbles:true}));res.propose_catches_clash=/already exists/.test(document.getElementById('wcheck').innerText);}
 show('propose');document.getElementById('wcl').click();document.querySelector('[data-add=types]').click();{const k=document.querySelector('[data-k="types.0.kind"]');k.value='struct';k.dispatchEvent(new Event('change',{bubbles:true}));const m=document.querySelector('[data-k="types.0.members"]');const n=document.querySelector('[data-k="types.0.name"]');n.value='cl_demo_pair_zzdemo';n.dispatchEvent(new Event('input',{bubbles:true}));m.value='cl_uint a\\ncl_uint b';m.dispatchEvent(new Event('input',{bubbles:true}));const j=JSON.parse(document.getElementById('wjson').value);res.propose_struct=(j.types[0].members.length===2&&!j.types[0].base);}
 {let okt=TOUR.length===7;for(let i=0;i<TOUR.length;i++){tourGo(i);okt=okt&&CUR===TOUR[i].tab&&!!document.getElementById('tour')&&document.getElementById('tour').innerText.length>60&&/step \\d of 7/.test(document.getElementById('tour').innerText);}res.tour_steps=okt;tourClose();res.tour_closed=!document.getElementById('tour')&&!/tour=/.test(location.hash);
 location.hash='#overview?tour=2';route();res.tour_resume=/step 3 of 7/.test((document.getElementById('tour')||{innerText:''}).innerText);tourClose();}
 show('help');res.help_terms=document.querySelectorAll('#hl tr').length;
}catch(e){res.EXCEPTION=e.stack;}
const pre=document.createElement('pre');pre.id='RESULT';pre.textContent=JSON.stringify({early:__early,res});document.body.appendChild(pre);},300);
"""
page = os.path.join(ROOT, "_viewer_test.html")
open(page, "w").write(h.replace("</body>", "<script>" + js + "</script></body>"))
try:
    out = subprocess.run(["chromium", "--headless=new", "--no-sandbox", "--disable-gpu", "--virtual-time-budget=8000", "--dump-dom", "file://" + page],
                         capture_output=True, text=True, timeout=180).stdout
finally:
    os.remove(page)
m = re.search(r'id="RESULT">(.*?)</pre>', out, re.S)
if not m:
    sys.exit("FAIL: no result from the page (did it fail to load?)")
r = json.loads(html.unescape(m.group(1)))
print(json.dumps(r["res"], indent=1))
bad = []
if r["early"]: bad.append("js errors: %s" % r["early"])
if "EXCEPTION" in r["res"]: bad.append(r["res"]["EXCEPTION"])
for k, v in r["res"].items():
    if k == "v31_entries":
        if v < 10: bad.append("3.1 changelog view has only %s entries" % v)
    elif k in ("glossary_marks", "help_terms") or isinstance(v, bool):
        pass
    elif k == "concerns_high":
        pass                                  # a count of chips, checked separately below
    elif isinstance(v, int) and not isinstance(v, bool) and v < 100: bad.append("%s looks empty (%s chars)" % (k, v))
for k in ("apph_attribution", "apph_rows", "compare_has_31_summary", "tour_steps", "tour_closed", "tour_resume", "propose_struct", "propose_no_stacking", "propose_example", "propose_clean", "propose_hash", "propose_restore", "propose_catches_clash", "dl_compare", "dl_bench", "dl_ext", "dl_concerns", "dl_structure", "roundtrip", "plain_box", "popup"):
    if not r["res"].get(k): bad.append("shareable-link / plain-language check failed: " + k)
if r["res"].get("glossary_marks", 0) < 3: bad.append("glossary marked fewer than 3 terms on the Optional features tab")
if r["res"].get("help_terms", 0) < 30: bad.append("Start-here glossary has too few terms")
if not r["res"].get("concerns_sources"): bad.append("concerns tab lacks source tags")
if not r["res"].get("concerns_high"): bad.append("concerns tab shows no high-level concerns")
if not r["res"].get("bench_links_stored"): bad.append("workbench did not link the stored s01 result")
if not r["res"].get("v311_has_revert"): bad.append("v3.1.1 view lacks the CL_COMPLETE revert entry")
if bad: sys.exit("FAIL:\n  " + "\n  ".join(bad))
print("viewer OK")
