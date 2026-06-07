# Spike: «Конспект встреч в Телемосте с Алисой Про»

**Status:** investigation only. **Not in MVP scope.** Do not build on this yet.

## Question
Yandex tariffs include "Конспект встреч в Телемосте с Алисой Про" (an AI meeting
summary produced by Yandex itself). Can Grey Cardinal pull that summary via a
public API instead of running its own ASR + summarization?

## Findings (as of this spike)
- The **public** Telemost API (`https://cloud-api.yandex.net/v1/telemost-api/...`)
  documents **conference lifecycle** only: create / read / update / delete a
  conference, manage access level and the waiting room. Scopes:
  `telemost-api:conferences.create|read|update`.
- There is **no documented public endpoint** that returns the Alice meeting
  summary / transcript ("конспект") for a conference. It is surfaced inside the
  Telemost UI / Yandex 360 products, not via the conferences API.
- Therefore, as of this spike, **we cannot fetch the Alice summary programmatically**
  through the OAuth scopes we have (or any documented public scope).

## Decision for MVP
- **Do not** depend on the Alice "конспект" feature.
- **Do not** scrape it via browser automation / headless login. That is brittle,
  violates expectations around automated access, and is explicitly out of scope.
- Grey Cardinal produces its own summary/tasks from audio it captures with the
  user's consent (the tray meeting agent → ASR → semantic parser → proposals),
  which is the existing, owned pipeline.

## If we revisit later
1. Re-check the official Telemost API changelog for a `summary` / `transcript`
   resource and the scope it requires.
2. Check whether Yandex 360 Admin API (separate product/scopes) exposes meeting
   artifacts for an organization.
3. Only integrate through an **official, documented** API with an explicit scope —
   never through UI scraping.

## Pointers
- Telemost API base: `https://cloud-api.yandex.net/v1/telemost-api/conferences`
- OAuth: `https://oauth.yandex.ru/authorize`, `https://oauth.yandex.ru/token`
- Our integration code: `apps/brain-api/src/brain_api/integrations/yandex_telemost.py`
