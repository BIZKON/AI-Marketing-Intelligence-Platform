/**
 * Web Push notification helpers — subscribe, unsubscribe, and permission management.
 */

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "/api/v1";

export async function isPushSupported(): Promise<boolean> {
  return (
    typeof window !== "undefined" &&
    "serviceWorker" in navigator &&
    "PushManager" in window &&
    "Notification" in window
  );
}

export async function getPushPermission(): Promise<NotificationPermission> {
  if (!("Notification" in window)) return "denied";
  return Notification.permission;
}

export async function requestPushPermission(): Promise<NotificationPermission> {
  if (!("Notification" in window)) return "denied";
  return Notification.requestPermission();
}

export async function registerServiceWorker(): Promise<ServiceWorkerRegistration | null> {
  if (!("serviceWorker" in navigator)) return null;

  try {
    const registration = await navigator.serviceWorker.register("/sw.js", {
      scope: "/",
    });
    return registration;
  } catch (err) {
    console.error("SW registration failed:", err);
    return null;
  }
}

export async function subscribeToPush(token: string): Promise<boolean> {
  try {
    const registration = await registerServiceWorker();
    if (!registration) return false;

    const permission = await requestPushPermission();
    if (permission !== "granted") return false;

    // Get VAPID public key from backend
    const vapidRes = await fetch(`${API_BASE}/notifications/vapid-key`);
    if (!vapidRes.ok) return false;
    const { public_key: vapidPublicKey } = await vapidRes.json();
    if (!vapidPublicKey) return false;

    // Convert VAPID key to ArrayBuffer for pushManager.subscribe
    const keyBytes = urlBase64ToUint8Array(vapidPublicKey);
    const applicationServerKey = keyBytes.buffer as ArrayBuffer;

    const subscription = await registration.pushManager.subscribe({
      userVisibleOnly: true,
      applicationServerKey,
    });

    const json = subscription.toJSON();
    const keys = json.keys || {};

    // Send subscription to backend
    const res = await fetch(`${API_BASE}/notifications/subscribe`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${token}`,
      },
      body: JSON.stringify({
        endpoint: json.endpoint,
        p256dh_key: keys.p256dh || "",
        auth_key: keys.auth || "",
      }),
    });

    return res.ok;
  } catch (err) {
    console.error("Push subscription failed:", err);
    return false;
  }
}

export async function unsubscribeFromPush(token: string): Promise<boolean> {
  try {
    const registration = await navigator.serviceWorker.ready;
    const subscription = await registration.pushManager.getSubscription();
    if (!subscription) return true;

    const json = subscription.toJSON();

    // Notify backend
    await fetch(`${API_BASE}/notifications/unsubscribe`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${token}`,
      },
      body: JSON.stringify({
        endpoint: json.endpoint,
        p256dh_key: json.keys?.p256dh || "",
        auth_key: json.keys?.auth || "",
      }),
    });

    await subscription.unsubscribe();
    return true;
  } catch (err) {
    console.error("Push unsubscribe failed:", err);
    return false;
  }
}

function urlBase64ToUint8Array(base64String: string): Uint8Array {
  const padding = "=".repeat((4 - (base64String.length % 4)) % 4);
  const base64 = (base64String + padding).replace(/-/g, "+").replace(/_/g, "/");
  const rawData = window.atob(base64);
  const outputArray = new Uint8Array(rawData.length);
  for (let i = 0; i < rawData.length; ++i) {
    outputArray[i] = rawData.charCodeAt(i);
  }
  return outputArray;
}
