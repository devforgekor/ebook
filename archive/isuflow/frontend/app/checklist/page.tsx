"use client";

import { useState } from "react";
import axios from "axios";
import { CheckListResponse } from "@/utils/types";

export default function CheckListPage(): JSX.Element {
  const [name, setName] = useState<string>("");
  const [yymmdd, setYymmdd] = useState<string>("");
  const [result, setResult] = useState<CheckListResponse | null>(null);

  const handleSearch = async () => {
    const res = await axios.post<CheckListResponse>("/api/checkList", { name, yymmdd });
    setResult(res.data);
  };

  return (
    <div>
      <h1>이수 기록 조회</h1>

      <input placeholder="이름" onChange={(e) => setName(e.target.value)} />
      <input placeholder="생년월일" onChange={(e) => setYymmdd(e.target.value)} />
      <button onClick={handleSearch}>조회</button>

      {result && (
        <div>
          <h2>최신본</h2>
          <img src={result.latest_webp_url} alt="latest" width={300} />

          <h3>이력</h3>
          {result.history.map((h, i) => (
            <div key={i}>
              {h.submitted_at} — {h.title} — {h.hours}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
