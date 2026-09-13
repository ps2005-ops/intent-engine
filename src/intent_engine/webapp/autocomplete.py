"""The company combobox: markup, style and the small script that drives it.

WHY THERE IS SCRIPT HERE WHEN THE REST OF THE PRODUCT HAS NONE
--------------------------------------------------------------
Everything else in this product renders without JavaScript, deliberately: the
history date control is a radio group, the slides are CSS, and a page that
needs a runtime to say what it found is a page that can fail to say it.

Suggestions are the one exception, and the reason is that the alternative is
worse rather than merely different. `<datalist>` is the JS-free option and it
cannot show a second line — a customer choosing between "Johnson & Johnson"
and "Johnson Controls International" needs the ticker and the country, and a
datalist gives them a list of bare strings. Since choosing the wrong company
is the worst failure this product has, the second line is not decoration.

**THE FORM WORKS WITHOUT THE SCRIPT.** The input is an ordinary text field in
an ordinary form; if the script never runs, the customer types a name and
submits, and the server-side resolution that has always existed handles it
exactly as before. Suggestions are an enhancement over a working control, not
a replacement for one.

ARIA (§86)
----------
A real `combobox`/`listbox` pairing: `aria-expanded`, `aria-controls`,
`aria-activedescendant`, `role="option"` and `aria-selected`. Arrow keys move
the active option, Enter selects it, Escape closes the list and returns focus
to the input. A screen reader announces the option count and the active
option, because the pattern is the one screen readers are built to narrate.
"""
from __future__ import annotations

from html import escape


def _e(text) -> str:
    return escape(str(text or ""), quote=True)


AUTOCOMPLETE_CSS = """
<style>
.cbox{position:relative}
.cbox-list{position:absolute;z-index:40;left:0;right:0;top:100%;margin:.25rem 0
0;padding:.25rem;list-style:none;background:var(--panel,#fff);
border:1px solid var(--line,#dbe2ea);border-radius:10px;
box-shadow:0 10px 30px rgba(8,15,30,.16);max-height:19rem;overflow-y:auto}
.cbox-list[hidden]{display:none}
.cbox-list li{padding:.45rem .6rem;border-radius:7px;cursor:pointer;
line-height:1.3}
.cbox-list li[aria-selected="true"],.cbox-list li:hover{
background:var(--soft,#eef2ff)}
.cbox-list .nm{display:block;font-weight:600;font-size:.95rem}
.cbox-list .dsc{display:block;font-size:.78rem;color:var(--muted,#64748b)}
.cbox-list .src{float:right;font-size:.66rem;color:var(--muted,#64748b);
text-transform:uppercase;letter-spacing:.06em}
.cbox-status{font-size:.8rem;color:var(--muted,#64748b);margin:.3rem 0 0;
min-height:1.1em}
.cbox-picked{display:flex;flex-wrap:wrap;gap:.3rem .7rem;align-items:baseline;
font-size:.85rem;margin:.4rem 0 0}
.cbox-picked b{font-size:.95rem}
.cbox-picked .clear{background:none;border:0;padding:0;color:var(--accent,
#1d4ed8);text-decoration:underline;cursor:pointer;font:inherit}
</style>
"""

#: The listbox, the status line and the hidden fields the picked identity
#: rides in on. Injected next to the existing company-name input.
MARKUP = (
    '<ul id="company_suggestions" class="cbox-list" role="listbox" '
    'aria-label="Company suggestions" hidden></ul>'
    '<p class="cbox-status" id="company_status" role="status" '
    'aria-live="polite"></p>'
    '<div class="cbox-picked" id="company_picked" hidden></div>'
    '<input type="hidden" name="entity_id" id="pick_entity_id" value="">'
    '<input type="hidden" name="suggest_cik" id="pick_cik" value="">'
    '<input type="hidden" name="suggest_ticker" id="pick_ticker" value="">'
    '<input type="hidden" name="suggest_domain" id="pick_domain" value="">'
    '<input type="hidden" name="suggest_country" id="pick_country" value="">'
    '<input type="hidden" name="suggest_confirmed" id="pick_confirmed" '
    'value="">'
)

