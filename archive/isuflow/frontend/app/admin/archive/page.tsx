"use client";

import { useState } from "react";
import axios from "axios";

export default function ArchivePage() {
  const [gen, setGen] = useState("1");
  const [data, setData] = useState<any>(null);

  const load = async () => {
    const res = await axios.get(`/api/archive?generation=${gen}`);
    setData(res.data);
  };

  return (
    <div>
      <h1>아카이브 조회</h1>

      <select onChange={(e) => setGen(e.target.value)}>
        <option value="1">1기</option>
        <option value="2">2기</option>
      </select>

      <button onClick={load}>조회</button>

      {data && (
        <pre style={{ maxHeight: 300, overflow: 'scroll' }}>
          {JSON.stringify(data, null, 2)}
        </pre>
      )}
    </div>
  );
}
