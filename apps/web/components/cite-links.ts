const GROUP=/[ 	]*(?:\[\d{1,3}\](?:[ 	]*[,，、][ 	]*)?){1,8}/g;
export function linkCitations(text:string,count:number){
 const order:number[]=[];
 const out=text.replace(GROUP,group=>{
  const nums=[...new Set([...group.matchAll(/\[(\d{1,3})\]/g)].map(m=>Number(m[1])))].filter(n=>n>=1&&n<=count);
  if(!nums.length)return '';
  return nums.map(n=>{if(!order.includes(n))order.push(n);return ` [${order.indexOf(n)+1}](#cite-${n})`}).join('');
 });
 return {text:out,order};
}
