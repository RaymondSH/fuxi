"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import { apiGet, apiPost } from "@/lib/api";
interface Notice { id:string; title:string; body:string; link?:string; read_at?:string; created_at:string }
export default function NotificationsPage(){
  const [data,setData]=useState<{unread:number;items:Notice[]}>({unread:0,items:[]});
  const load=()=>apiGet<typeof data>("/notifications").then(setData);
  useEffect(()=>{load().catch(()=>{})},[]);
  async function read(){await apiPost("/notifications/read",{});await load()}
  return <div className="mx-auto max-w-4xl px-8 py-8"><div className="flex justify-between"><div><h1 className="font-serif text-2xl font-semibold">通知中心</h1><p className="text-sm text-muted">{data.unread} 条未读</p></div><button onClick={read} className="text-sm text-accent">全部已读</button></div>
  <div className="mt-6 space-y-2">{data.items.map(n=><div key={n.id} className={`rounded-xl border border-line p-4 ${n.read_at?"bg-white":"bg-panel"}`}><div className="text-sm font-medium">{n.title}</div><div className="text-xs text-muted">{n.body}</div>{n.link&&<Link href={n.link} className="text-xs text-accent">查看内容</Link>}</div>)}</div></div>
}

