import React from "react";
import AdminNav from "@/components/AdminNav";

export default function AdminLayout({
  children,
}: {
  children: React.ReactNode;
}): JSX.Element {
  return (
    <div style={{ display: "flex" }}>
      <AdminNav />
      <div style={{ padding: 20, flexGrow: 1 }}>{children}</div>
    </div>
  );
}
