import { useCallback, useEffect, useState } from "react";
import { View, Text, StyleSheet, ScrollView, Pressable, RefreshControl, ActivityIndicator } from "react-native";
import { useRouter } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { api, getUser, AuthUser } from "@/src/api";
import { colors, fonts, radius, spacing } from "@/src/theme";
import { Card, Eyebrow, H1, Pill } from "@/src/components/ui";

type CheckIn = { id: string; checked_in_at: string; scanner_name?: string; station?: string; full_name: string; reference: string; batch: string; branch_name?: string };
type Attempt = { id: string; result: string; attempted_at: string; scanner_name?: string; station?: string; full_name?: string; reference?: string; batch?: string; branch_name?: string };

const RESULT_LABEL: Record<string, { label: string; tone: "warning" | "error" | "info" }> = {
  ALREADY_CHECKED_IN: { label: "Duplicate", tone: "warning" },
  NOT_APPROVED: { label: "Not approved", tone: "error" },
  REVOKED: { label: "Revoked", tone: "error" },
  INVALID: { label: "Invalid QR", tone: "error" },
};

export default function Attendance() {
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const [user, setUser] = useState<AuthUser | null>(null);
  const [branches, setBranches] = useState<{ id: string; name: string }[]>([]);
  const [branchId, setBranchId] = useState<string>("");
  const [view, setView] = useState<"checkins" | "attempts">("checkins");
  const [data, setData] = useState<{ checkins: CheckIn[]; attempts: Attempt[]; duplicate_count: number } | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const load = useCallback(async (bid: string) => {
    setErr(null);
    try {
      setData(await api(`/attendance${bid ? `?branch_id=${bid}` : ""}`));
    } catch (e: any) { setErr(e.message); }
    finally { setLoading(false); setRefreshing(false); }
  }, []);

  useEffect(() => {
    (async () => {
      const u = await getUser();
      if (!u || u.role === "scanner") { router.replace("/staff/login"); return; }
      setUser(u);
      if (u.role === "super_admin") setBranches(await api("/branches"));
      load("");
    })();
  }, [router, load]);

  function pickBranch(id: string) { setBranchId(id); setLoading(true); load(id); }

  const fmt = (s: string) => new Date(s).toLocaleString([], { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit", second: "2-digit" });

  return (
    <View style={{ flex: 1, backgroundColor: colors.surface }}>
      <View style={[styles.header, { paddingTop: insets.top + spacing.sm }]}>
        <Pressable testID="attendance-back-btn" onPress={() => (router.canGoBack() ? router.back() : router.replace("/staff/dashboard"))} style={styles.back}>
          <Text style={styles.backTxt}>← Dashboard</Text>
        </Pressable>
        <Eyebrow>ATTENDANCE HISTORY</Eyebrow>
        <H1>Check-in log</H1>

        {user?.role === "super_admin" && (
          <ScrollView horizontal showsHorizontalScrollIndicator={false} style={styles.chipScroll} contentContainerStyle={styles.chipRow}>
            {[{ id: "", name: "All branches" }, ...branches].map((b) => (
              <Pressable key={b.id || "all"} testID={`attendance-branch-${b.id || "all"}`} onPress={() => pickBranch(b.id)} style={[styles.chip, branchId === b.id && styles.chipActive]}>
                <Text style={[styles.chipTxt, branchId === b.id && styles.chipTxtActive]}>{b.name}</Text>
              </Pressable>
            ))}
          </ScrollView>
        )}

        <View style={styles.segment}>
          <Pressable testID="attendance-view-checkins" onPress={() => setView("checkins")} style={[styles.segBtn, view === "checkins" && styles.segActive]}>
            <Text style={[styles.segTxt, view === "checkins" && styles.segTxtActive]}>Check-ins ({data?.checkins.length ?? 0})</Text>
          </Pressable>
          <Pressable testID="attendance-view-attempts" onPress={() => setView("attempts")} style={[styles.segBtn, view === "attempts" && styles.segActive]}>
            <Text style={[styles.segTxt, view === "attempts" && styles.segTxtActive]}>Refused scans ({data?.attempts.length ?? 0})</Text>
          </Pressable>
        </View>
      </View>

      <ScrollView
        contentContainerStyle={{ padding: spacing.lg, paddingBottom: insets.bottom + spacing.xl }}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={() => { setRefreshing(true); load(branchId); }} />}
      >
        {loading && <ActivityIndicator color={colors.brandPrimary} />}
        {err && <Text style={styles.err} testID="attendance-error">{err}</Text>}

        {!loading && data && view === "checkins" && (
          <>
            {data.checkins.length === 0 && <Text style={styles.empty}>No one has checked in yet.</Text>}
            {data.checkins.map((c) => (
              <Card key={c.id} style={styles.item}>
                <View style={styles.itemTop}>
                  <Text style={styles.name} numberOfLines={1}>{c.full_name}</Text>
                  <Text style={styles.time}>{fmt(c.checked_in_at)}</Text>
                </View>
                <Text style={styles.meta}>{c.reference} • {c.branch_name} • {c.batch}</Text>
                <Text style={styles.meta}>By {c.scanner_name || "—"} • Station {c.station || "—"}</Text>
              </Card>
            ))}
          </>
        )}

        {!loading && data && view === "attempts" && (
          <>
            <Card style={[styles.item, { backgroundColor: colors.brandTertiary }]}>
              <Text style={styles.name} testID="attendance-duplicate-count">{data.duplicate_count} duplicate scan attempts</Text>
              <Text style={styles.meta}>Passes that were scanned again after entry. No second entry was recorded.</Text>
            </Card>
            {data.attempts.length === 0 && <Text style={styles.empty}>No refused scans.</Text>}
            {data.attempts.map((a) => {
              const r = RESULT_LABEL[a.result] ?? { label: a.result, tone: "error" as const };
              return (
                <Card key={a.id} style={styles.item}>
                  <View style={styles.itemTop}>
                    <Text style={styles.name} numberOfLines={1}>{a.full_name || "Unknown pass"}</Text>
                    <Pill label={r.label} tone={r.tone} />
                  </View>
                  {a.reference ? <Text style={styles.meta}>{a.reference} • {a.branch_name} • {a.batch}</Text> : null}
                  <Text style={styles.meta}>{fmt(a.attempted_at)} • By {a.scanner_name || "—"} • Station {a.station || "—"}</Text>
                </Card>
              );
            })}
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
  chipScroll: { marginTop: spacing.md, marginHorizontal: -spacing.lg, flexGrow: 0, height: 56 },
  chipRow: { gap: 8, paddingHorizontal: spacing.lg, alignItems: "center" },
  chip: { height: 36, paddingHorizontal: 14, justifyContent: "center", borderRadius: radius.pill, backgroundColor: colors.surfaceTertiary, borderWidth: 1, borderColor: colors.border, flexShrink: 0 },
  chipActive: { backgroundColor: colors.brandSecondary, borderColor: colors.brandSecondary },
  chipTxt: { fontSize: 12, color: colors.onSurface, fontFamily: fonts.textMed },
  chipTxtActive: { color: colors.onBrandSecondary },
  segment: { flexDirection: "row", marginTop: spacing.md, backgroundColor: colors.surfaceTertiary, borderRadius: radius.pill, padding: 4 },
  segBtn: { flex: 1, minHeight: 40, alignItems: "center", justifyContent: "center", borderRadius: radius.pill },
  segActive: { backgroundColor: colors.brandPrimary },
  segTxt: { fontSize: 12, fontFamily: fonts.textMed, color: colors.onSurface },
  segTxtActive: { color: colors.onBrandPrimary, fontFamily: fonts.textBold },
  item: { marginBottom: spacing.md },
  itemTop: { flexDirection: "row", justifyContent: "space-between", alignItems: "center", gap: 8 },
  name: { fontFamily: fonts.textBold, fontSize: 15, color: colors.onSurface, flexShrink: 1 },
  time: { fontFamily: fonts.textMed, fontSize: 12, color: colors.brandPrimary },
  meta: { color: colors.muted, fontSize: 12, marginTop: 3, fontFamily: fonts.text },
  empty: { color: colors.muted, textAlign: "center", marginTop: spacing.xl, fontFamily: fonts.text },
  err: { color: colors.error, textAlign: "center", fontFamily: fonts.textMed },
});
