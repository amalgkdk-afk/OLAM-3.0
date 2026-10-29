import { useEffect, useState } from "react";
import { View, Text, StyleSheet, Pressable, ScrollView, KeyboardAvoidingView, Platform } from "react-native";
import { BgScreen, panel } from "@/src/components/bg-screen";
import { useRouter } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { api, login, Role } from "@/src/api";
import { colors, fonts, radius, spacing } from "@/src/theme";
import { Eyebrow, Field, GoldButton, H1, TextInputPill } from "@/src/components/ui";

const ROLES: { key: Role; label: string; hint: string }[] = [
  { key: "coordinator", label: "Branch Coordinator", hint: "Approve students of your own branch" },
  { key: "scanner", label: "Gate Scanner", hint: "Scan passes at the entrance" },
  { key: "super_admin", label: "Admin", hint: "Full access to all branches" },
];

export default function StaffLogin() {
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const [role, setRole] = useState<Role | null>(null);
  const [branches, setBranches] = useState<{ id: string; name: string }[]>([]);
  const [branchId, setBranchId] = useState("");
  const [email, setEmail] = useState("");
  const [pw, setPw] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    api<{ id: string; name: string }[]>("/public/branches").then(setBranches).catch(() => {});
  }, []);

  async function submit() {
    setErr(null);
    if (!role) { setErr("Please choose how you are signing in."); return; }
    if (role === "coordinator" && !branchId) { setErr("Please choose your branch."); return; }
    if (!email.trim() || !pw) { setErr("Please enter your email and password."); return; }
    setBusy(true);
    try {
      const u = await login(email.trim(), pw, role, role === "coordinator" ? branchId : undefined);
      if (u.must_change_password) router.replace("/staff/change-password");
      else if (u.role === "scanner") router.replace("/staff/scanner");
      else router.replace("/staff/dashboard");
    } catch (e: any) { setErr(e.message); }
    finally { setBusy(false); }
  }

  return (
    <BgScreen>
    <KeyboardAvoidingView style={{ flex: 1 }} behavior={Platform.OS === "ios" ? "padding" : undefined}>
      <ScrollView keyboardShouldPersistTaps="handled" contentContainerStyle={{ padding: spacing.lg, paddingTop: insets.top + spacing.lg, paddingBottom: insets.bottom + spacing.xl, flexGrow: 1, justifyContent: "center" }}>
        <View style={panel}>
        <Pressable testID="login-home-btn" onPress={() => router.replace("/")} style={styles.backBtn}><Text style={styles.back}>← Home</Text></Pressable>
        <View style={{ marginTop: spacing.md }}>
          <Eyebrow>DELTA ACADEMY STAFF</Eyebrow>
          <H1>Sign in</H1>
          <Text style={styles.sub}>Choose your role. Coordinators can only approve students of their own branch.</Text>
        </View>
        <View style={{ marginTop: spacing.xl }}>
          <Field label="Sign in as">
            <View style={{ gap: 8 }}>
              {ROLES.map((r) => (
                <Pressable key={r.key} testID={`login-role-${r.key}`} onPress={() => { setRole(r.key); setErr(null); }} style={[styles.roleCard, role === r.key && styles.roleCardOn]}>
                  <View style={[styles.radio, role === r.key && styles.radioOn]}>{role === r.key ? <View style={styles.radioDot} /> : null}</View>
                  <View style={{ flex: 1 }}>
                    <Text style={styles.roleLabel}>{r.label}</Text>
                    <Text style={styles.roleHint}>{r.hint}</Text>
                  </View>
                </Pressable>
              ))}
            </View>
          </Field>
          {role === "coordinator" && (
            <Field label="Your branch">
              <View style={styles.chipRow}>
                {branches.map((b) => (
                  <Pressable key={b.id} testID={`login-branch-${b.id}`} onPress={() => { setBranchId(b.id); setErr(null); }} style={[styles.chip, branchId === b.id && styles.chipOn]}>
                    <Text style={[styles.chipTxt, branchId === b.id && styles.chipTxtOn]}>{b.name}</Text>
                  </Pressable>
                ))}
              </View>
            </Field>
          )}
          <Field label="Email">
            <TextInputPill testID="login-email-input" value={email} onChangeText={setEmail} autoCapitalize="none" keyboardType="email-address" placeholder="you@olam.delta" />
          </Field>
          <Field label="Password">
            <TextInputPill testID="login-password-input" value={pw} onChangeText={setPw} secureTextEntry placeholder="Your password" />
          </Field>
          {err ? <Text style={styles.err} testID="login-error">{err}</Text> : null}
          <GoldButton testID="login-submit-btn" label={busy ? "Signing in..." : "Sign in"} onPress={submit} loading={busy} />
        </View>
        </View>
      </ScrollView>
    </KeyboardAvoidingView>
    </BgScreen>
  );
}

const styles = StyleSheet.create({
  backBtn: { minHeight: 44, justifyContent: "center", alignSelf: "flex-start" },
  back: { color: colors.muted, fontFamily: fonts.textMed, fontSize: 14 },
  sub: { color: colors.muted, fontSize: 14, marginTop: 8, lineHeight: 20, fontFamily: fonts.text },
  err: { color: colors.error, marginBottom: spacing.md, fontFamily: fonts.textMed },
  roleCard: { flexDirection: "row", alignItems: "center", gap: spacing.md, padding: spacing.md, minHeight: 56, borderRadius: radius.md, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surfaceSecondary },
  roleCardOn: { borderColor: colors.brandSecondary, backgroundColor: colors.surfaceTertiary },
  radio: { width: 22, height: 22, borderRadius: 11, borderWidth: 2, borderColor: colors.border, alignItems: "center", justifyContent: "center" },
  radioOn: { borderColor: colors.brandSecondary },
  radioDot: { width: 10, height: 10, borderRadius: 5, backgroundColor: colors.brandSecondary },
  roleLabel: { fontFamily: fonts.textBold, fontSize: 14, color: colors.onSurface },
  roleHint: { fontFamily: fonts.text, fontSize: 12, color: colors.muted, marginTop: 2 },
  chipRow: { flexDirection: "row", flexWrap: "wrap", gap: 8 },
  chip: { minHeight: 44, paddingHorizontal: 16, justifyContent: "center", borderRadius: radius.pill, backgroundColor: colors.surfaceTertiary, borderWidth: 1, borderColor: colors.border },
  chipOn: { backgroundColor: colors.brandSecondary, borderColor: colors.brandSecondary },
  chipTxt: { fontFamily: fonts.textMed, fontSize: 13, color: colors.onSurface },
  chipTxtOn: { color: colors.onBrandSecondary },
});
