import { useEffect, useState } from "react";
import { Platform, Pressable, Text, StyleSheet, View } from "react-native";
import { colors, fonts, radius, spacing } from "@/src/theme";

/** Web only: offers "Add to Home Screen". Android/desktop Chrome get the native install prompt; iPhone gets instructions. */
export function InstallApp() {
  const [prompt, setPrompt] = useState<any>(null);
  const [showIosHelp, setShowIosHelp] = useState(false);
  const [installed, setInstalled] = useState(false);

  useEffect(() => {
    if (Platform.OS !== "web" || typeof window === "undefined") return;
    if (window.matchMedia?.("(display-mode: standalone)").matches || (navigator as any).standalone) setInstalled(true);
    const onPrompt = (e: any) => { e.preventDefault(); setPrompt(e); };
    const onInstalled = () => setInstalled(true);
    window.addEventListener("beforeinstallprompt", onPrompt);
    window.addEventListener("appinstalled", onInstalled);
    return () => {
      window.removeEventListener("beforeinstallprompt", onPrompt);
      window.removeEventListener("appinstalled", onInstalled);
    };
  }, []);

  if (Platform.OS !== "web" || installed || typeof navigator === "undefined") return null;
  const isIos = /iphone|ipad|ipod/i.test(navigator.userAgent) || (/macintosh/i.test(navigator.userAgent) && navigator.maxTouchPoints > 1);
  if (!prompt && !isIos) return null;

  return (
    <View style={styles.wrap}>
      <Pressable
        testID="install-app-btn"
        style={styles.btn}
        onPress={async () => {
          if (prompt) { prompt.prompt(); await prompt.userChoice.catch(() => null); setPrompt(null); }
          else setShowIosHelp((v) => !v);
        }}
      >
        <Text style={styles.btnTxt}>📲 Add OLAM 3.0 to your home screen</Text>
      </Pressable>
      {showIosHelp && (
        <Text style={styles.help} testID="install-ios-help">
          In Safari, tap the Share button (square with an arrow), then choose “Add to Home Screen”.
        </Text>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: { marginTop: spacing.md, alignItems: "center", width: "100%", maxWidth: 420 },
  btn: { minHeight: 44, paddingHorizontal: spacing.md, justifyContent: "center", borderRadius: radius.pill, borderWidth: 1, borderColor: colors.brandPrimary },
  btnTxt: { color: colors.brandPrimary, fontFamily: fonts.textMed, fontSize: 13 },
  help: { color: "#FFFFFF", opacity: 0.85, fontFamily: fonts.text, fontSize: 12, marginTop: spacing.sm, textAlign: "center" },
});
