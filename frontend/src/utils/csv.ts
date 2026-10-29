import { Platform } from "react-native";
import { getPublicUrl, getToken } from "@/src/api";

/** Download an authenticated CSV. Web saves a file; native shows a helpful message via the returned string. */
export async function downloadCsv(path: string, filename: string): Promise<string | null> {
  if (Platform.OS !== "web") return "CSV download is available from the web dashboard on a computer.";
  const token = await getToken();
  const r = await fetch(`${getPublicUrl()}/api${path}`, { headers: { Authorization: `Bearer ${token}` } });
  if (!r.ok) return r.status === 403 ? "CSV download is not enabled for your account." : "Download failed. Please try again.";
  const blob = await r.blob();
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = filename;
  a.click();
  return null;
}
