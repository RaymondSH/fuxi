"use client";
import { useEffect,useState } from "react";
import { canAct,useSpaces } from "@/components/SpacesProvider";
import { apiGet,apiPost } from "@/lib/api";
interface Proposal{id:string;action:string;rationale:string;payload:Record<string,unknown>;status:string}
export default function AgentPage(){
 const {spaces,activeSpace}=useSpaces();const [spaceId,setSpaceId]=useState("");const [items,setItems]=useState<Proposal[]>([]);
 const selected=spaces.find(s=>s.id===spaceId);
 useEffect(()=>{if(!spaceId&&spaces.length)setSpaceId(activeSpace?.id||spaces[0].id)},[spaces,activeSpace,spaceId]);
 const load=(id=spaceId)=>id?apiGet<{items:Proposal[]}>(`/agent/proposals?space_id=${id}&status=pending`).then(x=>setItems(x.items)):Promise.resolve();
 useEffect(()=>{load().catch(()=>{})},[spaceId]); // eslint-disable-line react-hooks/exhaustive-deps
 async function act(id:string,kind:"approve"|"reject"){await apiPost(`/agent/proposals/${id}/${kind}`);setItems(p=>p.filter(x=>x.id!==id))}
 return <div className="mx-auto max-w-5xl px-8 py-8"><div className="flex justify-between"><div><h1 className="font-serif text-2xl font-semibold">治理 Agent</h1><p className="text-sm text-muted">模型只提案，人工审批后执行。</p></div><div className="flex gap-2"><select value={spaceId} onChange={e=>setSpaceId(e.target.value)} className="rounded border border-line bg-white px-3">{spaces.map(s=><option key={s.id} value={s.id}>{s.name}</option>)}</select>{canAct(selected?.my_role,"space_admin")&&<button onClick={()=>apiPost("/agent/runs",{space_id:spaceId})} className="rounded bg-brand px-3 py-2 text-sm text-cream">生成提案</button>}</div></div>
 <div className="mt-6 space-y-3">{items.map(x=><div key={x.id} className="rounded-xl border border-line bg-panel p-4"><div className="font-mono text-xs text-accent">{x.action}</div><p className="mt-1 text-sm">{x.rationale}</p>{canAct(selected?.my_role,"space_admin")&&<div className="mt-3 flex gap-3 text-xs"><button onClick={()=>act(x.id,"approve")} className="text-accent">批准执行</button><button onClick={()=>act(x.id,"reject")} className="text-muted">拒绝</button></div>}</div>)}</div></div>
}