#: Kept in one string so the markup, the ARIA wiring and the keyboard model
#: are read together. Everything it touches is inside the analyse form.
SCRIPT = """
<script>
(function(){
  var input = document.getElementById('company_name');
  var list  = document.getElementById('company_suggestions');
  var stat  = document.getElementById('company_status');
  var picked= document.getElementById('company_picked');
  if(!input || !list) return;
  var F = {id:'pick_entity_id',cik:'pick_cik',tk:'pick_ticker',
           dm:'pick_domain',ct:'pick_country',ok:'pick_confirmed'};
  function set(k,v){var el=document.getElementById(F[k]); if(el) el.value=v||'';}
  input.setAttribute('role','combobox');
  input.setAttribute('aria-expanded','false');
  input.setAttribute('aria-controls','company_suggestions');
  input.setAttribute('aria-autocomplete','list');
  input.setAttribute('autocomplete','off');
  var rows=[], active=-1, timer=null, lastQuery='';
  function close(){
    list.hidden=true; list.innerHTML=''; rows=[]; active=-1;
    input.setAttribute('aria-expanded','false');
    input.removeAttribute('aria-activedescendant');
  }
  function clearPick(){
    ['id','cik','tk','dm','ct','ok'].forEach(function(k){set(k,'');});
    if(picked){picked.hidden=true; picked.innerHTML='';}
  }
  function confirm(row){
    set('id',row.entity_id); set('cik',row.cik); set('tk',row.ticker);
    set('dm',row.domain); set('ct',row.country); set('ok',row.legal_name);
    input.value = row.legal_name;
    if(picked){
      var bits=[row.ticker,row.country,row.domain].filter(Boolean).join(' \\u00b7 ');
      picked.innerHTML='';
      var s=document.createElement('span');
      s.innerHTML='Analysing <b></b>';
      s.querySelector('b').textContent=row.legal_name;
      picked.appendChild(s);
      if(bits){var m=document.createElement('span');
        m.className='dsc'; m.textContent=bits; picked.appendChild(m);}
      var b=document.createElement('button');
      b.type='button'; b.className='clear'; b.textContent='change';
      b.addEventListener('click',function(){
        clearPick(); input.value=''; input.focus();});
      picked.appendChild(b);
      picked.hidden=false;
    }
    stat.textContent='';
    close();
  }
  function mark(i){
    for(var n=0;n<list.children.length;n++){
      list.children[n].setAttribute('aria-selected', n===i ? 'true':'false');
    }
    if(i>=0 && list.children[i]){
      input.setAttribute('aria-activedescendant', list.children[i].id);
      list.children[i].scrollIntoView({block:'nearest'});
    } else { input.removeAttribute('aria-activedescendant'); }
    active=i;
  }
  function draw(items){
    rows=items; list.innerHTML='';
    items.forEach(function(row,i){
      var li=document.createElement('li');
      li.id='cbo'+i; li.setAttribute('role','option');
      li.setAttribute('aria-selected','false');
      var nm=document.createElement('span'); nm.className='nm';
      nm.textContent=row.legal_name; li.appendChild(nm);
      if(row.describe){var d=document.createElement('span');
        d.className='dsc'; d.textContent=row.describe; li.appendChild(d);}
      li.addEventListener('mousedown',function(ev){
        ev.preventDefault(); confirm(row);});
      list.appendChild(li);
    });
    list.hidden = items.length===0;
    input.setAttribute('aria-expanded', items.length? 'true':'false');
    stat.textContent = items.length
      ? items.length+' match'+(items.length>1?'es':'')+
        '. Use the arrow keys to choose, or keep typing.'
      : '';
    mark(-1);
  }
  function fetchRows(q){
    if(q===lastQuery) return; lastQuery=q;
    if(q.length<2){ close(); stat.textContent=''; return; }
    fetch('/api/companies?q='+encodeURIComponent(q),
          {headers:{'Accept':'application/json'}})
      .then(function(r){return r.ok? r.json():{companies:[]};})
      .then(function(d){ if(input.value.trim()===q) draw(d.companies||[]); })
      .catch(function(){ /* the form still works without this */ });
  }
  input.addEventListener('input',function(){
    clearPick();
    var q=input.value.trim();
    clearTimeout(timer);
    timer=setTimeout(function(){fetchRows(q);},160);
  });
  input.addEventListener('keydown',function(ev){
    if(ev.key==='ArrowDown'){ ev.preventDefault();
      if(list.hidden){fetchRows(input.value.trim());return;}
      mark(active+1>=rows.length?0:active+1); }
    else if(ev.key==='ArrowUp'){ ev.preventDefault();
      if(list.hidden) return; mark(active-1<0?rows.length-1:active-1); }
    else if(ev.key==='Enter'){
      if(!list.hidden && active>=0){ ev.preventDefault(); confirm(rows[active]); } }
    else if(ev.key==='Escape'){ if(!list.hidden){ ev.preventDefault(); close(); } }
  });
  input.addEventListener('blur',function(){setTimeout(close,140);});
})();
</script>
"""


def inject(page: str) -> str:
    """Attach the combobox to the landing page's company-name input.

    A string replacement rather than a template change because the landing
    page is rendered by the presentation package, which knows nothing about
    sessions or routes and should keep knowing nothing about them.
    """
    marker = ('<input id="company_name" name="company_name" '
              'placeholder="Cloudflare" autofocus required></span>')
    if marker not in page:
        return page
    replacement = (
        '<input id="company_name" name="company_name" '
        'placeholder="Start typing a company name" autofocus required '
        'aria-describedby="company_status">' + MARKUP + '</span>')
    page = page.replace(marker, replacement, 1)
    page = page.replace('<span class="field grow">',
                        '<span class="field grow cbox">', 1)
    page = page.replace('</head>', AUTOCOMPLETE_CSS + '</head>', 1) \
        if '</head>' in page else AUTOCOMPLETE_CSS + page
    return page.replace('</form>', '</form>' + SCRIPT, 1)
