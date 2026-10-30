# Zetaris + Meterless — how this project uses them, step by step

The hackathon's rule 05 says every submission must integrate Zetaris and
Meterless. This file is the honest version: what was **verified** from the
vendors' own documentation, what is **designed but unverified** because it
needs an account, and what runs **with no account at all**.

Nothing here is a guess presented as a fact. Where a number or a name is not
from the vendor's documentation, it says so.

---

## Meterless (Nightshift) — the runtime and the meter

### What was verified

From `github.com/meterless/Meterless` (public, **Apache-2.0**, 257★ as of
2026-10-25) and the vendor's own provider contract —
https://github.com/meterless/Meterless/blob/main/docs/agent-ready/add-meterless-provider.md
— as follows:

| Fact | Where it comes from |
|---|---|
| The runtime speaks the **OpenAI-compatible** API at `http://127.0.0.1:8088/v1` | the provider contract, "Meterless Runtime 0.90.0" |
| Auth is real: `Authorization: Bearer <token>`, token written to `<stateDir>/proxy-token` | the same contract |
| Every request carries `meterless-app: <stable lowercase id>`; chat carries `meterless-scope: user` | the same contract |
| Model ids are **routing modes**, not model names: `meterless/<disposition>` (`auto`, `fast`, `deep`, `cheap`, `local`, `fusion`), `meterless/<class>`, `meterless/<class>.<disposition>` | the same contract |
| `GET /healthz` only proves the process is up; **`GET /v1/models` decides** — 401/403 is "unauthorized", 200 with `meterless/*` ids is "online" | the same contract |
| Auto Detect tries ports **8088, 8090, 8787, 11434** on `127.0.0.1`, `localhost` and `[::1]` | the same contract |
| Use a **180 s timeout**: a cold model load can take minutes, and a short timeout reads as a false outage | the same contract |
| A job races attempts across models, judges them, and returns **a receipt for every check** | the project README ("One published night on one DGX Spark: 202 attempts, 1 accepted, 5h15m unattended, $0.00 cloud spend") |

### What this project does with it

The agent's prose is written by a model over an OpenAI-compatible endpoint.
`narrate.py` defaults to the **local Meterless runtime**
(`http://127.0.0.1:8088/v1`, model `meterless/auto`), and sends
`meterless-app: why-agent` on every request, exactly as the contract asks.

Two things follow from the contract, and both are in the code:

- **`/v1/models` decides status, not `/healthz`.** The agent's provider check
  asks for the model list; a 401 is reported as *unauthorized*, not as
  *offline*, because a token problem and a dead process need different answers.
- **180 s timeout.** A cold load is not an outage.

### The second, better use: Meterless as the meter

The house rule is that every model call is accounted for. Meterless keeps one
open job per app id and meters the calls under it — so the agent's own
reasoning shows up as a `meterless-app: why-agent` job with a receipt, in the
same ledger where the rest of the work is metered.

**Not verified:** the exact job-log schema the runtime writes locally. The
integration depends on the provider contract above, which *is* documented; the
receipt *format* is not, and this project does not parse it.

### Running it with no account

```
# 1. the runtime is running on 8088 (any local install)
curl -s http://127.0.0.1:8088/v1/models | head

# 2. the agent narrates through it
python3 why_agent.py explain why-alpha --narrate
```

If the runtime is not installed, `--narrate` is simply not used: the
deterministic report still works, and it is the part that decides what is
true. **The narrative is optional; the reconciliation is not.**

---

## Zetaris — the evidence layer

### What was verified

From `zetaris.com` (2026-10-25):

| Fact | Where it comes from |
|---|---|
| "The World's Leading Data Harness for AI" | the site's own headline |
| It harnesses your engines — **DuckDB**, Spark, Presto, Trino — with automatic smart routing | the site |
| A **governed semantic layer** over DuckDB, Spark, Presto and Trino | the site, and the getting-started docs |
| "Unstructured business context — policies, table definitions, domain glossaries — made queryable at runtime" | the site |
| A **Hobby tier, free forever**, single node up to 12 vCPUs, BYOC, ~20-minute setup, self-serve register | the site |

### What this project does with it

This is the part of the problem Zetaris describes almost exactly. The evidence
is **fragmented by nature** — a card, a receipt, a commit, a check run, a
model verdict, five places that never talk to each other — and the question
is "what do these five together say about this item?". That is a
semantic-layer question, not a single-file question.

