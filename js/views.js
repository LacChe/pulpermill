/* Pulpermill page: Drawing: navigation, cards, story, top bar, redraw that keeps the caret and scroll position. */
function inline(text){
  const out=[],re=/(\*\*[^*\n]+\*\*|\*[^*\n]+\*)/g;let last=0,m;
  while((m=re.exec(text))){
    if(m.index>last)out.push(text.slice(last,m.index));
    const s=m[0];out.push(s.startsWith('**')?el('strong',{},s.slice(2,-2)):el('em',{},s.slice(1,-1)));last=m.index+s.length;
  }
  if(last<text.length)out.push(text.slice(last));
  return out;
}
function prose(text){
  const box=el('div',{class:'prose'});
  String(text).split(/\n{2,}/).forEach(p=>{if(p.trim())box.append(el('p',{},inline(p.trim())))});
  return box;
}

function navSub(pg,j){
  const S=st.story;
  if(S.job&&S.job.j===j&&st.busy==='chapter')return t('Writing…');
  if(isEnding(j))return t('After chapter {k}',{k:j});
  if(pg.result)return pg.result.words.toLocaleString()+' '+unitWord()+(resStale(j)?t(' · out of date'):'')+(cardsEdited(pg)?t(' · cards changed'):'');
  return haveCards(pg)?t('Ready to write'):(j===0?t('Setting up the cards'):t('Ready'));
}
function goPage(j){st.story.cur=j;st.report=null;st.armed=false;st.ask=null;draw(false);const r=$('#right');if(r)r.scrollTop=0;try{window.scrollTo(0,0)}catch(e){/* no scrolling here (e.g. a test page); nothing depends on it */}}
function drawNav(){
  const nav=$('#nav'),S=st.story;nav.innerHTML='';
  nav.append(el('h2',{},t('Chapters')));
  const ol=el('ol',{class:'navlist'});
  S.pages.forEach((pg,j)=>ol.append(el('li',{},el('button',{type:'button',class:'navbtn','aria-current':j===S.cur?'page':false,onclick:()=>goPage(j)},
    el('b',{},pageName(j)),el('span',{class:'navsub'},navSub(pg,j))))));
  nav.append(ol);
  const foot=el('div',{class:'navfoot'});
  foot.append(el('button',{id:'saveproj',onclick:()=>downloadText(storyFile()+'_project.json',projectFile(),'application/json')},t('Save project')),
    el('button',{id:'loadproj',disabled:!!st.busy,onclick:()=>$('#projfile').click()},t('Load project')));
  if(!st.armed)foot.append(el('button',{id:'reset',class:'danger',disabled:!!st.busy,onclick:()=>{st.armed=true;drawNav()}},t('Reset everything…')));
  else foot.append(el('div',{class:'guard',role:'alertdialog','aria-label':t('Confirm reset')},
    el('p',{class:'hint'},t('This erases every card, note and chapter in this browser. Save the project first if you want to keep it.')),
    el('div',{class:'row'},el('button',{id:'resetno',onclick:()=>{st.armed=false;drawNav()}},t('Cancel')),el('button',{id:'resetyes',class:'danger solid',onclick:resetAll},t('Erase everything')))));
  nav.append(foot);
}
function resetAll(){
  if(st.busy)return;
  st.story={pages:[newPage()],cur:0,job:null};st.report=null;st.armed=false;st.ask=null;st.banner='';
  $('#slug').value='';save('slug','');draw(false);saveProject();
}

