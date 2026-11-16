import type { Metadata } from 'next';
import { cookies } from 'next/headers';
import Hub from '../components/hub';
import {LANG_COOKIE,normalizeLang} from '../lib/lang';
import './globals.css';
import './capsule.css';
import './dark-colors.css';
const THEME_INIT="try{var t=localStorage.getItem('hub.theme');if(t==='dark'||(t!=='light'&&matchMedia('(prefers-color-scheme: dark)').matches))document.documentElement.classList.add('dark')}catch(e){}";
export const dynamic='force-dynamic';
export async function generateMetadata():Promise<Metadata>{
  const lang=normalizeLang((await cookies()).get(LANG_COOKIE)?.value);
  return lang==='en'
    ?{title:'AI Knowledge Hub · Intelligent Knowledge Workspace',description:'Search knowledge, chat with documents and manage AI across your organization'}
    :{title:'AI Knowledge Hub · พื้นที่ความรู้อัจฉริยะ',description:'ค้นหาความรู้ สนทนากับเอกสาร และจัดการ AI ภายในองค์กร'};
}
/** Hub lives in the root layout: layouts persist across client navigation, so the shell, query cache and topbar stay mounted. A page under [[...path]] would remount on every path change. */
export default async function RootLayout({children}:{children:React.ReactNode}) {
  const jar=await cookies(); let user=null; const lang=normalizeLang(jar.get(LANG_COOKIE)?.value);
  try {const r=await fetch(`${process.env.API_INTERNAL_URL||'http://127.0.0.1:8100'}/api/auth/me`,{headers:{Cookie:jar.toString()},cache:'no-store'}); if(r.ok)user=await r.json();} catch {}
  return <html lang={lang} suppressHydrationWarning><head><script dangerouslySetInnerHTML={{__html:THEME_INIT}}/></head><body><Hub initialUser={user} initialLang={lang}/>{children}</body></html>;
}
