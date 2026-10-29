import { View, Text, StyleSheet, Pressable, ScrollView, Platform } from "react-native";
import { useRouter } from "expo-router";
import { Image } from "expo-image";
import { LinearGradient } from "expo-linear-gradient";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { colors, fonts, radius, spacing } from "@/src/theme";
import { GoldButton } from "@/src/components/ui";

const HERO = "https://images.unsplash.com/photo-1780432478362-96fac052084a?crop=entropy&cs=srgb&fm=jpg&ixid=M3w3NDQ2NDF8MHwxfHNlYXJjaHwxfHxlbGVnYW50JTIwd2VkZGluZyUyMHJlY2VwdGlvbiUyMGNoYW1wYWduZSUyMGdvbGR8ZW58MHx8fHwxNzkzMjUwOTIyfDA&ixlib=rb-4.1.0&q=85";

export default function Landing() {
  const router = useRouter();
  const insets = useSafeAreaInsets();
  return (
    <View style={styles.wrap} testID="landing-screen">
      <Image source={{ uri: HERO }} style={StyleSheet.absoluteFill} contentFit="cover" transition={300} />
      <LinearGradient colors={["rgba(11,25,44,0.3)", "rgba(11,25,44,0.95)"]} style={StyleSheet.absoluteFill} />
      <View style={[styles.topRow, { paddingTop: insets.top + spacing.md }]}>
        <Text style={styles.brandMark}>DELTA ACADEMY</Text>
        <Pressable testID="landing-staff-login-btn" onPress={() => router.push("/staff/login")} style={styles.staffBtn}>
          <Text style={styles.staffBtnText}>Staff Sign In</Text>
        </Pressable>
      </View>
      <ScrollView contentContainerStyle={{ flexGrow: 1, justifyContent: "flex-end", padding: spacing.xl, paddingBottom: insets.bottom + 120 }}>
        <Text style={styles.eyebrow}>PRESENTS</Text>
        <Text style={styles.title}>OLAM 3.0</Text>
        <Text style={styles.tagline}>THE GRAND WEDDING</Text>
        <Text style={styles.sub}>An inter-branch arts festival. Pre-register online, get your digital invitation.</Text>
      </ScrollView>
      <View style={[styles.ctaBar, { paddingBottom: insets.bottom + spacing.lg }]}>
        <GoldButton testID="landing-register-btn" label="Register as a Student" onPress={() => router.push("/register")} />
        <Pressable testID="landing-retrieve-btn" onPress={() => router.push("/my-pass")} style={{ marginTop: spacing.sm, alignItems: "center", justifyContent: "center", minHeight: 44 }}>
          <Text style={styles.linkText}>Already registered?  Retrieve my pass</Text>
        </Pressable>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: { flex: 1, backgroundColor: colors.surfaceInverse },
  topRow: { position: "absolute", top: 0, left: 0, right: 0, flexDirection: "row", justifyContent: "space-between", alignItems: "center", paddingHorizontal: spacing.lg, zIndex: 2 },
  brandMark: { color: colors.brandPrimary, letterSpacing: 4, fontFamily: fonts.textBold, fontSize: 11, textShadowColor: "rgba(0,0,0,0.8)", textShadowRadius: 6 },
  staffBtn: { paddingHorizontal: spacing.lg, minHeight: 44, justifyContent: "center", borderRadius: radius.pill, borderWidth: 1, borderColor: "rgba(253,251,247,0.4)", backgroundColor: "rgba(11,25,44,0.4)" },
  staffBtnText: { color: colors.onSurfaceInverse, fontSize: 12, fontFamily: fonts.textMed },
  eyebrow: { color: colors.brandPrimary, letterSpacing: 6, fontSize: 11, fontFamily: fonts.textBold },
  title: { color: colors.onSurfaceInverse, fontFamily: fonts.display, fontSize: 72, letterSpacing: -1, marginTop: 4 },
  tagline: { color: colors.onSurfaceInverse, letterSpacing: 8, fontSize: 13, fontFamily: fonts.textMed, marginTop: 2, opacity: 0.85 },
  sub: { color: colors.onSurfaceInverse, opacity: 0.75, fontSize: 15, lineHeight: 22, marginTop: spacing.lg, maxWidth: 320, fontFamily: fonts.text },
  ctaBar: { position: "absolute", left: 0, right: 0, bottom: 0, padding: spacing.lg, backgroundColor: Platform.OS === "web" ? "rgba(11,25,44,0.6)" : "rgba(11,25,44,0.7)", borderTopWidth: 1, borderTopColor: "rgba(212,175,55,0.3)" },
  linkText: { color: colors.brandPrimary, fontFamily: fonts.textMed, fontSize: 13 },
});
