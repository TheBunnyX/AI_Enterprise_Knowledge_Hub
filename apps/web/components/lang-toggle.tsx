'use client';
import { useLang } from '../lib/i18n';

/** TH / EN switch shown next to the theme toggle. Labels are written in the language they switch *to*, so they are not translated. */
export function LangToggle(){
 const {lang,setLang}=useLang();
 const next=lang==='th'?'en':'th';
 const label=lang==='th'?'Switch to English':'สลับเป็นภาษาไทย';
 return <button type="button" onClick={()=>setLang(next)} aria-label={label} title={label}
  className="inline-flex h-9 items-center justify-center rounded-full px-2 text-xs font-semibold tracking-wide !border-0 !bg-transparent !shadow-none transition-colors hover:!bg-accent !text-slate-500">
  <span className={lang==='th'?'!text-foreground':''}>TH</span><span className="mx-1 opacity-40">|</span><span className={lang==='en'?'!text-foreground':''}>EN</span>
 </button>;
}
