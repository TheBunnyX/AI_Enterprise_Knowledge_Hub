/** Short options the assistant offered at the end of a clarifying question ("• A • B • other"), so the page can show them as buttons. */
const OTHER=/ระบุ|อื่น|other|specify/i;

export function choiceOptions(content:string):{question:string;options:string[];other:string|null}{
  const text=(content||'').trim();
  const asked=text.search(/[?？]|ต้องการ|ให้ช่วย|would you like|which/i);
  if(asked<0)return {question:'',options:[],other:null};
  // bullets on their own lines, or all on one line separated by "•"
  const items:string[]=[];
  if(text.includes('•')){
    for(const part of text.split('•').slice(1))items.push(part.split('\n')[0].trim());
  }else{
    for(const line of text.split('\n')){const m=line.match(/^\s*(?:[-*–]|\d{1,2}[.)])\s+(.+)$/);if(m)items.push(m[1].trim())}
  }
  const clean=items.map(s=>s.replace(/[\s.。]+$/,'').replace(/^\*\*(.+)\*\*$/,'$1')).filter(s=>s&&s.length<=80);
  if(clean.length<2||clean.length>6||clean.length!==items.length)return {question:'',options:[],other:null};
  const other=clean.find(s=>OTHER.test(s))||null;
  const head=text.includes('•')?text.split('•')[0]:text.split('\n').slice(0,text.split('\n').findIndex(l=>/^\s*(?:[-*–]|\d{1,2}[.)])\s+/.test(l))).join(' ');
  return {question:head.trim().slice(0,300),options:clean.filter(s=>s!==other),other};
}

export type MadeFile={name:string;href:string};

/** The "📎 ไฟล์ที่สร้างให้: [name](/api/files/id) · ..." line the server appends to a reply, split into file cards. */
export function splitFiles(content:string):{text:string;files:MadeFile[]}{
  const m=(content||'').match(/\n*📎[^\n]*?:\s*((?:\[[^\]]+\]\(\/api\/files\/[^)\s]+\)(?:\s*·\s*)?)+)\s*$/);
  if(!m)return {text:content||'',files:[]};
  const files=[...m[1].matchAll(/\[([^\]]+)\]\((\/api\/files\/[^)\s]+)\)/g)].map(x=>({name:x[1],href:x[2]}));
  return {text:(content.slice(0,m.index)).trimEnd(),files};
}

/** The options of a question written inline ("• A • B") as a list, so they read as separate lines. */
export function listOptions(content:string):string{
  const c=choiceOptions(content);
  if(!c.options.length&&!c.other)return content;
  const all=[...c.options,...(c.other?[c.other]:[])];
  return c.question+'\n\n'+all.map(o=>'- '+o).join('\n');
}
