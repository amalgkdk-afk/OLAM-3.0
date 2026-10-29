import { useCallback, useEffect, useState } from "react";
import { View, Text, StyleSheet, ScrollView, Pressable, RefreshControl, ActivityIndicator } from "react-native";
import { useRouter } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { api, getUser, AuthUser } from "@/src/api";
import { colors, fonts, radius, spacing } from "@/src/theme";
import { Card, Eyebrow, GoldButton, H1 } from "@/src/components/ui";
import { downloadCsv } from "@/src/utils/csv";

type Row = { branch_name?: string; batch?: string; registered: number; approved: number; checked_in: number; absent: number; attendance_pct: number };
type Summary = { generated_at: string; totals: Row; first_checkin?: string | null; last_checkin?: string | null; by_branch: Row[]; by_batch: Row[]; by_branch_batch: Row[] };

const fmtTime = (s?: string | null) => (s ? new Date(s).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }) : "—");

function RowCard({ title, row, testID }: { title: string; row: Row; testID: string }) {
  return (
    <View testID={testID}>
    <Card style={styles.item}>
      <View style={styles.itemTop}>
        <Text style={styles.name} numberOfLines={1}>{title}</Text>
        <Text style={styles.pct}>{row.attendance_pct}%</Text>
      </View>
      <View style={styles.bar}><View style={[styles.barFill, { width: `${Math.min(row.attendance_pct, 100)}%` }]} /></View>
      <Text style={styles.meta}>
        <Text style={{ color: colors.success }}>{row.checked_in} present</Text> • <Text style={{ color: colors.error }}>{row.absent} absent</Text> • {row.approved} approved • {row.registered} registered
      </Text>
    </Card>
    </View>
  );
}

