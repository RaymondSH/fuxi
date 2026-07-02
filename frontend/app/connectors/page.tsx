"use client";

import { useEffect, useState } from "react";
import { canAct, useSpaces } from "@/components/SpacesProvider";
import { apiGet, apiPost } from "@/lib/api";

interface Connector { id: string; provider: string; name: string; status: string; error_msg?: string; last_synced_at?: string }
const PROVIDERS = ["confluence", "feishu", "google_drive", "sharepoint"];

export default function ConnectorsPage() {
  const { spaces, activeSpace } = useSpaces();
  const [spaceId, setSpaceId] = useState("");
  const [items, setItems] = useState<Connector[]>([]);
  const [provider, setProvider] = useState("confluence");
  const [name, setName] = useState("");
  const [config, setConfig] = useState("{}");
  const [credentials, setCredentials] = useState("{}");
  const selected = spaces.find((s) => s.id === spaceId);
  useEffect(() => { if (!spaceId && spaces.length) setSpaceId(activeSpace?.id || spaces[0].id); }, [spaces, activeSpace, spaceId]);
  const load = (id = spaceId) => id
    ? apiGet<{items: Connector[]}>(`/connectors?space_id=${id}`).then((x) => setItems(x.items))
    : Promise.resolve();
  useEffect(() => { load().catch(() => {}); }, [spaceId]); // eslint-disable-line react-hooks/exhaustive-deps
  async function create() {
    await apiPost("/connectors", { space_id: spaceId, provider, name,
      config: JSON.parse(config), credentials: JSON.parse(credentials) });
    setName(""); setCredentials("{}"); await load();
  }
  return <div className="mx-auto max-w-5xl px-8 py-8">
    <div className="mb-6 flex items-end justify-between"><div><h1 className="font-serif text-2xl font-semibold">企业连接器</h1><p className="text-sm text-muted">只读增量同步远端知识。</p></div>
      <select value={spaceId} onChange={(e) => setSpaceId(e.target.value)} className="rounded border border-line bg-white px-3 py-2 text-sm">{spaces.map(s=><option key={s.id} value={s.id}>{s.name}</option>)}</select></div>
    {canAct(selected?.my_role, "space_admin") && <div className="mb-6 grid gap-2 rounded-xl border border-line bg-panel p-4 md:grid-cols-2">
      <select value={provider} onChange={e=>setProvider(e.target.value)} className="rounded border border-line p-2">{PROVIDERS.map(p=><option key={p}>{p}</option>)}</select>
      <input placeholder="连接器名称" value={name} onChange={e=>setName(e.target.value)} className="rounded border border-line p-2"/>
      <textarea value={config} onChange={e=>setConfig(e.target.value)} className="rounded border border-line p-2 font-mono text-xs" placeholder="非敏感 config JSON"/>
      <textarea value={credentials} onChange={e=>setCredentials(e.target.value)} className="rounded border border-line p-2 font-mono text-xs" placeholder="凭据 JSON（提交后加密）"/>
      <button onClick={create} className="rounded bg-brand px-4 py-2 text-sm text-cream">创建连接器</button>
    </div>}
    <div className="space-y-3">{items.map(x=><div key={x.id} className="flex justify-between rounded-xl border border-line bg-panel p-4"><div><b>{x.name}</b><div className="text-xs text-muted">{x.provider} · {x.status}{x.error_msg && ` · ${x.error_msg}`}</div></div>{canAct(selected?.my_role,"space_admin")&&<button onClick={()=>apiPost(`/connectors/${x.id}/sync`)} className="text-xs text-accent">立即同步</button>}</div>)}</div>
  </div>;
}
