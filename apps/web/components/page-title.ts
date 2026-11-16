'use client';
import {usePathname} from 'next/navigation';
import {createElement,type ReactNode} from 'react';
import {tr,useT} from '../lib/i18n';

const titles:Record<string,string>={};
export function registerTitles(items:readonly (readonly [string,string,...unknown[]])[]){for(const [path,title] of items)titles[path]=title}
export function titleFor(path:string){
 const p=path==='/studio/video'?'/studio/image':path==='/studio/tts'?'/studio/stt':path;
 return titles[p]?tr(titles[p]):'';
}
export function usePageTitle(){useT();return titleFor(usePathname()||'')}
/** Page heading that is not repeated when the same text is already shown in the top bar. */
export function H1({children}:{children:ReactNode}){const t=usePageTitle();return typeof children==='string'&&children===t?null:createElement('h1',null,children)}
