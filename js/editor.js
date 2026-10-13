/* Pulpermill page: The card field editor: field rendering, links between cards, flags, use counts, selects. */
const STAGES=[
 {k:'style',t:'Style',d:'How the narration sounds. Built from your input with no names or plot.'},
 {k:'characters',t:'Characters',d:'The whole cast in one pass, written to be different from each other.'},
 {k:'world',t:'World',d:'Setting, rules, hidden truths, places, objects and groups.'},
 {k:'outline',t:'Setup',d:'Premise, ending, arcs and the opening beat. The story continues from here, one chapter at a time.'}
];
const HINTS={style:'How should the narration sound? What kind of narrator is telling this, and what attitude does it take toward events (humor, if any)? Do they comment or stay quiet? How do they handle feelings? What rhythm, how much dialogue? What would ruin it?',characters:'For each person: what they want, how they see themselves versus what they actually do, how they talk, their habits, and how they feel about each other person. Say exactly who did what to whom.',world:'The place and occasion, how it works as plain fact (one line per mechanic), the places, the objects that matter, and the secrets: what is true, who knows it, who does not.',outline:'Chapter by chapter: where, whose point of view, what each person wants and is hiding, what goes wrong, how it ends. What must be planted early and pay off later. What the ending looks like concretely, and what stays unresolved.'};
let HIDE=[];
/* true while drawing a character's `wrap`: live state that starts empty and that the model fills in chapter by chapter */
let LIVE=false;
const LIVE_HINT=()=>t('Starts empty; filled in as the story goes');
const withHide=(list,fn)=>{const old=HIDE;HIDE=list;try{return fn()}finally{HIDE=old}};

/* ---------- links between cards ----------
   Some fields name something on another card: a character, a place, a hidden truth (the backend lists them in SCH.refs).
   When a card is regenerated its ids can change, and every field on the other cards that named the old ones now points at
   nothing. These functions find those fields so the editor can mark them and generation can refuse to build on them. A
   link can only be judged when the card it points into is on the page. */
let PATH=[];                                   // where the field being drawn sits: ['world','objects','owner']
let REFCTX={character:null,location:null,truth:null};
function refContext(cards){
  /* id -> what the person sees for it (a name, or for a hidden truth the fact); two with the same name show their ids */
  const ids=(arr,nameOf)=>{
    const rows=(arr||[]).filter(x=>x&&x.id).map(x=>[x.id,String(nameOf(x)||x.id).replace(/\s+/g,' ').trim()]);
    const count={};rows.forEach(r=>count[r[1]]=(count[r[1]]||0)+1);
    return new Map(rows.map(([id,n])=>[id,count[n]>1?n+' ('+id+')':n]));
  };
  const cut=s=>s.length>60?s.slice(0,60).trimEnd()+'…':s;
  const w=cards.world;
  REFCTX={character:cards.characters?ids(cards.characters,c=>c.name):null,location:w?ids(w.locations,l=>l.name):null,
          truth:w?ids(w.hidden_truths,x=>cut(String(x.fact||''))):null};
}
const kindName=k=>k==='character'?t('character'):k==='location'?t('location'):t('hidden truth');
const knownIds=k=>REFCTX[k]?[...REFCTX[k].keys()]:[];
/* false when the value is fine, else {missing:true} (empty but required) or {missing:false} (names nothing) */
function badRef(kind,path,v){
  const set=REFCTX[kind];if(!set)return false;
  if(v==null||v===''){return (SCH.nullable||[]).includes(path)?false:{missing:true}}
  return set.has(String(v).trim())?false:{missing:false};
}
function refWhy(kind,bad,vals){
  const known=knownIds(kind),list=known.slice(0,8).join(', ')+(known.length>8?'…':'');
  return bad.missing?t('This needs a {kind}. Available: {known}',{kind:kindName(kind),known:list}):
    t('Not a {kind} on the cards: {v}. Available: {known}',{kind:kindName(kind),v:vals.join(', '),known:list});
}
/* every broken link inside `o`, which sits at `path` (card name first) */
function scanRefs(o,path,out,who){
  out=out||[];
  if(Array.isArray(o)){o.forEach(x=>scanRefs(x,path,out,who));return out}
  if(o&&typeof o==='object'){
    const w=o.name||(o.chapter_num!=null?t('Chapter {k}',{k:o.chapter_num}):null)||o.id||who;
    for(const k in o)scanRefs(o[k],path.concat(k),out,w);
    return out;
  }
  const p=path.join('.'),kind=(SCH.refs||{})[p];
  if(!kind)return out;
  const bad=badRef(kind,p,o);
  if(bad)out.push({path:p,kind,value:o,missing:bad.missing,card:path[0],who:who||'',field:path[path.length-1]});
  return out;
}
const brokenIn=(cards,keys)=>{refContext(cards);return (keys||CARD_KEYS).flatMap(k=>cards[k]?scanRefs(cards[k],[k],[]):[])};
function brokenLine(b){
  const card=t((STAGES.find(s=>s.k===b.card)||{t:b.card}).t);
  const where=[card,b.who,label(b.field)].filter(Boolean).join(' › ');
  return b.missing?t('{where}: needs a {kind}',{where,kind:kindName(b.kind)}):t('{where}: "{v}" is not a {kind} on the cards',{where,v:b.value,kind:kindName(b.kind)});
}
function markRef(lab,ta,kind,path,vals){
  const why=el('span',{class:'why'});lab.append(why);
  const upd=()=>{
    const vs=vals(),bad=vs.map(v=>badRef(kind,path,v)),idx=bad.map((b,i)=>b?i:-1).filter(i=>i>=0);
    lab.classList.toggle('bad',idx.length>0);why.hidden=!idx.length;
    why.textContent=idx.length?refWhy(kind,bad[idx[0]],idx.map(i=>vs[i])):'';
  };
  ta.addEventListener('input',upd);ta.addEventListener('change',upd);upd();
}

