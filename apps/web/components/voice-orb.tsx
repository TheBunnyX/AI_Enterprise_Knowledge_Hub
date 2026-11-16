'use client';
import {useEffect,useRef,type MutableRefObject} from 'react';
import { tr } from '../lib/i18n';

type Phase='idle'|'listening'|'hearing'|'thinking'|'speaking';
const N=4200;
const PTS=(()=>{ // Fibonacci sphere: evenly spread points with their latitude/longitude
 const a=new Float32Array(N*5);const g=Math.PI*(3-Math.sqrt(5));
 for(let i=0;i<N;i++){const y=1-(i/(N-1))*2,r=Math.sqrt(1-y*y),th=g*i;
  a[i*5]=Math.cos(th)*r;a[i*5+1]=y;a[i*5+2]=Math.sin(th)*r;a[i*5+3]=Math.asin(y);a[i*5+4]=th}
 return a})();

/** A glowing sphere of particles whose surface ripples with the voice (the user's microphone or the AI's speech). */
export function VoiceOrb({phase,mic,out,size=572}:{phase:Phase;mic:number;out:MutableRefObject<number>;size?:number}){
 const ref=useRef<HTMLCanvasElement>(null);
 const live=useRef({phase,mic});live.current={phase,mic};
 useEffect(()=>{
  const cv=ref.current;if(!cv)return;const ctx=cv.getContext('2d');if(!ctx)return;
  const dpr=Math.min(2,window.devicePixelRatio||1);cv.width=size*dpr;cv.height=size*dpr;ctx.scale(dpr,dpr);
  let raf=0,t=0,e=0,spin=0,hue=232,last=performance.now();
  const frame=(now:number)=>{
   const dt=Math.min(0.05,(now-last)/1000);last=now;
   const {phase:ph,mic:m}=live.current;
   const target=ph==='speaking'?out.current:ph==='hearing'||ph==='listening'?m:0;
   e+=(Math.max(target,0)-e)*(target>e?0.35:0.12); // quick attack, slower release
   const idle=ph==='idle'?0.35:1;
   t+=dt*(1+e*2+(ph==='thinking'?1.6:0));spin+=dt*(0.18+e*0.5+(ph==='thinking'?0.7:0));
   const amp=(0.03+e*0.17)*idle;
   const R=size*0.252,cx=size/2,cy=size/2;
   const dark=document.documentElement.classList.contains('dark'); // additive glow needs a dark page; on light pages draw darker, opaque dots
   ctx.globalCompositeOperation='source-over';ctx.clearRect(0,0,size,size);
   // colour tells who is speaking: the user is warm pink/orange, the AI is cyan-blue, thinking is violet
   const userTalking=ph==='hearing'||(ph==='listening'&&m>0.06);
   const hueTarget=ph==='speaking'?198:userTalking?338:ph==='thinking'?262:232;
   hue+=(hueTarget-hue)*Math.min(1,dt*7);
   const hue0=hue;
   const glow=ctx.createRadialGradient(cx,cy,R*0.2,cx,cy,R*(1.55+e*0.5));
   glow.addColorStop(0,`hsla(${hue0},90%,55%,${(0.16+e*0.25)*(dark?1:0.45)})`);glow.addColorStop(1,'hsla(240,90%,50%,0)');
   ctx.fillStyle=glow;ctx.fillRect(0,0,size,size);
   ctx.globalCompositeOperation=dark?'lighter':'source-over';
   const cs=Math.cos(spin),sn=Math.sin(spin),tilt=0.35,ct=Math.cos(tilt),st=Math.sin(tilt);
   for(let i=0;i<N;i++){
    const x=PTS[i*5],y=PTS[i*5+1],z=PTS[i*5+2],lat=PTS[i*5+3],lon=PTS[i*5+4];
    const w=Math.sin(lon*3+t*1.7)*Math.cos(lat*2-t*1.1)*0.55+Math.sin(lat*5+t*2.3+lon)*0.3+Math.sin(lon*7-t*3.1)*Math.cos(lat*3)*0.25*(0.4+e*1.6);
    const d=1+amp*w;
    let X=x*d,Y=y*d,Z=z*d;
    const X1=X*cs+Z*sn,Z1=-X*sn+Z*cs;
    const Y2=Y*ct-Z1*st,Z2=Y*st+Z1*ct;
    const depth=(Z2+1)/2,rim=1-Math.abs(Z2);
    const sx=cx+X1*R*(1+Z2*0.08),sy=cy+Y2*R*(1+Z2*0.08);
    const a=(0.1+depth*0.5+rim*0.55)*(ph==='idle'?0.8:1);
    const hue=hue0+(Y2*0.5+0.5)*45-rim*20;
    ctx.fillStyle=`hsla(${hue},95%,${dark?52+rim*28+e*10:46-rim*8+e*6}%,${Math.min(1,a)})`;
    const s=0.6+depth*0.7+rim*0.6;
    ctx.fillRect(sx-s/2,sy-s/2,s,s);
   }
   raf=requestAnimationFrame(frame);
  };
  raf=requestAnimationFrame(frame);
  return()=>cancelAnimationFrame(raf);
 },[size,out]);
 return <canvas ref={ref} role="img" aria-label={tr('วงกลมเสียง AI ขยับตามเสียงพูด')} style={{width:size,height:size}} className="voice-orb-canvas"/>;
}
