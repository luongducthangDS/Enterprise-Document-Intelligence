"use client";

import { useCallback, useEffect, useState } from "react";
import { LoaderCircle, RefreshCw, Save, ShieldCheck } from "lucide-react";
import { api, ApiClientError } from "@/lib/api";
import type { AccessModel, AccessUser, AuditLog } from "@/lib/types";

export function AccessAdmin({ canManage }: { canManage: boolean }) {
  const [model, setModel] = useState<AccessModel | null>(null);
  const [users, setUsers] = useState<AccessUser[]>([]);
  const [audit, setAudit] = useState<AuditLog[]>([]);
  const [drafts, setDrafts] = useState<Record<string, { role: string; department: string }>>({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const [nextModel, nextUsers, nextAudit] = await Promise.all([
        api.getAccessModel(),
        api.listAccessUsers(),
        canManage ? api.listAuditLogs() : Promise.resolve([]),
      ]);
      setModel(nextModel);
      setUsers(nextUsers);
      setAudit(nextAudit);
      setDrafts(Object.fromEntries(nextUsers.map((user) => [user.user_id, { role: user.role, department: user.department }])));
    } catch (reason) {
      setError(reason instanceof ApiClientError ? reason.message : "Không thể tải dữ liệu phân quyền.");
    } finally {
      setLoading(false);
    }
  }, [canManage]);

  useEffect(() => { void load(); }, [load]);

  async function save(userId: string) {
    const draft = drafts[userId];
    if (!draft) return;
    try {
      await api.updateUserAccess(userId, draft);
      await load();
    } catch (reason) {
      setError(reason instanceof ApiClientError ? reason.message : "Không thể cập nhật quyền.");
    }
  }

  return <div className="content-page animate__animated animate__fadeInUp motion-view">
    <div className="page-heading"><div><p className="eyebrow">ACCESS CONTROL</p><h2>Quản trị phân quyền</h2><p>Vai trò và phòng ban được lưu trong ProfileDB; mọi thay đổi được ghi audit.</p></div><button className="icon-command" onClick={() => void load()} title="Tải lại"><RefreshCw size={17} /></button></div>
    {error && <div className="stream-error">{error}</div>}
    {loading ? <section className="work-panel panel-loading"><LoaderCircle className="spin" /> Đang tải phân quyền</section> : <>
      <section className="work-panel">
        <div className="data-table-wrap"><table className="data-table"><thead><tr><th>Người dùng</th><th>Vai trò</th><th>Phòng ban</th><th>Quyền chính</th><th></th></tr></thead><tbody>
          {users.map((user) => { const draft = drafts[user.user_id] ?? { role: user.role, department: user.department }; return <tr key={user.user_id}>
            <td><strong>{user.display_name}</strong><small>{user.email}</small></td>
            <td><select disabled={!canManage} value={draft.role} onChange={(event) => setDrafts((value) => ({ ...value, [user.user_id]: { ...draft, role: event.target.value } }))}>{Object.keys(model?.roles ?? {}).map((role) => <option key={role}>{role}</option>)}</select></td>
            <td><input disabled={!canManage} value={draft.department} onChange={(event) => setDrafts((value) => ({ ...value, [user.user_id]: { ...draft, department: event.target.value } }))} /></td>
            <td><small>{(model?.roles[draft.role] ?? []).join(" · ")}</small></td>
            <td>{canManage && <button className="icon-command" title="Lưu" onClick={() => void save(user.user_id)}><Save size={16} /></button>}</td>
          </tr>; })}
        </tbody></table></div>
      </section>
      <section className="work-panel"><div className="page-heading"><div><p className="eyebrow">AUDIT LOG</p><h3>Lịch sử thay đổi quyền</h3></div><ShieldCheck size={23} /></div>
        {!canManage ? <p>Chỉ SUPER_ADMIN được xem audit log.</p> : <div className="data-table-wrap"><table className="data-table"><thead><tr><th>Thời gian</th><th>Hành động</th><th>Tài nguyên</th><th>Trước → Sau</th></tr></thead><tbody>{audit.map((entry) => <tr key={entry.audit_id}><td>{new Date(entry.created_at).toLocaleString("vi-VN")}</td><td>{entry.action}</td><td>{entry.resource_type}<small>{entry.resource_id}</small></td><td><small>{JSON.stringify(entry.before)} → {JSON.stringify(entry.after)}</small></td></tr>)}{!audit.length && <tr><td colSpan={4} className="empty-cell">Chưa có thay đổi nào.</td></tr>}</tbody></table></div>}
      </section>
    </>}
  </div>;
}