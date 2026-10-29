import { useEffect, useState } from "react";
import { View, Text, StyleSheet, ScrollView, Pressable, KeyboardAvoidingView, Platform, ActivityIndicator } from "react-native";
import { useRouter } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { api, getUser } from "@/src/api";
import { colors, fonts, radius, spacing } from "@/src/theme";
import { Card, Eyebrow, Field, GoldButton, H1, TextInputPill } from "@/src/components/ui";

type Settings = { registration_open: boolean; closed_message: string; privacy_notice: string; updated_at?: string; updated_by_name?: string; event_date?: string | null; event_time_venue?: string | null; auto_reminder?: boolean; auto_reminder_done_for?: string | null };

export default function EventSettings() {
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const [s, setS] = useState<Settings | null>(null);
  const [saved, setSaved] = useState<Settings | null>(null);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);
  const [rem, setRem] = useState<{ eligible: number; already_sent: number; pending: number; failed?: number; sending?: boolean } | null>(null);
  const [remMsg, setRemMsg] = useState<string | null>(null);
  const [remOk, setRemOk] = useState(true);
  const [sending, setSending] = useState(false);
  const [confirmSend, setConfirmSend] = useState(false);

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
      const r = await api<Settings>("/settings", { method: "PUT", body: JSON.stringify({ registration_open: next.registration_open, closed_message: next.closed_message, privacy_notice: next.privacy_notice, event_date: next.event_date?.trim() || null, event_time_venue: next.event_time_venue || null, auto_reminder: next.auto_reminder ?? true }) });
      setS(r);
      setSaved(r);
      loadReminder();
      setMsg({ ok: true, text: "Settings saved." });
    } catch (e: any) { setMsg({ ok: false, text: e.message === "Request failed" ? "Check: closed message ≥ 3 characters, privacy notice ≥ 20, event date as YYYY-MM-DD." : e.message }); }
    finally { setBusy(false); }
  }

  async function loadReminder() {
    try { setRem(await api("/reminders/status")); } catch {}
  }
  useEffect(() => {
    loadReminder();
    // Keep the status line fresh while on this page (also when sending started elsewhere).
    const t = setInterval(loadReminder, 10000);
    return () => clearInterval(t);
  }, []);

  async function sendNow() {
    setSending(true); setRemMsg(null); setRemOk(true);
    setRem((r) => (r ? { ...r, sending: true } : r));
    try {
      const r = await api<{ queued: number }>("/reminders/send", { method: "POST" });
      setRemMsg(r.queued ? `Sending ${r.queued} reminder emails… progress updates below.` : "Everyone eligible has already received a reminder.");
      // Poll progress until the background send finishes.
      let n = 0;
      const t = setInterval(async () => {
        n += 1;
        try {
          const st = await api<{ eligible: number; already_sent: number; pending: number; failed: number; sending: boolean; queued: number }>("/reminders/status");
          setRem(st);
          if (!st.sending) {
            clearInterval(t);
            setRemMsg(st.pending === 0 ? "All reminders delivered." : `${st.pending} not delivered yet${st.failed ? ` (${st.failed} failed)` : ""} — tap Send again to retry.`);
            setRemOk(st.pending === 0);
          } else if (n > 100) {
            clearInterval(t);
            setRemMsg(`Still sending in the background (${st.queued} left). The email provider allows only a few emails per minute — you can leave this page.`);
            setRemOk(true);
          }
        } catch { clearInterval(t); }
      }, 3000);
    } catch (e: any) { setRemMsg(e.message); }
    finally { setSending(false); setConfirmSend(false); }
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

            <Card style={{ marginTop: spacing.lg }}>
              <Text style={styles.title}>Pass reminder email</Text>
              <Text style={styles.help}>Approved students who have not entered yet get an email with their pass link. Each student receives it once per event date.</Text>
              <View style={{ marginTop: spacing.md }}>
                <Field label="Event date (YYYY-MM-DD)">
                  <TextInputPill testID="event-date-input" value={s.event_date ?? ""} onChangeText={(v) => setS({ ...s, event_date: v })} placeholder="2026-12-20" autoCapitalize="none" />
                </Field>
                <Field label="Time & venue (shown in the email)">
                  <TextInputPill testID="event-venue-input" value={s.event_time_venue ?? ""} onChangeText={(v) => setS({ ...s, event_time_venue: v })} placeholder="9:30 AM · Delta Academy Kaloor Auditorium" />
                </Field>
              </View>
              <Pressable testID="event-auto-reminder-toggle" onPress={() => setS({ ...s, auto_reminder: !(s.auto_reminder ?? true) })} style={styles.toggleRow}>
                <View style={{ flex: 1 }}>
                  <Text style={styles.title}>Send automatically the day before</Text>
                  <Text style={styles.help}>{s.auto_reminder_done_for ? `Automatic reminder already sent for ${s.auto_reminder_done_for}.` : "Goes out the day before the event date (India time)."}</Text>
                </View>
                <View style={[styles.switch, (s.auto_reminder ?? true) && styles.switchOn]}>
                  <View style={[styles.knob, (s.auto_reminder ?? true) && styles.knobOn]} />
                </View>
              </Pressable>
              <GoldButton testID="event-reminder-save-btn" label="Save reminder settings" variant="navy" loading={busy} onPress={() => save({ ...(saved ?? s), event_date: s.event_date, event_time_venue: s.event_time_venue, auto_reminder: s.auto_reminder ?? true })} style={{ marginTop: spacing.md }} />
              {rem ? <Text style={styles.help} testID="reminder-status">{rem.eligible} approved students not yet checked in • {rem.already_sent} reminded • {rem.pending} still to remind{rem.failed ? ` • ${rem.failed} failed` : ""}{rem.sending ? " • sending in background…" : ""}</Text> : null}
              {confirmSend ? (
                <View style={{ flexDirection: "row", gap: 8, marginTop: spacing.md }}>
                  <GoldButton testID="reminder-cancel-btn" label="Cancel" variant="ghost" onPress={() => setConfirmSend(false)} style={{ flex: 1, paddingHorizontal: 8 }} />
                  <GoldButton testID="reminder-confirm-btn" label={`Send ${rem?.pending ?? ""}`} loading={sending} onPress={sendNow} style={{ flex: 1, paddingHorizontal: 8 }} />
                </View>
              ) : (
                <GoldButton testID="reminder-send-now-btn" label="Send reminder now" onPress={() => setConfirmSend(true)} disabled={!rem || rem.pending === 0 || !!rem.sending} style={{ marginTop: spacing.md }} />
              )}
              {remMsg ? <Text style={[styles.msg, { color: remOk ? colors.success : colors.error }]} testID="reminder-msg">{remMsg}</Text> : null}
            </Card>
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