export default function EventSummary() {
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const [user, setUser] = useState<AuthUser | null>(null);
  const [data, setData] = useState<Summary | null>(null);
  const [view, setView] = useState<"branch" | "batch" | "both">("branch");
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);

  const load = useCallback(async () => {
    try { setData(await api<Summary>("/reports/event-day")); setMsg(null); }
    catch (e: any) { setMsg(e.message); }
    finally { setLoading(false); setRefreshing(false); }
  }, []);

  useEffect(() => {
    (async () => {
      const u = await getUser();
      if (!u) { router.replace("/staff/login"); return; }
      if (u.role === "scanner") { router.replace("/staff/scanner"); return; }
      setUser(await api<AuthUser>("/auth/me").catch(() => u));
      load();
    })();
  }, [router, load]);

  const canExport = user?.role === "super_admin" || !!user?.can_export;
  const t = data?.totals;

  return (
    <View style={{ flex: 1, backgroundColor: colors.surface }}>
      <View style={[styles.header, { paddingTop: insets.top + spacing.sm }]}>
        <Pressable testID="summary-back-btn" onPress={() => (router.canGoBack() ? router.back() : router.replace("/staff/dashboard"))} style={styles.back}>
          <Text style={styles.backTxt}>← Dashboard</Text>
        </Pressable>
        <Eyebrow>REPORTS</Eyebrow>
        <H1>Event day summary</H1>
        <Text style={styles.sub}>Who came and who didn&apos;t, by branch and batch. Pull down to refresh.</Text>
      </View>

      <ScrollView
        contentContainerStyle={{ padding: spacing.lg, paddingBottom: insets.bottom + spacing.xl }}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={() => { setRefreshing(true); load(); }} />}
      >
        {loading && <ActivityIndicator color={colors.brandPrimary} />}
        {msg ? <Text style={styles.err} testID="summary-msg">{msg}</Text> : null}
        {!loading && data && t && (
          <>
            <View style={styles.hero} testID="summary-totals">
              <Text style={styles.heroLbl}>OVERALL ATTENDANCE</Text>
              <Text style={styles.heroVal} testID="summary-total-pct">{t.attendance_pct}%</Text>
              <Text style={styles.heroSub}>{t.checked_in} of {t.approved} approved students checked in</Text>
            </View>
            <View style={styles.summary}>
              <View style={styles.sumBox}><Text style={[styles.sumVal, { color: colors.success }]} testID="summary-present">{t.checked_in}</Text><Text style={styles.sumLbl}>PRESENT</Text></View>
              <View style={styles.sumBox}><Text style={[styles.sumVal, { color: colors.error }]} testID="summary-absent">{t.absent}</Text><Text style={styles.sumLbl}>ABSENT</Text></View>
              <View style={styles.sumBox}><Text style={styles.sumVal}>{t.registered}</Text><Text style={styles.sumLbl}>REGISTERED</Text></View>
            </View>
            <Text style={styles.times}>First entry {fmtTime(data.first_checkin)} • Last entry {fmtTime(data.last_checkin)} • Updated {fmtTime(data.generated_at)}</Text>

            {canExport ? (
              <GoldButton testID="summary-export-btn" label="Download summary CSV" variant="navy" onPress={async () => setMsg(await downloadCsv("/export/event-day.csv", "olam-event-day-summary.csv"))} style={{ marginVertical: spacing.lg }} />
            ) : (
              <Text style={styles.note} testID="summary-export-disabled">CSV download is not enabled for your account. Ask the admin if you need it.</Text>
            )}

            <View style={styles.chipRow}>
              {([["branch", "By branch"], ["batch", "By batch"], ["both", "Branch + batch"]] as const).map(([k, l]) => (
                <Pressable key={k} testID={`summary-view-${k}`} onPress={() => setView(k)} style={[styles.chip, view === k && styles.chipActive]}>
                  <Text style={[styles.chipTxt, view === k && styles.chipTxtActive]}>{l}</Text>
                </Pressable>
              ))}
            </View>

            {view === "branch" && data.by_branch.map((r) => <RowCard key={r.branch_name} title={r.branch_name!} row={r} testID={`summary-branch-${r.branch_name}`} />)}
            {view === "batch" && data.by_batch.map((r) => <RowCard key={r.batch} title={r.batch!} row={r} testID={`summary-batch-${r.batch}`} />)}
            {view === "both" && Object.entries(
              data.by_branch_batch.reduce<Record<string, Row[]>>((g, r) => { (g[r.branch_name!] ||= []).push(r); return g; }, {}),
            ).map(([b, rows]) => (
              <View key={b} style={{ marginBottom: spacing.md }}>
                <Text style={styles.branchTitle}>{b}</Text>
                {rows.map((r) => <RowCard key={`${b}-${r.batch}`} title={r.batch!} row={r} testID={`summary-pair-${b}-${r.batch}`} />)}
              </View>
            ))}
            {data.by_branch.length === 0 && <Text style={styles.empty}>No registrations yet.</Text>}
          </>
        )}
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  header: { paddingHorizontal: spacing.lg, paddingBottom: spacing.md, borderBottomWidth: 1, borderBottomColor: colors.border, backgroundColor: colors.surface },
  back: { minHeight: 44, justifyContent: "center", alignSelf: "flex-start" },
  backTxt: { color: colors.muted, fontFamily: fonts.textMed, fontSize: 14 },
  sub: { color: colors.muted, fontSize: 13, marginTop: 4, fontFamily: fonts.text },
  hero: { backgroundColor: colors.brandSecondary, borderRadius: radius.lg, padding: spacing.lg, alignItems: "center", marginBottom: spacing.md },
  heroLbl: { color: colors.brandPrimary, fontFamily: fonts.textBold, fontSize: 11, letterSpacing: 3 },
  heroVal: { color: colors.onBrandSecondary, fontFamily: fonts.display, fontSize: 48, marginTop: 4 },
  heroSub: { color: colors.onBrandSecondary, opacity: 0.8, fontFamily: fonts.text, fontSize: 13, textAlign: "center" },
  summary: { flexDirection: "row", gap: spacing.sm },
  sumBox: { flex: 1, backgroundColor: colors.surfaceSecondary, borderRadius: radius.md, borderWidth: 1, borderColor: colors.border, padding: spacing.md, alignItems: "center" },
  sumVal: { fontFamily: fonts.display, fontSize: 28, color: colors.onSurface },
  sumLbl: { fontFamily: fonts.textBold, fontSize: 10, letterSpacing: 2, color: colors.muted },
  times: { color: colors.muted, fontSize: 12, textAlign: "center", marginTop: spacing.md, fontFamily: fonts.text },
  chipRow: { flexDirection: "row", gap: 8, marginBottom: spacing.md, flexWrap: "wrap" },
  chip: { height: 44, paddingHorizontal: 16, justifyContent: "center", borderRadius: radius.pill, backgroundColor: colors.surfaceTertiary, borderWidth: 1, borderColor: colors.border },
  chipActive: { backgroundColor: colors.brandSecondary, borderColor: colors.brandSecondary },
  chipTxt: { fontSize: 12, color: colors.onSurface, fontFamily: fonts.textMed },
  chipTxtActive: { color: colors.onBrandSecondary },
  branchTitle: { fontFamily: fonts.textBold, fontSize: 12, letterSpacing: 2, color: colors.goldText, marginBottom: spacing.sm },
  item: { marginBottom: spacing.sm },
  itemTop: { flexDirection: "row", justifyContent: "space-between", alignItems: "center", gap: 8 },
  name: { fontFamily: fonts.textBold, fontSize: 15, color: colors.onSurface, flexShrink: 1 },
  pct: { fontFamily: fonts.display, fontSize: 22, color: colors.onSurface },
  bar: { height: 6, borderRadius: 3, backgroundColor: colors.surfaceTertiary, marginTop: 8, overflow: "hidden" },
  barFill: { height: 6, backgroundColor: colors.brandPrimary },
  meta: { color: colors.muted, fontSize: 12, marginTop: 6, fontFamily: fonts.text },
  note: { color: colors.muted, fontSize: 12, textAlign: "center", marginVertical: spacing.lg, fontFamily: fonts.text },
  err: { color: colors.error, textAlign: "center", marginBottom: spacing.md, fontFamily: fonts.textMed },
  empty: { color: colors.muted, textAlign: "center", marginTop: spacing.xl, fontFamily: fonts.text },
});
