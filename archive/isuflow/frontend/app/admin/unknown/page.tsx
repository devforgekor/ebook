"use client";

import { useEffect, useState } from "react";
import axios from "axios";

interface UnknownItem {
  record_key: string;
  person_id: string;
  submitted_at: string;
}

export default function UnknownPage(): JSX.Element {
  const [items, setItems] = useState<UnknownItem[]>([]);

  useEffect(() => {
    (async () => {
      const res = await axios.get("/api/unknown");
      setItems(res.data.items);
    })();
  }, []);

  const handleAdd = async (rec: string) => {
    await axios.post("/api/addToRosterFromUnknown", { record_key: rec });
    alert("✅ Roster에 추가되었습니다.");
  };

  return (
    <div>
      <h1>Unknown 처리</h1>

      <table border={1} cellPadding={5}>
        <thead>
          <tr>
            <th>record_key</th>
            <th>person_id</th>
            <th>submitted_at</th>
            <th>처리</th>
          </tr>
        </thead>

        <tbody>
          {items.map((u) => (
            <tr key={u.record_key}>
              <td>{u.record_key}</td>
              <td>{u.person_id}</td>
              <td>{u.submitted_at}</td>
              <td>
                <button onClick={() => handleAdd(u.record_key)}>Roster에 추가</button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