/* ---------- generic card editor ----------
   `bp` is the same card as it stood in the previous chapter's page. A field that differs from it turns yellow and shows
   the old value on top of it (and goes back to normal if you type the old value back). Page 1 has nothing to compare to. */
const norm=x=>Array.isArray(x)?x.map(norm):(x&&typeof x==='object')?Object.fromEntries(Object.keys(x).filter(k=>k!=='uses').sort().map(k=>[k,norm(x[k])])):(x==null?'':x);   // use counts are not an edit
const same=(a,b)=>JSON.stringify(norm(a))===JSON.stringify(norm(b));
const showOld=v=>{const s=Array.isArray(v)?v.join('; '):(v==null?'':String(v));return s.trim()?s:t('(empty)')};
function matchItem(arr,it,i){
  if(!Array.isArray(arr))return undefined;
  if(it&&it.id!=null)return arr.find(x=>x&&x.id===it.id);
  if(it&&it.chapter_num!=null)return arr.find(x=>x&&x.chapter_num===it.chapter_num);
  return arr[i];
}
function track(lab,ctl,old,get){
  const was=el('span',{class:'was'},t('was: {old}',{old:showOld(old)}));
  lab.insertBefore(was,ctl);
  const upd=()=>{const d=!same(get(),old);lab.classList.toggle('chg',d);was.hidden=!d};
  ctl.addEventListener('input',upd);ctl.addEventListener('change',upd);upd();
}
/* The title of a list item is the thing itself: its name, or for a hidden truth the fact. Ids (truth_1, loc_2) are only
   labels for the code, so they never become titles. Long titles are cut with an ellipsis (the full text is the tooltip);
   a Han character counts as two letters because it is about twice as wide. */
const personName=v=>{const m=REFCTX.character;return typeof v!=='string'||v===''?'':(m&&m.has(v)?m.get(v):v)};   // a character id as the person's name
function itemTitle(it,i){
  const raw=String(it.name||it.fact||(it.chapter_num?t('Chapter {k}',{k:it.chapter_num}):'')||personName(it.character)||personName(it.toward)||t('Item {k}',{k:i+1})).replace(/\s+/g,' ').trim();
  let w=0,out='';
  for(const c of raw){w+=cjkRe.test(c)?2:1;cjkRe.lastIndex=0;if(w>64)return {text:out.trimEnd()+'…',full:raw};out+=c}
  return {text:raw,full:raw};
}
/* Use counts. A list the backend rotates (SCH.pools) shows, beside each item, how many chapters it was handed to the writer in;
   the least-used ones are handed over next. The counts live in the owning card's `uses` ({field: {item text or id: n}}).
   A plain text list becomes one row per item so each count sits next to its item; editing an item's text keeps its count. */
