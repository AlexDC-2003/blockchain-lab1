from __future__ import annotations

import asyncio
import hashlib
import os
import struct
import time
from binascii import hexlify, unhexlify
from pathlib import Path

from ipv8.community import Community, CommunitySettings
from ipv8.configuration import ConfigBuilder,Strategy,WalkerDefinition,default_bootstrap_defs
from ipv8.lazy_community import lazy_wrapper
from ipv8.messaging.lazy_payload import VariablePayload,vp_compile
from ipv8.peer import Peer
from ipv8_service import IPv8

# Registration parameters: the community to join, the server we submit to, and
# the identity/PoW settings. EMAIL and GITHUB_URL are also the bytes we mine over.
COMMUNITY_ID_HEX = "2c1cc6e35ff484f99ebdfb6108477783c0102881"
SERVER_PUBLIC_KEY_HEX = "4c69624e61434c504b3a86b23934a28d669c390e2d1fc0b0870706c4591cc0cb178bc5a811da6d87d27ef319b2638ef60cc8d119724f4c53a1ebfad919c3ac4136c501ce5c09364e0ebb"

#TODO: Fill in your email and github url
EMAIL = "input-your-email"
GITHUB_URL = "input-your-url"

DIFFICULTY_BITS = 28
KEY_FILE = "my_id.pem"
RESPONSE_TIMEOUT_SECONDS = 15 * 60
DEBUG_PRINT = False

# communication with the server
@vp_compile
class SubmissionPayload(VariablePayload):
    msg_id = 1
    format_list = ["varlenHutf8", "varlenHutf8", "q"]
    names = ["email", "github_url", "nonce"]

@vp_compile
class ResponsePayload(VariablePayload):
    msg_id = 2
    format_list = ["?", "varlenHutf8"]
    names = ["success", "message"]

# Check if the mined nonce meets the target difficulty
# True if the digest has at least `bits` leading zero bits.
def _meets_difficulty(digest: bytes, bits: int) -> bool:
    full_zero_bytes, remainder = divmod(bits, 8)
    # Every whole leading byte must be zero.
    if any(digest[i] != 0 for i in range(full_zero_bytes)):
        return False
    if remainder == 0:
        return True
    return digest[full_zero_bytes] < (1 << (8 - remainder))

# Mine the PoW.
def mine_pow(email: str, github_url: str, bits: int = 28, start: int = 0) -> int:
    prefix = email.encode("utf-8") + b"\n" + github_url.encode("utf-8") + b"\n"
    base = hashlib.sha256(prefix)
    print(f"mining {len(prefix)} bytes; {bits} leading zero bits")
    pack = struct.pack
    nonce = start
    report_every = 1 << 20
    t0 = time.time()
    last_report = t0
    # Brute force nonce-mining
    while nonce < (1 << 63):
        # Try this nonce, copy the prefixed state, check if it meets diffculty append the nonce, hash.
        h = base.copy()
        h.update(pack(">q", nonce))
        digest = h.digest()
        if _meets_difficulty(digest, bits):
            dt = time.time() - t0
            print(f"mining FOUND nonce={nonce} in {dt:.1f}s; hash={digest.hex()}")
            return nonce
        nonce += 1
        if DEBUG_PRINT is True:
            # Periodically report progress and the current hash rate.
            if nonce % report_every == 0:
                now = time.time()
                rate = report_every / max(now - last_report, 1e-9)
                last_report = now
                print(f"mining {nonce:>14,} tried ({rate / 1e6:.2f} MH/s)")
    raise RuntimeError("Exhausted int64 nonce space.")

