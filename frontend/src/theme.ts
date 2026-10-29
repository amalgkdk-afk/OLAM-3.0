import { useMemo } from "react";
import { Appearance, StyleSheet, useColorScheme } from "react-native";

export type ColorScheme = "light" | "dark";

const light = {
  surface: "#FDFBF7",
  onSurface: "#0B192C",
  surfaceSecondary: "#FFFFFF",
  onSurfaceSecondary: "#0B192C",
  surfaceTertiary: "#F3EFE9",
  onSurfaceTertiary: "#0B192C",
  surfaceInverse: "#0B192C",
  onSurfaceInverse: "#FDFBF7",
  muted: "#5C6B82",

  brand: "#0B192C",
  onBrand: "#FDFBF7",
  brandPrimary: "#D4AF37",
  onBrandPrimary: "#0B192C",
  brandSecondary: "#0B192C",
  onBrandSecondary: "#FDFBF7",
  brandTertiary: "#E9DCC9",
  onBrandTertiary: "#0B192C",

  success: "#10B981",
  onSuccess: "#FFFFFF",
  warning: "#F59E0B",
  onWarning: "#FFFFFF",
  error: "#EF4444",
  onError: "#FFFFFF",
  info: "#3B82F6",
  onInfo: "#FFFFFF",

  border: "#E5E0D8",
  borderStrong: "#D4AF37",
  divider: "#E5E0D8",
};

export type ThemeColors = typeof light;
export const defaultScheme = "light" satisfies ColorScheme;
export const themes: { light: ThemeColors; dark?: ThemeColors } = { light };

export const colors = light;

export const spacing = { xs: 4, sm: 8, md: 12, lg: 16, xl: 24, "2xl": 32, "3xl": 48 };
export const radius = { sm: 6, md: 12, lg: 20, pill: 999 };
export const fonts = { display: "PlayfairDisplay_700Bold", displayReg: "PlayfairDisplay_400Regular", text: "Inter_400Regular", textBold: "Inter_700Bold", textMed: "Inter_500Medium" };

export function setColorScheme(scheme: ColorScheme | null) {
  Appearance.setColorScheme?.(scheme ?? "unspecified");
}
setColorScheme?.(themes.dark ? null : defaultScheme);

export function useTheme(): { scheme: ColorScheme; colors: ThemeColors } {
  const system = useColorScheme();
  const scheme: ColorScheme = (system === "light" || system === "dark") && themes[system] ? system : defaultScheme;
  return { scheme, colors: themes[scheme] ?? themes.light };
}

export function makeStyles<T extends StyleSheet.NamedStyles<T> | StyleSheet.NamedStyles<any>>(
  factory: (colors: ThemeColors) => T & StyleSheet.NamedStyles<any>,
): () => T {
  return function useStyles(): T {
    const { colors: c } = useTheme();
    return useMemo(() => StyleSheet.create(factory(c)), [c]);
  };
}
