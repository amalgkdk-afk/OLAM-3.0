import { useState } from "react";
import { View, Text, StyleSheet, Pressable, ScrollView, KeyboardAvoidingView, Platform } from "react-native";
import { BgScreen, panel } from "@/src/components/bg-screen";
import { useRouter } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { login } from "@/src/api";
import { colors, fonts, spacing } from "@/src/theme";
import { Eyebrow, Field, GoldButton, H1, TextInputPill } from "@/src/components/ui";

export default function StaffLogin() {
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const [email, setEmail] = useState("");
  const [pw, setPw] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  async function submit() {
    setErr(null); setBusy(true);
    try {
      const u = await login(email.trim(), pw);
      if (u.role === "scanner") router.replace("/staff/scanner");
      else router.replace("/staff/dashboard");
    } catch (e: any) { setErr(e.message); }
    finally { setBusy(false); }
  }

  return (
    <BgScreen>
    <KeyboardAvoidingView style={{ flex: 1 }} behavior={Platform.OS === "ios" ? "padding" : undefined}>
      <ScrollView contentContainerStyle={{ padding: spacing.lg, paddingTop: insets.top + spacing.lg, flexGrow: 1, justifyContent: "center" }}>
        <View style={panel}>
        <Pressable onPress={() => router.replace("/")}><Text style={styles.back}>← Home</Text></Pressable>
        <View style={{ marginTop: spacing.xl }}>
          <Eyebrow>DELTA ACADEMY STAFF</Eyebrow>
          <H1>Sign in</H1>
          <Text style={styles.sub}>Admin, coordinator and scanner access.</Text>
        </View>
        <View style={{ marginTop: spacing["2xl"] }}>
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
  back: { color: colors.muted, fontFamily: fonts.textMed, fontSize: 14 },
  sub: { color: colors.muted, fontSize: 14, marginTop: 8, fontFamily: fonts.text },
  err: { color: colors.error, marginBottom: spacing.md, fontFamily: fonts.textMed },
});
