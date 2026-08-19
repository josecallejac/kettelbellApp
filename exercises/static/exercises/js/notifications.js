/**
 * KettleBell Pro - Push Notifications Module
 *
 * Usage:
 *   KBNotifications.init(vapidPublicKey)
 *   KBNotifications.toggle()  // subscribe or unsubscribe
 *   KBNotifications.getStatus()
 */

const KBNotifications = (function () {
  'use strict';

  let vapidKey = null;
  let swRegistration = null;
  const SUB_KEY = 'kb-push-subscribed';

  function urlBase64ToUint8Array(base64String) {
    const padding = '='.repeat((4 - (base64String.length % 4)) % 4);
    const base64 = (base64String + padding).replace(/-/g, '+').replace(/_/g, '/');
    const rawData = atob(base64);
    const arr = new Uint8Array(rawData.length);
    for (let i = 0; i < rawData.length; i++) arr[i] = rawData.charCodeAt(i);
    return arr;
  }

  function getCSRF() {
    const cookie = document.cookie.split(';').find(c => c.trim().startsWith('csrftoken='));
    return cookie ? cookie.split('=')[1] : '';
  }

  async function init(publicKey) {
    vapidKey = publicKey;

    if (!('serviceWorker' in navigator) || !('PushManager' in window)) {
      console.log('Push notifications not supported');
      return false;
    }

    try {
      swRegistration = await navigator.serviceWorker.ready;
      return true;
    } catch (e) {
      console.log('SW not ready:', e);
      return false;
    }
  }

  async function subscribe() {
    if (!swRegistration || !vapidKey) return null;

    const permission = await Notification.requestPermission();
    if (permission !== 'granted') {
      console.log('Notification permission denied');
      return null;
    }

    const subscription = await swRegistration.pushManager.subscribe({
      userVisibleOnly: true,
      applicationServerKey: urlBase64ToUint8Array(vapidKey),
    });

    const subJson = subscription.toJSON();

    const response = await fetch('/api/push-subscription/', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRFToken': getCSRF(),
      },
      body: JSON.stringify({
        endpoint: subJson.endpoint,
        keys: subJson.keys,
      }),
    });

    if (response.ok) {
      localStorage.setItem(SUB_KEY, '1');
      return subscription;
    }

    return null;
  }

  async function unsubscribe() {
    if (!swRegistration) return false;

    const subscription = await swRegistration.pushManager.getSubscription();
    if (!subscription) return false;

    const endpoint = subscription.endpoint;
    await subscription.unsubscribe();

    await fetch('/api/push-subscription/remove/', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRFToken': getCSRF(),
      },
      body: JSON.stringify({ endpoint }),
    });

    localStorage.removeItem(SUB_KEY);
    return true;
  }

  async function isSubscribed() {
    if (!swRegistration) return false;
    const subscription = await swRegistration.pushManager.getSubscription();
    return !!subscription;
  }

  async function toggle() {
    const subscribed = await isSubscribed();
    if (subscribed) {
      await unsubscribe();
      return false;
    } else {
      const sub = await subscribe();
      return !!sub;
    }
  }

  function getStatus() {
    if (!('Notification' in window)) return 'unsupported';
    if (Notification.permission === 'denied') return 'denied';
    if (localStorage.getItem(SUB_KEY)) return 'subscribed';
    return 'default';
  }

  return { init, subscribe, unsubscribe, toggle, isSubscribed, getStatus };
})();
