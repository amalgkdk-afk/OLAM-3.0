import { useEffect, useState } from "react";
import { View, Text, StyleSheet, ScrollView, Pressable, KeyboardAvoidingView, Platform, ActivityIndicator } from "react-native";
import { useRouter } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { api, getUser } from "@/src/api";
import { colors, fonts, radius, spacing } from "@/src/theme";
import { Card, Eyebrow, Field, GoldButton, H1, TextInputPill } from "@/src/components/ui";

type Settings = { registration_open: boolean; closed_message: string; privacy_notice: string; updated_at?: string; updated_by_name?: string };

export default function EventSettings() {
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const [s, setS] = useState<Settings | null>(null);
  const [saved, setSaved] = useState<Settings | null>(null);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);

  useEffect(() => {
    (async () => {
      const u = await getUser();
      if (!u || u.role !== "super_admin") { router.replace("/staff/login"); return; }
      try { const r = await api<Settings>("/settings"); setS(r); setSaved(r); } catch (e: any) { setMsg({ ok: false, text: e.message }); }
    })();
  }, [router]);

  async function save(next: Settings) {
    setBusy(true); setMsg(null);
    try {
      const r = await api<Settings>("/settings", { method: "PUT", body: JSON.stringify({ registration_open: next.registration_open, closed_message: next.closed_message, privacy_notice: next.privacy_notice }) });
      setS(r);
      setSaved(r);
      setMsg({ ok: true, text: "Settings saved." });
    } catch (e: any) { setMsg({ ok: false, text: e.message === "Request failed" ? "Closed message needs at least 3 characters and privacy notice at least 20." : e.message }); }
    finally { setBusy(false); }
  }

  return (
    <KeyboardAvoidingView style={{ flex: 1, backgroundColor: colors.surface }} behavior={Platform.OS === "ios" ? "padding" : undefined}>
      <ScrollView keyboardShouldPersistTaps="handled" contentContainerStyle={{ padding: spacing.lg, paddingTop: insets.top + spacing.sm, paddingBottom: insets.bottom + spacing.xl }}>
        <Pressable testID="event-settings-back-btn" onPress={() => (router.canGoBack() ? router.back() : router.replace("/staff/dashboard"))} style={styles.back}>
          <Text style={styles.backTxt}>← Dashboard</Text>
        </Pressable>
        <Eyebrow>EVENT SETTINGS</Eyebrow>
        <H1>Registration</H1>
        {!s && !msg && <ActivityIndicator color={colors.brandPrimary} style={{ marginTop: spacing.xl }} />}
        {s && (
          <>
            <Card style={{ marginTop: spacing.lg }}>
              <Pressable testID="event-registration-toggle" disabled={busy} onPress={() => save({ ...(saved ?? s), registration_open: !s.registration_open })} style={styles.toggleRow}>
                <View style={{ flex: 1 }}>
                  <Text style={styles.title}>Student registration</Text>
                  <Text style={[styles.state, { color: s.registration_open ? colors.success : colors.error }]} testID="event-registration-state">
                    {s.registration_open ? "OPEN — students can register" : "CLOSED — new registrations blocked"}
                  </Text>
                </View>
                <View style={[styles.switch, s.registration_open && styles.switchOn]}>
                  <View style={[styles.knob, s.registration_open && styles.knobOn]} />
                </View>
              </Pressable>
              <Text style={styles.help}>Closing only stops new registrations. Approvals, passes and scanning keep working.</Text>
            </Card>

            <Card style={{ marginTop: spacing.lg }}>
              <Field label="Message shown when registration is closed">
                <TextInputPill testID="event-closed-message-input" value={s.closed_message} onChangeText={(v) => setS({ ...s, closed_message: v })} multiline style={{ minHeight: 70, textAlignVertical: "top" }} />
              </Field>
              <Field label="Privacy notice (students must accept before submitting)">
                <TextInputPill testID="event-privacy-input" value={s.privacy_notice} onChangeText={(v) => setS({ ...s, privacy_notice: v })} multiline style={{ minHeight: 140, textAlignVertical: "top" }} />
              </Field>
              <GoldButton testID="event-settings-save-btn" label="Save messages" loading={busy} onPress={() => save(s)} />
            </Card>
            {s.updated_at ? <Text style={styles.updated}>Last updated {new Date(s.updated_at).toLocaleString()} by {s.updated_by_name}</Text> : null}
          </>
        )}
        {msg ? <Text style={[styles.msg, { color: msg.ok ? colors.success : colors.error }]} testID="event-settings-msg">{msg.text}</Text> : null}
      </ScrollView>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  back: { minHeight: 44, justifyContent: "center", alignSelf: "flex-start" },
  backTxt: { color: colors.muted, fontFamily: fonts.textMed, fontSize: 14 },
  toggleRow: { flexDirection: "row", alignItems: "center", gap: spacing.md, minHeight: 56 },
  title: { fontFamily: fonts.textBold, fontSize: 15, color: colors.onSurface },
  state: { fontFamily: fonts.textBold, fontSize: 12, marginTop: 4 },
  help: { color: colors.muted, fontSize: 12, marginTop: spacing.md, fontFamily: fonts.text },
  switch: { width: 52, height: 30, borderRadius: 15, backgroundColor: colors.border, padding: 3, justifyContent: "center" },
  switchOn: { backgroundColor: colors.success },
  knob: { width: 24, height: 24, borderRadius: 12, backgroundColor: "#FFFFFF" },
  knobOn: { alignSelf: "flex-end" },
  updated: { color: colors.muted, fontSize: 11, textAlign: "center", marginTop: spacing.md, fontFamily: fonts.text },
  msg: { textAlign: "center", marginTop: spacing.md, fontFamily: fonts.textMed },
});
