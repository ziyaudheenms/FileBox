## Asynchronous Notification System with Django Channels, Redis, and Celery

This PR implements a robust, asynchronous notification system using **Django Channels (ASGI)**, **Redis**, and **Celery**. It enables the backend to "push" status updates (e.g., ImageKit upload completion) directly to the frontend, eliminating the need for inefficient API polling.

---

### 🏗️ Architecture & Technical Decisions

- **Protocol Switch (WSGI to ASGI):** Migrated the server entry point to Daphne to support both standard HTTP and persistent WebSocket connections on a single port.
- **Stateful Consumers:** Implemented `FileNotifyConsumer` using `AsyncWebsocketConsumer`. This allows the server to handle high-concurrency connections without blocking the event loop.
- **Secure Multi-tenancy (Clerk Integration):** Developed a custom `ClerkAuthMiddleware` that intercepts the WebSocket handshake.
	- The middleware extracts the Clerk JWT from the query string and validates it via the Clerk SDK.
- **Data Isolation:** Users are dynamically assigned to private Channel Groups (`user_{id}`). This ensures that User A never receives notification data intended for User B.
- **Asynchronous Bridge:** Leveraged the Redis Channel Layer. When a background Celery task completes an image transformation, it broadcasts the result to the specific user's group, triggering the Consumer to push the final payload to the Next.js frontend.

---

### 🛠️ Backend Stack

- **Django Channels:** For WebSocket protocol handling.
- **Daphne:** ASGI HTTP/WebSocket server.
- **Redis:** As the backing store (Channel Layer) for inter-process communication.
- **Clerk SDK:** For JWT verification and secure session handling.
- **PyJWT/Dataclasses:** For custom middleware adapter patterns.

---

### 📡 Data Flow Summary

1. **Handshake:** Client connects to `ws/files/?token=<clerk_jwt>`.
2. **Auth:** `ClerkAuthMiddleware` verifies the token; `scope['user']` is populated.
3. **Subscription:** Consumer adds the connection to a unique `user_{id}` group.
4. **Task:** File upload is triggered; Celery processes the file in the background.
5. **Broadcast:** Celery sends a message to `user_{id}` via the Channel Layer.
6. **Push:** Consumer receives the event and sends a JSON payload to the client.