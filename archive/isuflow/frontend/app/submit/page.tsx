"use client";

import { useState } from "react";
import axios from "axios";
import { SasResponse, SubmitPreviewResponse } from "@/utils/types";

export default function SubmitPage(): JSX.Element {
  const [file, setFile] = useState<File | null>(null);
  const [name, setName] = useState<string>("");
  const [yymmdd, setYymmdd] = useState<string>("");
  const [previewUrl, setPreviewUrl] = useState<string>("");

  const handleUpload = async () => {
    if (!file) return;

    // 1) getSas
    const sas = await axios.get<SasResponse>(`/api/getSas?file=${file.name}`);
    const uploadUrl = sas.data.url;

    await axios.put(uploadUrl, file, {
      headers: { "x-ms-blob-type": "BlockBlob" },
    });

    // 2) preview
    const prev = await axios.get<SubmitPreviewResponse>(
      `/api/preview?file=${file.name}&name=${name}&yymmdd=${yymmdd}`
    );

    setPreviewUrl(prev.data.url);
  };

  return (
    <div>
      <h1>PDF 제출</h1>

      <input
        type="text"
        placeholder="이름"
        onChange={(e) => setName(e.target.value)}
      />
      <input
        type="text"
        placeholder="생년월일(YYMMDD)"
        onChange={(e) => setYymmdd(e.target.value)}
      />

      <input type="file" onChange={(e) => setFile(e.target.files?.[0] || null)} />
      <button onClick={handleUpload}>제출</button>

      {previewUrl && <img src={previewUrl} alt="preview" width={300} />}
    </div>
  );
}