Checked against the getting-started docs on 2026-10-27: a Mini cluster is
queried from the SQL workspace, or over JDBC. A CSV lands in the stack
bucket and is registered as a filestore table. There is **no MCP endpoint**
on that path. An earlier draft of this file said the agent would call the
harness over MCP. That was wrong, and it is withdrawn.

| Here | In a Zetaris harness |
|---|---|
| `evidence/items.jsonl` (or the DuckDB table) | a CSV in the stack bucket, then a filestore table |
| the `aspect` vocabulary (`state`, `outcome`, `cause`) | the semantic layer — the governed vocabulary the query groups by |
| `find_unsupported()` — every value the narrative states must already exist in the evidence | the same constraint, applied to the rows the `SELECT` returns |
| the citation on each claim | the source and locator columns the query returns |

The local read is the same shape: `why_agent.py explain <id> --duckdb
evidence/work.duckdb` reads the allowlisted tables `items` and `evidence`.
Moving the rows into a filestore table does not change the reconciliation.
Only the source of the rows changes.

### The part that needs the founder

Zetaris Hobby is free but a Mini cluster is **BYOC** — it deploys into a
cloud account, and provisioning takes about 30 minutes.

1. Register and create the Mini cluster `why-agent-mini`.
2. Put a CSV of the synthetic evidence in the stack bucket.
3. Register a filestore table and run the reconciliation `SELECT` in the SQL
   workspace, or over JDBC with the cluster's own endpoint.
4. Paste the real result below. Credentials stay in the Gateway. They are
   not written into this repository.

**Not verified on 2026-10-27:** the cluster was not Active from this machine.
AWS credentials were not available to the session (`NoCredentials`), and no
JDBC host was on disk. The designed statements are below. They were not run.

### Running it with no account

The evidence layer works with **no account at all**: the JSONL file and the
DuckDB file are the same rows, read by the same code. The Zetaris path is an
upgrade in governance (one governed vocabulary, a filestore table, provenance),
not a dependency for correctness.

---

## What the submission says about the two integrations

The submission form asks how Zetaris, Meterless, Cursor and NVIDIA were used.
The honest answer, which `docs/OPEN_AGENT_HACKATHON_2026-10-27.md` carries verbatim:

- **Meterless** — the narration client speaks the OpenAI-compatible runtime.
  On 2026-10-27 the free M1–M4 app was installed and `GET /v1/models` returned
  200 with `meterless/*` ids. `explain why-alpha --narrate` then returned
  HTTP 502. The output is under "Live run — 2026-10-27 (Meterless)" below.
  The token is resolved automatically (`--narrate-key`, then
  `METERLESS_TOKEN`, then `WHY_AGENT_NARRATE_KEY`, then the runtime token
  file). The placeholder `rt-local` is rejected. The value is never printed.
- **Zetaris** — designed as the governed semantic layer: CSV to the stack
  bucket, a filestore table, a reconciliation `SELECT`. No live query on
  2026-10-27. See the Zetaris live-run section below.
- **Cursor** — not used for the original build. The original code was written
  by the MiniMax lane and reviewed by two outside model families. A later
  hardening pass on 2026-10-27 was done in Cursor. The files that pass
  touched are listed under "Cursor, this pass" below.
- **NVIDIA** — the reviewer families that approved the original change include
  NVIDIA's `nemotron-3-ultra-550b-a55b` on the free NVIDIA endpoint, and the
  reconciliation step is deterministic code that runs on CPU. The M1 narration
  attempt routed to a local WebLLM lane, not to an NVIDIA model.

---

## Live run — 2026-10-27 (Meterless)

Machine: Apple M1, 8 GB. The free M1–M4 edition does not advertise an
OpenAI listener on IPv4 port 8088. The installed app is Nightshift M1-M4
0.92.7, from `https://meterless.ai/Nightshift/M1+/`.

What the process actually did:

- The UI listened on `127.0.0.1:47321`.
- The OpenAI API listened on `[::1]:8088`.
- At the start of the pass, `127.0.0.1:8088` was a different process. Its
  `GET /v1/models` body was a model id `stub`. That process was not used as
  this run.

`GET http://[::1]:8088/v1/models` with the bearer token from the app's
runtime-token file returned **HTTP 200**. The ids included `meterless/auto`,
`meterless/fast`, `meterless/deep`, `meterless/cheap`, `meterless/local`,
`meterless/fusion`, and several `webllm/*` ids. The token value is not
copied here.

