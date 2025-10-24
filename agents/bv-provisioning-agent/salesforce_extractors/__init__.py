"""
Salesforce Extractors Package

Modular Salesforce data extraction tools for BroadVoice service delivery automation.
Provides specialized extractors for opportunities, contacts, documents, transcripts, and more.
"""

from .base import SalesforceBase
from .opportunity import OpportunityExtractor
from .contacts import ContactExtractor
from .documents import DocumentExtractor
from .transcripts import TranscriptExtractor
from .relationships import RelationshipMapper
from .reports import ReportGenerator
from . import utils

__version__ = "1.0.0"
__author__ = "BroadVoice Service Delivery Team"

__all__ = [
    "SalesforceBase",
    "OpportunityExtractor",
    "ContactExtractor", 
    "DocumentExtractor",
    "TranscriptExtractor",
    "RelationshipMapper",
    "ReportGenerator",
    "utils"
]