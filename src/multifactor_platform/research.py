"""Explicit eligibility checks for historical research inputs."""


class ResearchDataError(ValueError):
    pass


def require_historical_research(frame):
    reason = frame.attrs.get("historical_research_blocked")
    if reason:
        raise ResearchDataError(reason)