The narration command, pointed at that listener:

```
python3 why_agent.py explain why-alpha --narrate --narrate-base http://[::1]:8088/v1
```

Stderr:

```
narrate token source: runtime-token file
narration outage: narration endpoint returned HTTP 502
```

The 502 body, from the same messages the command sends:

```
{"error":{"message":"prompt should always be the first message in `messages`.","type":"api_error","code":"provider_error","param":null,"meterless_detail":"System prompt should always be the first message in `messages`."},"meterless":{"requested_model":"meterless/auto","routed_model":null,"app":"why-agent","candidates":[{"model":"webllm/Llama-3.2-1B-Instruct-q4f16_1-MLC","provider":"webllm","code":"model_load_failed"}]}}
```

The same command was tried three times. The first returned 502 after about
149 seconds. The next two returned 502 in about 2 seconds. A separate
one-line probe to the same endpoint (`Reply with the single word ok.`)
returned HTTP 200 from `webllm/Llama-3.2-1B-Instruct-q4f16_1-MLC`, so the
runtime was up. **CHECK PASSED was not observed.** The deterministic report
does not need this call, and it is the part that decides what is true.

---

## Live run — 2026-10-27 (Zetaris)

No live result.

The AWS tool returned expired credentials. The local AWS CLI returned
`Unable to locate credentials`. No JDBC host for `why-agent-mini` was on
disk. The 17:00 Toronto cutoff for standing the cluster up had passed, and
a Mini cluster takes about 30 minutes to provision, so the cluster was not
created from this pass.

Designed statements, not executed. The bucket name and the credentials come
from the cluster Gateway. They are not in this file.

```sql
CREATE LIGHTNING DATABASE why_agent_files;
CREATE LIGHTNING FILESTORE TABLE evidence
  FROM why_agent_files
  FORMAT CSV
  OPTIONS (
    path "s3a://<stack-bucket>/why-agent/evidence.csv",
    header "true"
  );
SELECT item_id, aspect, value, source, locator
FROM why_agent_files.evidence
WHERE item_id = 'why-delta'
ORDER BY aspect, source;
```

What is verified: the local reconciliation, the allowlisted DuckDB read, and
the getting-started shape (stack bucket, filestore table, SQL workspace or
JDBC). What is designed and not run: those three statements against
`why-agent-mini`.

---

## Cursor, this pass

Not used for the original build. Used on 2026-10-27 for the hardening pass.
Files touched:

- `narrate.py`
- `evidence.py`
- `why_agent.py`
- `test_why_agent.py`
- `demo.py`
- `evidence/items.jsonl`
- `SECURITY.md`
- `README.md`
- `INTEGRATION.md`
- `docs/OPEN_AGENT_HACKATHON_2026-10-27.md`
- `DECK.md`
- `DECK.pdf`
- `DRILLS-2026-10-27.md`
- `RECEIPT-2026-10-27.md`

---

## Tavily live-evidence lane (Nebius build)

`tavily_lane.py` checks a claim against the live web and records what it
finds as evidence. A Tavily search result becomes an ordinary `Evidence` row
with `kind="web"` and `source="tavily"`: the row's locator is the result URL,
its statement is the page's title (or the start of its text), and its
`observed_at` is when the page was retrieved. From that point on a web row is
a claim like any other source — the card, the receipt, the commit — and
reconciliation treats it the same way: it can corroborate a state, and it can
conflict with one, stated plainly rather than smoothed over.

The guard is deterministic: a row carries the claimed value **only if that
value literally appears in the page's content** (case-insensitive). A page
that does not contain the value still produces a row — with an empty value
and a statement saying the value was not found there. A recorded non-match is
evidence too; dropping it would let a caller shop for the one page that
agrees and hide the rest. And Tavily's own generated `answer` is never
evidence: it is a model's summary of the pages, exactly the kind of
uncheckable assertion this tool exists to catch, so the lane does not even
request it (`include_answer` is off).

The key comes from the `TAVILY_API_KEY` environment variable only; with no
key set, the lane raises instead of running.

This lane is the significant update for the Nebius x NVIDIA Global AI
Hackathon (Best Apps and Agents track): it takes why-agent from reconciling
only local artefacts to checking claims against fresh web sources, and the
Best Use of Tavily bonus requires a functional, runtime call to the Tavily
API, which `search_claims` is.
