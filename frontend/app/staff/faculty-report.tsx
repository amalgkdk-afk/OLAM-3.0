import { useCallback, useEffect, useState } from "react";
import { View, Text, StyleSheet, ScrollView, Pressable, RefreshControl, ActivityIndicator } from "react-native";
import { useRouter } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { api, getUser, AuthUser } from "@/src/api";
import { colors, fonts, radius, spacing } from "@/src/theme";
import { Card, Eyebrow, GoldButton, H1 } from "@/src/components/ui";
import { downloadCsv } from "@/src/utils/csv";

type Row = { branch_id: string; branch_name: string; faculty_name: string; total: number; approved: number; pending: number; rejected: number; checked_in: number };

export default function FacultyReport() {
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const [user, setUser] = useState<AuthUser | null>(null);
  const [branches, setBranches] = useState<{ id: string; name: string }[]>([]);
  const [branchId, setBranchId] = useState("");
  const [data, setData] = useState<{ rows: Row[]; total_students: number; faculty_count: number } | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);

  const load = useCallback(async (bid: string) => {
    try { setData(await api(`/reports/faculty${bid ? `?branch_id=${bid}` : ""}`)); setMsg(null); }
    catch (e: any) { setMsg(e.message); }
    finally { setLoading(false); setRefreshing(false); }
  }, []);

  useEffect(() => {
    (async () => {
      const u = await getUser();
      if (!u || u.role === "scanner") { router.replace("/staff/login"); return; }
      const me = await api<AuthUser>("/auth/me").catch(() => u);
      setUser(me);
      if (me.role === "super_admin") setBranches(await api("/branches"));
      load("");
    })();
  }, [router, load]);

  const canExport = user?.role === "super_admin" || !!user?.can_export;
  // Group rows by branch for display
  const groups: Record<string, Row[]> = {};
  (data?.rows ?? []).forEach((r) => { (groups[r.branch_name] ||= []).push(r); });

  return (
    <View style={{ flex: 1, backgroundColor: colors.surface }}>
      <View style={[styles.header, { paddingTop: insets.top + spacing.sm }]}>
        <Pressable testID="faculty-back-btn" onPress={() => (router.canGoBack() ? router.back() : router.replace("/staff/dashboard"))} style={styles.back}>
          <Text style={styles.backTxt}>← Dashboard</Text>
        </Pressable>
        <Eyebrow>REPORTS</Eyebrow>
        <H1>Faculty report</H1>
        <Text style={styles.sub}>How many students each faculty member brought, branch by branch.</Text>
        {user?.role === "super_admin" && (
          <ScrollView horizontal showsHorizontalScrollIndicator={false} style={styles.chipScroll} contentContainerStyle={styles.chipRow}>
            {[{ id: "", name: "All branches" }, ...branches].map((b) => (
              <Pressable key={b.id || "all"} testID={`faculty-branch-${b.id || "all"}`} onPress={() => { setBranchId(b.id); setLoading(true); load(b.id); }} style={[styles.chip, branchId === b.id && styles.chipActive]}>
                <Text style={[styles.chipTxt, branchId === b.id && styles.chipTxtActive]}>{b.name}</Text>
              </Pressable>
            ))}
          </ScrollView>
        )}
      </View>

      <ScrollView
        contentContainerStyle={{ padding: spacing.lg, paddingBottom: insets.bottom + spacing.xl }}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={() => { setRefreshing(true); load(branchId); }} />}
      >
        {loading && <ActivityIndicator color={colors.brandPrimary} />}
        {!loading && data && (
          <>
            <View style={styles.summary}>
              <View style={styles.sumBox}><Text style={styles.sumVal} testID="faculty-count">{data.faculty_count}</Text><Text style={styles.sumLbl}>FACULTY</Text></View>
              <View style={styles.sumBox}><Text style={styles.sumVal} testID="faculty-students-total">{data.total_students}</Text><Text style={styles.sumLbl}>STUDENTS</Text></View>
            </View>
            {canExport ? (
              <GoldButton testID="faculty-export-btn" label="Download faculty CSV" variant="navy" onPress={async () => setMsg(await downloadCsv(`/export/faculty.csv${branchId ? `?branch_id=${branchId}` : ""}`, "olam-faculty-report.csv"))} style={{ marginBottom: spacing.lg }} />
            ) : (
              <Text style={styles.note} testID="faculty-export-disabled">CSV download is not enabled for your account. Ask the admin if you need it.</Text>
            )}
            {msg ? <Text style={styles.err} testID="faculty-msg">{msg}</Text> : null}
            {data.rows.length === 0 && <Text style={styles.empty}>No registrations with a faculty name yet.</Text>}
            {Object.entries(groups).map(([bname, rows]) => (
              <View key={bname} style={{ marginBottom: spacing.lg }}>
                <Text style={styles.branchTitle}>{bname}</Text>
                {rows.map((r) => (
                  <Card key={`${r.branch_id}-${r.faculty_name}`} style={styles.item}>
                    <View style={styles.itemTop}>
                      <Text style={styles.name} numberOfLines={1}>{r.faculty_name}</Text>
                      <Text style={styles.total}>{r.total}</Text>
                    </View>
                    <Text style={styles.meta}>
                      <Text style={{ color: colors.success }}>{r.approved} approved</Text> • <Text style={{ color: colors.warning }}>{r.pending} pending</Text> • <Text style={{ color: colors.error }}>{r.rejected} rejected</Text> • {r.checked_in} checked in
                    </Text>
                  </Card>
                ))}
              </View>
            ))}
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
  chipScroll: { marginTop: spacing.md, marginHorizontal: -spacing.lg, flexGrow: 0, height: 56 },
  chipRow: { gap: 8, paddingHorizontal: spacing.lg, alignItems: "center" },
  chip: { height: 44, paddingHorizontal: 16, justifyContent: "center", borderRadius: radius.pill, backgroundColor: colors.surfaceTertiary, borderWidth: 1, borderColor: colors.border, flexShrink: 0 },
  chipActive: { backgroundColor: colors.brandSecondary, borderColor: colors.brandSecondary },
  chipTxt: { fontSize: 12, color: colors.onSurface, fontFamily: fonts.textMed },
  chipTxtActive: { color: colors.onBrandSecondary },
  summary: { flexDirection: "row", gap: spacing.md, marginBottom: spacing.lg },
  sumBox: { flex: 1, backgroundColor: colors.surfaceSecondary, borderRadius: radius.md, borderWidth: 1, borderColor: colors.border, padding: spacing.md },
  sumVal: { fontFamily: fonts.display, fontSize: 32, color: colors.onSurface },
  sumLbl: { fontFamily: fonts.textBold, fontSize: 10, letterSpacing: 2, color: colors.muted },
  branchTitle: { fontFamily: fonts.textBold, fontSize: 12, letterSpacing: 2, color: colors.goldText, marginBottom: spacing.sm },
  item: { marginBottom: spacing.sm },
  itemTop: { flexDirection: "row", justifyContent: "space-between", alignItems: "center", gap: 8 },
  name: { fontFamily: fonts.textBold, fontSize: 15, color: colors.onSurface, flexShrink: 1 },
  total: { fontFamily: fonts.display, fontSize: 24, color: colors.onSurface },
  meta: { color: colors.muted, fontSize: 12, marginTop: 4, fontFamily: fonts.text },
  note: { color: colors.muted, fontSize: 12, textAlign: "center", marginBottom: spacing.lg, fontFamily: fonts.text },
  err: { color: colors.error, textAlign: "center", marginBottom: spacing.md, fontFamily: fonts.textMed },
  empty: { color: colors.muted, textAlign: "center", marginTop: spacing.xl, fontFamily: fonts.text },
});
