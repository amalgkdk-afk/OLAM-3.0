import { View, Text, StyleSheet, Pressable } from "react-native";
import { useRouter } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { colors, fonts, radius, spacing } from "@/src/theme";
import { GoldButton } from "@/src/components/ui";
import { BgScreen } from "@/src/components/bg-screen";
import { LinearGradient } from "expo-linear-gradient";

export default function Landing() {
  const router = useRouter();
  const insets = useSafeAreaInsets();
  return (
    <BgScreen dim={0.15} testID="landing-screen">
      <View style={[styles.topRow, { paddingTop: insets.top + spacing.sm }]}>
        <Pressable testID="landing-staff-login-btn" onPress={() => router.push("/staff/login")} style={styles.staffBtn}>
          <Text style={styles.staffBtnText}>Staff Sign In</Text>
        </Pressable>
      </View>

      <View style={{ flex: 1 }} />

      <LinearGradient colors={["rgba(0,0,0,0)", "rgba(0,0,0,0.72)"]} style={{ height: 80, marginBottom: -1 }} pointerEvents="none" />
      <View style={[styles.bottom, { paddingBottom: insets.bottom + spacing.lg }]}>
        <Text style={styles.eyebrow}>DELTA ACADEMY PRESENTS</Text>
        <Text style={styles.title}>OLAM 3.0</Text>
        <Text style={styles.tagline}>THE GRAND WEDDING</Text>
        <Text style={styles.sub}>Inter-branch arts festival · Register online and get your digital entry pass</Text>
        <GoldButton testID="landing-register-btn" label="Register as a Student" onPress={() => router.push("/register")} style={styles.cta} />
        <Pressable testID="landing-retrieve-btn" onPress={() => router.push("/my-pass")} style={styles.link}>
          <Text style={styles.linkText}>Already registered? Retrieve my pass</Text>
        </Pressable>
      </View>
    </BgScreen>
  );
}

const shadow = { textShadowColor: "rgba(0,0,0,0.9)", textShadowOffset: { width: 0, height: 1 }, textShadowRadius: 8 };

const styles = StyleSheet.create({
  topRow: { flexDirection: "row", justifyContent: "flex-end", paddingHorizontal: spacing.lg },
  staffBtn: { paddingHorizontal: spacing.lg, minHeight: 44, justifyContent: "center", borderRadius: radius.pill, borderWidth: 1, borderColor: "rgba(212,175,55,0.7)", backgroundColor: "rgba(0,0,0,0.55)" },
  staffBtnText: { color: colors.onSurfaceInverse, fontSize: 13, fontFamily: fonts.textMed },
  bottom: { paddingHorizontal: spacing.xl, paddingTop: spacing.lg, alignItems: "center", backgroundColor: "rgba(0,0,0,0.72)", width: "100%" },
  eyebrow: { color: colors.brandPrimary, letterSpacing: 4, fontSize: 11, fontFamily: fonts.textBold, textAlign: "center", ...shadow },
  title: { color: "#FFFFFF", fontFamily: fonts.display, fontSize: 52, lineHeight: 60, marginTop: spacing.xs, textAlign: "center", ...shadow },
  tagline: { color: colors.brandPrimary, letterSpacing: 6, fontSize: 13, fontFamily: fonts.textBold, textAlign: "center", ...shadow },
  sub: { color: "#FFFFFF", opacity: 0.9, fontSize: 14, lineHeight: 21, marginTop: spacing.md, maxWidth: 340, textAlign: "center", fontFamily: fonts.text, ...shadow },
  cta: { marginTop: spacing.xl, width: "100%", maxWidth: 420 },
  link: { minHeight: 44, justifyContent: "center", marginTop: spacing.xs },
  linkText: { color: colors.brandPrimary, fontFamily: fonts.textMed, fontSize: 14, textAlign: "center" },
});