const usedTxt=n=>t('used {n}×',{n});
const usedTip=()=>t('How many chapters this was handed to the writer in. The least-used items are handed over next.');
const isPool=p=>(SCH.pools||{})[p]!=null;
const usesOf=(owner,key)=>{owner.uses=owner.uses&&typeof owner.uses==='object'?owner.uses:{};return owner.uses[key]=owner.uses[key]||{}};
/* A short note under a list whose empty state means something. */
const LIST_HINTS={'style.chapter_shapes':()=>t('One shape is handed to each chapter in turn, the least-used first. Empty is fine: the model then decides how each chapter opens and closes.')};
const withListHint=(lab,path)=>{const h=LIST_HINTS[path];if(h)lab.append(el('p',{class:'hint'},h()));return lab};
function usedList(parent,key,hasBase,old){
  const lab=el('div',{class:'f'},el('span',{},label(key))),box=el('div',{class:'urows'});lab.append(box);
  const commit=()=>box.dispatchEvent(new Event('change',{bubbles:true}));
  const drop=(i,cur)=>{delete usesOf(parent,key)[cur];parent[key].splice(i,1);render();commit()};
  const render=()=>{
    box.textContent='';
    parent[key].forEach((txt,i)=>{
      let cur=txt;const n=usesOf(parent,key)[txt]||0;
      const ta=el('textarea',{rows:Math.min(6,Math.max(1,Math.ceil(txt.length/70)))});ta.value=txt;
      ta.addEventListener('input',()=>{
        const nv=ta.value.trim(),u=usesOf(parent,key);
        if(nv!==cur){delete u[cur];if(nv&&n)u[nv]=n;cur=nv}
        parent[key][i]=nv;
      });
      ta.addEventListener('change',()=>{if(!ta.value.trim())drop(i,cur)});
      box.append(el('div',{class:'urow'},ta,el('span',{class:'used'+(n?'':' zero'),title:usedTip()},usedTxt(n)),
        el('button',{class:'sm',type:'button',title:t('Remove this item'),onclick:()=>drop(i,cur)},'×')));
    });
    box.append(el('div',{class:'addrow'},el('button',{class:'sm',type:'button',onclick:()=>{parent[key].push('');render();const r=box.querySelectorAll('.urow textarea');r[r.length-1].focus()}},t('Add item'))));
  };
  render();
  if(hasBase)track(lab,box,old,()=>parent[key]);
  return lab;
}
/* A field that names a character, place or hidden truth is picked from the ones on the cards, never typed. A value that is
   already there but names nothing (the thing was regenerated away) stays in the list marked "not on the cards" so it can
   be seen and replaced. */
const missingOpt=v=>t('{v} (not on the cards)',{v});
function refSelect(parent,key,kind,path,hasBase,old){
  const v=parent[key]==null?'':String(parent[key]),map=REFCTX[kind],nullable=(SCH.nullable||[]).includes(path);
  const sel=el('select',{});
  sel.append(el('option',{value:''},nullable?t('(none)'):t('(choose one)')));
  map.forEach((name,id)=>sel.append(el('option',{value:id},name)));
  if(v!==''&&!map.has(v))sel.append(el('option',{value:v},missingOpt(v)));
  sel.value=v;
  sel.addEventListener('change',()=>{parent[key]=sel.value});
  const lab=el('label',{class:'f'},el('span',{},label(key)),sel);
  if(hasBase)track(lab,sel,old,()=>parent[key]);
  markRef(lab,sel,kind,path,()=>[sel.value]);
  return lab;
}
function refMulti(parent,key,kind,path,hasBase,old){
  const map=REFCTX[kind],cur=Array.isArray(parent[key])?parent[key]:[];
  const lab=el('div',{class:'f'},el('span',{},label(key)));
  const det=el('details',{class:'multi'}),sum=el('summary',{}),body=el('div',{class:'mbody'});
  const opts=[...map.entries(),...cur.filter(x=>!map.has(x)).map(x=>[x,missingOpt(x)])];
  const boxes=opts.map(([id,name])=>{
    const cb=el('input',{type:'checkbox',value:id});cb.checked=cur.includes(id);
    body.append(el('label',{class:'chk'},cb,' '+name));return cb;
  });
  const nameOf=id=>(opts.find(o=>o[0]===id)||[id,id])[1];
  const sync=()=>{parent[key]=boxes.filter(b=>b.checked).map(b=>b.value);sum.textContent=parent[key].length?parent[key].map(nameOf).join(', '):t('(none)')};
  boxes.forEach(b=>b.addEventListener('change',sync));
  sum.textContent=cur.length?cur.map(nameOf).join(', '):t('(none)');
  det.append(sum,body);lab.append(det);
  if(hasBase)track(lab,det,old,()=>parent[key]);
  markRef(lab,det,kind,path,()=>parent[key]||[]);
  return lab;
}
function choiceSelect(parent,key,choices,path,hasBase,old){
  const v=parent[key],has=!(v==null||v===''||v===0),nullable=(SCH.nullable||[]).includes(path);
  const sel=el('select',{});
  if(nullable||!has)sel.append(el('option',{value:''},t('(none)')));
  choices.forEach(([val,name])=>sel.append(el('option',{value:String(val)},val+' · '+t(name))));
  if(has&&!choices.some(c=>c[0]===v))sel.append(el('option',{value:String(v)},String(v)));
  sel.value=has?String(v):'';
  sel.addEventListener('change',()=>{parent[key]=sel.value===''?null:Number(sel.value)});
  const lab=el('label',{class:'f'},el('span',{},label(key)),sel);
  if(hasBase)track(lab,sel,old,()=>parent[key]);
  return lab;
}
/* Warnings that name a field (the backend sends `at` with each): the field is outlined in orange, with the warning under it,
   for as long as it still holds what the warning is about. Changing it clears the outline at once. */
