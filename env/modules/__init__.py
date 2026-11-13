from .activity import main as Activity
from .apps import main as Apps
from .capacity import main as Capacity
from .capacity_metrics import main as CapacityMetrics
from .catalog import main as Catalog
from .delegatedsettings import main as DelegatedSettings
from .domains import main as Domains
from .fabricconnections import main as FabricConnections
from .fabricdeploymentpipelineoperations import (
    main as FabricDeploymentPipelineOperations,
)
from .fabriceventstreamtopology import main as FabricEventstreamTopology
from .fabricitemaccesspermissions import main as FabricItemAccessPermissions
from .fabricitemdefinitions import main as FabricItemDefinitions
from .fabricitemjobhistory import main as FabricItemJobHistory
from .fabricitems import main as FabricItems
from .fabricpipelineactivityruns import main as FabricPipelineActivityRuns
from .fabricshortcuts import main as FabricShortcuts
from .gateway import main as Gateway
from .gitconnections import main as GitConnections
from .graph import main as Graph
from .refreshables import main as Refreshables
from .refreshhistory import main as RefreshHistory
from .roles import main as Roles
from .tags import main as Tags
from .tenant import main as Tenant
from .widelysharedlinks import main as WidelySharedLinks
from .workspaces import main as Workspaces

__all__ = [
    "Activity",
    "Apps",
    "Capacity",
    "CapacityMetrics",
    "Catalog",
    "DelegatedSettings",
    "Domains",
    "FabricConnections",
    "FabricDeploymentPipelineOperations",
    "FabricEventstreamTopology",
    "FabricItemAccessPermissions",
    "FabricItemDefinitions",
    "FabricItemJobHistory",
    "FabricItems",
    "FabricPipelineActivityRuns",
    "FabricShortcuts",
    "Gateway",
    "GitConnections",
    "Graph",
    "RefreshHistory",
    "Refreshables",
    "Roles",
    "Tags",
    "Tenant",
    "WidelySharedLinks",
    "Workspaces",
]
