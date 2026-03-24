const CACHE_NAME = "healthcare-chatbot-cache-v7";

const URLS_TO_CACHE = [
    "/login",
    "/register",
    "/forgot-password",
    "/settings",
    "/medicine-reminder",
    "/appointments",
    "/static/style.css",
    "/static/theme.js",
    "/manifest.json"
];

self.addEventListener("install", (event) => {
    event.waitUntil(
        caches.open(CACHE_NAME).then((cache) => {
            return cache.addAll(URLS_TO_CACHE);
        })
    );
    self.skipWaiting();
});

self.addEventListener("activate", (event) => {
    event.waitUntil(
        caches.keys().then((keys) => {
            return Promise.all(
                keys.map((key) => {
                    if (key !== CACHE_NAME) {
                        return caches.delete(key);
                    }
                })
            );
        })
    );
    self.clients.claim();
});

self.addEventListener("fetch", (event) => {
    if (event.request.method !== "GET") {
        return;
    }

    const request = event.request;
    const accept = request.headers.get("accept") || "";
    const isHtml = request.mode === "navigate" || accept.includes("text/html");

    if (isHtml) {
        event.respondWith(
            fetch(request)
                .then((networkResponse) => {
                    const copy = networkResponse.clone();
                    caches.open(CACHE_NAME).then((cache) => cache.put(request, copy));
                    return networkResponse;
                })
                .catch(() => caches.match(request))
        );
        return;
    }

    event.respondWith(
        caches.match(request).then((cachedResponse) => {
            if (cachedResponse) return cachedResponse;
            return fetch(request).then((networkResponse) => {
                const copy = networkResponse.clone();
                caches.open(CACHE_NAME).then((cache) => cache.put(request, copy));
                return networkResponse;
            });
        })
    );
});

self.addEventListener("push", (event) => {
    let payload = {};

    if (event.data) {
        try {
            payload = event.data.json();
        } catch (error) {
            payload = { body: event.data.text() };
        }
    }

    const title = payload.title || "Healthcare Reminder";
    const body = payload.body || "You have a new reminder.";
    const icon = payload.icon || "/static/icons/icon-192.png";
    const badge = payload.badge || "/static/icons/icon-192.png";

    event.waitUntil(
        self.registration.showNotification(title, {
            body,
            icon,
            badge,
            tag: payload.tag || "healthcare-reminder",
            renotify: true,
            data: {
                url: payload.url || "/dashboard",
                speech: payload.speech || "",
                type: payload.type || "general"
            }
        })
    );
});

function buildTargetUrl(notificationData) {
    const basePath = notificationData.url || "/dashboard";
    const url = new URL(basePath, self.location.origin);

    if (notificationData.speech) {
        url.searchParams.set("push_speak", notificationData.speech);
    }
    if (notificationData.type) {
        url.searchParams.set("push_type", notificationData.type);
    }
    url.searchParams.set("from_push", "1");

    return url.toString();
}

self.addEventListener("notificationclick", (event) => {
    event.notification.close();

    const targetUrl = buildTargetUrl(event.notification.data || {});

    event.waitUntil(
        clients.matchAll({ type: "window", includeUncontrolled: true }).then((clientList) => {
            for (const client of clientList) {
                const clientUrl = new URL(client.url);
                const target = new URL(targetUrl);

                if (clientUrl.origin === target.origin && "focus" in client) {
                    if ("navigate" in client) {
                        return client.navigate(targetUrl).then(() => client.focus());
                    }
                    return client.focus();
                }
            }

            if (clients.openWindow) {
                return clients.openWindow(targetUrl);
            }
        })
    );
});