let FLAGS=[];
const flagText=x=>x==null?'':String(x).trim();
function flagLive(at,cur){
  const vals=Array.isArray(cur)?cur.map(flagText):[flagText(cur)];
  const has=at.value==null?(!Array.isArray(cur)&&flagText(cur)===''):vals.includes(flagText(at.value));
  return at.mode==='lacks'?!has:has;
}
function applyFlags(lab,parent,key){
  const p=PATH.join('.'),item=parent.id!=null?String(parent.id):parent.chapter_num!=null?String(parent.chapter_num):null;
  const mine=FLAGS.filter(f=>f.at.path===p&&(f.at.item==null||f.at.item===item));
  if(!mine.length)return;
  const note=el('span',{class:'flagwhy'});lab.append(note);
  const upd=()=>{
    const live=mine.filter(f=>flagLive(f.at,parent[key]));
    lab.classList.toggle('flag',live.length>0);note.hidden=!live.length;note.textContent=live.length?msg(live[0].w):'';
  };
  lab.addEventListener('input',upd);lab.addEventListener('change',upd);upd();
}
const flagsOf=w=>(w||[]).flatMap(x=>((x&&x.at)||[]).map(at=>({at,w:x})));
function field(parent,key,en,bp){PATH.push(key);try{const lab=field_(parent,key,en,bp);if(lab&&FLAGS.length)applyFlags(lab,parent,key);return lab}finally{PATH.pop()}}
function field_(parent,key,en,bp){
  const v=parent[key],hasBase=bp!=null&&typeof bp==='object',old=hasBase?bp[key]:undefined;
  if(HIDE.includes(key)||key==='uses')return null;          // use counts are shown beside the items they count
  if(key==='id')return el('div',{class:'ro'},'id: '+v);
  const pathStr=PATH.join('.'),rk=(SCH.refs||{})[pathStr],ch=(SCH.choices||{})[pathStr];
  if(rk&&REFCTX[rk]&&(typeof v==='string'||v==null))return refSelect(parent,key,rk,pathStr,hasBase,old);
  if(rk&&REFCTX[rk]&&Array.isArray(v)&&!v.some(x=>x&&typeof x==='object'))return refMulti(parent,key,rk,pathStr,hasBase,old);
  if(ch&&(typeof v==='number'||v==null||v===''))return choiceSelect(parent,key,ch,pathStr,hasBase,old);
  if(en&&en[key]&&typeof v==='string'){
    const opts=en[key].includes(v)?en[key]:[v,...en[key]];
    const sel=el('select',{},opts.map(o=>el('option',{value:o},optLabel(o))));sel.value=v;
    sel.addEventListener('change',()=>{parent[key]=sel.value});
    const lab=el('label',{class:'f'},el('span',{},label(key)),sel);
    if(hasBase)track(lab,sel,old,()=>parent[key]);
    return lab;
  }
  if(Array.isArray(v)){
    const objs=v.length&&v.some(x=>x&&typeof x==='object');
    if(!objs&&isPool(pathStr)&&!LIVE)return withListHint(usedList(parent,key,hasBase,old),pathStr);
    if(!objs){
      const ta=el('textarea',LIVE?{rows:Math.max(2,v.length+1),placeholder:LIVE_HINT()}:{rows:Math.max(2,v.length+1)});
      ta.value=v.join('\n');
      ta.addEventListener('input',()=>{parent[key]=ta.value.split('\n').map(s=>s.trim()).filter(Boolean)});
      const lab=el('label',{class:'f'},el('span',{},label(key)+t(' (one per line)')),ta);
      if(hasBase)track(lab,ta,old,()=>parent[key]);
          if(rk)markRef(lab,ta,rk,pathStr,()=>parent[key]||[]);
      return lab;
    }
    const box=el('div',{class:'f'},el('span',{class:'ro'},label(key)));
    const hasList=hasBase&&Array.isArray(old),here=PATH.slice(),flagsHere=FLAGS;
    const render=()=>{
      const keep=PATH,keepF=FLAGS;PATH=here.slice();FLAGS=flagsHere;
      try{
      box.querySelectorAll('.item,.addrow').forEach(n=>n.remove());
      v.forEach((it,i)=>{
        const bi=hasList?matchItem(old,it,i):undefined;
        const tag=!hasList?null:!bi?el('span',{class:'tag chgtag'},t('new')):!same(it,bi)?el('span',{class:'tag chgtag'},t('changed')):null;
        const ti=itemTitle(it,i),broken=scanRefs(it,PATH.slice(),[]).length;
        const pooled=isPool(pathStr)&&it&&it.id!=null,n=pooled?(usesOf(parent,key)[it.id]||0):0;
        const isCast=PATH.join('.')==='characters',ii=i;
        const expBtn=isCast?el('button',{class:'sm',type:'button',title:t('Export this character'),onclick:(ev)=>{ev.preventDefault();ev.stopPropagation();exportCharacter(st.story.cur,ii)}},t('Export')):null;
        const ttl=el('span',{class:'ttl'},ti.text),sum=el('summary',ti.text===ti.full?{}:{title:ti.full},ttl,tag,expBtn,pooled?el('span',{class:'tag usedtag'+(n?'':' zero'),title:usedTip()},usedTxt(n)):null,broken?el('span',{class:'tag bad'},t('broken link')):null);
        const d=el('details',broken?{class:'item',open:'open'}:{class:'item'},sum);
        const inner=el('div',{class:'in'});
        /* the title follows what is typed (or picked) in the fields it is made from */
        const retitle=()=>{const x=itemTitle(it,i);ttl.textContent=x.text;if(x.text===x.full)sum.removeAttribute('title');else sum.title=x.full};
        inner.addEventListener('input',retitle);inner.addEventListener('change',retitle);
        for(const kk in it){const f=field(it,kk,en,bi);if(f)inner.append(f)}
        inner.append(el('button',{class:'sm',onclick:()=>{
          if(!confirm(t('Remove “{name}” from this card? This cannot be undone.',{name:itemTitle(it,i).text})))return;       // deleting an item is guarded
          if(pooled)delete usesOf(parent,key)[it.id];v.splice(i,1);render();
          scheduleSave();
        }},t('Remove this item')));
        d.append(inner);box.append(d);
      });
      box.append(el('div',{class:'addrow'},el('button',{class:'sm',onclick:()=>{v.push(blank(v[0]));render()}},t('Add item'))));
      }finally{PATH=keep;FLAGS=keepF}
    };
    render();return box;
  }
  if(v&&typeof v==='object'){
    const live=key==='wrap',was=LIVE;
    const fs=el('fieldset',{},el('legend',{},live?t('Updated after each chapter'):label(key)));
    const sub=hasBase?(old&&typeof old==='object'&&!Array.isArray(old)?old:{}):undefined;
    if(live)LIVE=true;
    try{for(const kk in v){const f=field(v,kk,en,sub);if(f)fs.append(f)}}finally{LIVE=was}
    return fs;
  }
  const isNum=typeof v==='number';
  const ta=el('textarea',{rows:isNum?1:Math.min(8,Math.max(1,Math.ceil(String(v||'').length/90)))});
  if(LIVE&&!isNum)ta.placeholder=LIVE_HINT();
  ta.value=v==null?'':v;
  ta.addEventListener('input',()=>{parent[key]=isNum?Number(ta.value):ta.value});
  const lab=el('label',{class:'f'},el('span',{},label(key)),ta);
  if(hasBase)track(lab,ta,old,()=>parent[key]);
  if(rk&&!isNum)markRef(lab,ta,rk,pathStr,()=>[ta.value.trim()]);
  return lab;
}
/* `card` is the card's name (style, characters, world, outline): the start of every field's path */
function editor(data,en,base,card){
  const wrap=el('div'),keep=PATH;
  try{
    if(Array.isArray(data)&&data.length&&data.every(x=>x&&typeof x==='object')){
      PATH=[];
      const f=field({[card]:data},card,en,Array.isArray(base)?{[card]:base}:undefined);
      f.querySelector('span.ro').remove();wrap.append(f);
    }else if(data&&typeof data==='object'){
      PATH=[card];
      const b=base&&typeof base==='object'&&!Array.isArray(base)?base:undefined;
      for(const k in data){const f=field(data,k,en,b);if(f)wrap.append(f)}
    }
  }finally{PATH=keep}
  return wrap;
}