function inputSection(pg){
  const sec=el('section',{class:'box',id:'examplebox'});
  sec.append(el('div',{class:'head'},el('h2',{},t('Example chapter (optional)'))),
    el('p',{class:'hint',id:'modehint'},t('Paste a chapter from any story to give the model something to work from. Each card below has its own switch for using it. The limit shown is the tightest of the cards that use it, and the chapter counts against each of their limits.')));
  const ta=el('textarea',{id:'chapter',rows:10,placeholder:t('Paste one chapter here.'),'aria-label':t('Example chapter')});
  ta.value=pg.chapter;ta.addEventListener('input',()=>{pg.chapter=ta.value;updateCounters()});
  sec.append(ta,el('div',{class:'count',id:'chcount'}));
  /* what the example is for: one choice */
  const fs=el('fieldset',{class:'uses',id:'exuses'},el('legend',{},t('What is the example for?')));
  EXAMPLE_USES.forEach(u=>{
    const rb=el('input',{type:'radio',name:'exuse',id:'use-'+(u.k||'same'),value:u.k});
    rb.checked=(pg.use||'')===u.k;
    rb.addEventListener('change',()=>{if(rb.checked){pg.use=u.k;draw()}});
    fs.append(el('label',{class:'chk'},rb,el('span',{class:'usename'},t(u.t)),el('span',{class:'ro'},' — '+t(u.d))));
  });
  sec.append(fs);
  return sec;
}
function drawStages(root,pg,j){
  const hide=j===0?(SCH.hidden||[]):[],P=pages();
  refContext(pg.cards);    // the live-state fields (wrap) only matter once a story is running
  STAGES.forEach((s,i)=>{
    const has=!!pg.cards[s.k],prev=i===0||!!pg.cards[STAGES[i-1].k],busy=st.busy===s.k&&st.busyPg===pg;
    const sec=el('section',{class:'box stage'+(has?' done':'')+(!prev?' locked':''),'data-card':s.k});
    const tags=el('span');
    const base=j>0?P[j-1].cards[s.k]:undefined;
    if(pg.stale[s.k])tags.append(el('span',{class:'tag stale'},t('Built from an earlier version of a previous card')));
    else if(has)tags.append(el('span',{class:'tag'},j===0?t('Ready to check'):t('Ready')));
    const broken=has?scanRefs(pg.cards[s.k],[s.k],[]):[];
    if(broken.length)tags.append(el('span',{class:'tag bad'},t('broken links: {n}',{n:broken.length})));
    if(has&&base&&!same(pg.cards[s.k],base))tags.append(el('span',{class:'tag chgtag'},t('Changed since the last chapter')));
    const extra=st.limits&&s.k==='characters'?' '+t('A generation writes up to {n} characters. Add as many as you like and choose up to {m} for each chapter.',{n:st.limits.max_characters,m:st.limits.max_cast||6}):st.limits&&s.k==='outline'?' '+t('Up to {n} chapters.',{n:st.limits.max_chapters}):'';
    sec.append(el('div',{class:'head'},el('h2',{},t(s.t)),tags),el('p',{class:'hint'},t(s.d)+extra));
    const usingEx=j===0&&usesExample(s.k)&&!!pg.chapter.trim();
    if(j===0){
      const cb=el('input',{type:'checkbox',id:'ex-'+s.k,'data-k':s.k});cb.checked=usesExample(s.k);
      cb.addEventListener('change',()=>{pg.useEx[s.k]=cb.checked;draw()});
      sec.append(el('label',{class:'chk useex'},cb,el('span',{},t('Use the example chapter for this card')),
        pg.chapter.trim()?null:el('span',{class:'ro'},' '+t('(paste an example chapter above first)'))));
    }
    const nt=el('textarea',{rows:has?3:5,placeholder:usingEx?t('Optional extra direction for this card. Leave blank to infer it all from the chapter.'):t(HINTS[s.k]),'aria-label':t('{card} notes',{card:t(s.t)})});
    nt.value=pg.notes[s.k]||'';
    nt.addEventListener('input',()=>{pg.notes[s.k]=nt.value;updateCounters()});
    sec.append(el('details',{class:'notes',open:has?false:'open'},el('summary',{},t('Your notes for this card')),nt,el('div',{class:'count nc','data-k':s.k})));
    if(pg.err[s.k])sec.append(el('div',{class:'msg err',role:'alert'},msg(pg.err[s.k])));
    if(!has){
      sec.append(el('button',{class:'go gen','data-k':s.k,'data-lock':(!prev||st.busy)?'1':'0',disabled:!prev||!!st.busy,onclick:()=>generate(i)},busy?[t('Generating…'),el('span',{class:'timer'})]:[t('Generate {what}',{what:t(s.t).toLowerCase()}),tookTag(pg.took&&pg.took[s.k])]));
      if(!prev)sec.append(el('span',{class:'ro'},'  '+t('Generate {what} first.',{what:t(STAGES[i-1].t).toLowerCase()})));
    }else{
      const w=pg.warn[s.k]||[];
      if(w.length)sec.append(el('div',{class:'msg warn'},t('Check these:'),el('ul',{},w.map(x=>el('li',{},msg(x))))));
      if(broken.length)sec.append(el('div',{class:'msg err',role:'alert'},t('These fields point at something that no longer exists:'),el('ul',{},broken.map(b=>el('li',{},brokenLine(b))))));
      FLAGS=flagsOf(pg.warn[s.k]);
      try{sec.append(withHide(hide,()=>editor(pg.cards[s.k],(SCH.enums||{})[s.k],base,s.k)))}finally{FLAGS=[]}
      const fb=el('textarea',{rows:1,class:'fbnote',placeholder:t('What should change? (optional)'),'aria-label':t('Note for regeneration')});
      const grow=()=>{fb.style.height='auto';fb.style.height=Math.min(fb.scrollHeight+2,320)+'px'};
      pg.draft=pg.draft||{};fb.value=pg.draft[s.k]||'';if(fb.value)setTimeout(grow,0);
      fb.addEventListener('input',()=>{pg.draft[s.k]=fb.value;grow()});
      sec.append(el('div',{class:'rerun'},fb,
        el('button',{class:'gen','data-k':s.k,'data-lock':st.busy?'1':'0',disabled:!!st.busy,onclick:()=>generate(i,fb.value.trim())},busy?[t('Generating…'),el('span',{class:'timer'})]:[t('Regenerate with note'),tookTag(pg.took&&pg.took[s.k])]),
        el('button',{class:'sm clr','data-k':s.k,disabled:!!st.busy,title:t('Remove this card so it can be generated again from scratch. Your notes stay.'),onclick:()=>clearCard(i)},t('Clear card'))));
    }
    if(busy)sec.append(progBlock(true));
    root.append(sec);
  });
}
function askNode(j){
  const P=pages(),k=j+1,nxt=P[j+1],needs=!!nxt&&(edited(nxt)||!!nxt.result);
  const end=!!nxt&&isEnding(j+1);
  const box=el('div',{class:'pending',role:'alertdialog','aria-label':t('Confirm rewrite')});
  const note=(st.ask&&st.ask.note)||'';
  box.append(el('p',{},note?t('Rewrite chapter {k} with your note? The new version replaces this one.',{k}):t('Rewrite chapter {k}? The new version replaces this one.',{k})));
  if(note)box.append(el('p',{class:'hint asknote'},t('Your note: {note}',{note})));
  const cancel=el('button',{id:'askno',onclick:()=>{st.ask=null;draw()}},t('Cancel'));
  if(needs){
    box.append(el('p',{},end?t('When it finishes, the cards it ends with can replace the ending cards. Only one version of those cards is kept, so if you want to keep the current ones, export them before you generate.'):t('When it finishes, the cards it ends with can replace chapter {n}\'s starting cards. Only one version of those cards is kept, so if you want to keep the current ones, export them before you generate.',{n:k+1})));
    box.append(el('div',{class:'row'},el('button',{id:'askexport',class:'sm',onclick:()=>exportPageCards(j+1)},end?t('Export the ending cards'):t('Export chapter {n}\'s starting cards',{n:k+1})),
      el('button',{id:'askreplace',class:'go',onclick:()=>writeChapter('replace',note)},t('Rewrite and replace them')),
      el('button',{id:'askkeep',onclick:()=>writeChapter('keep',note)},t('Rewrite and keep them')),cancel));
  }else box.append(el('div',{class:'row'},el('button',{id:'askyes',class:'go',onclick:()=>writeChapter('replace',note)},t('Rewrite chapter {k}',{k})),cancel));
  return box;
}
/* the people this chapter is written about: tick up to the limit, the main character is fixed */
function castBox(pg,j){
  const k=j+1,chars=pg.cards.characters||[],lead=leadOf(pg),sel=castFor(pg,k),max=maxCast(),b=beatOf(pg,k),inBeat=(b&&b.present)||[];
  const box=el('div',{class:'castbox',id:'castbox'},el('div',{class:'lab'},t('Characters in this chapter')),
    el('p',{class:'hint'},t('Choose up to {n}. The model only writes about these people, and the main character is always one of them.',{n:max})));
  const list=el('div',{class:'castlist'});
  chars.forEach(c=>{
    const on=sel.includes(c.id),isLead=c.id===lead,full=!on&&sel.length>=max;
    const cb=el('input',{type:'checkbox',id:'cast-'+c.id,value:c.id});
    cb.checked=on;cb.disabled=isLead||full||!!st.busy;
    cb.addEventListener('change',()=>{pg.cast=cb.checked?[...sel,c.id]:sel.filter(i=>i!==c.id);draw()});
    list.append(el('label',{class:'chk'+(full?' off':'')},cb,el('span',{class:'castname'},c.name||c.id),
      el('span',{class:'ro'},(c.role?' — '+c.role:'')+(isLead?' · '+t('main character'):'')+(inBeat.includes(c.id)&&!isLead?' · '+t('in the chapter beat'):''))));
  });
  box.append(list,el('div',{class:'count',id:'castcount'},t('{n} of {max} chosen',{n:sel.length,max})));
  const left=inBeat.filter(i=>!sel.includes(i)).map(i=>(chars.find(c=>c.id===i)||{}).name||i);
  if(left.length)box.append(el('div',{class:'msg warn',id:'castwarn'},t('The beat for this chapter includes {names}, who are not chosen. Writing will plan the beat again for the people you chose.',{names:left.join(', ')})));
  return box;
}
function drawMid(){
  const root=$('#mid'),S=st.story,j=S.cur,pg=cur(),k=j+1,P=S.pages,prev=j>0?P[j-1]:null,ending=isEnding(j);
  root.innerHTML='';
  const head=el('section',{class:'box'});
  const have=Object.keys(pg.cards).length>0;
  head.append(el('div',{class:'head'},el('h2',{},ending?t('Ending cards'):t('Chapter {k} cards',{k})),el('span',{class:'row',style:'margin:0'},
    el('button',{class:'sm',id:'importbtn',disabled:!!st.busy,onclick:()=>$('#importfile').click()},t('Import cards')),
    el('button',{class:'sm',id:'exportbtn',disabled:!have,onclick:()=>exportPageCards()},t('Export cards')))));
  head.append(el('p',{class:'hint'},j===0
    ?t('Generate the four cards in order and check each one, or import them. Then write the chapter.')
    :ending?t('The cards as chapter {j} left them. The story has no chapter {k}, so there is nothing more to write. Edit or export them, or raise Total chapters on the Setup card to keep going.',{j,k})
    :t('These are the cards as chapter {j} left them. Edit anything you like before writing chapter {k}; changed fields are marked.',{j,k})));
  if(j>0&&resStale(j-1))head.append(el('div',{class:'msg warn'},t('Chapter {j} is out of date (an earlier chapter was rewritten), so these cards may not match what came before.',{j})));
  if(pg.result&&cardsEdited(pg))head.append(el('div',{class:'msg warn'},t('These cards changed after chapter {k} was written. Rewrite the chapter to apply the changes.',{k})));
  if(pg.msg)head.append(el('div',{class:'msg err',role:'alert'},msg(pg.msg)));
  if(!ending){
    const okWrite=haveCards(pg)&&(j===0||!!(prev&&prev.result));
    const writing=st.busy==='chapter'&&st.busyPg===pg;
    if(haveCards(pg)&&(pg.cards.characters||[]).length)head.append(castBox(pg,j));
    head.append(el('div',{class:'row'},
      el('button',{class:'go',id:'writebtn',disabled:!!st.busy||!okWrite,onclick:()=>writeChapter()},pg.result?t('Rewrite chapter {k}',{k}):t('Write chapter {k}',{k}),pg.result&&pg.result.secs!=null?tookTag(pg.result.secs):null),
      el('span',{class:'ro'},t('The model keeps writing until the chapter reaches a natural ending.'))));
    if(writing){head.append(el('div',{class:'hint chprog','data-live':'1',role:'status'},t('Starting')));head.append(progBlock(false))}      // only on the page being written
    if(pg.result){
      const fb=el('textarea',{rows:1,class:'fbnote',id:'chnote',placeholder:t('What should change in this chapter? (optional)'),'aria-label':t('Note for rewriting the chapter')});
      const grow=()=>{fb.style.height='auto';fb.style.height=Math.min(fb.scrollHeight+2,320)+'px'};
      pg.draft=pg.draft||{};fb.value=pg.draft.chapter||'';if(fb.value)setTimeout(grow,0);
      fb.addEventListener('input',()=>{pg.draft.chapter=fb.value;grow()});
      head.append(el('div',{class:'rerun'},fb,el('button',{class:'gen',id:'rewritenote',disabled:!!st.busy||!okWrite,onclick:()=>writeChapter(undefined,fb.value.trim())},t('Rewrite with note'),pg.result.secs!=null?tookTag(pg.result.secs):null)));
    }
    const allBroken=brokenIn(pg.cards);
    if(allBroken.length)head.append(el('div',{class:'msg err',role:'alert'},t('Broken links between cards ({n}). Fix the highlighted fields before writing.',{n:allBroken.length})));
    if(!okWrite)head.append(el('p',{class:'hint'},j===0?t('Generate all four cards first.'):t('Write chapter {j} first.',{j})));
    if(st.ask&&st.ask.j===j&&!st.busy)head.append(askNode(j));
    const beat=beatOf(pg,k);
    if(beat){
      const loc=((pg.cards.world&&pg.cards.world.locations||[]).find(l=>l.id===beat.location)||{}).name||beat.location;
      head.append(el('details',pg.result?{class:'notes'}:{class:'notes',open:'open'},el('summary',{},t('What chapter {k} has to cover',{k})),el('p',{class:'hint'},t('Opens at {loc}, {when}. Events:',{loc,when:beat.when})),el('ol',{},(beat.events||[]).map(x=>el('li',{},x)))));
    }
  }
  root.append(head);
  const rep=reportNode();if(rep)root.append(rep);
  if(j===0)root.append(inputSection(pg));
  drawStages(root,pg,j);
}

