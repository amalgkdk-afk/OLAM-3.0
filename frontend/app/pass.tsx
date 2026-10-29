import { useEffect, useState } from "react";
import { View, Text, StyleSheet, ScrollView, Pressable, ActivityIndicator, Platform } from "react-native";
import { useLocalSearchParams, useRouter } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { api } from "@/src/api";
import { colors, fonts, spacing } from "@/src/theme";
import { QRPassCard } from "@/src/components/qr-pass";
import { GoldButton } from "@/src/components/ui";
import { savePassPdf } from "@/src/utils/print-pass";
import { BgScreen } from "@/src/components/bg-screen";

export default function PassScreen() {
  const { t } = useLocalSearchParams<{ t: string; ref: string }>();
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const [data, setData] = useState<any>(null);
  const [err, setErr] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [saveErr, setSaveErr] = useState<string | null>(null);

  useEffect(() => {
    (async () => {
      try {
        const r = await api<any>(`/pass/verify/${encodeURIComponent(String(t))}`);
        setData(r.registration);
      } catch (e: any) { setErr(e.message); }
    })();
  }, [t]);

  return (
    <BgScreen>
    <ScrollView style={{ flex: 1 }} contentContainerStyle={{ padding: spacing.lg, paddingTop: insets.top + spacing.lg, paddingBottom: insets.bottom + spacing.xl }}>
      <Pressable testID="pass-back-btn" onPress={() => (router.canGoBack() ? router.back() : router.replace("/my-pass"))} style={{ minHeight: 44, justifyContent: "center", alignSelf: "flex-start" }}><Text style={styles.back}>← Back</Text></Pressable>
      {!data && !err && <ActivityIndicator color={colors.brandPrimary} style={{ marginTop: spacing["3xl"] }} />}
      {err && <Text style={styles.err} testID="pass-error">{err}</Text>}
      {data && (
        <View style={{ marginTop: spacing.xl }}>
          <QRPassCard token={String(t)} name={data.full_name} reference={data.reference} branch={data.branch_name} batch={data.batch} />
          <GoldButton
            testID="pass-save-pdf-btn"
            label={Platform.OS === "web" ? "Print / Save as PDF" : "Save pass as PDF"}
            loading={saving}
            onPress={async () => {
              setSaving(true); setSaveErr(null);
              try { await savePassPdf({ token: String(t), name: data.full_name, reference: data.reference, branch: data.branch_name, batch: data.batch }); }
              catch (e: any) { setSaveErr(e?.message || "Could not create PDF"); }
              finally { setSaving(false); }
            }}
            style={{ marginTop: spacing.xl, alignSelf: "center", width: "100%", maxWidth: 380 }}
          />
          {saveErr ? <Text style={styles.err} testID="pass-save-error">{saveErr}</Text> : null}
          <Text style={styles.footer}>Save or print it so you can show it even without internet. Each pass admits one guest, one time.</Text>
        </View>
      )}
    </ScrollView>
    </BgScreen>
  );
}

const styles = StyleSheet.create({
  back: { color: "#FFFFFF", marginBottom: spacing.md, fontFamily: fonts.textMed, fontSize: 14 },
  err: { color: "#FFFFFF", backgroundColor: colors.error, padding: spacing.md, borderRadius: 12, overflow: "hidden", textAlign: "center", marginTop: spacing["3xl"], fontFamily: fonts.textMed },
  footer: { color: "#FFFFFF", opacity: 0.85, fontSize: 12, textAlign: "center", marginTop: spacing.lg, fontFamily: fonts.text, lineHeight: 18 },
});
