from .base import KnowledgeSourceConnector
from .bookstack import BookStackConfig, BookStackConnector
from .capabilities import (
    HierarchicalDiscoveryConnector,
    MarkdownConfigurableConnector,
    SearchableConnector,
)
from .confluence import ConfluenceRestConnector
from .contentful import ContentfulConnector
from .document360 import Document360Config, Document360Connector
from .freshdesk import FreshdeskConfig, FreshdeskConnector
from .generic_docs import GenericDocsConnector
from .generic_web import GenericWebConnector, SafeStaticHttpClient, StaticHtmlParser
from .ghost import GhostConnector
from .gitbook import GitBookConfig, GitBookConnector
from .github_docs import GitHubDocsConfig, GitHubDocsConnector
from .gitlab import GitLabDocsConnector
from .guru import GuruConnector
from .helpjuice import HelpjuiceConnector
from .helpscout import HelpScoutConfig, HelpScoutConnector
from .hubspot import HubSpotConnector
from .intercom import IntercomConnector
from .local_files import LocalFilesConnector
from .mediawiki import MediaWikiConnector
from .notion import NotionConnector
from .outline import OutlineConfig, OutlineConnector
from .readme import ReadMeConnector
from .registry import ConnectorDescriptor, ConnectorRegistry, default_registry
from .salesforce import SalesforceConnector
from .sanity import SanityConnector
from .sharepoint import SharePointConnector
from .slite import SliteConnector
from .strapi import StrapiConnector
from .wordpress import WordPressConnector
from .zendesk import ZendeskConfig, ZendeskGuideConnector

__all__ = [
    "BookStackConfig",
    "BookStackConnector",
    "ConfluenceRestConnector",
    "ConnectorDescriptor",
    "ConnectorRegistry",
    "ContentfulConnector",
    "Document360Config",
    "Document360Connector",
    "FreshdeskConfig",
    "FreshdeskConnector",
    "GenericDocsConnector",
    "GenericWebConnector",
    "GhostConnector",
    "GitBookConfig",
    "GitBookConnector",
    "GitHubDocsConfig",
    "GitHubDocsConnector",
    "GitLabDocsConnector",
    "GuruConnector",
    "HelpjuiceConnector",
    "HelpScoutConfig",
    "HelpScoutConnector",
    "HierarchicalDiscoveryConnector",
    "HubSpotConnector",
    "IntercomConnector",
    "KnowledgeSourceConnector",
    "LocalFilesConnector",
    "MarkdownConfigurableConnector",
    "MediaWikiConnector",
    "NotionConnector",
    "OutlineConfig",
    "OutlineConnector",
    "ReadMeConnector",
    "SafeStaticHttpClient",
    "SalesforceConnector",
    "SanityConnector",
    "SearchableConnector",
    "SharePointConnector",
    "SliteConnector",
    "StaticHtmlParser",
    "StrapiConnector",
    "WordPressConnector",
    "ZendeskConfig",
    "ZendeskGuideConnector",
    "default_registry",
]