function drawRight(){
  const root=$('#right'),S=st.story,j=S.cur,pg=cur(),k=j+1,r=pg.result;
  root.innerHTML='';
  if(isEnding(j)){
    root.append(el('div',{class:'head'},el('h2',{},t('Ending'))),
      el('p',{class:'hint'},t('Chapter {j} was the last chapter of the story, so there is no more story to write. The cards on the left are how it ended.',{j})));
    return;
  }
  const tags=el('span',{class:'row',style:'margin:0'});
  if(r)tags.append(el('span',{class:'tag'},r.words.toLocaleString()+' '+unitWord()));
  if(resStale(j))tags.append(el('span',{class:'tag stale'},t('Out of date: an earlier chapter was rewritten')));
  if(r&&cardsEdited(pg))tags.append(el('span',{class:'tag stale'},t('Cards changed since')));
  if(r&&r.update_failed)tags.append(el('span',{class:'tag stale'},t('Cards not updated')));
  root.append(el('div',{class:'head'},el('h2',{},t('Chapter {k} story',{k})),tags));
  const writing=st.busy==='chapter'&&st.busyPg===pg;
  if(writing&&r)root.append(el('p',{class:'hint'},t('The version below is replaced when this finishes.')));      // progress itself is shown beside the Write chapter button
  if(!r){root.append(el('p',{class:'hint'},t('Chapter {k} has not been written yet. Once you write it, the story appears here.',{k})));return}
  if(r.warnings.length)root.append(el('div',{class:'msg warn'},t('Check these:'),el('ul',{},r.warnings.map(w=>el('li',{},msg(w))))));
  if(r.unintroduced.length)root.append(el('div',{class:'msg warn'},t('Characters who appear without a card:'),el('ul',{},r.unintroduced.map(u=>el('li',{},u.name+(u.role?' ('+u.role+')':''))))));
  root.append(prose(r.text));
  root.append(el('h3',{class:'sm'},r.changes.length?t('What this chapter changed in the cards'):t('This chapter changed nothing in the cards')));
  if(r.changes.length)root.append(el('ul',{class:'chg'},r.changes.map(x=>el('li',{},msg(x.text)+(x.dropped&&x.dropped.length?t(' (dropped from the card: {items})',{items:x.dropped.join('; ')}):'')))));
  root.append(el('div',{class:'row'},el('button',{class:'sm',id:'dlchapter',onclick:()=>downloadText('chapter_'+pad(k)+'.md',r.text,'text/markdown')},t('Download chapter (.md)'))));
}

