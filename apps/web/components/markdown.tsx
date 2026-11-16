'use client';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import remarkMath from 'remark-math';
import rehypeKatex from 'rehype-katex';
import 'katex/dist/katex.min.css';
import { tr } from '../lib/i18n';
import './markdown.css';
import { linkCitations } from './cite-links';
export { linkCitations };

// Models often answer with \( \) and \[ \] math; remark-math expects $ and $$.
export function normalizeMath(text:string){
 return text
  .replace(/\\\[([\s\S]+?)\\\]/g,(_,m:string)=>'\n$$'+m+'$$\n')
  .replace(/\\\(([\s\S]+?)\\\)/g,(_,m:string)=>'$'+m+'$');
}

const NL=String.fromCharCode(10);

/** Citation markers in an answer, numbered by first use: {text with markers turned into links, order[displayNo-1]=original number}. */

export type Cites={count:number;onPick:(original:number)=>void;active?:number};

export function Markdown({text,breaks=false,cites}:{text:string;breaks?:boolean;cites?:Cites}){
 const source=normalizeMath(cites?linkCitations(text,cites.count).text:text);
 return <div className="md"><ReactMarkdown remarkPlugins={[remarkGfm,remarkMath]} rehypePlugins={[[rehypeKatex,{throwOnError:false,strict:false}]]} components={{a:({href,children})=>{const m=/^#cite-(\d+)$/.exec(href||'');if(m&&cites){const n=Number(m[1]);return <button type="button" className={'cite-chip'+(cites.active===n?' on':'')} aria-label={tr('ดูแหล่งอ้างอิง {children}',{children:String(children??'')})} onClick={()=>cites.onPick(n)}>{children}</button>}return <a href={href} target="_blank" rel="noopener noreferrer">{children}</a>}}}>{breaks?source.split(NL).join('  '+NL):source}</ReactMarkdown></div>;
}
