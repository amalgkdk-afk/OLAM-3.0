import { useEffect, useRef, useState, useCallback } from "react";
import { View, Text, StyleSheet, Pressable, ScrollView, Platform, Linking } from "react-native";
import { useRouter, useFocusEffect } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { CameraView, useCameraPermissions } from "expo-camera";
import * as Haptics from "expo-haptics";
import { useAudioPlayer, setAudioModeAsync } from "expo-audio";

const CHIME = require("../../assets/sounds/welcome-chime.wav");
import { api, clearSession, getUser, AuthUser } from "@/src/api";
import { colors, fonts, radius, spacing } from "@/src/theme";
import { Card, Eyebrow, Field, GoldButton, H1, Pill, TextInputPill } from "@/src/components/ui";

type ScanResult = {
  result: "VALID" | "ALREADY_CHECKED_IN" | "NOT_APPROVED" | "REVOKED" | "INVALID" | "ERROR";
  message: string;
  checked_in_at?: string;
  scanner_name?: string;
  registration?: { full_name: string; reference: string; batch: string; branch_name?: string };
};

export default function Scanner() {
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const [user, setUser] = useState<AuthUser | null>(null);
  const [perm, requestPerm] = useCameraPermissions();
  const [scanning, setScanning] = useState(true);
  const [result, setResult] = useState<ScanResult | null>(null);
  const [history, setHistory] = useState<any[]>([]);
  const [manual, setManual] = useState("");
  const [busy, setBusy] = useState(false);
  const lastScanRef = useRef<{ v: string; t: number }>({ v: "", t: 0 });
  const busyRef = useRef(false);
  const chime = useAudioPlayer(CHIME);

  useEffect(() => {
    // Let the chime play even when the iPhone is on silent.
    setAudioModeAsync({ playsInSilentMode: true }).catch(() => {});
  }, []);

  function playChime() {
    chime.seekTo(0).then(() => chime.play()).catch(() => {});
  }

  useFocusEffect(useCallback(() => {
    (async () => {
      const u = await getUser();
      if (!u) { router.replace("/staff/login"); return; }
      setUser(u);
      loadHistory();
    })();
  // eslint-disable-next-line
  }, []));

  async function loadHistory() {
    try { setHistory(await api<any[]>("/scan/history")); } catch {}
  }

  async function submitScan(token: string) {
    const t = token.trim();
    // Native cameras fire many callbacks per second; the ref blocks them before state updates land.
    if (!t || busyRef.current) return;
    const now = Date.now();
    if (lastScanRef.current.v === t && now - lastScanRef.current.t < 2500) return;
    lastScanRef.current = { v: t, t: now };
    busyRef.current = true;
    setBusy(true); setScanning(false);
    let r: ScanResult;
    try {
      r = await api<ScanResult>("/scan", { method: "POST", body: JSON.stringify({ token: t, station: Platform.OS }) });
      loadHistory();
    } catch (e: any) {
      r = { result: "ERROR", message: e.message || "Network error" };
    }
    setResult(r);
    setBusy(false);
    if (r.result === "VALID") playChime();
    if (Platform.OS !== "web") {
      Haptics.notificationAsync(
        r.result === "VALID" ? Haptics.NotificationFeedbackType.Success :
        r.result === "ALREADY_CHECKED_IN" ? Haptics.NotificationFeedbackType.Warning :
        Haptics.NotificationFeedbackType.Error,
      ).catch(() => {});
    }
  }

  function resume() {
    setResult(null); setManual("");
    busyRef.current = false;
    lastScanRef.current = { v: "", t: 0 };
    setTimeout(() => setScanning(true), 100);
  }

  const tone =
    result?.result === "VALID" ? colors.success :
    result?.result === "ALREADY_CHECKED_IN" ? colors.warning :
    result?.result === "ERROR" ? colors.info :
    colors.error;

  if (!user) return <View style={{ flex: 1, backgroundColor: colors.surfaceInverse }} />;

  return (
    <View style={{ flex: 1, backgroundColor: colors.surfaceInverse }}>
      <View style={[styles.header, { paddingTop: insets.top + spacing.md }]}>
        <View>
          <Eyebrow>OLAM 3.0 • SCANNER</Eyebrow>
          <Text style={styles.hello}>{user.name || user.email}</Text>
        </View>
        <View style={{ flexDirection: "row", gap: spacing.md }}>
          {user.role !== "scanner" && <Pressable testID="scanner-dashboard-btn" onPress={() => (router.canGoBack() ? router.back() : router.replace("/staff/dashboard"))}><Text style={styles.logout}>Dashboard</Text></Pressable>}
          <Pressable testID="scanner-logout-btn" onPress={async () => { await clearSession(); router.replace("/staff/login"); }}><Text style={styles.logout}>Sign out</Text></Pressable>
        </View>
      </View>

      {/* Camera / preview area */}
      <View style={[styles.camWrap, result && { height: 140 }]}>
        {!perm?.granted ? (
          <View style={styles.permWrap}>
            <Text style={styles.permTitle}>Camera permission needed</Text>
            <Text style={styles.permSub}>Allow camera access to scan entry QR passes.</Text>
            <GoldButton testID="scanner-request-perm-btn" label={perm?.canAskAgain === false ? "Open settings" : "Allow camera"} onPress={() => (perm?.canAskAgain === false ? Linking.openSettings() : requestPerm())} style={{ marginTop: spacing.lg }} />
          </View>
        ) : (
          <CameraView
            testID="scanner-camera-view"
            style={StyleSheet.absoluteFill}
            facing="back"
            barcodeScannerSettings={{ barcodeTypes: ["qr"] }}
            onBarcodeScanned={scanning ? ({ data }) => submitScan(data) : undefined}
          />
        )}
        {perm?.granted ? <View style={styles.viewfinder} pointerEvents="none" /> : null}
      </View>

      {/* Manual + result */}
      <ScrollView style={{ flex: 1 }} keyboardShouldPersistTaps="handled" contentContainerStyle={{ padding: spacing.lg, paddingBottom: insets.bottom + spacing.xl }}>
        {result?.result === "VALID" && result.registration ? (
          <View style={styles.welcomeCard} testID="scanner-welcome-card">
            <Text style={styles.welcomeEyebrow}>✦ ENTRY APPROVED ✦</Text>
            <Text style={styles.welcomeHello}>Welcome to OLAM 3.0,</Text>
            <Text style={styles.welcomeName} testID="scanner-welcome-name">{result.registration.full_name}</Text>
            <View style={styles.welcomeDivider} />
            <Text style={styles.welcomeBranch} testID="scanner-welcome-branch">{result.registration.branch_name}</Text>
            <Text style={styles.welcomeMeta}>{result.registration.batch} • {result.registration.reference}</Text>
            <Text style={styles.welcomeLine}>The Grand Wedding awaits you. Enjoy the celebration!</Text>
            {result.checked_in_at && <Text style={styles.welcomeMeta}>Checked in at {new Date(result.checked_in_at).toLocaleTimeString()}</Text>}
            <GoldButton testID="scanner-continue-btn" label="Scan next" onPress={resume} style={{ marginTop: spacing.lg, alignSelf: "stretch" }} />
          </View>
        ) : result ? (
          <View style={[styles.resultCard, { borderColor: tone }]} testID="scanner-result-card">
            <View style={[styles.resultBadge, { backgroundColor: tone }]}>
              <Text style={styles.resultBadgeTxt}>{result.result.replace(/_/g, " ")}</Text>
            </View>
            <Text style={styles.resultMsg}>{result.message}</Text>
            {result.registration && (
              <View style={{ marginTop: spacing.md }}>
                <Text style={styles.resultName}>{result.registration.full_name}</Text>
                <Text style={styles.resultMeta}>{result.registration.reference}</Text>
                <Text style={styles.resultMeta}>{result.registration.branch_name} • {result.registration.batch}</Text>
              </View>
            )}
            {result.checked_in_at && (
              <Text style={styles.resultMeta}>At {new Date(result.checked_in_at).toLocaleString()} {result.scanner_name ? `• by ${result.scanner_name}` : ""}</Text>
            )}
            <GoldButton testID="scanner-continue-btn" label="Scan next" onPress={resume} style={{ marginTop: spacing.lg }} />
          </View>
        ) : (
          <View>
            <Field label="Manual token / reference lookup">
              <View style={{ flexDirection: "row", gap: 8 }}>
                <TextInputPill testID="scanner-manual-input" value={manual} onChangeText={setManual} autoCapitalize="characters" autoCorrect={false} placeholder="Paste pass token or OLM-XXXXXX" style={{ flex: 1, minWidth: 0 }} />
                <GoldButton testID="scanner-manual-submit-btn" label="Check" onPress={() => submitScan(manual)} loading={busy} style={{ height: 50, paddingHorizontal: 16, flexShrink: 0 }} />
              </View>
            </Field>
          </View>
        )}

        <Text style={styles.sectionTitle}>Recent Check-ins</Text>
        {history.length === 0 && <Text style={styles.empty}>No scans yet.</Text>}
        {history.slice(0, 10).map((h) => (
          <Card key={h.id} style={{ marginTop: 8, backgroundColor: "rgba(253,251,247,0.08)", borderColor: "rgba(212,175,55,0.3)" }}>
            <View style={{ flexDirection: "row", justifyContent: "space-between" }}>
              <Text style={styles.histName}>{h.full_name}</Text>
              <Text style={styles.histTime}>{new Date(h.checked_in_at).toLocaleTimeString()}</Text>
            </View>
            <Text style={styles.histMeta}>{h.reference} • {h.branch_name} • {h.batch}</Text>
          </Card>
        ))}
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  header: { paddingHorizontal: spacing.lg, paddingBottom: spacing.md, flexDirection: "row", justifyContent: "space-between", alignItems: "flex-end", borderBottomWidth: 1, borderBottomColor: "rgba(212,175,55,0.2)" },
  hello: { fontFamily: fonts.display, fontSize: 20, color: colors.onSurfaceInverse, marginTop: 4 },
  logout: { color: colors.brandPrimary, fontFamily: fonts.textMed, fontSize: 13 },
  camWrap: { height: 320, backgroundColor: "#000", margin: spacing.lg, borderRadius: radius.lg, overflow: "hidden", borderWidth: 1, borderColor: colors.brandPrimary, alignItems: "center", justifyContent: "center" },
  viewfinder: { position: "absolute", width: 220, height: 220, borderWidth: 2, borderColor: colors.brandPrimary, borderRadius: radius.lg },
  permWrap: { padding: spacing.xl, alignItems: "center" },
  permTitle: { color: colors.onSurfaceInverse, fontFamily: fonts.display, fontSize: 20, textAlign: "center" },
  permSub: { color: colors.onSurfaceInverse, opacity: 0.7, textAlign: "center", marginTop: 8, fontFamily: fonts.text },
  welcomeCard: { backgroundColor: "rgba(212,175,55,0.12)", borderRadius: radius.lg, padding: spacing.xl, borderWidth: 2, borderColor: colors.brandPrimary, alignItems: "center" },
  welcomeEyebrow: { color: colors.success, fontFamily: fonts.textBold, fontSize: 12, letterSpacing: 3 },
  welcomeHello: { color: colors.onSurfaceInverse, fontFamily: fonts.text, fontSize: 15, marginTop: spacing.md, opacity: 0.85 },
  welcomeName: { color: colors.brandPrimary, fontFamily: fonts.display, fontSize: 32, textAlign: "center", marginTop: 4 },
  welcomeDivider: { width: 64, height: 1, backgroundColor: colors.brandPrimary, marginVertical: spacing.md },
  welcomeBranch: { color: colors.onSurfaceInverse, fontFamily: fonts.textBold, fontSize: 18, letterSpacing: 2, textAlign: "center" },
  welcomeMeta: { color: colors.onSurfaceInverse, opacity: 0.75, fontSize: 12, marginTop: 4, fontFamily: fonts.text, textAlign: "center" },
  welcomeLine: { color: colors.onSurfaceInverse, fontFamily: fonts.text, fontSize: 14, marginTop: spacing.md, textAlign: "center", fontStyle: "italic" },
  resultCard: { backgroundColor: "rgba(253,251,247,0.08)", borderRadius: radius.lg, padding: spacing.lg, borderWidth: 2 },
  resultBadge: { alignSelf: "flex-start", paddingHorizontal: 12, paddingVertical: 6, borderRadius: radius.pill },
  resultBadgeTxt: { color: "#FFFFFF", fontFamily: fonts.textBold, fontSize: 12, letterSpacing: 1 },
  resultMsg: { color: colors.onSurfaceInverse, fontFamily: fonts.text, marginTop: spacing.md, fontSize: 14 },
  resultName: { color: colors.onSurfaceInverse, fontFamily: fonts.display, fontSize: 24 },
  resultMeta: { color: colors.onSurfaceInverse, opacity: 0.75, fontSize: 12, marginTop: 4, fontFamily: fonts.text },
  sectionTitle: { color: colors.brandPrimary, letterSpacing: 3, fontSize: 11, fontFamily: fonts.textBold, marginTop: spacing.xl, marginBottom: spacing.sm },
  empty: { color: colors.onSurfaceInverse, opacity: 0.6, fontFamily: fonts.text },
  histName: { color: colors.onSurfaceInverse, fontFamily: fonts.textMed, fontSize: 14 },
  histMeta: { color: colors.onSurfaceInverse, opacity: 0.7, fontSize: 12, marginTop: 2, fontFamily: fonts.text },
  histTime: { color: colors.brandPrimary, fontSize: 12, fontFamily: fonts.textMed },
});
