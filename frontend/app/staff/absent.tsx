import { useCallback, useEffect, useRef, useState } from "react";
import { View, Text, StyleSheet, ScrollView, Pressable, RefreshControl, ActivityIndicator, Linking } from "react-native";
import { useRouter } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { api, getUser, AuthUser } from "@/src/api";
import { colors, fonts, radius, spacing } from "@/src/theme";
import { Card, Eyebrow, GoldButton, H1, TextInputPill } from "@/src/components/ui";
import { downloadCsv } from "@/src/utils/csv";

type Student = { id: string; reference: string; full_name: string; mobile: string; email: string; batch: string; batch_no?: string; faculty_name?: string };
type Data = { total: number; branches: { branch_name: string; count: number; students: Student[] }[] };

export default function Absent() {
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const [user, setUser] = useState<AuthUser | null>(null);
  const [branches, setBranches] = useState<{ id: string; name: string }[]>([]);
  const [branchId, setBranchId] = useState("");
  const [data, setData] = useState<Data | null>(null);
  const [q, setQ] = useState("");
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const latest = useRef("");

  const load = useCallback(async (bid: string) => {
    latest.current = bid;
    try {
      const d = await api<Data>(`/reports/absent${bid ? `?branch_id=${bid}` : ""}`);
      if (latest.current !== bid) return; // a newer branch was picked meanwhile
      setData(d); setMsg(null);
    }
    catch (e: any) { setMsg(e.message); }
    finally { setLoading(false); setRefreshing(false); }
  }, []);

  useEffect(() => {
    (async () => {
      const u = await getUser();
      if (!u) { router.replace("/staff/login"); return; }
      if (u.role === "scanner") { router.replace("/staff/scanner"); return; }
      const me = await api<AuthUser>("/auth/me").catch(() => u);
      setUser(me);
      if (me.role === "super_admin") setBranches(await api("/branches"));
      load("");
    })();
  }, [router, load]);

  const canExport = user?.role === "super_admin" || !!user?.can_export;
  const needle = q.trim().toLowerCase();
  const match = (s: Student) => !needle || [s.full_name, s.reference, s.mobile, s.batch, s.faculty_name].some((v) => v?.toLowerCase().includes(needle));

  return (
    <View style={{ flex: 1, backgroundColor: colors.surface }}>
      <View style={[styles.header, { paddingTop: insets.top + spacing.sm }]}>
        <Pressable testID="absent-back-btn" onPress={() => (router.canGoBack() ? router.back() : router.replace("/staff/dashboard"))} style={styles.back}>
          <Text style={styles.backTxt}>← Dashboard</Text>
        </Pressable>
        <Eyebrow>FOLLOW UP</Eyebrow>
        <H1>Not arrived yet</H1>
        <Text style={styles.sub}>Approved students who haven&apos;t checked in. Tap a number to call. Pull down to refresh.</Text>
        {user?.role === "super_admin" && (
          <ScrollView horizontal showsHorizontalScrollIndicator={false} style={styles.chipScroll} contentContainerStyle={styles.chipRow}>
            {[{ id: "", name: "All branches" }, ...branches].map((b) => (
              <Pressable key={b.id || "all"} testID={`absent-branch-${b.id || "all"}`} onPress={() => { setBranchId(b.id); setLoading(true); load(b.id); }} style={[styles.chip, branchId === b.id && styles.chipActive]}>
                <Text style={[styles.chipTxt, branchId === b.id && styles.chipTxtActive]}>{b.name}</Text>
              </Pressable>
            ))}
          </ScrollView>
        )}
      </View>

      <ScrollView
        keyboardShouldPersistTaps="handled"
        contentContainerStyle={{ padding: spacing.lg, paddingBottom: insets.bottom + spacing.xl }}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={() => { setRefreshing(true); load(branchId); }} />}
      >
        {loading && <ActivityIndicator color={colors.brandPrimary} />}
        {msg ? <Text style={styles.err} testID="absent-msg">{msg}</Text> : null}
        {!loading && data && (
          <>
            <View style={styles.sumBox}>
              <Text style={styles.sumVal} testID="absent-total">{data.total}</Text>
              <Text style={styles.sumLbl}>STUDENTS NOT ARRIVED</Text>
            </View>
            <TextInputPill testID="absent-search-input" value={q} onChangeText={setQ} placeholder="Search name, reference, mobile, batch" autoCorrect={false} style={{ marginTop: spacing.md }} />
            {canExport ? (
              <GoldButton testID="absent-export-btn" label="Download list (CSV)" variant="navy" onPress={async () => setMsg(await downloadCsv(`/export/absent.csv${branchId ? `?branch_id=${branchId}` : ""}`, "olam-absent-students.csv"))} style={{ marginVertical: spacing.md }} />
            ) : (
              <Text style={styles.note} testID="absent-export-disabled">CSV download is not enabled for your account.</Text>
            )}
            {data.total === 0 && <Text style={styles.empty} testID="absent-empty">Everyone approved has arrived. 🎉</Text>}
            {data.total > 0 && needle && !data.branches.some((g) => g.students.some(match)) && (
              <Text style={styles.empty} testID="absent-no-match">No students match “{q.trim()}”.</Text>
            )}
            {data.branches.map((g) => {
              const list = g.students.filter(match);
              if (!list.length) return null;
              return (
                <View key={g.branch_name} style={{ marginBottom: spacing.lg }} testID={`absent-group-${g.branch_name}`}>
                  <Text style={styles.branchTitle}>{g.branch_name} • {needle ? `${list.length} of ${g.count}` : g.count}</Text>
                  {list.map((s) => (
                    <Card key={s.id} style={styles.item}>
                      <View testID={`absent-student-${s.reference}`}>
                        <View style={styles.itemTop}>
                          <Text style={styles.name} numberOfLines={1}>{s.full_name}</Text>
                          <Text style={styles.ref}>{s.reference}</Text>
                        </View>
                        <Text style={styles.meta}>{s.batch}{s.batch_no ? ` • No. ${s.batch_no}` : ""}{s.faculty_name ? ` • ${s.faculty_name}` : ""}</Text>
                        <Pressable testID={`absent-call-${s.reference}`} onPress={() => Linking.openURL(`tel:${s.mobile}`)} style={styles.call}>
                          <Text style={styles.callTxt}>📞 {s.mobile}</Text>
                        </Pressable>
                      </View>
                    </Card>
                  ))}
                </View>
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
  sub: { color: colors.muted, fontSize: 13, marginTop: 4, fontFamily: fonts.text },
  chipScroll: { marginTop: spacing.md, marginHorizontal: -spacing.lg, flexGrow: 0, height: 56 },
  chipRow: { gap: 8, paddingHorizontal: spacing.lg, alignItems: "center" },
  chip: { height: 44, paddingHorizontal: 16, justifyContent: "center", borderRadius: radius.pill, backgroundColor: colors.surfaceTertiary, borderWidth: 1, borderColor: colors.border, flexShrink: 0 },
  chipActive: { backgroundColor: colors.brandSecondary, borderColor: colors.brandSecondary },
  chipTxt: { fontSize: 12, color: colors.onSurface, fontFamily: fonts.textMed },
  chipTxtActive: { color: colors.onBrandSecondary },
  sumBox: { backgroundColor: colors.surfaceSecondary, borderRadius: radius.md, borderWidth: 1, borderColor: colors.border, padding: spacing.md, alignItems: "center" },
  sumVal: { fontFamily: fonts.display, fontSize: 36, color: colors.error },
  sumLbl: { fontFamily: fonts.textBold, fontSize: 10, letterSpacing: 2, color: colors.muted },
  branchTitle: { fontFamily: fonts.textBold, fontSize: 12, letterSpacing: 2, color: colors.goldText, marginBottom: spacing.sm },
  item: { marginBottom: spacing.sm },
  itemTop: { flexDirection: "row", justifyContent: "space-between", alignItems: "center", gap: 8 },
  name: { fontFamily: fonts.textBold, fontSize: 15, color: colors.onSurface, flexShrink: 1 },
  ref: { fontFamily: fonts.textMed, fontSize: 12, color: colors.muted },
  meta: { color: colors.muted, fontSize: 12, marginTop: 4, fontFamily: fonts.text },
  call: { minHeight: 44, justifyContent: "center", alignSelf: "flex-start" },
  callTxt: { color: colors.goldText, fontFamily: fonts.textBold, fontSize: 14 },
  note: { color: colors.muted, fontSize: 12, textAlign: "center", marginVertical: spacing.md, fontFamily: fonts.text },
  err: { color: colors.error, textAlign: "center", marginBottom: spacing.md, fontFamily: fonts.textMed },
  empty: { color: colors.muted, textAlign: "center", marginTop: spacing.xl, fontFamily: fonts.text },
});
