// (test/live-notify) 라이브 알림 시험판 서비스 워커 — 서버가 보낸 푸시를 알림으로 띄우고, 누르면 방송 주소를 연다.
self.addEventListener("push", (e) => {
  const d = e.data ? e.data.json() : {};
  e.waitUntil(self.registration.showNotification(d.title || "라이브 알림", {
    body: d.body || "",
    icon: d.icon,
    tag: d.tag,
    data: { url: d.url },
  }));
});

self.addEventListener("notificationclick", (e) => {
  e.notification.close();
  const url = e.notification.data && e.notification.data.url;
  if (url) e.waitUntil(clients.openWindow(url));
});
