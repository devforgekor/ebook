"use client";

import { useState } from "react";
import axios from "axios";

export default function ShadowIndexPage() {
  const [personId, setPersonId] = useState("");
  const [rows, setRows] = useState<any[]>([]);

  const search = async () => {
    const res = await axios.get(`/api/shadowindex?person_id=${personId}`);
    setRows(res.data.rows);
  };

  const rebuild = async () => {
    await axios.post("/api/rebuildShadowIndex");
    alert("✅ ShadowIndex 재빌드 완료!");
  };

  return (
    <div>
      <h1>ShadowIndex 관리</h1>

      <input placeholder="person_id" onChange={(e) => setPersonId(e.target.value)} />
      <button onClick={search}>조회</button>

      <button onClick={rebuild} style={{ marginLeft: 20 }}>전체 재빌드</button>

      <pre>{JSON.stringify(rows, null, 2)}</pre>
    </div>
  );
}
