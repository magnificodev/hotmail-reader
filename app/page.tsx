"use client";

import { useState } from "react";

export default function Page() {
  const [credString, setCredString] = useState("");
  const [fromFilter, setFromFilter] = useState("");
  const [pageSize, setPageSize] = useState(20);
  const [items, setItems] = useState<any[]>([]);
  const [nextPageToken, setNextPageToken] = useState<string | null>(null);
  const [otpFrom, setOtpFrom] = useState("");
  const [otpRegex, setOtpRegex] = useState("");
  const [otp, setOtp] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function fetchMessages(token?: string) {
    setLoading(true);
    try {
      const res = await fetch("http://localhost:8000/messages", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ credString, from_: fromFilter || undefined, page_size: pageSize, page_token: token }),
      });
      const data = await res.json();
      setItems(data.items || []);
      setNextPageToken(data.next_page_token || null);
    } finally {
      setLoading(false);
    }
  }

  async function extractOtp() {
    setLoading(true);
    setOtp(null);
    try {
      const res = await fetch("http://localhost:8000/otp", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ credString, from_: otpFrom || fromFilter || undefined, regex: otpRegex || undefined }),
      });
      const data = await res.json();
      setOtp(data.otp ?? null);
    } finally {
      setLoading(false);
    }
  }

  async function useDevCred() {
    const res = await fetch("http://localhost:8000/dev/cred", { method: "GET" });
    if (res.ok) {
      const data = await res.json();
      if (data.credString) setCredString(data.credString);
    }
  }

  return (
    <main style={{ padding: 24, maxWidth: 960, margin: "0 auto" }}>
      <h1 style={{ margin: 0, fontSize: 24 }}>Đọc Email Outlook/Hotmail</h1>
      <p style={{ color: "#555" }}>Nhập chuỗi 4 phần: email|password|refresh_token|client_id</p>

      <div style={{ display: "flex", gap: 8, alignItems: "center", marginTop: 12 }}>
        <input style={{ flex: 1, padding: 8 }} placeholder="email|password|refresh_token|client_id" value={credString} onChange={(e) => setCredString(e.target.value)} />
        <button onClick={useDevCred}>Dán dữ liệu mẫu (DEV)</button>
      </div>

      <div style={{ marginTop: 16, display: "flex", gap: 8, alignItems: "center" }}>
        <input style={{ flex: 1, padding: 8 }} placeholder="Lọc theo người gửi (from)" value={fromFilter} onChange={(e) => setFromFilter(e.target.value)} />
        <input style={{ width: 120, padding: 8 }} type="number" min={1} max={50} value={pageSize} onChange={(e) => setPageSize(parseInt(e.target.value || "20", 10))} />
        <button disabled={loading} onClick={() => fetchMessages()}>Kết nối & Lấy mail</button>
        <button disabled={loading || !nextPageToken} onClick={() => fetchMessages(nextPageToken || undefined)}>Trang kế tiếp</button>
      </div>

      <section style={{ marginTop: 24 }}>
        <h2 style={{ fontSize: 18, marginBottom: 8 }}>Danh sách email</h2>
        {items.length === 0 ? <div>Không có dữ liệu</div> : (
          <ul style={{ listStyle: "none", padding: 0, margin: 0 }}>
            {items.map((m) => (
              <li key={m.id} style={{ padding: 12, border: "1px solid #eee", borderRadius: 8, marginBottom: 8 }}>
                <div><strong>From:</strong> {m.from}</div>
                <div><strong>To:</strong> {Array.isArray(m.to) ? m.to.join(", ") : m.to}</div>
                <div><strong>Subject:</strong> {m.subject}</div>
                <div><strong>Date:</strong> {m.date}</div>
                <div style={{ color: "#555" }}>{m.snippet}</div>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section style={{ marginTop: 24 }}>
        <h2 style={{ fontSize: 18, marginBottom: 8 }}>Trích xuất OTP</h2>
        <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
          <input style={{ flex: 1, padding: 8 }} placeholder="Người gửi (from)" value={otpFrom} onChange={(e) => setOtpFrom(e.target.value)} />
          <input style={{ flex: 1, padding: 8 }} placeholder="Regex tùy chỉnh (tùy chọn)" value={otpRegex} onChange={(e) => setOtpRegex(e.target.value)} />
          <button disabled={loading} onClick={extractOtp}>Lấy OTP</button>
        </div>
        {otp && <div style={{ marginTop: 12, fontSize: 16 }}><strong>OTP:</strong> {otp}</div>}
      </section>
    </main>
  );
}

