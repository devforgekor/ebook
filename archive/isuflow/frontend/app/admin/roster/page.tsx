"use client";

import { useState } from "react";
import axios from "axios";

export default function RosterPage(): JSX.Element {
  const [file, setFile] = useState<File | null>(null);
  const [status, setStatus] = useState<string>("");

  const handleUpload = async () => {
    if (!file) return alert("파일을 선택하세요.");

    const form = new FormData();
    form.append("file", file);

    setStatus("업로드 중...");

    try {
      await axios.post("/api/uploadRoster", form);
      setStatus("✅ 명단 업데이트 완료!");
    } catch (e: any) {
      setStatus("❌ 오류: " + e.message);
    }
  };

  return (
    <div>
      <h1>명단 업로드</h1>

      <input 
        type="file"
        onChange={(e) => setFile(e.target.files?.[0] || null)}
      />
      
      <button onClick={handleUpload}>업로드</button>
      <p>{status}</p>
    </div>
  );
}
