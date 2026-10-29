import React from "react";
import { Pressable, Text, StyleSheet, ActivityIndicator, View, ViewStyle, StyleProp } from "react-native";
import { colors, radius, spacing, fonts } from "@/src/theme";

export function GoldButton({
  label,
  onPress,
  loading,
  disabled,
  variant = "primary",
  testID,
  style,
}: {
  label: string;
  onPress: () => void;
  loading?: boolean;
  disabled?: boolean;
  variant?: "primary" | "ghost" | "danger" | "navy";
  testID?: string;
  style?: StyleProp<ViewStyle>;
}) {
  const bg =
    variant === "primary" ? colors.brandPrimary :
    variant === "ghost" ? "transparent" :
    variant === "danger" ? colors.error :
    colors.brandSecondary;
  const fg =
    variant === "primary" ? colors.onBrandPrimary :
    variant === "ghost" ? colors.brandSecondary :
    variant === "danger" ? colors.onError :
    colors.onBrandSecondary;
  return (
    <Pressable
      testID={testID}
      disabled={disabled || loading}
      onPress={onPress}
      style={({ pressed }) => [
        styles.btn,
        { backgroundColor: bg, opacity: disabled ? 0.5 : pressed ? 0.9 : 1, borderWidth: variant === "ghost" ? 1 : 0, borderColor: colors.borderStrong },
        style,
      ]}
    >
      {loading ? <ActivityIndicator color={fg} /> : <Text style={[styles.lbl, { color: fg }]}>{label}</Text>}
    </Pressable>
  );
}

export function Field({ label, children, error, hint }: { label: string; children: React.ReactNode; error?: string; hint?: string }) {
  return (
    <View style={{ marginBottom: spacing.lg }}>
      <Text style={styles.fieldLabel}>{label}</Text>
      {children}
      {hint && !error ? <Text style={styles.hint}>{hint}</Text> : null}
      {error ? <Text style={styles.err}>{error}</Text> : null}
    </View>
  );
}

export function Card({ children, style }: { children: React.ReactNode; style?: StyleProp<ViewStyle> }) {
  return <View style={[styles.card, style]}>{children}</View>;
}

export function Pill({ label, tone = "info" }: { label: string; tone?: "info" | "success" | "warning" | "error" | "muted" }) {
  const map = {
    info: { bg: "#EEF2FF", fg: colors.info },
    success: { bg: "#DCFCE7", fg: colors.success },
    warning: { bg: "#FEF3C7", fg: "#92400E" },
    error: { bg: "#FEE2E2", fg: colors.error },
    muted: { bg: colors.surfaceTertiary, fg: colors.muted },
  }[tone];
  return (
    <View style={{ alignSelf: "flex-start", backgroundColor: map.bg, paddingVertical: 4, paddingHorizontal: 10, borderRadius: radius.pill }}>
      <Text style={{ color: map.fg, fontFamily: fonts.textBold, fontSize: 11, letterSpacing: 0.5 }}>{label.toUpperCase()}</Text>
    </View>
  );
}

export function Divider() {
  return <View style={styles.divider} />;
}

export function H1({ children }: { children: React.ReactNode }) {
  return <Text style={styles.h1}>{children}</Text>;
}
export function H2({ children }: { children: React.ReactNode }) {
  return <Text style={styles.h2}>{children}</Text>;
}
export function Eyebrow({ children }: { children: React.ReactNode }) {
  return <Text style={styles.eyebrow} numberOfLines={1}>{children}</Text>;
}

const styles = StyleSheet.create({
  btn: {
    height: 52,
    borderRadius: radius.pill,
    alignItems: "center",
    justifyContent: "center",
    paddingHorizontal: spacing.xl,
  },
  lbl: { fontSize: 15, fontFamily: fonts.textBold, letterSpacing: 0.3 },
  fieldLabel: { fontSize: 12, color: colors.muted, fontFamily: fonts.textMed, marginBottom: 6, letterSpacing: 0.4, textTransform: "uppercase" },
  hint: { fontSize: 12, color: colors.muted, marginTop: 4 },
  err: { fontSize: 12, color: colors.error, marginTop: 4 },
  card: { backgroundColor: colors.surfaceSecondary, borderRadius: radius.lg, padding: spacing.lg, borderWidth: 1, borderColor: colors.border, shadowColor: "#000", shadowOffset: { width: 0, height: 2 }, shadowOpacity: 0.04, shadowRadius: 8, elevation: 1 },
  divider: { height: 1, backgroundColor: colors.divider, marginVertical: spacing.md },
  h1: { fontSize: 32, fontFamily: fonts.display, color: colors.onSurface, letterSpacing: -0.5 },
  h2: { fontSize: 22, fontFamily: fonts.display, color: colors.onSurface },
  eyebrow: { fontSize: 10, letterSpacing: 4, color: colors.goldText, fontFamily: fonts.textBold, textTransform: "uppercase" },
});

export { colors, spacing, radius, fonts };

export function TextInputPill(props: React.ComponentProps<typeof import("react-native").TextInput>) {
  const { TextInput } = require("react-native");
  return (
    <TextInput
      placeholderTextColor={colors.muted}
      {...props}
      style={[
        {
          backgroundColor: colors.surfaceTertiary,
          borderRadius: radius.md,
          borderWidth: 1,
          borderColor: colors.border,
          paddingHorizontal: spacing.lg,
          paddingVertical: 14,
          fontSize: 15,
          color: colors.onSurface,
          fontFamily: fonts.text,
        },
        props.style,
      ]}
    />
  );
}
