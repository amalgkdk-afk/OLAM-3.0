import { useEffect, useState, useCallback } from "react";
import { View, Text, StyleSheet, ScrollView, Pressable, RefreshControl, ActivityIndicator, Modal, TextInput, Platform } from "react-native";
import { useRouter, useFocusEffect } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { api, clearSession, getUser, AuthUser, getPublicUrl, getToken } from "@/src/api";
import { colors, fonts, radius, spacing } from "@/src/theme";
import { Card, GoldButton, Pill, Eyebrow, TextInputPill, Field } from "@/src/components/ui";
import { downloadCsv } from "@/src/utils/csv";
import { BranchRow } from "@/src/components/branch-row";

type Reg = { id: string; reference: string; full_name: string; student_code?: string | null; mobile: string; email: string; branch_name: string; branch_id: string; batch: string; batch_no?: string; faculty_name?: string; pass_email_status?: string | null; status: "pending" | "approved" | "rejected"; rejection_reason?: string; checked_in: boolean; checked_in_at?: string; reviewed_by_name?: string };
type Stats = { total: number; pending: number; approved: number; rejected: number; checked_in: number; not_checked_in: number; attendance_pct: number; by_branch: { branch: string; total: number; approved: number; checked_in: number }[] };

export default function Dashboard() {
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const [user, setUser] = useState<AuthUser | null>(null);
  const [tab, setTab] = useState<"overview" | "regs" | "settings" | "scanner">("overview");
  const [stats, setStats] = useState<Stats | null>(null);
  const [regs, setRegs] = useState<Reg[]>([]);
  const [branches, setBranches] = useState<any[]>([]);
  const [batches, setBatches] = useState<any[]>([]);
  const [filter, setFilter] = useState<"all" | "pending" | "approved" | "rejected">("pending");
  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [rejectModal, setRejectModal] = useState<Reg | null>(null);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [bulkConfirm, setBulkConfirm] = useState(false);
  const [bulkBusy, setBulkBusy] = useState(false);
  const [bulkMsg, setBulkMsg] = useState<string | null>(null);
  const toggleSel = (id: string) => setSelected((s) => { const n = new Set(s); if (n.has(id)) n.delete(id); else n.add(id); return n; });
  async function bulkApprove() {
    setBulkBusy(true);
    try {
      const r = await api<{ approved: number; skipped: { id: string; reason: string }[] }>("/registrations/bulk-approve", { method: "POST", body: JSON.stringify({ ids: Array.from(selected) }) });
      setBulkMsg(`${r.approved} approved${r.skipped.length ? `, ${r.skipped.length} skipped` : ""}. Pass emails are on their way.`);
      setSelected(new Set());
      refresh();
    } catch (e: any) { setBulkMsg(e.message); }
    finally { setBulkBusy(false); setBulkConfirm(false); }
  }
  const [rejectReason, setRejectReason] = useState("");
  const [newBranchName, setNewBranchName] = useState("");
  const [newBatchName, setNewBatchName] = useState("");

  useFocusEffect(useCallback(() => {
    (async () => {
      const u = await getUser();
      if (!u) { router.replace("/staff/login"); return; }
      setUser(u);
      if (u.role === "scanner") { router.replace("/staff/scanner"); return; }
      refresh();
    })();
  // eslint-disable-next-line
  }, []));

  async function refresh() {
    setLoading(true);
    try {
      const [s, r, b, bt, me] = await Promise.all([
        api<Stats>("/stats"),
        api<Reg[]>(`/registrations${filter === "all" ? "" : "?status_=" + filter}`),
        api<any[]>("/branches"),
        api<any[]>("/batches"),
        api<AuthUser>("/auth/me"),
      ]);
      setStats(s); setRegs(r); setBranches(b); setBatches(bt); setUser(me);
    } catch (e: any) {
      if (/401/.test(e.message || "")) router.replace("/staff/login");
    }
    finally { setLoading(false); setRefreshing(false); }
  }

  useEffect(() => { if (user) refresh(); /* eslint-disable-next-line */ }, [filter]);

  const filteredRegs = regs.filter((r) => {
    if (!query) return true;
    const q = query.toLowerCase();
    const qDigits = query.replace(/\D/g, "");
    if (qDigits.length >= 4 && r.mobile.replace(/\D/g, "").includes(qDigits)) return true;
    return r.full_name.toLowerCase().includes(q) || r.mobile.includes(q) || r.email.toLowerCase().includes(q) || r.reference.toLowerCase().includes(q) || r.batch.toLowerCase().includes(q) || (r.faculty_name || "").toLowerCase().includes(q) || (r.batch_no || "").toLowerCase().includes(q);
  });
  const pendingVisible = filteredRegs.filter((r) => r.status === "pending");
  const anyQueued = regs.some((r) => r.status === "approved" && r.pass_email_status === "queued");
  useEffect(() => {
    if (tab !== "regs" || !anyQueued) return;
    const t = setInterval(() => { api<Reg[]>(`/registrations${filter === "all" ? "" : "?status_=" + filter}`).then(setRegs).catch(() => {}); }, 15000);
    return () => clearInterval(t);
  }, [tab, anyQueued, filter]);
  const allPendingSelected = pendingVisible.length > 0 && pendingVisible.every((r) => selected.has(r.id));

  async function approve(r: Reg) {
    try { await api(`/registrations/${r.id}/approve`, { method: "POST" }); refresh(); }
    catch (e: any) { alert(e.message); }
  }
  async function reject() {
    if (!rejectModal || !rejectReason.trim()) return;
    try { await api(`/registrations/${rejectModal.id}/reject`, { method: "POST", body: JSON.stringify({ reason: rejectReason.trim() }) }); setRejectModal(null); setRejectReason(""); refresh(); }
    catch (e: any) { alert(e.message); }
  }

  async function exportCsv() {
    const m = await downloadCsv("/export/registrations.csv", "olam-registrations.csv");
    if (m) alert(m);
  }

  if (!user) return <View style={{ flex: 1, backgroundColor: colors.surface }} />;

  return (
    <View style={{ flex: 1, backgroundColor: colors.surface }}>
      {/* Header */}
      <View style={[styles.header, { paddingTop: insets.top + spacing.md, flexDirection: "column", alignItems: "stretch" }]}>
        <View style={{ flexDirection: "row", alignItems: "center", justifyContent: "space-between", gap: spacing.sm }}>
          <View style={{ flex: 1, minWidth: 0 }}>
            <Eyebrow>{user.role === "super_admin" ? "OLAM 3.0 • ADMIN • ALL BRANCHES" : `${branches.find((b) => b.id === user.branch_id)?.name ?? "BRANCH"} BRANCH`}</Eyebrow>
          </View>
          <View style={{ flexDirection: "row", alignItems: "center", gap: spacing.md, flexShrink: 0 }}>
            <Pressable testID="dashboard-change-password-btn" onPress={() => router.push("/staff/change-password")} style={{ minHeight: 44, justifyContent: "center" }}>
              <Text style={styles.logout}>Password</Text>
            </Pressable>
            <Pressable testID="dashboard-logout-btn" onPress={async () => { await clearSession(); router.replace("/staff/login"); }} style={{ minHeight: 44, minWidth: 64, justifyContent: "center", alignItems: "flex-end" }}>
              <Text style={styles.logout}>Sign out</Text>
            </Pressable>
          </View>
        </View>
        <Text style={styles.hello} numberOfLines={2}>{user.role === "coordinator" ? "Coordinator · " : "Hi, "}{user.name || user.email}</Text>
      </View>

      {/* Tabs */}
      <ScrollView horizontal showsHorizontalScrollIndicator={false} style={styles.tabsScroll} contentContainerStyle={styles.tabs}>
        {([
          ["overview", "Overview"],
          ["regs", "Registrations"],
          ["attendance", "Attendance"],
          ["faculty", "Faculty"],
          ["summary", "Day Summary"],
          user.role === "super_admin" && ["settings", "Settings"],
          ["scanner", "Scanner"],
        ].filter(Boolean) as any[]).map(([k, l]) => (
          <Pressable key={k} testID={`dashboard-tab-${k}`} onPress={() => k === "scanner" ? router.push("/staff/scanner") : k === "attendance" ? router.push("/staff/attendance") : k === "faculty" ? router.push("/staff/faculty-report") : k === "summary" ? router.push("/staff/event-summary") : setTab(k)} style={[styles.tab, tab === k && styles.tabActive]}>
            <Text style={[styles.tabTxt, tab === k && styles.tabTxtActive]}>{l}</Text>
          </Pressable>
        ))}
      </ScrollView>

      <ScrollView contentContainerStyle={{ padding: spacing.lg, paddingBottom: insets.bottom + spacing.xl }} refreshControl={<RefreshControl refreshing={refreshing} onRefresh={() => { setRefreshing(true); refresh(); }} />}>
        {loading && <ActivityIndicator color={colors.brandPrimary} />}

        {tab === "overview" && stats && (
          <View>
            <View style={styles.statGrid}>
              <StatCard label="Total" value={stats.total} testID="stat-total" />
              <StatCard label="Pending" value={stats.pending} tone="warning" testID="stat-pending" />
              <StatCard label="Approved" value={stats.approved} tone="success" testID="stat-approved" />
              <StatCard label="Rejected" value={stats.rejected} tone="error" testID="stat-rejected" />
              <StatCard label="Checked In" value={stats.checked_in} tone="info" testID="stat-checkedin" />
              <StatCard label="Not Yet In" value={stats.not_checked_in} testID="stat-notin" />
            </View>
            <Card style={{ marginTop: spacing.lg }}>
              <Text style={styles.cardTitle}>Attendance</Text>
              <Text style={styles.bigNum}>{stats.attendance_pct}%</Text>
              <Text style={styles.cardSub}>{stats.checked_in} / {stats.approved} approved students checked in</Text>
            </Card>
            {!!stats.by_branch?.length && (
              <Card style={{ marginTop: spacing.lg }}>
                <Text style={styles.cardTitle}>By Branch</Text>
                {stats.by_branch.map((b) => (
                  <View key={b.branch} style={styles.branchRow}>
                    <Text style={styles.branchName}>{b.branch}</Text>
                    <Text style={styles.branchStat}>{b.checked_in}/{b.approved} in • {b.total} total</Text>
                  </View>
                ))}
              </Card>
            )}
            {user.role === "super_admin" || user.can_export ? (
              <GoldButton testID="dashboard-export-btn" label="Export CSV" variant="navy" onPress={exportCsv} style={{ marginTop: spacing.lg }} />
            ) : (
              <Text style={[styles.cardSub, { marginTop: spacing.lg, textAlign: "center" }]} testID="dashboard-export-disabled">CSV download is not enabled for your account. Ask the admin if you need it.</Text>
            )}
          </View>
        )}

        {tab === "regs" && (
          <View>
            <TextInputPill testID="dashboard-search-input" placeholder="Search name, phone, ref, batch, faculty..." value={query} onChangeText={setQuery} />
            <View style={styles.filterRow}>
              {(["all", "pending", "approved", "rejected"] as const).map((f) => (
                <Pressable key={f} testID={`dashboard-filter-${f}`} onPress={() => setFilter(f)} style={[styles.filterChip, filter === f && styles.filterChipActive]}>
                  <Text style={[styles.filterChipTxt, filter === f && styles.filterChipTxtActive]}>{f.toUpperCase()}</Text>
                </Pressable>
              ))}
            </View>
            {filteredRegs.length === 0 && !loading && <Text style={styles.empty}>No registrations match.</Text>}
            {pendingVisible.length > 0 && (
              <View style={styles.bulkBar} testID="bulk-bar">
                <Pressable testID="bulk-select-all-btn" onPress={() => setSelected(allPendingSelected ? new Set() : new Set(pendingVisible.map((r) => r.id)))} style={styles.bulkSelect}>
                  <View style={[styles.cb, allPendingSelected && styles.cbOn]}>{allPendingSelected ? <Text style={styles.cbTick}>✓</Text> : null}</View>
                  <Text style={styles.bulkTxt}>{allPendingSelected ? "Unselect all" : `Select all pending (${pendingVisible.length})`}</Text>
                </Pressable>
                <GoldButton testID="bulk-approve-btn" label={`Approve selected (${selected.size})`} disabled={selected.size === 0} onPress={() => setBulkConfirm(true)} style={{ height: 44, paddingHorizontal: 14 }} />
              </View>
            )}
            {bulkMsg ? <Text style={styles.bulkMsg} testID="bulk-result">{bulkMsg}</Text> : null}
            {filteredRegs.map((r) => (
              <Card key={r.id} style={{ marginTop: spacing.md }}>
                <View style={{ flexDirection: "row", justifyContent: "space-between", alignItems: "center", gap: 8 }}>
                  {r.status === "pending" ? (
                    <Pressable testID={`select-reg-${r.id}`} onPress={() => toggleSel(r.id)} hitSlop={10} style={styles.selBox}>
                      <View style={[styles.cb, selected.has(r.id) && styles.cbOn]}>{selected.has(r.id) ? <Text style={styles.cbTick}>✓</Text> : null}</View>
                    </Pressable>
                  ) : null}
                  <Text style={[styles.regName, { flex: 1 }]} testID={`reg-name-${r.id}`}>{r.full_name}</Text>
                  <Pill label={r.status} tone={r.status === "approved" ? "success" : r.status === "pending" ? "warning" : "error"} />
                </View>
                <Text style={styles.regMeta}>{r.reference} • {r.branch_name} • {r.batch}</Text>
                <Text style={styles.regMeta}>{r.mobile} • {r.email}</Text>
                {r.batch_no || r.faculty_name ? <Text style={styles.regMeta}>Batch No. {r.batch_no || "—"} • Faculty: {r.faculty_name || "—"}</Text> : null}
                {r.checked_in ? <Text style={[styles.regMeta, { color: colors.success }]}>Checked in {new Date(r.checked_in_at!).toLocaleString()}</Text> : null}
                {r.status === "approved" && r.pass_email_status ? (
                  <View style={{ flexDirection: "row", alignItems: "center", gap: 8, marginTop: 2 }}>
                    <Text style={[styles.regMeta, { color: r.pass_email_status === "sent" ? colors.success : r.pass_email_status === "failed" ? colors.error : colors.muted }]} testID={`email-status-${r.id}`}>
                      {r.pass_email_status === "sent" ? "Pass email sent" : r.pass_email_status === "failed" ? "Pass email failed" : "Pass email queued (sends automatically)"}
                    </Text>
                    {r.pass_email_status === "failed" ? (
                      <Pressable testID={`resend-email-btn-${r.id}`} onPress={async () => { try { await api(`/registrations/${r.id}/resend-email`, { method: "POST" }); refresh(); } catch (e: any) { alert(e.message); } }} style={{ minHeight: 44, minWidth: 64, justifyContent: "center" }}>
                        <Text style={[styles.regMeta, { color: colors.info, textDecorationLine: "underline" }]}>Resend</Text>
                      </Pressable>
                    ) : null}
                  </View>
                ) : null}
                {r.rejection_reason ? <Text style={[styles.regMeta, { color: colors.error }]}>Reason: {r.rejection_reason}</Text> : null}
                {(r.status !== "approved" || user.role === "super_admin") && (
                  <View style={{ flexDirection: "row", gap: 8, marginTop: spacing.md }}>
                    {r.status !== "approved" && <GoldButton testID={`approve-btn-${r.id}`} label="Approve" onPress={() => approve(r)} style={{ flex: 1, height: 44 }} />}
                    {r.status !== "rejected" && <GoldButton testID={`reject-btn-${r.id}`} label="Reject" variant="ghost" onPress={() => setRejectModal(r)} style={{ flex: 1, height: 44 }} />}
                  </View>
                )}
              </Card>
            ))}
          </View>
        )}

        {tab === "settings" && user.role === "super_admin" && (
          <View>
            <Card>
              <Text style={styles.cardTitle}>Branches</Text>
              <Text style={styles.cardSub}>Rename a branch or switch it off. Switched-off branches disappear from the student form; existing registrations are kept.</Text>
              <View style={{ marginTop: spacing.sm }}>
                {branches.map((b) => <BranchRow key={b.id} branch={b} onSaved={refresh} />)}
              </View>
              <View style={{ flexDirection: "row", gap: 8, marginTop: spacing.md }}>
                <TextInputPill testID="new-branch-input" placeholder="New branch name" value={newBranchName} onChangeText={setNewBranchName} style={{ flex: 1, minWidth: 0 }} />
                <GoldButton testID="add-branch-btn" label="Add" onPress={async () => { if (!newBranchName.trim()) return; try { await api("/branches", { method: "POST", body: JSON.stringify({ name: newBranchName.trim(), active: true }) }); setNewBranchName(""); refresh(); } catch (e: any) { alert(e.message); } }} style={{ height: 50 }} />
              </View>
            </Card>
            <Card style={{ marginTop: spacing.lg }}>
              <Text style={styles.cardTitle}>Batches</Text>
              {batches.map((b) => <Text key={b.id} style={styles.listItem}>• {b.name}</Text>)}
              <View style={{ flexDirection: "row", gap: 8, marginTop: spacing.md }}>
                <TextInputPill testID="new-batch-input" placeholder="New batch name" value={newBatchName} onChangeText={setNewBatchName} style={{ flex: 1, minWidth: 0 }} />
                <GoldButton testID="add-batch-btn" label="Add" onPress={async () => { if (!newBatchName.trim()) return; try { await api("/batches", { method: "POST", body: JSON.stringify({ name: newBatchName.trim() }) }); setNewBatchName(""); refresh(); } catch (e: any) { alert(e.message); } }} style={{ height: 50 }} />
              </View>
            </Card>
            <Pressable testID="event-settings-btn" onPress={() => router.push("/staff/event-settings")} style={{ marginTop: spacing.lg }}>
              <Card><Text style={styles.cardTitle}>Event Settings →</Text><Text style={styles.cardSub}>Open or close registration, edit the privacy notice</Text></Card>
            </Pressable>
            <Pressable testID="manage-staff-btn" onPress={() => router.push("/staff/manage")} style={{ marginTop: spacing.lg }}>
              <Card><Text style={styles.cardTitle}>Manage Staff Accounts →</Text><Text style={styles.cardSub}>Create coordinators and scanners</Text></Card>
            </Pressable>
          </View>
        )}
      </ScrollView>

      <Modal visible={bulkConfirm} transparent animationType="fade" onRequestClose={() => setBulkConfirm(false)}>
        <View style={styles.modalWrap}>
          <View style={styles.modal}>
            <Text style={styles.modalTitle}>Approve {selected.size} students?</Text>
            <Text style={styles.modalSub}>Each student gets a QR pass and an email with their pass link. You can still reject any of them later.</Text>
            <View style={{ flexDirection: "row", gap: 8 }}>
              <GoldButton testID="bulk-cancel-btn" label="Cancel" variant="ghost" onPress={() => setBulkConfirm(false)} style={{ flex: 1, paddingHorizontal: 8 }} />
              <GoldButton testID="bulk-confirm-btn" label="Approve all" loading={bulkBusy} onPress={bulkApprove} style={{ flex: 1, paddingHorizontal: 8 }} />
            </View>
          </View>
        </View>
      </Modal>

      <Modal visible={!!rejectModal} transparent animationType="fade" onRequestClose={() => setRejectModal(null)}>
        <View style={styles.modalWrap}>
          <View style={styles.modal}>
            <Text style={styles.modalTitle}>Reject registration</Text>
            <Text style={styles.modalSub}>{rejectModal?.full_name} • {rejectModal?.reference}</Text>
            <Field label="Reason">
              <TextInputPill testID="reject-reason-input" value={rejectReason} onChangeText={setRejectReason} multiline placeholder="Visible to the student" style={{ minHeight: 80 }} />
            </Field>
            <View style={{ flexDirection: "row", gap: 8 }}>
              <GoldButton testID="reject-cancel-btn" label="Cancel" variant="ghost" onPress={() => { setRejectModal(null); setRejectReason(""); }} style={{ flex: 1, paddingHorizontal: 8 }} />
              <GoldButton testID="confirm-reject-btn" label="Reject" variant="danger" onPress={reject} style={{ flex: 1, paddingHorizontal: 8 }} />
            </View>
          </View>
        </View>
      </Modal>
    </View>
  );
}

