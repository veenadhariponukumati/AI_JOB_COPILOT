"""Shared rate limiter for OpenAI-backed endpoints.

Prevents unbounded OpenAI API cost from repeated calls to expensive
endpoints (resume/JD upload, analysis, quiz generation) on a public
deployment with no other request throttling.
"""

from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)
