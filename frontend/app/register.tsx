import { useEffect, useState } from "react";
import { View, Text, ScrollView, StyleSheet, Pressable, KeyboardAvoidingView, Platform } from "react-native";
import { BgScreen, panel } from "@/src/components/bg-screen";
import { useRouter } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { api } from "@/src/api";
import { colors, fonts, radius, spacing } from "@/src/theme";
import { Eyebrow, Field, GoldButton, H1, TextInputPill } from "@/src/components/ui";

type Branch = { id: string; name: string };
type Batch = { id: string; name: string };

export default function Register() {
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const [branches, setBranches] = useState<Branch[]>([]);
  const [batches, setBatches] = useState<Batch[]>([]);
  const [form, setForm] = useState({ full_name: "", student_code: "", mobile: "", email: "", branch_id: "", batch: "", batch_no: "", faculty_name: "", confirm: false });
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    (async () => {
      try {
        const [b, bt] = await Promise.all([
          api<Branch[]>("/public/branches"),
          api<Batch[]>("/public/batches"),
        ]);
        setBranches(b);
        setBatches(bt);
      } catch (e: any) { setError(e.message); }
    })();
  }, []);

  const set = (k: string, v: any) => setForm((f) => ({ ...f, [k]: v }));

  async function submit() {
    setError(null);
    const labels: Record<string, string> = { full_name: "Full Name", student_code: "Student ID", mobile: "Mobile Number", email: "Email", branch_id: "Branch", batch: "Batch", batch_no: "Batch No.", faculty_name: "Faculty Name" };
    const missing = Object.keys(labels).filter((k) => !String((form as any)[k] ?? "").trim());
    if (missing.length) {
      setError(`Please fill in: ${missing.map((k) => labels[k]).join(", ")}.`);
      return;
    }
    if (!form.confirm) { setError("Please confirm your information is accurate."); return; }
    setSubmitting(true);
    try {
      const reg = await api<{ reference: string }>("/registrations", { method: "POST", body: JSON.stringify(form) });
      router.replace({ pathname: "/confirmation", params: { ref: reg.reference, email: form.email } });
    } catch (e: any) { setError(e.message); }
    finally { setSubmitting(false); }
  }

  return (
    <BgScreen>
    <KeyboardAvoidingView style={{ flex: 1 }} behavior={Platform.OS === "ios" ? "padding" : undefined}>
      <ScrollView contentContainerStyle={{ padding: spacing.lg, paddingTop: insets.top + spacing.lg, paddingBottom: 160 }} keyboardShouldPersistTaps="handled">
        <View style={panel}>
        <Pressable testID="register-back-btn" onPress={() => router.back()} style={styles.back}><Text style={styles.backTxt}>← Back</Text></Pressable>
        <Eyebrow>EVENT REGISTRATION</Eyebrow>
        <H1>Your invitation awaits</H1>
        <Text style={styles.sub}>Takes under two minutes. Approval comes from your branch coordinator.</Text>

        <View style={{ marginTop: spacing.xl }}>
          <Field label="Full Name">
            <TextInputPill testID="register-name-input" value={form.full_name} onChangeText={(v) => set("full_name", v)} placeholder="Enter your full name" />
          </Field>
          <Field label="Student ID / Admission No.">
            <TextInputPill testID="register-studentcode-input" value={form.student_code} onChangeText={(v) => set("student_code", v)} autoCapitalize="characters" placeholder="DA123456" />
          </Field>
          <Field label="Mobile Number">
            <TextInputPill testID="register-mobile-input" value={form.mobile} onChangeText={(v) => set("mobile", v)} keyboardType="phone-pad" placeholder="+91 9876543210" />
          </Field>
          <Field label="Email Address">
            <TextInputPill testID="register-email-input" value={form.email} onChangeText={(v) => set("email", v)} keyboardType="email-address" autoCapitalize="none" placeholder="you@example.com" />
          </Field>
          <Field label="Branch">
            <View style={styles.chipRow}>
              {branches.map((b) => (
                <Pressable key={b.id} testID={`register-branch-${b.id}`} onPress={() => set("branch_id", b.id)} style={[styles.chip, form.branch_id === b.id && styles.chipActive]}>
                  <Text style={[styles.chipTxt, form.branch_id === b.id && styles.chipTxtActive]}>{b.name}</Text>
                </Pressable>
              ))}
            </View>
          </Field>
          <Field label="Batch">
            <View style={styles.chipRow}>
              {batches.map((b) => (
                <Pressable key={b.id} testID={`register-batch-${b.id}`} onPress={() => set("batch", b.name)} style={[styles.chip, form.batch === b.name && styles.chipActive]}>
                  <Text style={[styles.chipTxt, form.batch === b.name && styles.chipTxtActive]}>{b.name}</Text>
                </Pressable>
              ))}
            </View>
          </Field>
          <Field label="Batch No.">
            <TextInputPill testID="register-batchno-input" value={form.batch_no} onChangeText={(v) => set("batch_no", v)} placeholder="Enter your batch number" autoCapitalize="characters" />
          </Field>
          <Field label="Faculty Name">
            <TextInputPill testID="register-faculty-input" value={form.faculty_name} onChangeText={(v) => set("faculty_name", v)} placeholder="Enter your faculty's name" autoCapitalize="words" />
          </Field>
          <Pressable testID="register-confirm-check" onPress={() => { set("confirm", !form.confirm); setError(null); }} style={styles.confirmRow}>
            <View style={[styles.cb, form.confirm && styles.cbOn]}>{form.confirm ? <Text style={{ color: colors.onBrandPrimary, fontWeight: "900" }}>✓</Text> : null}</View>
            <Text style={styles.confirmTxt}>I confirm the information I have provided is accurate and I am a current Delta Academy student.</Text>
          </Pressable>
        </View>
        </View>
      </ScrollView>
      <View style={[styles.ctaBar, { paddingBottom: insets.bottom + spacing.md }]}>
        {error ? <Text style={styles.ctaErr} testID="register-error">{error}</Text> : null}
        <GoldButton testID="register-submit-btn" label={submitting ? "Submitting..." : "Submit Registration"} onPress={submit} loading={submitting} />
      </View>
    </KeyboardAvoidingView>
    </BgScreen>
  );
}

