# Blockchain 2026 — Labs

Course code for the IPv8 labs.

## Collaboration

Labs 2 and 3 were group efforts. The team's shared development repository is available at https://github.com/AlexDC-2003/blockchain-common, where contributions from all members are visible. This personal repo contains my mirrored copy of the final code as required by the course (each member's Lab 1 GitHub URL is the registered submission point for the rest of the course).

The team coordinated through Discord (planning, live coding sessions, and grading runs) and divided work across phases for both lab assignment 2 and lab assignment 3.

## Setup

```bash
pip install -r requirements.txt
```

Each lab uses an IPv8 `.pem` key file. Labs 2 and 3 reuse the key each member registered in Lab 1.

## Lab 1 — Proof-of-Work Registration over IPv8

Individual registration. The client mines a Proof-of-Work nonce over `email + github_url`, joins the community, discovers the server, and submits the nonce. The server verifies the PoW and replies with a success/failure response.

### Files
- `lab1/pow_client.py` — the IPv8 client. Mines the nonce, discovers peers, identifies the server by its public key, and sends the submission payload.

### Running

```bash
cd lab1
python pow_client.py
```

The client first mines a nonce with `DIFFICULTY_BITS = 28` leading zero bits (this can take a while, so it prints a progress/hash-rate line periodically if debugging prints are enabled). Once mined, it waits to discover the server, submits, and prints on success.

### Notes
- The `.pem` registered here (`my_id.pem`) is the key that will be reused in Labs 2 and 3. SAVE AND KEEP TRACK OF IT!
- Edit `EMAIL` and `GITHUB_URL` at the top of `pow_client.py` before running — the nonce is mined over exactly those two strings, so they must match what you submit.
- `RESPONSE_TIMEOUT_SECONDS` (15 min) bounds how long the client waits for the server's reply before giving up.

## Lab 2 — Coordinated Group Signing over IPv8

3-person group signs 3 challenge nonces from the server within a 10-second wall-clock budget. Each round must be submitted by a different member.

### Files
- `lab2/part1.py` — one-time group registration. Sends the 3 member pubkeys (in canonical order) to the server and prints the returned `group_id`.
- `lab2/part2.py` — the timed signing client. Round-robin: member 1 submits round 1, member 2 round 2, member 3 round 3. Each member runs the same script with their own `.pem`.

### Running

**Part 1 (one person):**

```bash
cd lab2
python part1.py
```

Wait for `Response: success=True, group_id=...`. Save the `group_id`, then Ctrl+C.

**Part 2 (all 3 teammates):**

Each teammate fills in their own `MY_KEY_FILE` and pastes the shared `GROUP_ID` + 3 member pubkeys, then runs:

```bash
cd lab2
python part2.py
```

Each script discovers the other 2 + the server, does a Ready handshake, then member 1 fires round 1. The chain auto-progresses through all 3 rounds via `RoundDone` messages.

### Notes
- Uses the same `.pem` from Lab 1.
- Intra-team messages have retransmission tasks to handle UDP packet loss within the 10s budget.
- All 3 members must hardcode the 3 pubkeys in the same canonical order; this order also determines which round each member submits.


## Lab 3 — PoW Blockchain over IPv8

3-node Proof-of-Work blockchain. Each member runs one node; nodes mine, propagate, and converge on a single chain. After registration, the server joins the blockchain community, submits a test transaction, and verifies the chain across all 3 nodes.

### Files
- `lab3/part1.py` — one-time registration. Sends the `group_id` + the self-chosen blockchain community ID to the server so it knows which community to join.
- `lab3/chain.py` — chain primitives: block header packing (84 bytes), `block_hash`, `tx_hash`, `txs_hash` body commitment, PoW search, genesis block, and `serialize_txs`/`deserialize_txs` for sending transactions.
- `lab3/node.py` — `BlockChain` class. Owns the blocks list, mempool, mining (`prepare_next`), validation, append, and fork-switch logic.
- `lab3/community.py` — the IPv8 node. Server-facing handlers, block propagation between teammates, and the mining loop.

### Running

**Part 1 (one person):**

```bash
cd lab3
python part1.py
```

Wait for `Response: success=True, message=...`. Then Ctrl+C.

**Part 2 (all 3 teammates):**

Each teammate fills in their own `MY_KEY_FILE`, then runs:

```bash
cd lab3
python community.py
```

Each node joins the blockchain community, discovers the others, and starts mining. The server queries the nodes in the background; pass confirmation can be seen when running `part1.py` again after a good-looking run.

### Tests

Unit tests for the chain primitives and single-node mining + validation live in `lab3/tests/`. Run them with `pytest` from a virtualenv:

```bash
cd lab3
python3 -m venv .venv          # needs python3-venv (sudo apt install python3-venv)
source .venv/bin/activate
pip install pytest
pytest tests/
```

`tests/conftest.py` puts `lab3/` on `sys.path` so the tests import `chain`/`node` the same way the rest of the code does. Always run via `pytest` (not `python3 tests/test_chain.py` directly), otherwise the import path isn't set up.

### Notes
- Uses the same `.pem` from Lab 1.
- Mining difficulty is set high enough (`MINING_DIFFICULTY = 24`) + a 3s sleep between blocks to keep propagation ahead of new blocks and prevent the 3 chains from diverging.
- Re-run `part1.py` to reset the server's retry counter (or if the blockchain community ID changes).
- All 3 members must hardcode the 3 pubkeys in the same canonical order.