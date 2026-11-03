from pathlib import Path

from emporio.knowledge.index import PolicyHit, PolicyIndex
from emporio.knowledge.policies import PolicySection, parse_policies, policy_pdf_path


def load_policy_index(data_dir: Path) -> PolicyIndex:
    """Parse the manual found in data_dir and build the search index."""
    return PolicyIndex(parse_policies(policy_pdf_path(data_dir)))


__all__ = ["PolicyHit", "PolicyIndex", "PolicySection", "load_policy_index"]
