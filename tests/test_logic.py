"""
Unit tests for the deterministic part of claim_resolver.py (quorum rule,
validator equivalence rule, domain independence, challenge validation, input
validation).

The contract file imports `genlayer`, which only exists inside GenVM, so these
tests extract the block between the markers and run it as plain Python. Run
with:  python -m pytest tests/ -v
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
validate_challenge = ns["validate_challenge"]
host_of = ns["host_of"]


def res(verdicts):
    return {"verdicts": verdicts, "final": aggregate(verdicts)}


# ---- quorum ----
def test_quorum_sizes():
    assert [quorum_for(n) for n in (2, 3, 4, 5)] == [2, 2, 3, 4]


def test_quorum_sizes_for_challenged_claims():
    # claims that were challenged can have 6 or 7 sources
    assert [quorum_for(n) for n in (6, 7)] == [4, 5]


def test_aggregate_clear_yes_and_no():
    assert aggregate(["YES", "YES", "NO"]) == "YES"
    assert aggregate(["NO", "NO", "UNDETERMINED"]) == "NO"


def test_aggregate_unresolved_cases():
    assert aggregate(["YES", "NO"]) == "UNRESOLVED"
    assert aggregate(["YES", "UNDETERMINED", "UNDETERMINED"]) == "UNRESOLVED"
    assert aggregate(["UNDETERMINED", "UNDETERMINED"]) == "UNRESOLVED"


def test_aggregate_with_extra_sources_can_resolve():
    # 3 undetermined sources + 3 added sources that agree: quorum for 6 is 4,
    # so 3 agreeing sources are still not enough ...
    assert aggregate(["UNDETERMINED"] * 3 + ["YES"] * 3) == "UNRESOLVED"
    # ... but 4 agreeing sources out of 6 are.
    assert aggregate(["UNDETERMINED"] * 2 + ["YES"] * 4) == "YES"


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


def test_two_sources_differ_rejected_even_if_final_same():
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


def test_seven_source_claim_equivalence():
    leader = res(["YES"] * 5 + ["UNDETERMINED"] * 2)
    mine = res(["YES"] * 5 + ["NO", "UNDETERMINED"])
    assert leader["final"] == "YES"
    assert results_equivalent(leader, mine)


# ---- domain independence ----
def test_host_of_normalises_urls():
    assert host_of("https://www.Example.com/a?b=1#c") == "example.com"
    assert host_of("https://example.com:8443/x") == "example.com"
    assert host_of("https://user:pw@example.com/x") == "example.com"
    assert host_of("https://docs.python.org/3/") == "docs.python.org"
    assert host_of("https://") == ""


# ---- input validation ----
GOOD = ["https://a.example/x", "https://b.example/y"]


def test_valid_input():
    assert validate_inputs("Is the sky blue?", GOOD) is None


def test_invalid_inputs():
    assert validate_inputs("", GOOD)
    assert validate_inputs("q" * 301, GOOD)
    assert validate_inputs("q?", GOOD[:1])
    assert validate_inputs("q?", [f"https://x{i}.example/p" for i in range(6)])
    assert validate_inputs("q?", ["https://a.example", "https://a.example"])
    assert validate_inputs("q?", ["http://a.example", "https://b.example"])
    assert validate_inputs("q?", "https://a.example")


def test_same_domain_sources_rejected():
    err = validate_inputs("q?", ["https://a.example/1", "https://a.example/2"])
    assert err == "sources must come from different domains"


def test_www_and_case_do_not_hide_same_domain():
    err = validate_inputs("q?", ["https://www.a.example/1", "https://A.EXAMPLE/2"])
    assert err == "sources must come from different domains"


def test_different_subdomains_are_allowed():
    # documented limitation: subdomains count as different domains
    assert validate_inputs("q?", ["https://docs.a.example/1", "https://blog.a.example/2"]) is None


def test_source_without_host_rejected():
    assert validate_inputs("q?", ["https://", "https://b.example"])


# ---- challenge validation ----
EXISTING = ["https://a.example/x", "https://b.example/y", "https://c.example/z"]


def test_valid_challenge():
    assert validate_challenge(EXISTING, ["https://d.example/1"]) is None
    assert validate_challenge(EXISTING, [f"https://n{i}.example/p" for i in range(3)]) is None


def test_challenge_needs_between_one_and_three_sources():
    assert validate_challenge(EXISTING, [])
    assert validate_challenge(EXISTING, [f"https://n{i}.example/p" for i in range(4)])
    assert validate_challenge(EXISTING, "https://d.example/1")


def test_challenge_total_limit():
    five = [f"https://e{i}.example/p" for i in range(5)]
    assert validate_challenge(five, ["https://n1.example", "https://n2.example"]) is None
    assert validate_challenge(five, [f"https://n{i}.example" for i in range(3)])  # 8 > 7


def test_challenge_rejects_domains_already_used():
    assert validate_challenge(EXISTING, ["https://www.a.example/other"])
    assert validate_challenge(EXISTING, ["https://d.example/1", "https://d.example/2"])


def test_challenge_rejects_non_https_and_missing_host():
    assert validate_challenge(EXISTING, ["http://d.example/1"])
    assert validate_challenge(EXISTING, ["https://"])
