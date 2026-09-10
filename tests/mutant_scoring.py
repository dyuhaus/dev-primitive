"""Verdict rules for the mutation control, in their own module.

Separate from `control_mutants.py` on purpose. A mutant that targets the harness
has to name the line it replaces, and if that line lives in `control_mutants.py`
then the mutant's own definition string is a second copy of it — the harness
reports `PATTERN NOT UNIQUE` and the claim goes unverified. Putting the scoring
here lets the harness be mutated like anything else it tests.
"""

KILLED = "KILLED"
ERRORED_ONLY = "ERRORED-ONLY"
SURVIVED = "SURVIVED"


def classify(fails, errs) -> str:
    """Verdict for one mutant, from the named tests that died."""
    if fails:
        return KILLED
    return ERRORED_ONLY if errs else SURVIVED


def counts_as_verified(verdict: str) -> bool:
    """Only an ASSERTION FAILURE verifies a claim.

    The harness's contract is that a mutant must be killed by an assertion
    failure, not an error: an error can mean the test blew up before reaching
    any assertion, so it carries no information about the claim. The scoring
    used to append to `survivors` on `not fails and not errs`, which quietly
    excluded ERRORED-ONLY mutants from the survivor list and let the run exit 0
    reporting that every claim was verified — the trap the file exists to avoid,
    one level up. It printed the honest label and contradicted it in the exit
    code.
    """
    return verdict == KILLED
