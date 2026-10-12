/* Pulpermill page: Downloads: zip writer, card files, the story as markdown. */
const storyFile=()=>slugify($('#slug').value||t('story'));
function downloadBlob(name,blob){
  const a=el('a',{href:URL.createObjectURL(blob),download:name});
  document.body.append(a);a.click();a.remove();
}
function downloadText(name,text,type){downloadBlob(name,new Blob([text],{type:type||'text/plain'}))}

/* A zip file with nothing compressed (cards are small): enough to hand over several files in one download. Names are UTF-8. */
const utf8=s=>{const e=encodeURIComponent(s),o=[];for(let i=0;i<e.length;i++){if(e[i]==='%'){o.push(parseInt(e.substr(i+1,2),16));i+=2}else o.push(e.charCodeAt(i))}return Uint8Array.from(o)};
const CRC_TABLE=(()=>{const t=[];for(let n=0;n<256;n++){let c=n;for(let k=0;k<8;k++)c=c&1?0xEDB88320^(c>>>1):c>>>1;t.push(c>>>0)}return t})();
const crc32=b=>{let c=0xFFFFFFFF;for(let i=0;i<b.length;i++)c=CRC_TABLE[(c^b[i])&255]^(c>>>8);return (c^0xFFFFFFFF)>>>0};
function makeZip(files){
  const parts=[],central=[];let offset=0;
  const d=new Date(),time=(d.getHours()<<11)|(d.getMinutes()<<5)|(d.getSeconds()>>1),date=((Math.max(1980,d.getFullYear())-1980)<<9)|((d.getMonth()+1)<<5)|d.getDate();
  const u16=n=>[n&255,(n>>>8)&255],u32=n=>[n&255,(n>>>8)&255,(n>>>16)&255,(n>>>24)&255];
  files.forEach(f=>{
    const name=utf8(f.name),data=utf8(f.text),crc=crc32(data);
    const head=[0x50,0x4b,3,4,...u16(20),...u16(0x0800),...u16(0),...u16(time),...u16(date),...u32(crc),...u32(data.length),...u32(data.length),...u16(name.length),...u16(0)];
    parts.push(Uint8Array.from(head),name,data);
    central.push(Uint8Array.from([0x50,0x4b,1,2,...u16(20),...u16(20),...u16(0x0800),...u16(0),...u16(time),...u16(date),...u32(crc),...u32(data.length),...u32(data.length),
      ...u16(name.length),...u16(0),...u16(0),...u16(0),...u16(0),...u32(0),...u32(offset)]),name);
    offset+=head.length+name.length+data.length;
  });
  const cdSize=central.reduce((n,p)=>n+p.length,0);
  const end=Uint8Array.from([0x50,0x4b,5,6,0,0,0,0,...u16(files.length),...u16(files.length),...u32(cdSize),...u32(offset),0,0]);
  const all=[...parts,...central,end],out=new Uint8Array(all.reduce((n,p)=>n+p.length,0));let o=0;
  all.forEach(p=>{out.set(p,o);o+=p.length});
  return out;
}

/* One file per card, and one per character, so a single card can be kept, shared or imported by itself. The style, setup and world
   files are the wrapper the importer has always read ({format, chapter, <card>: ...}). A character file is just the character:
   the importer merges a single character file into the cast by id (replacing that character, or adding a new one), whereas a
   wrapped list would replace the whole cast, so several character files could not be imported together. */
const CARD_FILE_NAME={style:'style',outline:'setup',world:'world'};
/* The wrapper the importer has always read ({format, chapter, <card>: ...}) for one card, standing alone. Shared by
   the zip export below and by the single-card download button, so a card downloaded on its own is byte-for-byte
   the same file that was always sitting inside the zip — just reachable without unzipping anything. */
function cardFileText(key,pg,j){
  const end=isEnding(j),meta={format:'pulpermill-cards',version:1};
  if(end)meta.note='cards after chapter '+j;else meta.chapter=j+1;
  return JSON.stringify(Object.assign({},meta,{[key]:clean(pg.cards[key],key)}),null,2);
}
function exportCard(key){
  const j=st.story.cur,pg=cur();
  downloadText(CARD_FILE_NAME[key]+'.json',cardFileText(key,pg,j),'application/json');
}
function cardFiles(j){
  const pg=pages()[j];
  const files=[],used={};
  if(pg.cards.style)files.push({name:'style.json',text:cardFileText('style',pg,j)});
  if(pg.cards.outline)files.push({name:'setup.json',text:cardFileText('outline',pg,j)});
  if(pg.cards.world)files.push({name:'world.json',text:cardFileText('world',pg,j)});
  (pg.cards.characters||[]).forEach((c,i)=>{
    let base=slugify(c.id||c.name||('character '+(i+1)))||('character_'+(i+1));
    if(used[base])base+='_'+(i+1);used[base]=1;
    files.push({name:'characters/'+base+'.json',text:JSON.stringify(clean([c],'characters')[0],null,2)});
  });
  return files;
}
/* One character, one file, straight to disk — no zip, no picking it back out of a project export afterward. The
   importer already treats a single character file as "add or update this one person" (matched by id) rather than
   "replace the whole cast", so this and Import cards together are the mix-and-match path between stories: export
   a character here, drop the file into Import cards on any other project, done. */
function exportCharacter(c){
  downloadText((slugify(c.id||c.name||'character')||'character')+'.json',JSON.stringify(clean(c,'characters'),null,2),'application/json');
}
function exportPageCards(j){
  j=(typeof j==='number')?j:st.story.cur;
  const end=isEnding(j),folder=storyFile()+(end?'_ending_cards':'_chapter_'+pad(j+1)+'_cards');
  downloadBlob(folder+'.zip',new Blob([makeZip(cardFiles(j).map(f=>({name:folder+'/'+f.name,text:f.text})))],{type:'application/zip'}));
}
function exportStory(){
  const md=pages().map((p,i)=>p.result?'## '+t('Chapter {k}',{k:i+1})+'\n\n'+p.result.text.trim()+'\n':null).filter(Boolean).join('\n');
  if(md)downloadText(storyFile()+'_story.md',md,'text/markdown');
}
