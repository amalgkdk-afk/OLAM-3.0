import { Platform } from "react-native";
import AsyncStorage from "@react-native-async-storage/async-storage";
import * as SecureStore from "expo-secure-store";

const KEY = "olam3_token";
const USER_KEY = "olam3_user";

export type Role = "super_admin" | "coordinator" | "scanner" | "student";
export type AuthUser = { id: string; email: string; role: Role; name?: string; branch_id?: string | null; can_export?: boolean };

const API = process.env.EXPO_PUBLIC_BACKEND_URL as string;

async function setItem(k: string, v: string) {
  if (Platform.OS === "web") await AsyncStorage.setItem(k, v);
  else await SecureStore.setItemAsync(k, v);
}
async function getItem(k: string): Promise<string | null> {
  if (Platform.OS === "web") return AsyncStorage.getItem(k);
  return SecureStore.getItemAsync(k);
}
async function delItem(k: string) {
  if (Platform.OS === "web") await AsyncStorage.removeItem(k);
  else await SecureStore.deleteItemAsync(k);
}

export async function saveSession(token: string, user: AuthUser) {
  await setItem(KEY, token);
  await setItem(USER_KEY, JSON.stringify(user));
}

export async function getToken() {
  return getItem(KEY);
}
export async function getUser(): Promise<AuthUser | null> {
  const raw = await getItem(USER_KEY);
  return raw ? JSON.parse(raw) : null;
}
export async function clearSession() {
  await delItem(KEY);
  await delItem(USER_KEY);
}

export async function api<T = any>(path: string, init: RequestInit = {}): Promise<T> {
  const token = await getToken();
  const headers = new Headers(init.headers as any);
  if (!headers.has("Content-Type") && init.body) headers.set("Content-Type", "application/json");
  if (token) headers.set("Authorization", `Bearer ${token}`);
  const r = await fetch(`${API}/api${path}`, { ...init, headers });
  if (r.status === 401) await clearSession();
  const text = await r.text();
  let data: any = null;
  try { data = text ? JSON.parse(text) : null; } catch { data = text; }
  if (!r.ok) {
    const msg = typeof data === "object" && data?.detail ? data.detail : (typeof data === "string" ? data : `HTTP ${r.status}`);
    throw new Error(typeof msg === "string" ? msg : "Request failed");
  }
  return data as T;
}

export async function login(email: string, password: string) {
  const data = await api<{ access_token: string; user: AuthUser }>("/auth/login", {
    method: "POST",
    body: JSON.stringify({ email, password }),
  });
  await saveSession(data.access_token, data.user);
  return data.user;
}

export function getPublicUrl() {
  return API;
}
