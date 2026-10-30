import { Stack } from "expo-router";
import { View, StyleSheet, useWindowDimensions } from "react-native";
import { colors } from "@/src/theme";

/** On laptops/desktops, staff screens sit in a centred column instead of stretching edge to edge. Phones are unchanged. */
export default function StaffLayout() {
  const { width } = useWindowDimensions();
  const wide = width >= 900;
  return (
    <View style={[styles.outer, wide && styles.outerWide]}>
      <View style={[styles.inner, wide && styles.innerWide]}>
        <Stack screenOptions={{ headerShown: false, contentStyle: { backgroundColor: colors.surface } }} />
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  outer: { flex: 1 },
  outerWide: { backgroundColor: colors.surfaceInverse, alignItems: "center" },
  inner: { flex: 1, width: "100%" },
  innerWide: { maxWidth: 1120, borderLeftWidth: 1, borderRightWidth: 1, borderColor: colors.border, overflow: "hidden" },
});
