"use client";

import { useState } from "react";
import axios from "axios";

interface DateRange {
  start: string;
  end: string;
}

interface SchedulePayload {
  seol?: DateRange;
  chuseok?: DateRange;
  summer?: DateRange;
  winter?: DateRange;
  short_breaks: DateRange[];
  holidays: string[];
}

export default function SchedulePage() {
  const [payload, setPayload] = useState<SchedulePayload>({
    short_breaks: [],
    holidays: []
  });

  const updateField = (key: string, field: keyof DateRange, value: string) => {
    setPayload({
      ...payload,
      [key]: {
        ...(payload as any)[key],
        [field]: value
      }
    });
  };

  const save = async () => {
    await axios.post("/api/updateSchedule", payload);
    alert("✅ OFF_SCHEDULE 업데이트 완료!");
  };

  return (
    <div>
      <h1>일정 관리</h1>

      <h3>설 연휴</h3>
      <input placeholder="YYYY-MM-DD" onChange={e => updateField("seol", "start", e.target.value)} />
      <input placeholder="YYYY-MM-DD" onChange={e => updateField("seol", "end", e.target.value)} />

      <h3>추석</h3>
      <input placeholder="YYYY-MM-DD" onChange={e => updateField("chuseok", "start", e.target.value)} />
      <input placeholder="YYYY-MM-DD" onChange={e => updateField("chuseok", "end", e.target.value)} />

      <button onClick={save}>저장</button>
    </div>
  );
}
