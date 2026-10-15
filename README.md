# Clinic Assistant

A website chatbot and a staff inbox agent for a dental clinic, built as a portfolio
project. The clinic, Brightside Dental, is made up; so are its prices, phone numbers
and staff.

Two parts work together:

- **Patient chatbot.** Answers questions about prices, hours, insurance and visits
  using only the clinic's own documents, and shows which document each answer came
  from. When the documents don't cover something, it says so and points to the front
  desk instead of guessing. Emergencies get a fixed "call 911" or "call us today"
  reply before any AI model is involved.
- **Inbox agent.** Messages from the website's contact form are sorted into categories
  (appointment, billing, complaint and so on), and a reply is drafted for each one. A
  person reviews, edits and approves every reply. Nothing is sent automatically.

![Chat widget answering a price question with a source](docs/screenshots/chat.png)

| Emergency handling | Staff inbox |
| --- | --- |
| ![Emergency reply in the chat](docs/screenshots/emergency.png) | ![Staff reviewing a drafted reply](docs/screenshots/staff.png) |
| **Clinic website** | **On a phone** |
| ![Clinic home page showing today's opening hours](docs/screenshots/home.png) | ![Chat widget on a phone](docs/screenshots/mobile-chat.png) |

The screenshots were taken with a scripted stand-in for the model, so the wording of
the answers is mine. Everything else on screen is the real app.

## How it works

```
Patient question
  -> safety rules (emergency, urgent, medication)   -> fixed reply, no model call
  -> BM25 search over the clinic documents           -> nothing relevant: handoff reply
  -> model answers from the top sections, with [n] citations
       -> model says NOT_COVERED                     -> handoff reply
  -> streamed to the browser over server-sent events

Contact form message
  -> stored in SQLite, triaged in the background
  -> safety rules mark urgent messages (the model can't)
  -> model returns category, priority, summary and a draft reply as JSON
  -> staff edit and approve, or close without replying
```

- **Backend:** Python, FastAPI, SQLite, httpx. The Gemini and Groq APIs are called
  over plain HTTP rather than through SDKs.
- **Frontend:** React, TypeScript, Vite and Tailwind. FastAPI serves the built files,
  so the whole app runs as one service.
- **Models:** Gemini by default, with Groq as an automatic fallback. If the first
  provider fails before it has sent any text, the second one answers. A failure in
  the middle of an answer is reported instead, so the patient never sees two
  half-answers joined together.

## Design decisions

- **Safety checks are plain rules, not AI.** Phrases like "bleeding won't stop" or
  "swelling spreading to my eye" trigger a fixed reply. The rules are deliberately
  broad: a false alarm costs a patient a few seconds, a missed emergency could cost
  much more. They are in `backend/app/safety.py` and covered by tests.
- **Two layers against made-up answers.** Questions that match nothing in the
  documents never reach the model. Questions that do reach it get a prompt that tells
  it to answer only from the provided sections, or reply `NOT_COVERED`. That marker is
  held back from the stream and replaced with a handoff message.
- **Prompt injection.** Documents and patient text are passed to the model as
  delimited data, and the prompts say to ignore instructions inside them. The design
  doesn't rely on that alone: model output is always shown as plain text, never as
  HTML; triage output must match a fixed JSON schema; only the rule-based check can
  mark a message urgent; and no reply goes out without a person approving it.
- **Retrieval is keyword-based (BM25).** It needs no model download and no API calls,
  which keeps the service small enough for a free host. The evaluation below shows
  where it falls short. Retrieval sits behind an interface so an embedding-based
  retriever can be added and compared.
- **Staff access** uses one shared bearer token, checked in constant time. Staff
  endpoints refuse to work until a token of at least 16 characters is set.
- **Abuse limits:** 20 chat requests per minute and 5 contact messages per hour per IP,
  length limits on every input, and a hidden form field that catches simple spam bots.
- **Browser security headers:** a strict Content-Security-Policy (the app only loads
  its own scripts, styles and fonts), `nosniff`, and no framing.

## Evaluation

`backend/eval` has 45 patient questions and 30 contact messages, written the way
patients would phrase them and labeled by hand. The offline run needs no API key:

```
cd backend
python -m eval.run_eval --show-misses
```

Offline results:

| Measure | Result |
| --- | --- |
| Safety questions given the right fixed reply | 6/6 (100%) |
| Answerable: right section ranked first | 24/34 (71%) |
| Answerable: right section in top 4 | 28/34 (82%) |
| Answerable but stopped by the retrieval threshold | 1/34 (3%) |
| Out-of-scope questions stopped before the model | 2/5 (40%) |
| Urgent contact messages caught by the safety rules | 4/4 (100%) |
| Non-urgent messages wrongly flagged urgent | 0/26 (0%) |

What the misses show:

- **Keyword search misses synonyms.** "Is the clinic wheelchair accessible?" doesn't
  match "step-free access with a lift". "Pay in installments" doesn't match "payment
  plan". "Invisalign" doesn't match "clear aligners". Embeddings or query expansion
  would fix these; I left the documents and test questions as they are rather than
  tuning one to fit the other.
- **Off-topic questions often pass the first filter.** "Who won the football game last
  night?" gets through because "last" matches "lasts about 45 minutes" in the first-visit
  section. Those questions rely on the model replying `NOT_COVERED`, which the online run
  measures.
- **The sets are small.** 45 questions and 30 messages are enough to catch regressions,
  not to prove accuracy on real traffic.

The online run also calls the model for every question and message (about 75 calls,
spaced out to respect free-tier rate limits):

```
python -m eval.run_eval --online --show-misses
```

## Running it locally

You need Python 3.10 or newer and Node.js 22.

1. **Get an API key.** A free Gemini key from [Google AI Studio](https://aistudio.google.com),
   a free Groq key from the [Groq console](https://console.groq.com), or both.
2. **Create your `.env`.** Copy `.env.example` to `.env` in the project root and fill in
   the key(s) and a staff token. To generate a token:
   ```
   python -c "import secrets; print(secrets.token_urlsafe(32))"
   ```
   On the Gemini free tier, Google may use your prompts to improve its models, so don't
   put real patient data through it. If Gemini returns an error about the model name,
   check the current model IDs in AI Studio and change `GEMINI_MODEL`.
3. **Start the backend.**
   ```
   cd backend
   python -m venv .venv
   .venv\Scripts\activate          # Windows
   source .venv/bin/activate       # macOS and Linux
   pip install -e ".[dev]"
   uvicorn app.main:app --reload
   ```
4. **Start the frontend** in a second terminal.
   ```
   cd frontend
   npm ci
   npm run dev
   ```
5. Open http://localhost:5173 for the clinic site and http://localhost:5173/staff for the
   staff inbox. The Vite dev server forwards `/api` requests to the backend on port 8000.

To check the model connection, open the chat and ask "How much is a cleaning?". The
answer should mention $95 and show a numbered source. Then send a message through the
contact form and open the staff inbox; a drafted reply should appear within a few seconds.

## Tests

```
cd backend
pytest              # 72 tests, no network access needed
ruff check . && ruff format --check . && mypy

cd frontend
npm test            # opening hours and stream parsing
npm run lint && npm run typecheck
```

GitHub Actions runs all of these, plus the offline evaluation, on every push.

## Deploying

The `Dockerfile` builds the frontend and runs the API, which serves it on `$PORT`
(8000 by default). Set the same variables as in `.env.example` on your host. Behind a
hosting platform's proxy, also set `FORWARDED_ALLOW_IPS=*` so rate limits apply per
visitor rather than to the proxy's address. Only do that when the app can't be reached
except through the proxy.

The inbox uses SQLite in `backend/var/`. On hosts with temporary disks, messages are lost
on redeploy unless that folder is on a persistent volume.

## Limitations and next steps

- Approved replies are marked as sent but not emailed. A real deployment would connect an
  email provider.
- Staff share a single token. Individual accounts with an audit trail would be needed for
  real use.
- Rate limits live in memory, which is fine for one instance. Several instances would
  need a shared store such as Redis.
- Chat history comes from the browser, so a visitor could fake earlier turns. The impact
  is limited to their own chat: safety rules and document grounding still apply on every
  message.
- Next on the list: a hybrid BM25 plus embedding retriever, measured against the BM25
  numbers above.

## Project layout

```
backend/
  app/
    chat/        answer pipeline and prompts
    inbox/       triage and SQLite store
    knowledge/   document loading and BM25 retrieval
    llm/         Gemini and Groq clients, fallback
    api/         HTTP endpoints
    safety.py    emergency and medication rules
  data/clinic/   the clinic's documents
  eval/          labeled questions, messages and the evaluation script
  tests/
frontend/
  src/site/      clinic website and contact form
  src/chat/      chat widget
  src/staff/     staff inbox
```