class PoWCommunity(Community):
    assert len(COMMUNITY_ID_HEX) == 40, "invalid community ID length"
    community_id = unhexlify(COMMUNITY_ID_HEX)
    def __init__(self, settings: CommunitySettings) -> None:
        super().__init__(settings)
        self.add_message_handler(ResponsePayload, self.on_response)
        self.server_pubkey_bin = unhexlify(SERVER_PUBLIC_KEY_HEX)
        self.nonce: int | None = None
        self.submitted_to: set[bytes] = set()
        self.done = asyncio.Event()             # set once the server replies to end
        self.last_response: ResponsePayload | None = None

    def started(self) -> None:
        # IPv8 calls this once the overlay is up; kick off the submit loop.
        self.register_task("submit_loop", self._submit_loop)

    async def _submit_loop(self) -> None:
        # Mine the nonce before you connect to the server.
        if self.nonce is None:
            loop = asyncio.get_running_loop()
            self.nonce = await loop.run_in_executor(None, mine_pow, EMAIL, GITHUB_URL, DIFFICULTY_BITS)
        print("mined, waiting for server")
        announced_peers: set[bytes] = set()
        tick = 0
        # Poll discovered peers. When the server shows up, submit our nonce once.
        while not self.done.is_set():
            peers = self.get_peers()
            for peer in peers:
                pk = peer.public_key.key_to_bin()
                if pk not in announced_peers:
                    # Log each peer the first time we see it.
                    announced_peers.add(pk)
                    tag = "SERVER" if pk == self.server_pubkey_bin else "peer"
                    print(f"ipv8 discovered {tag} mid={peer.mid.hex()} addr={peer.address}")
                # Identify the server by its pubkey and submit exactly once.
                if pk == self.server_pubkey_bin and pk not in self.submitted_to:
                    self.submitted_to.add(pk)
                    print(f"ipv8 sending submission to server at {peer.address}")
                    payload = SubmissionPayload(EMAIL, GITHUB_URL, self.nonce)
                    self.ez_send(peer, payload)
            if DEBUG_PRINT is True:
                tick += 1
                print(f"\nipv8 peer list (tick {tick}, {len(peers)} known)")
                if not peers:
                    print("ipv8 no peers yet")
                for peer in peers:
                    pk = peer.public_key.key_to_bin()
                    tag = "SERVER" if pk == self.server_pubkey_bin else "peer  "
                    print(f"ipv8 {tag} mid={peer.mid.hex()} addr={peer.address}")
                    print(f"ipv8 pubkey={pk.hex()}")
                print()
            await asyncio.sleep(2.0)

    @lazy_wrapper(ResponsePayload)
    def on_response(self, peer: Peer, payload: ResponsePayload) -> None:
        # Only trust a response that actually came from the server's key.
        if peer.public_key.key_to_bin() != self.server_pubkey_bin:
            print(f"ipv8 ignoring response from non-server peer mid={peer.mid.hex()}")
            return
        verdict = "ok" if payload.success else "fail"
        print(f"server {verdict} : {payload.message}")
        self.last_response = payload
        self.done.set()

async def main() -> None:
    # Build a minimal IPv8 config
    builder = ConfigBuilder().clear_keys().clear_overlays()
    builder.add_key("my_key", "curve25519", KEY_FILE)
    builder.add_overlay("PoWCommunity", "my_key",[WalkerDefinition(Strategy.RandomWalk, 20, {"timeout": 3.0})],default_bootstrap_defs,{},[("started",)])
    ipv8 = IPv8(builder.finalize(), extra_communities={"PoWCommunity": PoWCommunity})
    await ipv8.start()
    community: PoWCommunity = ipv8.get_overlay(PoWCommunity)
    my_pk = hexlify(community.my_peer.public_key.key_to_bin()).decode()
    print(f"ipv8 key file: {Path(KEY_FILE).resolve()}")
    print(f"ipv8 my pubkey: {my_pk}")
    print(f"ipv8 community: {COMMUNITY_ID_HEX}")
    print(f"ipv8 server pk: {SERVER_PUBLIC_KEY_HEX}")

    try:
        await asyncio.wait_for(community.done.wait(), timeout=RESPONSE_TIMEOUT_SECONDS)
    except asyncio.TimeoutError:
        print(f"ipv8 no response within {RESPONSE_TIMEOUT_SECONDS}s.")
    finally:
        await ipv8.stop()

if __name__ == "__main__":
    if os.name == "nt":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main())
