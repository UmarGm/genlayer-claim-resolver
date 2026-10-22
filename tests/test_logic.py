"""
Unit tests for the deterministic part of claim_resolver.py (quorum rule,
validator equivalence rule, input validation).

The contract file imports `genlayer`, which only exists inside GenVM, so these
tests extract the pure-logic block between the markers and run it as plain
Python. Run with:  python -m pytest tests/ -v
"""
import pathlib

SRC = (pathlib.Path(__file__).parent.parent / "claim_resolver.py").read_text()
BLOCK = SRC.split("# --- pure logic begin ---")[1].split("# --- pure logic end ---")[0]
ns: dict = {}
exec(BLOCK, ns)

aggregate = ns["aggregate"]
quorum_for = ns["quorum_for"]
results_equivalent = ns["results_equivalent"]
validate_inputs = ns["validate_inputs"]


def res(verdicts):
    return {"verdicts": verdicts, "final": aggregate(verdicts)}


# ---- quorum ----
def test_quorum_sizes():
    assert [quorum_for(n) for n in (2, 3, 4, 5)] == [2, 2, 3, 4]


def test_aggregate_clear_yes_and_no():
    assert aggregate(["YES", "YES", "NO"]) == "YES"
    assert aggregate(["NO", "NO", "UNDETERMINED"]) == "NO"


def test_aggregate_unresolved_cases():
    assert aggregate(["YES", "NO"]) == "UNRESOLVED"
    assert aggregate(["YES", "UNDETERMINED", "UNDETERMINED"]) == "UNRESOLVED"
    assert aggregate(["UNDETERMINED", "UNDETERMINED"]) == "UNRESOLVED"


# ---- validator equivalence ----
def test_identical_results_accepted():
    r = res(["YES", "YES", "NO"])
    assert results_equivalent(r, r)


def test_one_flaky_source_tolerated():
    leader = res(["YES", "YES", "YES"])
    mine = res(["YES", "YES", "UNDETERMINED"])
    assert results_equivalent(leader, mine)


def test_different_final_rejected():
    leader = res(["YES", "YES", "NO"])
    mine = res(["NO", "NO", "NO"])
    assert not results_equivalent(leader, mine)


def test_two_sources_differ_rejected():
    leader = res(["YES", "YES", "YES", "YES", "YES"])
    mine = res(["YES", "YES", "YES", "UNDETERMINED", "UNDETERMINED"])
    # mine is UNRESOLVED anyway, but also checks the mismatch limit
    assert not results_equivalent(leader, mine)


def test_dishonest_leader_final_not_matching_its_own_verdicts():
    forged = {"verdicts": ["NO", "NO", "NO"], "final": "YES"}
    assert not results_equivalent(forged, res(["NO", "NO", "NO"]))
    assert not results_equivalent(forged, forged)


def test_malformed_leader_rejected():
    mine = res(["YES", "YES"])
    assert not results_equivalent({"verdicts": ["MAYBE", "YES"], "final": "YES"}, mine)
    assert not results_equivalent({"final": "YES"}, mine)
    assert not results_equivalent("garbage", mine)
    assert not results_equivalent({"verdicts": ["YES"], "final": "UNRESOLVED"}, mine)


# ---- input validation ----
GOOD = ["https://a.example/x", "https://b.example/y"]


def test_valid_input():
    assert validate_inputs("Is the sky blue?", GOOD) is None


def test_invalid_inputs():
    assert validate_inputs("", GOOD)
    assert validate_inputs("q" * 301, GOOD)
    assert validate_inputs("q?", GOOD[:1])
    assert validate_inputs("q?", [f"https://x.example/{i}" for i in range(6)])
    assert validate_inputs("q?", ["https://a.example", "https://a.example"])
    assert validate_inputs("q?", ["http://a.example", "https://b.example"])
    assert validate_inputs("q?", "https://a.example")
