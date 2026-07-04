"use client";
import { useEffect,useState } from "react";
import { canAct,useSpaces } from "@/components/SpacesProvider";
import { ApiError,apiGet,apiPost } from "@/lib/api";
interface Proposal{id:string;action:string;rationale:string;payload:Record<string,unknown>;status:string}
export default function AgentPage(){
 const {spaces,activeSpace,loading:spacesLoading,error:spacesError}=useSpaces();const [spaceId,setSpaceId]=useState("");const [items,setItems]=useState<Proposal[]>([]);
 const [loading,setLoading]=useState(false);const [error,setError]=useState("");
 const selected=spaces.find(s=>s.id===spaceId);
 useEffect(()=>{if(!spaceId&&spaces.length)setSpaceId(activeSpace?.id||spaces[0].id)},[spaces,activeSpace,spaceId]);
 async function load(id=spaceId){if(!id)return;setLoading(true);setError("");setItems([]);try{const data=await apiGet<{items:Proposal[]}>(`/agent/proposals?space_id=${id}&status=pending`);setItems(data.items)}catch(err){setError(err instanceof ApiError?err.message:"治理提案加载失败")}finally{setLoading(false)}}
 useEffect(()=>{void load()},[spaceId]); // eslint-disable-line react-hooks/exhaustive-deps
 async function run(){setError("");try{await apiPost("/agent/runs",{space_id:spaceId})}catch(err){setError(err instanceof ApiError?err.message:"治理提案任务创建失败")}}
 async function act(id:string,kind:"approve"|"reject"){setError("");try{await apiPost(`/agent/proposals/${id}/${kind}`);setItems(p=>p.filter(x=>x.id!==id))}catch(err){setError(err instanceof ApiError?err.message:"治理提案更新失败")}}
 return <div className="mx-auto max-w-5xl px-8 py-8"><div className="flex justify-between"><div><h1 className="font-serif text-2xl font-semibold">治理 Agent</h1><p className="text-sm text-muted">模型只提案，人工审批后执行。</p></div><div className="flex gap-2"><select value={spaceId} onChange={e=>setSpaceId(e.target.value)} className="rounded border border-line bg-white px-3">{spaces.map(s=><option key={s.id} value={s.id}>{s.name}</option>)}</select>{canAct(selected?.my_role,"space_admin")&&<button onClick={()=>void run()} className="rounded bg-brand px-3 py-2 text-sm text-cream">生成提案</button>}</div></div>
 {(spacesError||error)&&<p className="mt-4 text-sm text-[#B23C3C]">{spacesError||error}</p>}
 <div className="mt-6 space-y-3">{items.map(x=><div key={x.id} className="rounded-xl border border-line bg-panel p-4"><div className="font-mono text-xs text-accent">{x.action}</div><p className="mt-1 text-sm">{x.rationale}</p>{canAct(selected?.my_role,"space_admin")&&<div className="mt-3 flex gap-3 text-xs"><button onClick={()=>void act(x.id,"approve")} className="text-accent">批准执行</button><button onClick={()=>void act(x.id,"reject")} className="text-muted">拒绝</button></div>}</div>)}
 {(spacesLoading||loading)&&<div className="rounded-xl border border-dashed border-line p-10 text-center text-sm text-muted2">加载中…</div>}
 {!spacesLoading&&!loading&&!spacesError&&!error&&!items.length&&<div className="rounded-xl border border-dashed border-line p-10 text-center text-sm text-muted2">当前没有待审批的治理提案</div>}
 </div></div>
}
