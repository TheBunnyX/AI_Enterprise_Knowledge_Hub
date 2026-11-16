/** Server-safe language constants (no 'use client'), shared by app/layout.tsx and lib/i18n.tsx. */
export type Lang='th'|'en';
export const LANG_COOKIE='hub.lang';
export const LOCALE:Record<Lang,string>={th:'th-TH',en:'en-US'};
export const normalizeLang=(v?:string|null):Lang=>v==='en'?'en':'th';
