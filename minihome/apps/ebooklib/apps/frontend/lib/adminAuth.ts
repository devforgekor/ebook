// Admin auth external store — avoids setState-in-effect and hydration mismatch.
// getServerSnapshot returns false so SSR/prerender show the login screen safely.
//
// 자격증명은 서버(/api/pipeline/auth)에서 검증한다. 클라이언트에 비밀번호를
// 하드코딩하지 않는다. 로그인 시 사용자가 입력한 비밀번호만 세션 동안 보관한다.

const listeners = new Set<() => void>();

export function subscribe(cb: () => void): () => void {
  listeners.add(cb);
  return () => {
    listeners.delete(cb);
  };
}

export function getSnapshot(): boolean {
  return typeof window !== "undefined" && sessionStorage.getItem("admin_auth") === "1";
}

export function getServerSnapshot(): boolean {
  return false;
}

export function getUsername(): string {
  if (typeof window === "undefined") return "";
  return sessionStorage.getItem("admin_user") || "";
}

export function getPassword(): string {
  if (typeof window === "undefined") return "";
  return sessionStorage.getItem("admin_pw") || "";
}

export function signIn(username: string, password: string): void {
  sessionStorage.setItem("admin_auth", "1");
  sessionStorage.setItem("admin_user", username);
  sessionStorage.setItem("admin_pw", password);
  listeners.forEach((l) => l());
}

export function signOut(): void {
  sessionStorage.removeItem("admin_auth");
  sessionStorage.removeItem("admin_user");
  sessionStorage.removeItem("admin_pw");
  listeners.forEach((l) => l());
}
