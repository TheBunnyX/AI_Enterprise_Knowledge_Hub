'use client';
import { createContext, useContext, useEffect, useState, type ReactNode } from 'react';
import { EN } from './en';
import { LANG_COOKIE, LOCALE, normalizeLang, type Lang } from './lang';
export { LANG_COOKIE, LOCALE, normalizeLang, type Lang };

/**
 * UI-only translation. Thai source text is the key: `t('หน้าหลัก')` returns it as-is in Thai and the
 * English entry from ./en.ts in English. `{name}` placeholders are filled from the second argument.
 * Missing English entries fall back to the Thai text (tests/i18n.test.tsx fails if one is missing).
 */

let current:Lang='th';
export const getLang=()=>current;

type Vars=Record<string,string|number|null|undefined>;
/** Translate outside React (api errors, formatters). Components should use `useT()` so they re-render on a language switch. */
export function tr(th:string,vars?:Vars):string{
 let s=current==='en'?(EN[th]??th):th;
 if(vars)s=s.replace(/\{(\w+)\}/g,(m,k)=>k in vars?String(vars[k]??''):m);
 return s;
}

const Ctx=createContext<{lang:Lang;setLang:(l:Lang)=>void}>({lang:'th',setLang:()=>{}});

export function LangProvider({initialLang='th',children}:{initialLang?:Lang;children:ReactNode}){
 const [lang,set]=useState<Lang>(initialLang);
 current=lang; // set during render so every child rendered in this pass reads the new language
 useEffect(()=>{document.documentElement.lang=lang},[lang]);
 const setLang=(l:Lang)=>{
  current=l;set(l);
  try{document.cookie=`${LANG_COOKIE}=${l};path=/;max-age=31536000;samesite=lax`}catch{}
 };
 return <Ctx.Provider value={{lang,setLang}}>{children}</Ctx.Provider>;
}

export const useLang=()=>useContext(Ctx);
/** `const t=useT()` — subscribes the component to language changes. */
export function useT(){useContext(Ctx);return tr}
