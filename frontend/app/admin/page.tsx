"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";

// /admin 落到入库页
export default function AdminIndex() {
  const router = useRouter();
  useEffect(() => {
    router.replace("/admin/ingest");
  }, [router]);
  return null;
}
