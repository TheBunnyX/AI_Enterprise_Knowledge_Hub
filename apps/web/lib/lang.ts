/** Server-safe language constants (no 'use client'), shared by app/layout.tsx and lib/i18n.tsx. */
export type Lang='th'|'en';
export const LANG_COOKIE='hub.lang';
export const LOCALE:Record<Lang,string>={th:'th-TH',en:'en-US'};
/** English is the default; a visitor who picked Thai keeps it through the `hub.lang` cookie. */
export const DEFAULT_LANG:Lang='en';
export const normalizeLang=(v?:string|null):Lang=>v==='th'?'th':DEFAULT_LANG;
