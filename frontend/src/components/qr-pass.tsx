import React from "react";
import { View, Text, StyleSheet, Platform } from "react-native";
import QRCodeSvgLib from "qrcode-svg";
import { SvgXml } from "react-native-svg";
import { colors, fonts, radius, spacing } from "@/src/theme";

export function QRPassCard({
  token,
  name,
  reference,
  branch,
  batch,
  size = 220,
}: {
  token: string;
  name: string;
  reference: string;
  branch: string;
  batch: string;
  size?: number;
}) {
  const svg = new QRCodeSvgLib({ content: token, padding: 2, width: size, height: size, color: "#0B192C", background: "#FFFFFF", ecl: "M" }).svg();
  return (
    <View style={styles.ticket} testID="qr-pass-card">
      <View style={styles.header}>
        <Text style={styles.eyebrow}>DELTA ACADEMY PRESENTS</Text>
        <Text style={styles.event}>OLAM 3.0</Text>
        <Text style={styles.tagline}>THE GRAND WEDDING</Text>
      </View>
      <View style={styles.perforation} />
      <View style={styles.qrWrap}>
        <View style={styles.qrInner}>
          <SvgXml xml={svg} width={size} height={size} />
        </View>
        <Text style={styles.ref}>{reference}</Text>
      </View>
      <View style={styles.footer}>
        <Row label="GUEST" value={name} />
        <Row label="BRANCH" value={branch} />
        <Row label="BATCH" value={batch} />
      </View>
      <Text style={styles.note}>Present this pass at the entrance. One scan per guest.</Text>
    </View>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <View style={styles.row}>
      <Text style={styles.rowLabel}>{label}</Text>
      <Text style={styles.rowVal} numberOfLines={1}>{value}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  ticket: {
    backgroundColor: colors.surfaceInverse,
    borderRadius: radius.lg,
    padding: spacing.xl,
    width: "100%",
    maxWidth: 380,
    alignSelf: "center",
    borderWidth: 1,
    borderColor: colors.brandPrimary,
    ...Platform.select({ web: { boxShadow: "0 10px 40px rgba(11,25,44,0.25)" } as any, default: { shadowColor: "#000", shadowOffset: { width: 0, height: 10 }, shadowOpacity: 0.25, shadowRadius: 20, elevation: 8 } }),
  },
  header: { alignItems: "center", paddingBottom: spacing.lg },
  eyebrow: { color: colors.brandPrimary, fontSize: 10, letterSpacing: 4, fontFamily: fonts.textBold },
  event: { color: colors.onSurfaceInverse, fontFamily: fonts.display, fontSize: 36, marginTop: 4 },
  tagline: { color: colors.onSurfaceInverse, letterSpacing: 6, fontSize: 11, fontFamily: fonts.textMed, marginTop: 2, opacity: 0.8 },
  perforation: { height: 1, backgroundColor: colors.brandPrimary, opacity: 0.4, marginVertical: spacing.md },
  qrWrap: { alignItems: "center", paddingVertical: spacing.md },
  qrInner: { backgroundColor: "#FFFFFF", padding: 14, borderRadius: radius.md },
  ref: { color: colors.brandPrimary, fontFamily: fonts.textBold, fontSize: 13, letterSpacing: 3, marginTop: spacing.md },
  footer: { marginTop: spacing.md, borderTopWidth: 1, borderTopColor: "rgba(212,175,55,0.2)", paddingTop: spacing.md, gap: 10 },
  row: { flexDirection: "row", justifyContent: "space-between", alignItems: "center" },
  rowLabel: { color: colors.brandPrimary, letterSpacing: 2, fontSize: 10, fontFamily: fonts.textBold },
  rowVal: { color: colors.onSurfaceInverse, fontSize: 14, fontFamily: fonts.textMed, maxWidth: "70%", textAlign: "right" },
  note: { color: colors.onSurfaceInverse, opacity: 0.6, fontSize: 11, textAlign: "center", marginTop: spacing.md, fontFamily: fonts.text },
});