function StatCard({ label, value, tone, testID }: { label: string; value: number; tone?: "success" | "warning" | "error" | "info"; testID?: string }) {
  const color = tone === "success" ? colors.success : tone === "warning" ? colors.warning : tone === "error" ? colors.error : tone === "info" ? colors.info : colors.brandPrimary;
  return (
    <View style={styles.statCard} testID={testID}>
      <Text style={[styles.statVal, { color }]}>{value}</Text>
      <Text style={styles.statLbl}>{label}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  header: { paddingHorizontal: spacing.lg, paddingBottom: spacing.md, flexDirection: "row", justifyContent: "space-between", alignItems: "flex-end", borderBottomWidth: 1, borderBottomColor: colors.border, backgroundColor: colors.surface },
  hello: { fontFamily: fonts.display, fontSize: 24, color: colors.onSurface, marginTop: 4 },
  logout: { color: colors.muted, fontFamily: fonts.textMed, fontSize: 13 },
  tabsScroll: { flexGrow: 0, borderBottomWidth: 1, borderBottomColor: colors.border, backgroundColor: colors.surfaceSecondary },
  tabs: { flexDirection: "row", paddingHorizontal: spacing.lg, paddingVertical: spacing.md, gap: 8, alignItems: "center" },
  tab: { paddingHorizontal: 14, minHeight: 44, justifyContent: "center", borderRadius: radius.pill, backgroundColor: colors.surfaceTertiary, flexShrink: 0 },
  tabActive: { backgroundColor: colors.brandSecondary },
  tabTxt: { color: colors.onSurface, fontSize: 12, fontFamily: fonts.textMed },
  tabTxtActive: { color: colors.onBrandSecondary },
  statGrid: { flexDirection: "row", flexWrap: "wrap", gap: spacing.md },
  statCard: { width: "47%", backgroundColor: colors.surfaceSecondary, borderRadius: radius.md, padding: spacing.md, borderWidth: 1, borderColor: colors.border },
  statVal: { fontFamily: fonts.display, fontSize: 36 },
  statLbl: { color: colors.muted, fontSize: 11, letterSpacing: 2, fontFamily: fonts.textBold, textTransform: "uppercase" },
  cardTitle: { fontFamily: fonts.textBold, fontSize: 14, color: colors.onSurface, marginBottom: 4 },
  bigNum: { fontFamily: fonts.display, fontSize: 44, color: colors.brandPrimary, marginVertical: 4 },
  cardSub: { color: colors.muted, fontSize: 12, fontFamily: fonts.text },
  branchRow: { flexDirection: "row", justifyContent: "space-between", paddingVertical: 10, borderTopWidth: 1, borderTopColor: colors.divider },
  branchName: { fontFamily: fonts.textMed, color: colors.onSurface },
  branchStat: { color: colors.muted, fontSize: 12, fontFamily: fonts.text },
  filterRow: { flexDirection: "row", gap: 8, marginTop: spacing.md, flexWrap: "wrap" },
  filterChip: { paddingHorizontal: 14, minHeight: 40, justifyContent: "center", borderRadius: radius.pill, backgroundColor: colors.surfaceTertiary, borderWidth: 1, borderColor: colors.border, flexShrink: 0 },
  filterChipActive: { backgroundColor: colors.brandPrimary, borderColor: colors.brandPrimary },
  filterChipTxt: { fontSize: 10, letterSpacing: 1, color: colors.onSurface, fontFamily: fonts.textBold },
  filterChipTxtActive: { color: colors.onBrandPrimary },
  regName: { fontFamily: fonts.textBold, fontSize: 15, color: colors.onSurface },
  regMeta: { color: colors.muted, fontSize: 12, marginTop: 2, fontFamily: fonts.text },
  empty: { color: colors.muted, textAlign: "center", marginTop: spacing.xl, fontFamily: fonts.text },
  listItem: { color: colors.onSurface, fontSize: 14, paddingVertical: 4, fontFamily: fonts.text },
  bulkBar: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", gap: 8, marginTop: spacing.md, padding: spacing.sm, borderRadius: radius.md, backgroundColor: colors.surfaceSecondary, borderWidth: 1, borderColor: colors.border },
  bulkSelect: { flexDirection: "row", alignItems: "center", gap: 8, minHeight: 44, flexShrink: 1 },
  bulkTxt: { fontFamily: fonts.textMed, fontSize: 12, color: colors.onSurface, flexShrink: 1 },
  bulkMsg: { marginTop: spacing.sm, color: colors.success, fontFamily: fonts.textMed, fontSize: 13 },
  selBox: { minWidth: 44, minHeight: 44, justifyContent: "center" },
  cb: { width: 22, height: 22, borderRadius: 6, borderWidth: 1.5, borderColor: colors.borderStrong, alignItems: "center", justifyContent: "center", backgroundColor: colors.surfaceSecondary },
  cbOn: { backgroundColor: colors.brandPrimary, borderColor: colors.brandPrimary },
  cbTick: { color: colors.onBrandPrimary, fontWeight: "900", fontSize: 13 },
  modalWrap: { flex: 1, backgroundColor: "rgba(11,25,44,0.6)", justifyContent: "center", padding: spacing.lg },
  modal: { backgroundColor: colors.surfaceSecondary, borderRadius: radius.lg, padding: spacing.lg, borderWidth: 1, borderColor: colors.border },
  modalTitle: { fontFamily: fonts.display, fontSize: 22, color: colors.onSurface },
  modalSub: { color: colors.muted, fontSize: 13, marginTop: 4, marginBottom: spacing.md, fontFamily: fonts.text },
});
