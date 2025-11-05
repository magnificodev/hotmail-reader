"use client";

import { useEffect, useState, useCallback, memo, useMemo } from "react";
import { createPortal } from "react-dom";
import { Button } from "@/components/ui/button";
import { Mail, ClipboardPaste, Loader2, FileText, Code } from "lucide-react";
import { toast } from "sonner";
import { API_ENDPOINTS, apiRequest } from "./lib/api";
import { ITEMS_PER_PAGE, MAX_PAGE_SIZE, OTP_BUFFER_MULTIPLIER, POKEMON_FILTER_EMAIL, MESSAGES } from "./lib/constants";
import type { EmailMessage, PageResult, MessageBodyResponse, DevCredResponse } from "./lib/types";

export default function Page() {
  const [credString, setCredString] = useState("");
  // simplified state
  const [loading, setLoading] = useState(false);
  const [items, setItems] = useState<EmailMessage[]>([]);
  const [openId, setOpenId] = useState<string | null>(null);
  const [htmlMap, setHtmlMap] = useState<Record<string, string>>({}); // Cache HTML đã tải
  const [loadingHtml, setLoadingHtml] = useState<Record<string, boolean>>({});
  const [viewMode, setViewMode] = useState<Record<string, "text" | "html">>({}); // text hoặc html
  const [currentPage, setCurrentPage] = useState(1);
  const itemsPerPage = ITEMS_PER_PAGE;
  const [pageToken, setPageToken] = useState<string | null>(null); // Token cho trang tiếp theo
  const [hasMore, setHasMore] = useState(true); // Còn trang nào không
  const [loadingMore, setLoadingMore] = useState(false); // Đang load thêm
  const [reloadingFilter, setReloadingFilter] = useState(false);
  const [totalEmails, setTotalEmails] = useState<number | null>(null);
  const [filterFromPokemon, setFilterFromPokemon] = useState(true);
  const [appliedFilter, setAppliedFilter] = useState(false);
  const [filterWithOtp, setFilterWithOtp] = useState(true);
  function isValidOtp(otp: string, context: string): boolean {
    if (!otp || !/^\d+$/.test(otp)) return false;
    
    // Must be exactly 6 digits
    if (otp.length !== 6) return false;
    
    // Exclude if it's in a URL
    if (isInUrl(context, otp)) return false;
    
    // Exclude numbers with too many zeros (like 000000)
    const zeroCount = (otp.match(/0/g) || []).length;
    if (zeroCount >= 5) return false;
    
    // Exclude all same digits (111111, 222222, etc.)
    if (new Set(otp).size === 1) return false;
    
    // Exclude simple sequential (123456, 654321, etc.)
    const isSequential = 
      otp.split('').every((d, i) => i === 0 || parseInt(d) === parseInt(otp[i-1]) + 1) ||
      otp.split('').every((d, i) => i === 0 || parseInt(d) === parseInt(otp[i-1]) - 1);
    if (isSequential) return false;
    
    return true;
  }

  function isInUrl(text: string, otp: string): boolean {
    // Find all URLs in text - more comprehensive pattern
    const urlPattern = /https?:\/\/[^\s<>"')]+|www\.[^\s<>"')]+|go\.\w+[^\s<>"')]*|[\w.]+\.(com|org|net|io|co|vn|jp|uk)[^\s<>"')]*/gi;
    const urls = text.match(urlPattern) || [];
    
    for (const url of urls) {
      const otpPos = url.indexOf(otp);
      if (otpPos === -1) continue;
      
      // Check if it's in query parameters (like ?LinkID=281822 or &id=123456)
      if (new RegExp(`[?&][^=&]*=${otp}(?:[^0-9&]|$)`).test(url)) {
        return true;
      }
      // Check if it's in path segments (like /123456/ or /path/123456)
      if (new RegExp(`/${otp}(?:[/?#]|$)`).test(url)) {
        return true;
      }
      // Check if it's after domain (like example.com/123456)
      if (new RegExp(`\\.(com|org|net|io|co|vn|jp|uk)/${otp}`, 'i').test(url)) {
        return true;
      }
      // If URL is substantial and contains the OTP, likely part of URL
      if (url.length > 20 && url.includes(otp)) {
        // Check context around the OTP in URL
        const contextAround = url.substring(Math.max(0, otpPos - 1), Math.min(url.length, otpPos + otp.length + 1));
        // If surrounded by URL characters (digits, slashes, query params), likely part of URL
        if (/[0-9\/\?=&]/.test(contextAround)) {
          return true;
        }
      }
    }
    
    return false;
  }

  function extractOtp(text: string): string | null {
    if (!text) return null;
    
    // Simple pattern: only 6-digit numbers
    // 1. OTP with context keywords (most reliable)
    const contextPattern = /(?:code|otp|pin|verification|mã|mật|khẩu|mã xác thực)[\s:]*[:\-]?\s*(\d{6})/i;
    let m = text.match(contextPattern);
    if (m && m[1]) {
      const otp = m[1].replace(/[\s\-\.]/g, '');
      if (otp.length === 6 && isValidOtp(otp, text)) return otp;
    }
    
    // 2. Standalone 6-digit numbers
    m = text.match(/(?<![0-9])(\d{6})(?![0-9])/);
    if (m && m[1] && isValidOtp(m[1], text)) return m[1];
    
    return null;
  }

  function ClampedPreview({ text, onOpen }: { text: string; onOpen: () => void }) {
    if (!text) return null;
    return (
      <div
        className="text-muted-foreground break-words cursor-pointer hover:text-foreground transition-colors"
        onClick={(e) => {
          e.stopPropagation();
          onOpen();
        }}
      >
        <div
          className="line-clamp-2"
          style={{ display: "-webkit-box", WebkitLineClamp: 2, WebkitBoxOrient: "vertical", overflow: "hidden" }}
        >
          {text}
        </div>
      </div>
    );
  }


  function onlyEmail(raw: string): string {
    if (!raw) return "";
    // pick the first angle-bracket email if present
    const angle = raw.match(/<([^>]+)>/);
    if (angle?.[1]) return angle[1];
    // else find first email-like token
    const email = raw.match(/[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}/i);
    return email ? email[0] : raw;
  }

  async function copyToClipboard(text: string) {
    try {
      await navigator.clipboard.writeText(text);
      toast.success(MESSAGES.SUCCESS_COPY);
    } catch (e) {
      // Fallback
      try {
        const ta = document.createElement("textarea");
        ta.value = text;
        document.body.appendChild(ta);
        ta.select();
        document.execCommand("copy");
        ta.remove();
        toast.success(MESSAGES.SUCCESS_COPY);
      } catch {
        toast.error(MESSAGES.ERROR_COPY);
      }
    }
  }

  function pad2(n: number): string {
    return n < 10 ? `0${n}` : String(n);
    }

  function formatTime(raw: string): string {
    if (!raw) return "";
    const d = new Date(raw);
    if (isNaN(d.getTime())) return raw;
    const hh = pad2(d.getHours());
    const mm = pad2(d.getMinutes());
    const dd = pad2(d.getDate());
    const MM = pad2(d.getMonth() + 1);
    const yyyy = d.getFullYear();
    return `${hh}:${mm} - ${dd}/${MM}/${yyyy}`;
  }

  function showErrorToast(context: string, status: number, payload: string) {
    let message = MESSAGES.ERROR_UNKNOWN;
    try {
      const js = JSON.parse(payload);
      if (js?.detail) message = String(js.detail);
    } catch {
      if (payload) message = payload;
    }
    if (status === 0) message = MESSAGES.ERROR_SERVER;
    toast.error(`${context}: ${message}`);
  }
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setMounted(true);
  }, []);

  const filteredItems = useMemo(() => {
    if (!filterWithOtp) return items;
    return items.filter((item) => {
      const otp = extractOtp(item.subject + "\n" + item.content);
      return otp !== null;
    });
  }, [items, filterWithOtp]);

  const startIndex = (currentPage - 1) * itemsPerPage;
  const endIndex = startIndex + itemsPerPage;
  const displayedItems = filteredItems.slice(startIndex, endIndex);
  const canGoNext = hasMore || filteredItems.length > endIndex;

  async function fetchMessages() {
    setLoading(true);
    try {
      const data = await apiRequest<PageResult>(API_ENDPOINTS.MESSAGES, {
        method: "POST",
        body: JSON.stringify({ 
          credString, 
          page_size: itemsPerPage, 
          include_body: true,
          from_: filterFromPokemon ? POKEMON_FILTER_EMAIL : undefined,
        }),
      });
      
      const items: EmailMessage[] = (data.items || []).map((x) => ({
        id: String(x.id ?? ""),
        from_: String(x.from_ ?? ""),
        to: Array.isArray(x.to) ? x.to : [],
        date: String(x.date ?? ""),
        subject: String(x.subject ?? ""),
        content: String(x.content ?? ""),
      }));
      
      const count = items.length;
      toast.success(`Đã tải ${count} email`);
      if (process.env.NODE_ENV === "development") console.log("/messages response", { count, items: items.slice(0, 3), total: data.total });
      
      // Reset data khi fetch mới
      setItems(items);
      setPageToken(data.next_page_token || null);
      setHasMore(!!data.next_page_token);
      setCurrentPage(1); // Reset to first page when loading new data
      setAppliedFilter(filterFromPokemon);
      setTotalEmails(data.total ?? null);
    } catch (error: any) {
      showErrorToast("Lỗi khi đọc mail", error.status || 0, error.text || String(error));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    if (appliedFilter !== filterFromPokemon || !hasMore || !pageToken) {
      return;
    }
    
    const startIndex = (currentPage - 1) * itemsPerPage;
    const endIndex = startIndex + itemsPerPage;
    const itemsForCurrentPage = filterWithOtp 
      ? filteredItems.slice(startIndex, endIndex).length
      : items.slice(startIndex, endIndex).length;
    const neededItems = currentPage * itemsPerPage;
    const availableCount = filterWithOtp ? filteredItems.length : items.length;
    
    const needMoreData = (
      availableCount < neededItems || 
      (filterWithOtp && itemsForCurrentPage < itemsPerPage)
    ) && hasMore && !loadingMore && !reloadingFilter && pageToken;
    
    if (needMoreData) {
      setLoadingMore(true);
      
      let estimatedPageSize: number;
      if (filterWithOtp) {
        estimatedPageSize = Math.min(itemsPerPage * OTP_BUFFER_MULTIPLIER, MAX_PAGE_SIZE);
      } else if (totalEmails !== null) {
        const remainingEmails = totalEmails - items.length;
        const neededForCurrentPage = neededItems - availableCount;
        estimatedPageSize = Math.min(Math.max(neededForCurrentPage, 1), remainingEmails, itemsPerPage);
      } else {
        estimatedPageSize = itemsPerPage;
      }
      
      const loadMore = async (currentToken: string | null): Promise<void> => {
        if (!currentToken) {
          setLoadingMore(false);
          return;
        }
        
        try {
          const data = await apiRequest<PageResult>(API_ENDPOINTS.MESSAGES, {
            method: "POST",
            body: JSON.stringify({ 
              credString, 
              page_size: estimatedPageSize, 
              include_body: true,
              page_token: currentToken,
              from_: filterFromPokemon ? POKEMON_FILTER_EMAIL : undefined,
            }),
          });
          
          const newItems: EmailMessage[] = (data.items || []).map((x) => ({
            id: String(x.id ?? ""),
            from_: String(x.from_ ?? ""),
            to: Array.isArray(x.to) ? x.to : [],
            date: String(x.date ?? ""),
            subject: String(x.subject ?? ""),
            content: String(x.content ?? ""),
          }));
          
          const nextToken = data.next_page_token || null;
          
          if (!nextToken) {
            setLoadingMore(false);
            setPageToken(null);
            setHasMore(false);
            setItems((prev) => [...prev, ...newItems]);
            return;
          }
          
          setPageToken(nextToken);
          setHasMore(true);
          setItems((prev) => [...prev, ...newItems]);
          setLoadingMore(false);
        } catch (error: any) {
          showErrorToast("Lỗi khi tải thêm email", error.status || 0, error.text || String(error));
          setLoadingMore(false);
        }
      };
      
      loadMore(pageToken);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [currentPage, filteredItems.length, items.length, hasMore, loadingMore, reloadingFilter, pageToken, appliedFilter, filterFromPokemon, filterWithOtp]);

  async function useDevCred() {
    // Only work in development
    if (process.env.NODE_ENV !== "development") {
      return;
    }
    try {
      const data = await apiRequest<DevCredResponse>(API_ENDPOINTS.DEV_CRED, { method: "GET" });
      if (data.credString) setCredString(data.credString);
    } catch (error: any) {
      // Silently fail for dev endpoint
      console.warn("Failed to fetch dev cred:", error);
    }
  }

  const fetchHtml = useCallback(async (id: string, currentHtmlMap: Record<string, string>, currentLoadingHtml: Record<string, boolean>) => {
    if (currentHtmlMap[id]) {
      setViewMode((prev) => ({ ...prev, [id]: "html" }));
      return;
    }
    
    if (currentLoadingHtml[id]) {
      return;
    }
    
    setLoadingHtml((prev) => ({ ...prev, [id]: true }));
    
    try {
      const data = await apiRequest<MessageBodyResponse>(API_ENDPOINTS.MESSAGE, {
        method: "POST",
        body: JSON.stringify({ credString, id }),
      });
      
      setHtmlMap((prev) => {
        if (prev[id]) return prev;
        return { ...prev, [id]: data.html || "" };
      });
      setViewMode((prev) => ({ ...prev, [id]: "html" }));
    } catch (error: any) {
      showErrorToast("Lỗi khi tải HTML", error.status || 0, error.text || String(error));
    } finally {
      setLoadingHtml((prev) => ({ ...prev, [id]: false }));
    }
  }, [credString]);

  const toggleViewMode = useCallback((id: string) => {
    const current = viewMode[id] || "text";
    const next = current === "text" ? "html" : "text";
    setViewMode((prev) => ({ ...prev, [id]: next }));
    
    if (next === "html" && !htmlMap[id] && !loadingHtml[id]) {
      fetchHtml(id, htmlMap, loadingHtml);
    }
  }, [viewMode, htmlMap, loadingHtml, fetchHtml]);

  const openPopup = useCallback((id: string) => setOpenId(id), []);
  const closePopup = useCallback(() => setOpenId(null), []);

  useEffect(() => {
    const root = document.documentElement;
    if (openId) {
      root.style.overflow = 'hidden';
      try { (root.style as any).scrollbarGutter = ''; } catch {}
    } else {
      root.style.overflow = '';
      try { (root.style as any).scrollbarGutter = 'stable'; } catch {}
    }
    return () => { 
      root.style.overflow = '';
      try { (root.style as any).scrollbarGutter = ''; } catch {}
    };
  }, [openId]);

  useEffect(() => {
    if (!openId) return;
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        closePopup();
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [openId, closePopup]);

  useEffect(() => {
    if (items.length > 0 && credString.trim() && appliedFilter !== filterFromPokemon && !loading && !loadingMore && !reloadingFilter) {
        setItems([]);
        setPageToken(null);
        setHasMore(true);
        setCurrentPage(1);
        setTotalEmails(null);
        setReloadingFilter(true);
      
      apiRequest<PageResult>(API_ENDPOINTS.MESSAGES, {
        method: "POST",
        body: JSON.stringify({ 
          credString, 
          page_size: itemsPerPage, 
          include_body: true,
          from_: filterFromPokemon ? POKEMON_FILTER_EMAIL : undefined,
        }),
      }).then((data) => {
        const newItems: EmailMessage[] = (data.items || []).map((x) => ({
          id: String(x.id ?? ""),
          from_: String(x.from_ ?? ""),
          to: Array.isArray(x.to) ? x.to : [],
          date: String(x.date ?? ""),
          subject: String(x.subject ?? ""),
          content: String(x.content ?? ""),
        }));
        const count = newItems.length;
        toast.success(`Đã tải ${count} email`);
        setItems(newItems);
        setPageToken(data.next_page_token || null);
        setHasMore(!!data.next_page_token);
        setAppliedFilter(filterFromPokemon);
        setTotalEmails(data.total ?? null);
        setReloadingFilter(false);
      }).catch((error: any) => {
        showErrorToast("Lỗi khi đọc mail", error.status || 0, error.text || String(error));
        setReloadingFilter(false);
      });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [filterFromPokemon]);


  const Row = memo(function Row({ m, idx, startIndex, onOpenPopup }: { m: EmailMessage; idx: number; startIndex: number; onOpenPopup: (id: string) => void }) {
    const otp = extractOtp(m.subject + "\n" + m.content) || "";
    return (
      <tr className="border-b hover:bg-muted/40">
        <td className="p-4 align-middle text-muted-foreground">{startIndex + idx + 1}</td>
        <td className="p-4 align-middle break-words">{onlyEmail(m.from_)}</td>
        <td className="p-4 whitespace-nowrap align-middle text-muted-foreground">{formatTime(m.date)}</td>
        <td className="p-4 break-words align-middle">
          <div 
            className="font-semibold cursor-pointer hover:text-primary transition-colors"
            onClick={(e) => {
              e.stopPropagation();
              onOpenPopup(m.id);
            }}
          >
            {m.subject}
          </div>
          <ClampedPreview text={m.content} onOpen={() => onOpenPopup(m.id)} />
        </td>
        <td className="p-4 align-middle">
          {otp ? (
            <div className="flex flex-col items-start gap-1">
              <div className="inline-flex h-8 min-w-[80px] items-center justify-center rounded-md px-3 font-mono text-sm">
                {otp}
              </div>
              <Button
                variant="secondary"
                size="sm"
                className="h-8 min-w-[80px] justify-center transition-colors hover:bg-secondary/80"
                onClick={(e) => {
                  e.stopPropagation();
                  copyToClipboard(otp);
                }}
              >
                Copy
              </Button>
            </div>
          ) : null}
        </td>
      </tr>
    );
  });

  function PopupContent({
    openId,
    items,
    viewMode,
    htmlMap,
    loadingHtml,
    onClose,
    onToggleView,
  }: {
    openId: string | null;
    items: EmailMessage[];
    viewMode: Record<string, "text" | "html">;
    htmlMap: Record<string, string>;
    loadingHtml: Record<string, boolean>;
    onClose: () => void;
    onToggleView: (id: string) => void;
  }) {
    const item = openId ? items.find((x) => x.id === openId) : null;
    const mode = item ? (viewMode[item.id] || "text") : "text";
    const html = item ? (htmlMap[item.id] || "") : "";
    const loading = item ? !!loadingHtml[item.id] : false;
    const isHtmlMode = item && mode === "html" && html;

    if (!mounted) return null;

    return createPortal(
      <div className={`fixed inset-0 z-50 ${openId ? '' : 'pointer-events-none'}`}>
        <div
          className={`absolute inset-0 bg-black/50 transition-opacity duration-150 ${openId ? "opacity-100" : "opacity-0 pointer-events-none"}`}
          onClick={onClose}
        />
        <div
          className={`absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 w-full max-w-2xl max-h-[90vh] bg-background rounded-lg shadow-xl flex flex-col transition-all duration-150 ${openId ? "opacity-100 scale-100" : "opacity-0 scale-95 pointer-events-none"}`}
        >
          <div className="p-4 border-b flex items-center justify-between">
            <div className="text-lg font-semibold truncate">{item?.subject || "Chi tiết"}</div>
            <Button variant="secondary" onClick={onClose}>Đóng</Button>
          </div>
          <div className="p-4 space-y-2 overflow-y-auto flex-1 min-h-0">
            {item && (
              <>
                <div className="flex items-center justify-between mb-2">
                  <div className="text-sm text-muted-foreground space-y-1">
                    <div>From: {onlyEmail(item.from_)}</div>
                    {item.to && item.to.length > 0 && (
                      <div>To: {item.to.map((email, idx) => onlyEmail(email)).join(", ")}</div>
                    )}
                    <div>Time: {formatTime(item.date)}</div>
                  </div>
                  <Button variant="outline" size="sm" onClick={() => onToggleView(item.id)} disabled={loading}>
                    {loading ? (
                      <><Loader2 className="mr-2 h-4 w-4 animate-spin" /> Đang tải...</>
                    ) : mode === "text" ? (
                      <><Code className="mr-2 h-4 w-4" /> Xem HTML</>
                    ) : (
                      <><FileText className="mr-2 h-4 w-4" /> Xem Text</>
                    )}
                  </Button>
                </div>
                {isHtmlMode ? (
                  <div className="prose prose-sm max-w-none text-sm leading-6" dangerouslySetInnerHTML={{ __html: html }} />
                ) : (
                  <div className="whitespace-pre-wrap break-words text-sm leading-6">{item.content || "(Không có nội dung)"}</div>
                )}
              </>
            )}
          </div>
        </div>
      </div>,
      document.body
    );
  }

  return mounted ? (
    <main suppressHydrationWarning className="mx-auto max-w-7xl p-6 space-y-4">
      <h1 className="text-2xl font-semibold">Đọc Email Outlook/Hotmail</h1>

      <div className="space-y-2">
        <textarea
          className="w-full h-40 rounded-md border border-border bg-transparent px-3 py-2 text-sm shadow-sm placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          placeholder="email|password|refresh_token|client_id"
          value={credString}
          onChange={(e) => setCredString(e.target.value)}
        />
        <div className="flex items-center justify-between gap-2">
          <div className="flex items-center gap-4">
            <label className="flex items-center gap-2 cursor-pointer">
              <input
                type="checkbox"
                checked={filterFromPokemon}
                onChange={(e) => setFilterFromPokemon(e.target.checked)}
                className="w-4 h-4 rounded border-2 cursor-pointer"
                style={{ 
                  accentColor: "hsl(var(--primary))",
                }}
              />
              <span className="text-sm">
                Chỉ hiển thị email từ <span className="text-primary font-medium">{POKEMON_FILTER_EMAIL}</span>
              </span>
            </label>
            <label className="flex items-center gap-2 cursor-pointer">
              <input
                type="checkbox"
                checked={filterWithOtp}
                onChange={(e) => {
                  setFilterWithOtp(e.target.checked);
                  setCurrentPage(1); // Reset về trang 1 khi filter thay đổi
                }}
                className="w-4 h-4 rounded border-2 cursor-pointer"
                style={{ 
                  accentColor: "hsl(var(--primary))",
                }}
              />
              <span className="text-sm">
                Chỉ hiển thị email có OTP
              </span>
            </label>
          </div>
          <div className="flex gap-2">
            {process.env.NODE_ENV === "development" && (
              <Button variant="secondary" onClick={useDevCred}>
                <ClipboardPaste className="mr-2 h-4 w-4" /> Dán dữ liệu mẫu (DEV)
              </Button>
            )}
            <Button 
              onClick={() => fetchMessages()} 
              disabled={loading || !credString.trim()}
            >
              {loading ? (
                <>
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" /> {MESSAGES.LOADING}
                </>
              ) : (
                <>
                  <Mail className="mr-2 h-4 w-4" /> Đọc mail
                </>
              )}
            </Button>
          </div>
        </div>
      </div>

      <div className="rounded-md border bg-card shadow-sm">
        <table className="w-full caption-bottom text-sm table-fixed">
          <thead className="bg-muted text-muted-foreground [&_tr]:border-b">
            <tr>
              <th className="h-10 px-4 text-left align-middle font-medium w-12">STT</th>
              <th className="h-10 px-4 text-left align-middle font-medium w-56">From</th>
              <th className="h-10 px-4 text-left align-middle font-medium w-40">Time</th>
              <th className="h-10 px-4 text-left align-middle font-medium">Content</th>
              <th className="h-10 px-4 text-left align-middle font-medium w-28">OTP</th>
            </tr>
          </thead>
          <tbody>
            {displayedItems.map((m, idx) => (
              <Row key={m.id} m={m} idx={idx} startIndex={startIndex} onOpenPopup={openPopup} />
            ))}
            {(loadingMore || reloadingFilter) && (
              <tr>
                <td className="py-8 px-4 text-center text-muted-foreground" colSpan={5}>
                  <div className="flex flex-col items-center justify-center gap-2">
                    <div className="flex items-center gap-2">
                      <Loader2 className="h-4 w-4 animate-spin" />
                      <span>{reloadingFilter ? MESSAGES.LOADING_EMAILS : MESSAGES.LOADING_MORE}</span>
                    </div>
                    {loadingMore && totalEmails !== null && (
                      <div className="text-xs text-muted-foreground">
                        Đã tải {items.length} / {totalEmails} email
                      </div>
                    )}
                  </div>
                </td>
              </tr>
            )}
                {filteredItems.length === 0 && !loading && !loadingMore && !reloadingFilter && (
                  <tr>
                    <td className="py-8 px-4 text-center text-muted-foreground" colSpan={5}>
                      {items.length === 0 
                        ? MESSAGES.NO_DATA
                        : filterWithOtp 
                          ? MESSAGES.NO_OTP_EMAILS
                          : MESSAGES.NO_DATA}
                    </td>
                  </tr>
                )}
          </tbody>
        </table>
      </div>

      {(items.length > 0 || filteredItems.length > 0) && (
        <div className="flex items-center justify-between px-4 py-3">
          <div className="text-sm text-muted-foreground">
            Hiển thị {startIndex + 1} - {Math.min(endIndex, filteredItems.length)} {filterWithOtp ? `(đã lọc từ ${items.length} email${totalEmails !== null ? ` trong tổng số ${totalEmails}` : ""})` : totalEmails !== null ? `trong tổng số ${totalEmails} email` : hasMore ? `(đã tải ${items.length} email)` : `trong tổng số ${items.length} email`}
          </div>
          <div className="flex items-center gap-2">
            <Button
              variant="outline"
              size="sm"
              onClick={() => setCurrentPage((p) => Math.max(1, p - 1))}
              disabled={currentPage === 1}
            >
              Trước
            </Button>
            <Button
              variant="outline"
              size="sm"
              onClick={() => setCurrentPage((p) => p + 1)}
              disabled={!canGoNext}
            >
              Sau
            </Button>
          </div>
        </div>
      )}

      <PopupContent
        openId={openId}
        items={items}
        viewMode={viewMode}
        htmlMap={htmlMap}
        loadingHtml={loadingHtml}
        onClose={closePopup}
        onToggleView={toggleViewMode}
      />
    </main>
  ) : null;
}