function drawConn(){
  const c=st.conn,n=$('#conn');
  n.textContent=!c?'':c.k==='checking'?t('Checking…'):c.k==='ok'?(c.model?t('Connected ({model})',{model:c.model}):t('Connected')):t('Failed: {why}',{why:c.why});
}
function drawTop(){
  const b=$('#banner');b.innerHTML='';
  if(st.banner)b.append(el('div',{class:'msg err'},msg(st.banner)+' ',el('button',{class:'sm',onclick:()=>{st.banner='';drawTop()}},t('Dismiss'))));
  $('#exportstory').disabled=!pages().some(p=>p.result);
  const sb=$('#stopbtn');sb.hidden=!st.busy;sb.disabled=!!st.stopping||!st.jobId;sb.textContent=st.stopping?t('Stopping…'):t('Stop');
  const si=$('#seedinfo');si.hidden=st.lastSeed==null;if(st.lastSeed!=null)$('#lastseed').textContent=t('Last run used seed {n}',{n:st.lastSeed});
  drawConn();syncTabIcon();
}
/* the parts of the page that are plain HTML: text carries data-i18n (or -ph / -aria for placeholders and labels) */
function applyStatic(){
  document.documentElement.lang=LANG==='zh'?'zh-Hans':'en';
  document.title=t('Pulpermill');
  document.querySelectorAll('[data-i18n]').forEach(n=>{n.textContent=t(n.dataset.i18n)});
  document.querySelectorAll('[data-i18n-ph]').forEach(n=>{n.placeholder=t(n.dataset.i18nPh)});
  document.querySelectorAll('[data-i18n-aria]').forEach(n=>{n.setAttribute('aria-label',t(n.dataset.i18nAria))});
  $('#lang-en').setAttribute('aria-pressed',String(LANG==='en'));$('#lang-zh').setAttribute('aria-pressed',String(LANG==='zh'));
}
function setLang(l){
  LANG=l==='zh'?'zh':'en';save('lang',LANG);applyStatic();draw();
}
/* A redraw rebuilds the panels, which would take away the caret and the scroll position of someone typing or reading.
   So the focused field (found again by its place in the page, and only if it still holds the same text) and the scroll
   positions are put back afterwards. Moving to another page passes keep=false: nothing is carried over. */
