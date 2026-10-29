import { useEffect, useState } from "react";
import { View, Text, StyleSheet, ScrollView, Pressable, Modal } from "react-native";
import { useRouter } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { api, getUser } from "@/src/api";
import { colors, fonts, radius, spacing } from "@/src/theme";
import { Card, Eyebrow, Field, GoldButton, H1, Pill, TextInputPill } from "@/src/components/ui";

type Staff = { id: string; email: string; name?: string; role: "super_admin" | "coordinator" | "scanner"; branch_id?: string | null; active: boolean; can_export?: boolean };
type Branch = { id: string; name: string };

export default function ManageStaff() {
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const [staff, setStaff] = useState<Staff[]>([]);
  const [branches, setBranches] = useState<Branch[]>([]);
  const [showAdd, setShowAdd] = useState(false);
  const [form, setForm] = useState({ email: "", name: "", password: "", role: "coordinator" as Staff["role"], branch_id: "" });
  const [err, setErr] = useState<string | null>(null);

  async function refresh() {
    try {
      const [s, b] = await Promise.all([api<Staff[]>("/staff"), api<Branch[]>("/branches")]);
      setStaff(s); setBranches(b);
    } catch (e: any) { if (/401/.test(e.message || "")) router.replace("/staff/login"); }
  }

  useEffect(() => {
    (async () => {
      const u = await getUser();
      if (!u || u.role !== "super_admin") { router.replace("/staff/login"); return; }
      refresh();
    })();
  }, []);

  async function toggleExport(s: Staff) {
    setStaff((list) => list.map((x) => (x.id === s.id ? { ...x, can_export: !s.can_export } : x)));
    try { await api(`/staff/${s.id}`, { method: "PATCH", body: JSON.stringify({ can_export: !s.can_export }) }); }
    catch { refresh(); }
  }

  async function createStaff() {
    setErr(null);
    try {
      const body: any = { ...form };
      if (!body.branch_id) delete body.branch_id;
      await api("/staff", { method: "POST", body: JSON.stringify(body) });
      setShowAdd(false);
      setForm({ email: "", name: "", password: "", role: "coordinator", branch_id: "" });
      refresh();
    } catch (e: any) { setErr(e.message); }
  }

  return (
    <View style={{ flex: 1, backgroundColor: colors.surface }}>
      <View style={[styles.header, { paddingTop: insets.top + spacing.md }]}>
        <Pressable onPress={() => router.back()}><Text style={styles.back}>← Back</Text></Pressable>
        <Eyebrow>STAFF MANAGEMENT</Eyebrow>
      </View>
      <ScrollView contentContainerStyle={{ padding: spacing.lg, paddingBottom: insets.bottom + spacing.xl }}>
        <H1>Accounts</H1>
        <GoldButton testID="staff-add-btn" label="+ Add Staff Account" onPress={() => setShowAdd(true)} style={{ marginTop: spacing.lg }} />
        {staff.map((s) => {
          const branch = branches.find((b) => b.id === s.branch_id);
          return (
            <Card key={s.id} style={{ marginTop: spacing.md }}>
              <View style={{ flexDirection: "row", justifyContent: "space-between", alignItems: "center" }}>
                <Text style={styles.name}>{s.name || s.email}</Text>
                <Pill label={s.role.replace("_", " ")} tone={s.role === "super_admin" ? "info" : s.role === "coordinator" ? "success" : "muted"} />
              </View>
              <Text style={styles.meta}>{s.email}</Text>
              {branch ? <Text style={styles.meta}>Branch: {branch.name}</Text> : null}
              <Text style={[styles.meta, { color: s.active ? colors.success : colors.error }]}>{s.active ? "Active" : "Inactive"}</Text>
              {s.role === "coordinator" && (
                <Pressable
                  testID={`staff-csv-toggle-${s.id}`}
                  onPress={() => toggleExport(s)}
                  style={[styles.csvRow, { borderColor: s.can_export ? colors.success : colors.border }]}
                >
                  <View style={{ flex: 1 }}>
                    <Text style={styles.csvTitle}>CSV download</Text>
                    <Text style={styles.meta}>{s.can_export ? "Allowed — can download their branch list" : "Not allowed"}</Text>
                  </View>
                  <View style={[styles.switch, s.can_export && styles.switchOn]}>
                    <View style={[styles.knob, s.can_export && styles.knobOn]} />
                  </View>
                </Pressable>
              )}
            </Card>
          );
        })}
      </ScrollView>

      <Modal visible={showAdd} transparent animationType="fade" onRequestClose={() => setShowAdd(false)}>
        <View style={styles.modalWrap}>
          <ScrollView contentContainerStyle={{ padding: spacing.lg }}>
            <View style={styles.modal}>
              <H1>Add staff</H1>
              <Field label="Name"><TextInputPill testID="staff-name-input" value={form.name} onChangeText={(v) => setForm({ ...form, name: v })} /></Field>
              <Field label="Email"><TextInputPill testID="staff-email-input" value={form.email} onChangeText={(v) => setForm({ ...form, email: v })} autoCapitalize="none" keyboardType="email-address" /></Field>
              <Field label="Password (min 8)"><TextInputPill testID="staff-password-input" value={form.password} onChangeText={(v) => setForm({ ...form, password: v })} secureTextEntry /></Field>
              <Field label="Role">
                <View style={{ flexDirection: "row", gap: 8 }}>
                  {(["super_admin", "coordinator", "scanner"] as const).map((r) => (
                    <Pressable key={r} testID={`staff-role-${r}`} onPress={() => setForm({ ...form, role: r })} style={[styles.roleChip, form.role === r && styles.roleChipActive]}>
                      <Text style={[styles.roleChipTxt, form.role === r && styles.roleChipTxtActive]}>{r.replace("_", " ")}</Text>
                    </Pressable>
                  ))}
                </View>
              </Field>
              {form.role === "coordinator" && (
                <Field label="Assigned branch">
                  <View style={{ flexDirection: "row", flexWrap: "wrap", gap: 8 }}>
                    {branches.map((b) => (
                      <Pressable key={b.id} testID={`staff-branch-${b.id}`} onPress={() => setForm({ ...form, branch_id: b.id })} style={[styles.roleChip, form.branch_id === b.id && styles.roleChipActive]}>
                        <Text style={[styles.roleChipTxt, form.branch_id === b.id && styles.roleChipTxtActive]}>{b.name}</Text>
                      </Pressable>
                    ))}
                  </View>
                </Field>
              )}
              {err ? <Text style={styles.err}>{err}</Text> : null}
              <View style={{ flexDirection: "row", gap: 8 }}>
                <GoldButton label="Cancel" variant="ghost" onPress={() => setShowAdd(false)} style={{ flex: 1 }} />
                <GoldButton testID="staff-save-btn" label="Create" onPress={createStaff} style={{ flex: 1 }} />
              </View>
            </View>
          </ScrollView>
        </View>
      </Modal>
    </View>
  );
}

