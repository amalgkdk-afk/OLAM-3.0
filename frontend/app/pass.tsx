import { useEffect, useState } from "react";
import { View, Text, StyleSheet, ScrollView, Pressable, ActivityIndicator } from "react-native";
import { useLocalSearchParams, useRouter } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { api } from "@/src/api";
import { colors, fonts, spacing } from "@/src/theme";
import { QRPassCard } from "@/src/components/qr-pass";

export default function PassScreen() {
  const { t, ref } = useLocalSearchParams<{ t: string; ref: string }>();
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const [data, setData] = useState<any>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    (async () => {
      try {
        const r = await api<any>(`/pass/verify/${encodeURIComponent(String(t))}`);
        setData(r.registration);
      } catch (e: any) { setErr(e.message); }
    })();
  }, [t]);

  return (
    <ScrollView style={{ flex: 1, backgroundColor: colors.surface }} contentContainerStyle={{ padding: spacing.lg, paddingTop: insets.top + spacing.lg, paddingBottom: insets.bottom + spacing.xl }}>
      <Pressable testID="pass-back-btn" onPress={() => router.back()}><Text style={styles.back}>← Back</Text></Pressable>
      {!data && !err && <ActivityIndicator color={colors.brandPrimary} style={{ marginTop: spacing["3xl"] }} />}
      {err && <Text style={styles.err} testID="pass-error">{err}</Text>}
      {data && (
        <View style={{ marginTop: spacing.xl }}>
          <QRPassCard token={String(t)} name={data.full_name} reference={data.reference} branch={data.branch_name} batch={data.batch} />
          <Text style={styles.footer}>Keep this screen ready at the entrance. Each pass admits one guest, one time.</Text>
        </View>
      )}
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  back: { color: colors.muted, marginBottom: spacing.md, fontFamily: fonts.textMed, fontSize: 14 },
  err: { color: colors.error, textAlign: "center", marginTop: spacing["3xl"], fontFamily: fonts.textMed },
  footer: { color: colors.muted, fontSize: 12, textAlign: "center", marginTop: spacing.lg, fontFamily: fonts.text, lineHeight: 18 },
});
