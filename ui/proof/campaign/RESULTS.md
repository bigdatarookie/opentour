# Local campaign preview evidence

2026-11-09. Branch feat/fixture-campaign-preview; base e766cea54422d19b89ae85a706ddd28b5c8867af. Candidate commit is supplied by the native QA handoff; this document is included in that candidate.

Existing fixed r01 package is exposed through the same backend and UI. FIXTURE / PREVIEW-ONLY / NOT CONTENT-APPROVED / NOT SENT remain prominent. Audience unselected; recipient count unavailable; sender and provider ID absent. The source manifest is explicitly historical. No persistence or approval/send/reply control was added.

## Checks run by Developer

- node --check ui/app.js: exit 0.
- python3 -m unittest discover -s tests -p test_campaign_preview.py -v: 8 passed. Includes unchanged source bytes, snapshot/price caveats, inert preview transform, missing/tampered package fail-closed, arbitrary-path refusal, project authorization, public presentation-only CSS and POST refusal.
- python3 -m unittest discover -s tests -p test_backend.py -v: 21 passed. Existing HTTP/auth/project/scope, read projections, source errors and mutation refusal remain covered by synthetic adapters; no live source calls.
- python3 tools/campaign_preview_probe.py --proof-dir /private/tmp/opentour-campaign-proof: passed 12 checks: fixture labels; unselected audience; empty sandbox/no-referrer; absent sender/provider; frame opaque to application; unchanged text and manifest alternatives; mobile shell/dialog fit; visible mobile Close; no external requests; Escape focus return; disconnect cleanup.
- Desktop 1440×1000 and mobile 390×844 fixture screenshots inspected. Original email styling visibly renders; mobile email heading wraps within frame and Close remains reachable while detail scrolls. Long-title footer clipping found during verification was corrected in campaign-only dialog layout.
- git diff --check: clean.

The installed agent-browser cannot select the opaque srcdoc frame by CSS or URL. Child DOM/style/mobile overflow assertions are NOT RUN. Frame sandbox opacity is checked from the application, fixed source/transform safety by unit tests, and actual visible rendering by screenshots. This limitation is retained rather than granting origin/script permissions to make the harness pass.

The browser uses an ephemeral synthetic project-user grant and empty synthetic board in memory, plus its own temporary Chrome session/profile, all cleaned up. No owner profile, CRM records, private credential files, mailer/provider, source writes, recipients or native business actions were accessed. No live quote/inventory, manager identity, content approval, delivery, provider integration, full manager journey or slice acceptance is proven. Independent review remains pending. No push, merge, PR or deployment performed.

## Unchanged canonical source bytes

- draft-r01.md dba35fdb4f1e1243f6fc6064e9dc5d457df8df4eae041540ac14a37ab9129f6a
- email-preview-r01.html b29e27e535a316b1ccdf55d730e4c34246cf6a5d14000041c9791dcfe2754b95
- email-preview-r01.txt 01cccff52686c05e105dac1c26425f250b1a2d4420257c53aaf9ff7246c6e513
- email-r01.md 374d4817c7be40da033dc02f7ea7d3da16852b3b29ffd8830c56c968036f1216
- offer-r01.md 528c381ae09c60d52ccf8681fed86c23b55dc3702733bba56f9170a59501d354
