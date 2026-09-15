"use client";

import { useEffect, useState } from "react";
import axios from "axios";

interface Submission {
  record_key: string;
  webp: string;
}

export default function SubmissionsPage(): JSX.Element {
  const [items, setItems] = useState<Submission[]>([]);

  useEffect(() => {
    (async () => {
      const res = await axios.get("/api/submissions");
      setItems(res.data.items);
    })();
  }, []);

  return (
    <div>
      <h1>제출 문서 목록</h1>

      <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 20 }}>
        {items.map((item) => (
          <div key={item.record_key} style={{ border: "1px solid #ccc", padding: 10 }}>
            <img src={item.webp} width={200} />
            <p>{item.record_key}</p>
            <a href={`/api/getPdf?record_key=${item.record_key}`} target="_blank">
              PDF 보기
            </a>
          </div>
        ))}
      </div>
    </div>
  );
}
