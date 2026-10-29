import React from "react";
import { View, StyleSheet } from "react-native";
import { Image } from "expo-image";
import { LinearGradient } from "expo-linear-gradient";
import { colors, radius, spacing } from "@/src/theme";

export const BG_IMAGE = require("../../assets/images/olam-bg.jpg");

/** Event artwork background. The poster is shown whole (never cropped at the edges); a blurred
 *  copy fills any empty space so every screen size looks intentional. */
export function BgScreen({ children, dim = 0.6, testID, showPoster = true }: { children: React.ReactNode; dim?: number; testID?: string; showPoster?: boolean }) {
  return (
    <View style={styles.root} testID={testID}>
      <Image source={BG_IMAGE} style={StyleSheet.absoluteFill} contentFit="cover" blurRadius={30} />
      <View style={[StyleSheet.absoluteFill, { backgroundColor: "rgba(0,0,0,0.55)" }]} />
      {showPoster ? <Image source={BG_IMAGE} style={StyleSheet.absoluteFill} contentFit="contain" contentPosition="top" transition={200} /> : null}
      {dim > 0 ? (
        <LinearGradient
          colors={[`rgba(0,0,0,${dim * 0.6})`, `rgba(0,0,0,${dim})`, `rgba(0,0,0,${Math.min(dim + 0.25, 0.97)})`]}
          style={StyleSheet.absoluteFill}
        />
      ) : null}
      {children}
    </View>
  );
}

/** Full poster, scaled to fit the given area without cropping. */
export function Poster({ testID }: { testID?: string }) {
  return <Image testID={testID} source={BG_IMAGE} style={{ flex: 1, width: "100%" }} contentFit="contain" contentPosition="center" transition={200} />;
}

/** Readable ivory panel that sits on top of the artwork, centered and width-capped for tablets/desktop. */
export const panel = {
  backgroundColor: "rgba(253,251,247,0.97)",
  borderRadius: radius.lg,
  padding: spacing.xl,
  width: "100%",
  maxWidth: 520,
  alignSelf: "center",
  borderWidth: 1,
  borderColor: colors.brandPrimary,
} as const;

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: "#000000" },
});
