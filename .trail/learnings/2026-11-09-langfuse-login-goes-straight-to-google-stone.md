---
title: "Langfuse login goes straight to Google, not through Cloudflare Access"
author: Stone
date: 2026-11-09
branch: chore/platform-hosting-check
id: l-d648fbf3
scope: repo
status: active
src: agent
touches:
  - docs/specs/platform.md
---

## Decided
Langfuse sign-in uses Langfuse's own Google provider. Access needs two registrations by the lead: a Google test user on the Langfuse OAuth app and a member of the Langfuse organization. The FastAPI address still sits behind Cloudflare Access.

## Tried and ruled out
- Cloudflare Access as the OIDC login for Langfuse: after the Zero Trust team was renamed, its token endpoint returned 500 for real login codes even with a correct client id and secret, so every login ended in OAuthCallback.
- Email/password signup: there is no mail server to verify addresses, so anyone could register an invited teammate's address first and inherit that invite.

## Watch out
- A teammate who can open the Google screen but gets "access blocked" is missing from the Google test users, not from Langfuse.
- Langfuse only logs "OAUTH_CALLBACK_ERROR" by default; the cause shows only with JSON log format.

In the code:
- docs/specs/platform.md (tracing section) describes the current access rule
- Redirect URI: https://kant-langfuse.zerocode-studio.com/api/auth/callback/google
