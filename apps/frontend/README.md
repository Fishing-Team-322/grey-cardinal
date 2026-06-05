# Grey Cardinal Frontend

Production static Grey Cardinal frontend.

Run locally:

```bash
npm install
npm run build
npm run preview
```

The browser uses relative `/api` and `/ws/events` by default, so production
deployments should route those paths to `brain-api`. `window.GC_API_BASE_URL`
and `window.GC_WS_URL` may override this for local debugging.

Do not put production secrets into this client. The legacy internal-token field
is kept only for disposable local/dev internal screens; the main cockpit flow
uses public demo endpoints without `X-Internal-Token`.
