'use client';
import {useEffect,useState} from 'react';
import { tr } from '../lib/i18n';

const stroke={fill:'none',stroke:'currentColor',strokeWidth:1.5,strokeLinecap:'round',strokeLinejoin:'round'} as const;
/** Thin-line sun and moon: a plain glyph, no tile around it. */
const Sun=()=><svg width="20" height="20" viewBox="0 0 24 24" aria-hidden {...stroke}><circle cx="12" cy="12" r="3.6"/><path d="M12 3v1.8M12 19.2V21M3 12h1.8M19.2 12H21M5.6 5.6l1.3 1.3M17.1 17.1l1.3 1.3M18.4 5.6l-1.3 1.3M6.9 17.1l-1.3 1.3"/></svg>;
const Moon=()=><svg width="20" height="20" viewBox="0 0 24 24" aria-hidden {...stroke}><path d="M20 14.2A8 8 0 0 1 9.8 4a8 8 0 1 0 10.2 10.2Z"/></svg>;

/** Light / dark switch. The class on <html> is set before paint by the inline script in the root layout. */
export function ThemeToggle(){
 const [dark,setDark]=useState(false);
 useEffect(()=>{setDark(document.documentElement.classList.contains('dark'))},[]);
 const toggle=()=>{
  const next=!dark;setDark(next);
  document.documentElement.classList.toggle('dark',next);
  try{localStorage.setItem('hub.theme',next?'dark':'light')}catch{}
 };
 return <button type="button" onClick={toggle} aria-label={dark?tr('สลับเป็นธีมสว่าง'):tr('สลับเป็นธีมมืด')} aria-pressed={dark} title={dark?tr('ธีมสว่าง'):tr('ธีมมืด')}
  className={'inline-flex size-9 items-center justify-center rounded-full !border-0 !bg-transparent !shadow-none transition-colors hover:!bg-accent '+(dark?'!text-amber-400':'!text-slate-500')}>
  {dark?<Sun/>:<Moon/>}
 </button>;
}
