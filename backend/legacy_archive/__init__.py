"""Archived modules retained for reference and offline batch jobs.

This package holds code that is no longer part of the live FastAPI server
(notably the former `prediction` ML pipeline). The active server only imports
from here lazily and defensively. Internal modules under
`legacy_archive/prediction/*` may still use bare `prediction.*` import paths and
are not guaranteed to import cleanly outside their original batch context.
"""