const FIELD_SEL='#mid textarea,#mid input,#mid select,#right textarea,#right input,#right select';
function snapView(){
  const a=document.activeElement,i=a?[...document.querySelectorAll(FIELD_SEL)].indexOf(a):-1,nl=document.querySelector('#nav .navlist'),r=$('#right');
  return {i,tag:a&&a.tagName,type:a&&a.type,value:a&&a.value,s:a&&a.selectionStart,e:a&&a.selectionEnd,dir:a&&a.selectionDirection,
    right:r?r.scrollTop:0,nav:nl?nl.scrollTop:0,y:window.scrollY};
}
function restoreView(v){
  if(v.i>=0){
    const f=[...document.querySelectorAll(FIELD_SEL)][v.i];
    if(f&&f.tagName===v.tag&&f.type===v.type&&f.value===v.value){
      f.focus({preventScroll:true});
      try{if(v.s!=null)f.setSelectionRange(v.s,v.e,v.dir||'none')}catch(e){/* this kind of field has no caret to put back */}
    }
  }
  const nl=document.querySelector('#nav .navlist'),r=$('#right');
  if(r&&r.scrollTop!==v.right)r.scrollTop=v.right;
  if(nl&&nl.scrollTop!==v.nav)nl.scrollTop=v.nav;
  if(window.scrollY!==v.y)window.scrollTo(0,v.y);
}
function draw(keep=true){
  const v=keep?snapView():null;
  drawTop();drawNav();drawMid();drawRight();updateCounters();refreshBar();scheduleSave();
  if(v)restoreView(v);
}
