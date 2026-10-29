import { useEffect, useState } from "react";
import { View, Text, StyleSheet, Pressable } from "react-native";
import { api } from "@/src/api";
import { useRouter } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { colors, fonts, radius, spacing } from "@/src/theme";
import { GoldButton } from "@/src/components/ui";
import { LinearGradient } from "expo-linear-gradient";
import { BgScreen } from "@/src/components/bg-screen";

export default function Landing() {
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const [open, setOpen] = useState<boolean | null>(null);
  useEffect(() => {
    api<{ registration_open: boolean }>("/public/settings").then((s) => setOpen(s.registration_open)).catch(() => setOpen(null));
  }, []);
  return (
    <BgScreen dim={0} testID="landing-screen">
      <View style={[styles.topRow, { paddingTop: insets.top + spacing.sm }]}>
        <Pressable testID="landing-staff-login-btn" onPress={() => router.push("/staff/login")} style={styles.staffBtn}>
          <Text style={styles.staffBtnText}>Staff Sign In</Text>
        </Pressable>
      </View>

      <View style={{ flex: 1 }} />

      {/* Fade into black so the titles read clearly over the full-screen artwork */}
      <LinearGradient
        colors={["rgba(0,0,0,0)", "rgba(0,0,0,0.75)", "rgba(0,0,0,0.95)"]}
        locations={[0, 0.3, 1]}
        style={[styles.bottom, { paddingBottom: insets.bottom + spacing.lg }]}
      >
        <Text style={styles.eyebrow}>DELTA ACADEMY PRESENTS</Text>
        <Text style={styles.title}>OLAM 3.0</Text>
        <Text style={styles.tagline}>THE GRAND WEDDING</Text>
        <Text style={styles.sub}>Inter-branch arts festival · Register online and get your digital entry pass</Text>
        <GoldButton testID="landing-register-btn" label={open === false ? "Registration closed" : "Register as a Student"} variant={open === false ? "navy" : "primary"} onPress={() => router.push("/register")} style={styles.cta} />
        <Pressable testID="landing-retrieve-btn" onPress={() => router.push("/my-pass")} style={styles.link}>
          <Text style={styles.linkText}>Already registered? Retrieve my pass</Text>
        </Pressable>
      </LinearGradient>
    </BgScreen>
  );
}

const shadow = { textShadowColor: "rgba(0,0,0,0.9)", textShadowOffset: { width: 0, height: 1 }, textShadowRadius: 8 };

const styles = StyleSheet.create({
  topRow: { flexDirection: "row", justifyContent: "flex-end", paddingHorizontal: spacing.lg },
  staffBtn: { paddingHorizontal: spacing.lg, minHeight: 44, justifyContent: "center", borderRadius: radius.pill, borderWidth: 1, borderColor: "rgba(212,175,55,0.7)", backgroundColor: "rgba(0,0,0,0.55)" },
  staffBtnText: { color: colors.onSurfaceInverse, fontSize: 13, fontFamily: fonts.textMed },
  bottom: { paddingHorizontal: spacing.xl, paddingTop: 48, alignItems: "center", width: "100%" },
  eyebrow: { color: colors.brandPrimary, letterSpacing: 4, fontSize: 11, fontFamily: fonts.textBold, textAlign: "center", ...shadow },
  title: { color: "#FFFFFF", fontFamily: fonts.display, fontSize: 52, lineHeight: 60, marginTop: spacing.xs, textAlign: "center", ...shadow },
  tagline: { color: colors.brandPrimary, letterSpacing: 6, fontSize: 13, fontFamily: fonts.textBold, textAlign: "center", ...shadow },
  sub: { color: "#FFFFFF", opacity: 0.9, fontSize: 14, lineHeight: 21, marginTop: spacing.md, maxWidth: 340, textAlign: "center", fontFamily: fonts.text, ...shadow },
  cta: { marginTop: spacing.xl, width: "100%", maxWidth: 420 },
  link: { minHeight: 44, justifyContent: "center", marginTop: spacing.xs },
  linkText: { color: colors.brandPrimary, fontFamily: fonts.textMed, fontSize: 14, textAlign: "center" },
});
