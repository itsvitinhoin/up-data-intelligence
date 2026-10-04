/** No persistent Firebase identity. ID token lives only in the exchange's local variable. */
import { initializeApp, getApps } from "firebase/app";
import {
  initializeAuth,
  type Auth,
  inMemoryPersistence,
  signInWithEmailAndPassword,
  createUserWithEmailAndPassword,
  sendEmailVerification,
  sendPasswordResetEmail,
  signOut,
} from "firebase/auth";
let clientAuth: Auth | undefined;
async function authentication() {
  const response = await fetch("/api/auth/config", { cache: "no-store" });
  if (!response.ok) throw new Error("authentication_configuration_unavailable");
  const config = await response.json();
  // Do not initialize Firebase's default local/IndexedDB persistence, even briefly.
  clientAuth ??= initializeAuth(getApps()[0] ?? initializeApp(config), {
    persistence: inMemoryPersistence,
  });
  return clientAuth;
}
export async function csrf() {
  const response = await fetch("/api/auth/csrf", { cache: "no-store" });
  if (!response.ok) throw new Error("csrf_unavailable");
  const value = await response.json();
  if (typeof value.data?.csrf_token !== "string")
    throw new Error("csrf_unavailable");
  return value.data.csrf_token as string;
}
export async function liveSignIn(email: string, password: string) {
  const auth = await authentication();
  try {
    const credential = await signInWithEmailAndPassword(auth, email, password);
    if (!credential.user.emailVerified) {
      await sendEmailVerification(credential.user);
      throw new Error("verified_email_required");
    }
    const id_token = await credential.user.getIdToken();
    const response = await fetch("/api/auth/session", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-UP-CSRF": await csrf(),
      },
      body: JSON.stringify({ id_token }),
    });
    if (!response.ok)
      throw new Error(
        response.status === 403
          ? "access_not_provisioned"
          : "session_exchange_failed",
      );
  } finally {
    await signOut(auth);
  }
}
export async function firstAccess(email: string, password: string) {
  const auth = await authentication();
  try {
    const credential = await createUserWithEmailAndPassword(
      auth,
      email,
      password,
    );
    await sendEmailVerification(credential.user);
  } finally {
    await signOut(auth);
  }
}
export async function resetPassword(email: string) {
  const auth = await authentication();
  try {
    await sendPasswordResetEmail(auth, email);
  } finally {
    await signOut(auth);
  }
}
export async function liveSignOut() {
  const response = await fetch("/api/auth/logout", {
    method: "POST",
    headers: { "X-UP-CSRF": await csrf() },
  });
  if (!response.ok) throw new Error("logout_failed");
}
