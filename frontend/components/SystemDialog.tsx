"use client";

import { createContext, FormEvent, ReactNode, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";
import { AlertTriangle, Info, X } from "lucide-react";

type DialogRequest = {
  mode: "alert" | "confirm" | "prompt";
  title: string;
  message: string;
  confirmLabel?: string;
  cancelLabel?: string;
  tone?: "primary" | "danger";
  initialValue?: string;
  inputLabel?: string;
  placeholder?: string;
};

type DialogOptions = Omit<DialogRequest, "mode">;
type SystemDialogApi = {
  alert: (options: DialogOptions) => Promise<void>;
  confirm: (options: DialogOptions) => Promise<boolean>;
  prompt: (options: DialogOptions) => Promise<string | null>;
};

const SystemDialogContext = createContext<SystemDialogApi | null>(null);

export function SystemDialogProvider({ children }: { children: ReactNode }) {
  const [dialog, setDialog] = useState<DialogRequest | null>(null);
  const [inputValue, setInputValue] = useState("");
  const resolver = useRef<((value: boolean | string | null) => void) | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const confirmRef = useRef<HTMLButtonElement>(null);

  const open = useCallback((request: DialogRequest) => new Promise<boolean | string | null>((resolve) => {
    resolver.current?.(null);
    resolver.current = resolve;
    setInputValue(request.initialValue ?? "");
    setDialog(request);
  }), []);

  const close = useCallback((value: boolean | string | null) => {
    resolver.current?.(value);
    resolver.current = null;
    setDialog(null);
  }, []);

  const api = useMemo<SystemDialogApi>(() => ({
    alert: async (options) => { await open({ ...options, mode: "alert" }); },
    confirm: async (options) => Boolean(await open({ ...options, mode: "confirm" })),
    prompt: async (options) => {
      const result = await open({ ...options, mode: "prompt" });
      return typeof result === "string" ? result : null;
    },
  }), [open]);

  useEffect(() => {
    if (!dialog) return;
    const currentDialog = dialog;
    const timer = window.setTimeout(() => currentDialog.mode === "prompt" ? inputRef.current?.focus() : confirmRef.current?.focus(), 0);
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") close(currentDialog.mode === "alert" ? true : null);
    }
    window.addEventListener("keydown", onKeyDown);
    return () => {
      window.clearTimeout(timer);
      window.removeEventListener("keydown", onKeyDown);
    };
  }, [dialog, close]);

  function submit(event: FormEvent) {
    event.preventDefault();
    if (!dialog) return;
    close(dialog.mode === "prompt" ? inputValue.trim() : true);
  }

  return <SystemDialogContext.Provider value={api}>
    {children}
    {dialog && <div className="system-dialog-layer" onMouseDown={() => close(dialog.mode === "alert" ? true : null)}>
      <form className={`system-dialog ${dialog.tone === "danger" ? "danger" : ""}`} role="dialog" aria-modal="true" aria-labelledby="system-dialog-title" aria-describedby="system-dialog-message" onSubmit={submit} onMouseDown={(event) => event.stopPropagation()}>
        <div className="system-dialog-heading">
          <span className="system-dialog-icon">{dialog.tone === "danger" ? <AlertTriangle size={20} /> : <Info size={20} />}</span>
          <div><h3 id="system-dialog-title">{dialog.title}</h3><p id="system-dialog-message">{dialog.message}</p></div>
          <button type="button" className="system-dialog-close" aria-label="Đóng thông báo" onClick={() => close(dialog.mode === "alert" ? true : null)}><X size={18} /></button>
        </div>
        {dialog.mode === "prompt" && <label className="system-dialog-field">{dialog.inputLabel ?? "Tên hội thoại"}<input ref={inputRef} value={inputValue} placeholder={dialog.placeholder} maxLength={120} onChange={(event) => setInputValue(event.target.value)} /></label>}
        <div className="system-dialog-actions">
          {dialog.mode !== "alert" && <button type="button" className="secondary-command" onClick={() => close(null)}>{dialog.cancelLabel ?? "Hủy"}</button>}
          <button ref={confirmRef} type="submit" className={dialog.tone === "danger" ? "danger-confirm-command" : "primary-command"} disabled={dialog.mode === "prompt" && !inputValue.trim()}>{dialog.confirmLabel ?? (dialog.mode === "alert" ? "Đã hiểu" : "Xác nhận")}</button>
        </div>
      </form>
    </div>}
  </SystemDialogContext.Provider>;
}

export function useSystemDialog() {
  const context = useContext(SystemDialogContext);
  if (!context) throw new Error("useSystemDialog must be used inside SystemDialogProvider");
  return context;
}