const styles = StyleSheet.create({
  header: { paddingHorizontal: spacing.lg, paddingBottom: spacing.md, borderBottomWidth: 1, borderBottomColor: colors.border, gap: 4 },
  back: { color: colors.muted, fontFamily: fonts.textMed },
  name: { fontFamily: fonts.textBold, fontSize: 15, color: colors.onSurface },
  meta: { color: colors.muted, fontSize: 12, marginTop: 2, fontFamily: fonts.text },
  modalWrap: { flex: 1, backgroundColor: "rgba(11,25,44,0.6)", justifyContent: "center" },
  modal: { backgroundColor: colors.surfaceSecondary, borderRadius: radius.lg, padding: spacing.lg, borderWidth: 1, borderColor: colors.border },
  roleChip: { paddingHorizontal: 12, paddingVertical: 8, borderRadius: radius.pill, backgroundColor: colors.surfaceTertiary, borderWidth: 1, borderColor: colors.border },
  roleChipActive: { backgroundColor: colors.brandSecondary, borderColor: colors.brandSecondary },
  roleChipTxt: { fontSize: 12, color: colors.onSurface, fontFamily: fonts.textMed, textTransform: "capitalize" },
  roleChipTxtActive: { color: colors.onBrandSecondary },
  err: { color: colors.error, marginBottom: 8, fontFamily: fonts.textMed },
  csvRow: { flexDirection: "row", alignItems: "center", marginTop: spacing.md, padding: spacing.md, borderRadius: radius.md, borderWidth: 1, backgroundColor: colors.surfaceTertiary, minHeight: 56 },
  csvTitle: { fontFamily: fonts.textBold, fontSize: 13, color: colors.onSurface },
  switch: { width: 48, height: 28, borderRadius: 14, backgroundColor: colors.border, padding: 3, justifyContent: "center" },
  switchOn: { backgroundColor: colors.success },
  knob: { width: 22, height: 22, borderRadius: 11, backgroundColor: "#FFFFFF" },
  knobOn: { alignSelf: "flex-end" },
});