const styles = StyleSheet.create({
  back: { marginBottom: spacing.md, minHeight: 44, justifyContent: "center", alignSelf: "flex-start" },
  backTxt: { color: colors.muted, fontFamily: fonts.textMed, fontSize: 14 },
  sub: { color: colors.muted, fontSize: 14, lineHeight: 20, marginTop: 8, fontFamily: fonts.text },
  chipRow: { flexDirection: "row", flexWrap: "wrap", gap: 8 },
  chip: { paddingHorizontal: 14, paddingVertical: 10, borderRadius: radius.pill, backgroundColor: colors.surfaceTertiary, borderWidth: 1, borderColor: colors.border },
  chipActive: { backgroundColor: colors.brandSecondary, borderColor: colors.brandSecondary },
  chipTxt: { color: colors.onSurface, fontSize: 13, fontFamily: fonts.textMed },
  chipTxtActive: { color: colors.onBrandSecondary },
  confirmRow: { flexDirection: "row", alignItems: "flex-start", marginTop: spacing.md, gap: 10 },
  cb: { width: 22, height: 22, borderRadius: 6, borderWidth: 1.5, borderColor: colors.borderStrong, alignItems: "center", justifyContent: "center", backgroundColor: colors.surfaceSecondary },
  cbOn: { backgroundColor: colors.brandPrimary, borderColor: colors.brandPrimary },
  confirmTxt: { color: colors.onSurface, flex: 1, fontSize: 13, lineHeight: 19, fontFamily: fonts.text },
  err: { color: colors.error, marginTop: spacing.md, fontFamily: fonts.textMed, fontSize: 13 },
  ctaErr: { color: "#FFFFFF", backgroundColor: colors.error, borderRadius: radius.md, overflow: "hidden", paddingHorizontal: spacing.md, paddingVertical: spacing.sm, marginBottom: spacing.md, fontFamily: fonts.textMed, fontSize: 13, textAlign: "center" },
  ctaBar: { position: "absolute", left: 0, right: 0, bottom: 0, padding: spacing.lg, backgroundColor: "rgba(0,0,0,0.85)", borderTopWidth: 1, borderTopColor: "rgba(212,175,55,0.5)" },
});
