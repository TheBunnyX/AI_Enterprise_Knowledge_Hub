'use client';
import { createContext, useCallback, useContext, useEffect, useRef, useState, type ReactNode } from 'react';
import { Modal, DialogFooter } from './dialog';
import { Button } from './button';
import { tr } from '../../lib/i18n';

export type ConfirmOptions={title:string;text?:ReactNode;confirmLabel?:string;cancelLabel?:string;danger?:boolean};

export function ConfirmDialog({title,text,confirmLabel=tr('ยืนยัน'),cancelLabel=tr('ยกเลิก'),danger,onConfirm,onCancel}:ConfirmOptions&{onConfirm:()=>void;onCancel:()=>void}){
 return <Modal title={title} onClose={onCancel}>{text&&<div className="text-sm leading-7 text-muted-foreground">{text}</div>}<DialogFooter className="mt-5"><Button variant="outline" onClick={onCancel}>{cancelLabel}</Button><Button variant={danger?'destructive':'default'} onClick={onConfirm}>{confirmLabel}</Button></DialogFooter></Modal>;
}

/** Native alert/confirm/prompt are banned: they block the page, can't be styled and break the app's UX. Use `useConfirm()` or `notify()`. */
export function blockNativeDialogs(){
 const orig={alert:window.alert,confirm:window.confirm,prompt:window.prompt};
 for(const k of ['alert','confirm','prompt'] as const){
  (window as unknown as Record<string,unknown>)[k]=()=>{throw new Error(`window.${k}() is disabled in this app. Use useConfirm() or notify() instead.`)};
 }
 return ()=>{Object.assign(window,orig)};
}

type Confirm=(o:ConfirmOptions)=>Promise<boolean>;
const Ctx=createContext<Confirm>(async()=>true);

/** Mount once near the app root; any component then calls `const confirm=useConfirm()` and `if(!await confirm({title:'...'}))return;`. */
export function ConfirmProvider({children}:{children:ReactNode}){
 useEffect(blockNativeDialogs,[]);
 const [opts,setOpts]=useState<ConfirmOptions|null>(null);const resolver=useRef<((v:boolean)=>void)|null>(null);
 const confirm=useCallback<Confirm>(o=>new Promise<boolean>(resolve=>{resolver.current?.(false);resolver.current=resolve;setOpts(o)}),[]);
 const settle=(v:boolean)=>{resolver.current?.(v);resolver.current=null;setOpts(null)};
 return <Ctx.Provider value={confirm}>{children}{opts&&<ConfirmDialog {...opts} onConfirm={()=>settle(true)} onCancel={()=>settle(false)}/>}</Ctx.Provider>;
}
export const useConfirm=()=>useContext(Ctx);
