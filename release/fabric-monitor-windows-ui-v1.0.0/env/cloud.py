from dataclasses import dataclass

from azure.identity import AzureAuthorityHosts


COMMERCIAL = "Commercial"
GCC = "Gcc"
GCC_HIGH = "GccHigh"
DOD = "Dod"


@dataclass(frozen=True)
class CloudProfile:
    name: str
    authority_host: str
    azure_authority_host: str
    powerbi_api_root: str
    powerbi_scope: str
    graph_api_root: str
    graph_scope: str
    fabric_api_root: str | None
    fabric_scope: str | None
    onelake_dfs_root: str | None
    storage_blob_suffix: str

    @property
    def is_commercial(self) -> bool:
        return self.name == COMMERCIAL

    @property
    def supports_fabric_api(self) -> bool:
        return self.fabric_api_root is not None and self.fabric_scope is not None

    @property
    def supports_onelake(self) -> bool:
        return self.onelake_dfs_root is not None


_PROFILES = {
    COMMERCIAL: CloudProfile(
        name=COMMERCIAL,
        authority_host="https://login.microsoftonline.com",
        azure_authority_host=AzureAuthorityHosts.AZURE_PUBLIC_CLOUD,
        powerbi_api_root="https://api.powerbi.com/v1.0/myorg/",
        powerbi_scope="https://analysis.windows.net/powerbi/api/.default",
        graph_api_root="https://graph.microsoft.com/beta",
        graph_scope="https://graph.microsoft.com/.default",
        fabric_api_root="https://api.fabric.microsoft.com/",
        fabric_scope="https://api.fabric.microsoft.com/.default",
        onelake_dfs_root="https://onelake.dfs.fabric.microsoft.com",
        storage_blob_suffix="blob.core.windows.net",
    ),
    GCC: CloudProfile(
        name=GCC,
        authority_host="https://login.microsoftonline.com",
        azure_authority_host=AzureAuthorityHosts.AZURE_PUBLIC_CLOUD,
        powerbi_api_root="https://api.powerbigov.us/v1.0/myorg/",
        powerbi_scope="https://analysis.usgovcloudapi.net/powerbi/api/.default",
        graph_api_root="https://graph.microsoft.com/beta",
        graph_scope="https://graph.microsoft.com/.default",
        fabric_api_root=None,
        fabric_scope=None,
        onelake_dfs_root=None,
        storage_blob_suffix="blob.core.usgovcloudapi.net",
    ),
    GCC_HIGH: CloudProfile(
        name=GCC_HIGH,
        authority_host="https://login.microsoftonline.us",
        azure_authority_host=AzureAuthorityHosts.AZURE_GOVERNMENT,
        powerbi_api_root="https://api.high.powerbigov.us/v1.0/myorg/",
        powerbi_scope="https://high.analysis.usgovcloudapi.net/powerbi/api/.default",
        graph_api_root="https://graph.microsoft.us/beta",
        graph_scope="https://graph.microsoft.us/.default",
        fabric_api_root=None,
        fabric_scope=None,
        onelake_dfs_root=None,
        storage_blob_suffix="blob.core.usgovcloudapi.net",
    ),
    DOD: CloudProfile(
        name=DOD,
        authority_host="https://login.microsoftonline.us",
        azure_authority_host=AzureAuthorityHosts.AZURE_GOVERNMENT,
        powerbi_api_root="https://api.mil.powerbigov.us/v1.0/myorg/",
        powerbi_scope="https://mil.analysis.usgovcloudapi.net/powerbi/api/.default",
        graph_api_root="https://graph.microsoft.us/beta",
        graph_scope="https://graph.microsoft.us/.default",
        fabric_api_root=None,
        fabric_scope=None,
        onelake_dfs_root=None,
        storage_blob_suffix="blob.core.usgovcloudapi.net",
    ),
}

_ALIASES = {
    "commercial": COMMERCIAL,
    "public": COMMERCIAL,
    "azurecloud": COMMERCIAL,
    "gcc": GCC,
    "gcchigh": GCC_HIGH,
    "gcc-high": GCC_HIGH,
    "high": GCC_HIGH,
    "azureusgovernment": GCC_HIGH,
    "usgov": GCC_HIGH,
    "dod": DOD,
    "departmentofdefense": DOD,
}


def get_cloud_profile(name: str | None) -> CloudProfile:
    if not name:
        return _PROFILES[COMMERCIAL]

    normalized = name.replace(" ", "").replace("_", "").lower()
    profile_name = _ALIASES.get(normalized)
    if profile_name is None:
        valid = ", ".join(_PROFILES)
        raise ValueError(f"Unsupported CLOUD_ENVIRONMENT '{name}'. Expected one of: {valid}.")

    return _PROFILES[profile_name]

