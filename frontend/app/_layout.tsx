import { QueryClientProvider } from "@tanstack/react-query";
import { Stack } from "expo-router";
import { useEffect, useState } from "react";
import { LogBox, StyleSheet, View, ActivityIndicator } from "react-native";
import { GestureHandlerRootView } from "react-native-gesture-handler";
import { KeyboardProvider } from "react-native-keyboard-controller";
import * as Font from "expo-font";
import { SafeAreaProvider } from "react-native-safe-area-context";

import { ErrorBoundary } from "@/src/components/error-boundary";
import { queryClient } from "@/src/query-client";
import { colors } from "@/src/theme";

LogBox.ignoreAllLogs(true);

export default function RootLayout() {
  const [ready, setReady] = useState(false);
  useEffect(() => {
    (async () => {
      try {
        await Font.loadAsync({
          PlayfairDisplay_700Bold: require("../assets/fonts/PlayfairDisplay_700Bold.ttf"),
          PlayfairDisplay_400Regular: require("../assets/fonts/PlayfairDisplay_400Regular.ttf"),
          Inter_400Regular: require("../assets/fonts/Inter_400Regular.ttf"),
          Inter_500Medium: require("../assets/fonts/Inter_500Medium.ttf"),
          Inter_700Bold: require("../assets/fonts/Inter_700Bold.ttf"),
        });
      } catch {}
      setReady(true);
    })();
  }, []);
  if (!ready) {
    return (
      <View style={[styles.root, { backgroundColor: colors.surface, alignItems: "center", justifyContent: "center" }]}>
        <ActivityIndicator color={colors.brandPrimary} />
      </View>
    );
  }
  return (
    <GestureHandlerRootView style={styles.root}>
      <SafeAreaProvider>
        <ErrorBoundary>
          <QueryClientProvider client={queryClient}>
            <KeyboardProvider>
              <Stack screenOptions={{ headerShown: false, contentStyle: { backgroundColor: colors.surface } }} />
            </KeyboardProvider>
          </QueryClientProvider>
        </ErrorBoundary>
      </SafeAreaProvider>
    </GestureHandlerRootView>
  );
}

const styles = StyleSheet.create({ root: { flex: 1 } });
