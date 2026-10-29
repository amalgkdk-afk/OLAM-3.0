import { useEffect, useState } from "react";
import { View, Text, StyleSheet, Pressable, ScrollView, KeyboardAvoidingView, Platform } from "react-native";
import { useRouter } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { api, clearSession, getUser, saveSession, getToken, AuthUser } from "@/src/api";
import { colors, fonts, spacing } from "@/src/theme";
import { Eyebrow, Field, GoldButton, H1, TextInputPill } from "@/src/components/ui";
import { BgScreen, panel } from "@/src/components/bg-screen";

export default function ChangePassword() {
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const [user, setUser] = useState<AuthUser | null>(null);
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [confirm, setConfirm] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [done, setDone] = useState(false);

  useEffect(() => {
    (async () => {
      const u = await getUser();
      if (!u) { router.replace("/staff/login"); return; }
      setUser(u);
    })();
  }, [router]);

  const forced = !!user?.must_change_password;
  const strong = next.length >= 10 && /[A-Za-z]/.test(next) && /\d/.test(next);

  async function submit() {
    setErr(null);
    if (!strong) { setErr("Use at least 10 characters with letters and numbers."); return; }
    if (next !== confirm) { setErr("The new passwords do not match."); return; }
    setBusy(true);
    try {
      await api("/auth/change-password", { method: "POST", body: JSON.stringify({ current_password: current, new_password: next }) });
      const token = await getToken();
      if (token && user) await saveSession(token, { ...user, must_change_password: false });
      setDone(true);
      setTimeout(() => router.replace(user?.role === "scanner" ? "/staff/scanner" : "/staff/dashboard"), 900);
    } catch (e: any) { setErr(e.message); }
    finally { setBusy(false); }
  }

  return (
    <BgScreen>
      <KeyboardAvoidingView style={{ flex: 1 }} behavior={Platform.OS === "ios" ? "padding" : undefined}>
        <ScrollView keyboardShouldPersistTaps="handled" contentContainerStyle={{ padding: spacing.lg, paddingTop: insets.top + spacing.lg, paddingBottom: insets.bottom + spacing.xl, flexGrow: 1, justifyContent: "center" }}>
          <View style={panel}>
            <Eyebrow>ACCOUNT SECURITY</Eyebrow>
            <H1>{forced ? "Set a new password" : "Change password"}</H1>
            <Text style={styles.sub}>
              {forced
                ? "For security, please replace the temporary password before using the dashboard."
                : "Choose a strong password you don't use anywhere else."}
            </Text>
            <View style={{ marginTop: spacing.xl }}>
              <Field label="Current password">
                <TextInputPill testID="chpw-current-input" value={current} onChangeText={setCurrent} secureTextEntry placeholder="Current password" />
              </Field>
              <Field label="New password" hint="At least 10 characters, with letters and numbers">
                <TextInputPill testID="chpw-new-input" value={next} onChangeText={setNext} secureTextEntry placeholder="New password" />
              </Field>
              <Field label="Confirm new password">
                <TextInputPill testID="chpw-confirm-input" value={confirm} onChangeText={setConfirm} secureTextEntry placeholder="Repeat new password" />
              </Field>
              {err ? <Text style={styles.err} testID="chpw-error">{err}</Text> : null}
              {done ? <Text style={styles.ok} testID="chpw-success">Password updated. Taking you in…</Text> : null}
              <GoldButton testID="chpw-submit-btn" label="Save new password" onPress={submit} loading={busy} disabled={done} />
              {forced ? (
                <Pressable testID="chpw-signout-btn" onPress={async () => { await clearSession(); router.replace("/staff/login"); }} style={styles.link}>
                  <Text style={styles.linkTxt}>Sign out</Text>
                </Pressable>
              ) : (
                <Pressable testID="chpw-cancel-btn" onPress={() => (router.canGoBack() ? router.back() : router.replace("/staff/dashboard"))} style={styles.link}>
                  <Text style={styles.linkTxt}>Cancel</Text>
                </Pressable>
              )}
            </View>
          </View>
        </ScrollView>
      </KeyboardAvoidingView>
    </BgScreen>
  );
}

const styles = StyleSheet.create({
  sub: { color: colors.muted, fontSize: 14, marginTop: 8, lineHeight: 20, fontFamily: fonts.text },
  err: { color: colors.error, marginBottom: spacing.md, fontFamily: fonts.textMed },
  ok: { color: colors.success, marginBottom: spacing.md, fontFamily: fonts.textMed },
  link: { minHeight: 44, justifyContent: "center", alignItems: "center", marginTop: spacing.sm },
  linkTxt: { color: colors.muted, fontFamily: fonts.textMed, fontSize: 14 },
});
