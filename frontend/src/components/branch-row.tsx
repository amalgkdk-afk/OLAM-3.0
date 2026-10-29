import { useState } from "react";
import { View, Text, Pressable, StyleSheet } from "react-native";
import { api } from "@/src/api";
import { colors, fonts, radius, spacing } from "@/src/theme";
import { GoldButton, TextInputPill } from "@/src/components/ui";

type Branch = { id: string; name: string; active: boolean };

export function BranchRow({ branch, onSaved }: { branch: Branch; onSaved: () => void }) {
  const [editing, setEditing] = useState(false);
  const [name, setName] = useState(branch.name);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  async function save(next: { name: string; active: boolean }) {
    setBusy(true); setErr(null);
    try {
      await api(`/branches/${branch.id}`, { method: "PATCH", body: JSON.stringify(next) });
      setEditing(false);
      onSaved();
    } catch (e: any) { setErr(e.message); }
    finally { setBusy(false); }
  }

  return (
    <View style={styles.row} testID={`branch-row-${branch.id}`}>
      {editing ? (
        <View style={{ flexDirection: "row", gap: 8, alignItems: "center" }}>
          <TextInputPill testID={`branch-name-input-${branch.id}`} value={name} onChangeText={setName} style={{ flex: 1, minWidth: 0 }} autoFocus />
          <GoldButton testID={`branch-save-btn-${branch.id}`} label="Save" loading={busy} onPress={() => name.trim() && save({ name: name.trim(), active: branch.active })} style={{ height: 48, paddingHorizontal: 16, flexShrink: 0 }} />
          <Pressable testID={`branch-cancel-btn-${branch.id}`} onPress={() => { setEditing(false); setErr(null); }} style={styles.smallBtn}>
            <Text style={styles.smallBtnTxt}>Cancel</Text>
          </Pressable>
        </View>
      ) : (
        <View style={{ flexDirection: "row", alignItems: "center", gap: 8 }}>
          <View style={{ flex: 1 }}>
            <Text style={[styles.name, !branch.active && { color: colors.muted }]}>{branch.name}</Text>
            <Text style={[styles.status, { color: branch.active ? colors.success : colors.error }]}>
              {branch.active ? "Open for registration" : "Switched off — hidden from form"}
            </Text>
          </View>
          <Pressable testID={`branch-edit-btn-${branch.id}`} onPress={() => { setName(branch.name); setEditing(true); }} style={styles.smallBtn}>
            <Text style={styles.smallBtnTxt}>Rename</Text>
          </Pressable>
          <Pressable
            testID={`branch-toggle-btn-${branch.id}`}
            disabled={busy}
            onPress={() => save({ name: branch.name, active: !branch.active })}
            style={[styles.smallBtn, branch.active ? styles.offBtn : styles.onBtn]}
          >
            <Text style={[styles.smallBtnTxt, { color: branch.active ? colors.error : colors.success }]}>{branch.active ? "Switch off" : "Switch on"}</Text>
          </Pressable>
        </View>
      )}
      {err ? <Text style={styles.err}>{err}</Text> : null}
    </View>
  );
}

const styles = StyleSheet.create({
  row: { paddingVertical: spacing.md, borderTopWidth: 1, borderTopColor: colors.divider },
  name: { fontFamily: fonts.textBold, fontSize: 14, color: colors.onSurface },
  status: { fontFamily: fonts.text, fontSize: 11, marginTop: 2 },
  smallBtn: { minHeight: 44, paddingHorizontal: 12, justifyContent: "center", borderRadius: radius.pill, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surfaceTertiary },
  offBtn: { borderColor: colors.error },
  onBtn: { borderColor: colors.success },
  smallBtnTxt: { fontFamily: fonts.textMed, fontSize: 12, color: colors.onSurface },
  err: { color: colors.error, fontSize: 12, marginTop: 4, fontFamily: fonts.text },
});
