import { useEffect, useState } from "react";
import { View, Text, StyleSheet, ScrollView, Pressable } from "react-native";
import { useLocalSearchParams, useRouter } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { api } from "@/src/api";
import { colors, fonts, radius, spacing } from "@/src/theme";
import { Card, Eyebrow, Field, GoldButton, H1, Pill, TextInputPill } from "@/src/components/ui";

export default function Status() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const params = useLocalSearchParams<{ ref?: string; email?: string }>();
  const [ref, setRef] = useState(params.ref ?? "");
  const [email, setEmail] = useState(params.email ?? "");
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function lookup() {
    setLoading(true); setError(null); setData(null);
    try {
      const r = await api<any>("/registrations/lookup", { method: "POST", body: JSON.stringify({ reference: ref.trim(), email: email.trim() }) });
      setData(r);
    } catch (e: any) { setError(e.message); }
    finally { setLoading(false); }
  }

  useEffect(() => { if (params.ref && params.email) lookup(); /* eslint-disable-next-line */ }, []);

  const reg = data?.registration;
  const token = data?.pass_token;

  return (
    <ScrollView style={{ flex: 1, backgroundColor: colors.surface }} contentContainerStyle={{ padding: spacing.lg, paddingTop: insets.top + spacing.lg, paddingBottom: insets.bottom + spacing.xl }}>
      <Pressable onPress={() => router.replace("/")}><Text style={styles.back}>← Home</Text></Pressable>
      <Eyebrow>RETRIEVE YOUR INVITATION</Eyebrow>
      <H1>My Registration</H1>
      <Text style={styles.sub}>Enter the reference you received after registering and the email you used.</Text>

      <View style={{ marginTop: spacing.xl }}>
        <Field label="Registration Reference">
          <TextInputPill testID="status-ref-input" value={ref} onChangeText={setRef} autoCapitalize="characters" placeholder="OLM-XXXXXX" />
        </Field>
        <Field label="Email">
          <TextInputPill testID="status-email-input" value={email} onChangeText={setEmail} autoCapitalize="none" keyboardType="email-address" placeholder="you@example.com" />
        </Field>
        <GoldButton testID="status-lookup-btn" label={loading ? "Looking up..." : "Find my registration"} onPress={lookup} loading={loading} />
        {error ? <Text style={styles.err} testID="status-error">{error}</Text> : null}
      </View>

      {reg && (
        <Card style={{ marginTop: spacing.xl }}>
          <View style={{ flexDirection: "row", justifyContent: "space-between", alignItems: "center" }}>
            <Text style={styles.label}>STATUS</Text>
            <Pill label={reg.status} tone={reg.status === "approved" ? "success" : reg.status === "pending" ? "warning" : "error"} />
          </View>
          <Text style={styles.name}>{reg.full_name}</Text>
          <Text style={styles.meta}>{reg.branch_name} • {reg.batch}</Text>
          <Text style={styles.meta}>Ref: {reg.reference}</Text>
          {reg.status === "pending" && (
            <Text style={styles.helper}>Your branch coordinator is reviewing your details. Please check back soon.</Text>
          )}
          {reg.status === "rejected" && (
            <View>
              <Text style={styles.helper}>Your registration was not approved.</Text>
              {reg.rejection_reason ? <Text style={styles.helper}>Reason: {reg.rejection_reason}</Text> : null}
            </View>
          )}
          {reg.status === "approved" && token && (
            <GoldButton testID="status-view-pass-btn" label="View my digital pass" onPress={() => router.push({ pathname: "/pass", params: { ref: reg.reference, t: token } })} style={{ marginTop: spacing.lg }} />
          )}
        </Card>
      )}
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  back: { color: colors.muted, marginBottom: spacing.md, fontFamily: fonts.textMed, fontSize: 14 },
  sub: { color: colors.muted, fontSize: 14, marginTop: 8, fontFamily: fonts.text },
  label: { fontSize: 10, letterSpacing: 3, color: colors.brandPrimary, fontFamily: fonts.textBold },
  name: { fontSize: 22, fontFamily: fonts.display, color: colors.onSurface, marginTop: spacing.md },
  meta: { color: colors.muted, fontSize: 13, marginTop: 2, fontFamily: fonts.text },
  helper: { color: colors.onSurface, fontSize: 13, marginTop: spacing.md, fontFamily: fonts.text, lineHeight: 20 },
  err: { color: colors.error, marginTop: spacing.md, fontFamily: fonts.textMed, fontSize: 13 },
});
