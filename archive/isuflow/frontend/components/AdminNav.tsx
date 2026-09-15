"use client";

import Link from "next/link";
import React from "react";

export default function AdminNav(): JSX.Element {
  return (
    <nav style={{ 
      width: 220, 
      background: "#f4f4f4", 
      padding: 20, 
      height: "100vh",
      borderRight: "1px solid #ddd"
    }}>
      <h3 style={{ marginBottom: 20 }}>관리자 메뉴</h3>
      <ul style={{ display: "flex", flexDirection: "column", gap: 10 }}>
        <li><Link href="/admin/roster">명단 관리</Link></li>
        <li><Link href="/admin/schedule">일정 관리</Link></li>
        <li><Link href="/admin/submissions">제출 문서 목록</Link></li>
        <li><Link href="/admin/unknown">Unknown 처리</Link></li>
        <li><Link href="/admin/shadowindex">ShadowIndex 관리</Link></li>
        <li><Link href="/admin/archive">아카이브 조회</Link></li>
      </ul>
    </nav>
  );
}
