import { View, Text, StyleSheet, Pressable, ScrollView } from "react-native";
import { useLocalSearchParams, useRouter } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { colors, fonts, spacing } from "@/src/theme";
import { Card, Eyebrow, GoldButton, H1 } from "@/src/components/ui";
import { BgScreen, panel } from "@/src/components/bg-screen";

export default function Confirmation() {
  const { ref, email } = useLocalSearchParams<{ ref: string; email: string }>();
  const router = useRouter();
  const insets = useSafeAreaInsets();
  return (
    <BgScreen testID="confirmation-screen">
    <ScrollView contentContainerStyle={{ padding: spacing.lg, paddingTop: insets.top + spacing.xl, paddingBottom: insets.bottom + spacing.xl, flexGrow: 1, justifyContent: "center" }}>
      <View style={panel}>
        <Eyebrow>REGISTRATION RECEIVED</Eyebrow>
        <H1>Thank you.</H1>
        <Text style={styles.sub}>Your invitation request is being reviewed by your branch coordinator. You will receive your QR pass via email once approved.</Text>
        <Card style={{ marginTop: spacing.xl }}>
          <Text style={styles.label}>REGISTRATION REFERENCE</Text>
          <Text style={styles.ref} testID="confirmation-reference">{ref}</Text>
          <View style={styles.divider} />
          <Text style={styles.label}>EMAIL</Text>
          <Text style={styles.val}>{email}</Text>
          <Text style={styles.note}>Keep this reference safe. You will need it to retrieve your pass.</Text>
        </Card>
        <View style={{ marginTop: spacing.xl, gap: spacing.md }}>
          <GoldButton testID="confirmation-check-status-btn" label="Check Status / Retrieve Pass" onPress={() => router.replace({ pathname: "/my-pass", params: { ref, email } })} />
          <Pressable testID="confirmation-home-btn" onPress={() => router.replace("/")} style={{ minHeight: 44, justifyContent: "center" }}><Text style={styles.back}>Back to home</Text></Pressable>
        </View>
      </View>
    </ScrollView>
    </BgScreen>
  );
}

const styles = StyleSheet.create({
  wrap: { flex: 1, backgroundColor: colors.surface },
  sub: { color: colors.muted, fontSize: 15, lineHeight: 22, marginTop: spacing.md, fontFamily: fonts.text },
  label: { fontSize: 10, letterSpacing: 3, color: colors.goldText, fontFamily: fonts.textBold },
  ref: { fontSize: 28, color: colors.onSurface, letterSpacing: 2, fontFamily: fonts.display, marginTop: 4 },
  val: { fontSize: 15, color: colors.onSurface, marginTop: 4, fontFamily: fonts.textMed },
  divider: { height: 1, backgroundColor: colors.divider, marginVertical: spacing.md },
  note: { fontSize: 12, color: colors.muted, marginTop: spacing.md, fontFamily: fonts.text },
  back: { color: colors.muted, textAlign: "center", fontFamily: fonts.textMed, fontSize: 13 },
});
