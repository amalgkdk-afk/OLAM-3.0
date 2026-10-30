import { useEffect, useState } from "react";
import { View, Text, StyleSheet, ScrollView, Pressable, ActivityIndicator, Platform, Linking } from "react-native";
import { useLocalSearchParams, useRouter } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { api, getPublicUrl } from "@/src/api";
import { colors, fonts, spacing } from "@/src/theme";
import { QRPassCard } from "@/src/components/qr-pass";
import { GoldButton } from "@/src/components/ui";
import { savePassPdf } from "@/src/utils/print-pass";
import { BgScreen } from "@/src/components/bg-screen";
import { storage } from "@/src/utils/storage";

export default function PassScreen() {
  const { ref } = useLocalSearchParams<{ ref: string }>();
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const [data, setData] = useState<any>(null);
  const [t, setT] = useState<string>("");
  const [err, setErr] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [saveErr, setSaveErr] = useState<string | null>(null);

  useEffect(() => {
    (async () => {
      try {
        // Token is kept on this device only (never in the URL).
        const tok = await storage.getItem(`pass_${String(ref).replace(/[^A-Za-z0-9-]/g, "")}`, "");
        if (!tok) { setErr("Please open your pass from the My Registration page (reference + email)."); return; }
        const r = await api<any>("/pass/verify", { method: "POST", body: JSON.stringify({ token: tok }) });
        setT(String(tok));
        setData(r.registration);
      } catch (e: any) { setErr(e.message); }
    })();
  }, [ref]);

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
          <Pressable
            testID="pass-whatsapp-btn"
            accessibilityRole="button"
            onPress={() => {
              // Shares the reference + retrieve link only; the QR token never leaves this device.
              const base = Platform.OS === "web" && typeof window !== "undefined" ? window.location.origin : getPublicUrl();
              const link = `${base}/my-pass?ref=${encodeURIComponent(data.reference)}`;
              const msg = `🎉 I'm registered for OLAM 3.0 – The Grand Wedding!\n\nName: ${data.full_name}\nBranch: ${data.branch_name}\nReference: ${data.reference}\n\nOpen my pass (enter the registered email): ${link}`;
              Linking.openURL(`https://wa.me/?text=${encodeURIComponent(msg)}`).catch(() => setSaveErr("Couldn't open WhatsApp on this device."));
            }}
            style={styles.wa}
          >
            <Text style={styles.waTxt}>Share on WhatsApp</Text>
          </Pressable>
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
  // WhatsApp brand green stays the same in every theme.
  wa: { marginTop: spacing.md, alignSelf: "center", width: "100%", maxWidth: 380, height: 52, borderRadius: 999, backgroundColor: "#128C7E", alignItems: "center", justifyContent: "center" },
  waTxt: { color: "#FFFFFF", fontFamily: fonts.textBold, fontSize: 15 },
});
