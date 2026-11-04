import asyncio
import json
import os
import sys
from pathlib import PurePosixPath
from typing import TYPE_CHECKING

from azure.core.exceptions import AzureError, ResourceNotFoundError

from env.utility.blob import Blob_File_Management
from env.utility.fabric import File_Table_Management
from env.utility.local import Local_File_Management

# from env.utility.helps import Bob
if TYPE_CHECKING:
    from env.utility.fabric_collection import JsonObject


class File_Management(
    File_Table_Management, Blob_File_Management, Local_File_Management
):
    def __init__(self):
        # self.bob = Bob()
        # self.settings = "lakehouse"
        self.bfm = None  # Blob_File_Management()
        self.lfm = None  # Local_File_Management()
        self.ftm = None  # File_Table_Management()
        self.context = None

    def content(self, context):
        self.context = context

        # An explicit local OutputPath takes precedence over Blob/Lakehouse settings
        # so a proof-of-concept run can never write to production storage.
        if self.context.OutputPath:
            self.lfm = Local_File_Management()
            self.lfm.set_context(self.context)

        elif self.context.StorageAccountContainerName:
            self.bfm = Blob_File_Management()
            self.bfm.set_context(self.context)

        elif self.context.get_LakehouseName():
            self.ftm = File_Table_Management()
            self.ftm.set_context(self.context)
        else:
            self.lfm = Local_File_Management()
            self.lfm.set_context(self.context)

    async def save(self, path: str, file_name: str, content):
        """
        param: path is the location to where the content will be saved
        param: file_name is the name of the file to be saved
        param: content is a dictionary that is converted to bytes and saved as the path and file name
        """
        print("What is the path?", path)
        print("What is the file name?", file_name)
        print("What is the content?", content)

        if not content:
            print("No content to save")
            return

        if not self.context:
            print("No settings found, make sure to pass in or set the settings object")
            return

        try:
            if isinstance(content, (dict, list)):
                content = json.dumps(content)
                content = content.encode("utf-8")
            else:
                content = content.encode("utf-8")

            # save file to storage
            if self.context.OutputPath:
                await self.lfm.save(path=path, file_name=file_name, content=content)
            elif self.context.StorageAccountContainerName:
                root = self.context.StorageAccountContainerRootPath
                if root:
                    path = f"{root}/{path}{file_name}"
                else:
                    path = f"{path}{file_name}"

                if os.environ.get("DRY_RUN", "").lower() in ("1", "true", "yes"):
                    print(f"\n{'=' * 60}")
                    print(f"[DRY RUN] Would write to blob: {path}")
                    print(f"{'=' * 60}")
                    try:
                        print(
                            json.dumps(json.loads(content.decode("utf-8")), indent=2)[
                                :4000
                            ]
                        )
                    except (ValueError, UnicodeError):
                        print(content[:4000])
                    print(f"{'=' * 60}\n")
                else:
                    await self.bfm.write_to_file(blob_name=path, content=content)
            elif self.context.LakehouseName:
                if self.context.on_fabric:
                    path = f"/lakehouse/default/Files/{self.context.PathInLakehouse}/{path}"
                else:
                    path = f"{self.context.LakehouseName}.Lakehouse/Files/{self.context.PathInLakehouse}/{path}"

                path = path.replace("//", "/")

                await self.ftm.write_json_to_file(
                    path=path, file_name=file_name, json_data=content
                )
            else:
                print("No storage location found")
                sys.exit()

        except Exception as e:
            self.context.logger.error("Error saving file to storage: %s", e, exc_info=e)
            print(f"Error: {e}")
            if self.context.OutputPath and isinstance(e, OSError):
                # Local writes must not look successful; Blob/Lakehouse keep log-only behaviour.
                raise

    async def save_snapshot(
        self, path: str, file_name: str, content: "JsonObject"
    ) -> None:
        """Write a collector JSON envelope, including an empty successful result.

        Unlike legacy ``save``, this method never logs payloads or suppresses
        storage failures. Paths must be relative module folders, so this method
        cannot overwrite root ``state.yaml``. A failed write can leave a partial
        file; consumers must require a parsed, finished manifest and a complete
        resource envelope before treating that resource as a valid observation.

        :param path: Relative module folder.
        :param file_name: JSON basename.
        :param content: Nonempty JSON envelope.
        :raises RuntimeError: If storage is unconfigured, dry-run, or fails.
        :raises ValueError: If the path, filename, or envelope is invalid.
        """
        self._validate_snapshot_target(path, file_name)
        if not isinstance(content, dict) or not content:
            raise ValueError("A nonempty JSON envelope is required")
        if self.context is None:
            raise RuntimeError("Snapshot storage is not configured")
        if os.environ.get("DRY_RUN", "").lower() in ("1", "true", "yes"):
            raise RuntimeError("Dry-run cannot commit collector snapshots")
        payload = json.dumps(content, allow_nan=False).encode("utf-8")
        try:
            if self.context.OutputPath:
                await self.lfm.save(path, file_name, payload)
            elif self.context.StorageAccountContainerName:
                root = self.context.StorageAccountContainerRootPath or ""
                blob_name = "/".join(
                    part.strip("/") for part in (root, path, file_name) if part
                )
                client = self.bfm._get_client(blob_name)
                await asyncio.to_thread(client.upload_blob, payload, overwrite=True)
            elif self.context.LakehouseName:
                prefix = self.context.PathInLakehouse or ""
                if self.context.on_fabric:
                    await Local_File_Management("/lakehouse/default/Files").save(
                        f"{prefix}/{path}".lstrip("/"), file_name, payload
                    )
                else:
                    remote_path = "/".join(
                        part.strip("/")
                        for part in (
                            f"{self.context.LakehouseName}.Lakehouse/Files",
                            prefix,
                            path,
                            file_name,
                        )
                        if part
                    )
                    client = self.ftm.fsc.get_file_client(remote_path)
                    await asyncio.to_thread(client.upload_data, payload, overwrite=True)
            else:
                raise RuntimeError("Snapshot storage is not configured")
        except (AzureError, OSError, ValueError, TypeError, RuntimeError) as exc:
            # SDK errors can contain URLs or credentials; do not propagate them.
            raise RuntimeError(
                f"Snapshot write failed ({type(exc).__name__})"
            ) from None

    async def read_snapshot(self, path: str, file_name: str) -> "JsonObject | None":
        """Read a collector's JSON control file without changing root state.

        :param path: Relative collector folder.
        :param file_name: JSON basename.
        :return: Parsed JSON object, or None only when the file is absent.
        :raises RuntimeError: If reading or parsing fails.
        :raises ValueError: If the target is not a module-local JSON file.
        """
        self._validate_snapshot_target(path, file_name)
        if self.context is None:
            raise RuntimeError("Snapshot storage is not configured")
        try:
            if self.context.OutputPath:
                raw = await self.lfm.read(path, file_name)
            elif self.context.StorageAccountContainerName:
                root = self.context.StorageAccountContainerRootPath or ""
                blob_name = "/".join(
                    part.strip("/") for part in (root, path, file_name) if part
                )
                client = self.bfm._get_client(blob_name)
                raw = await asyncio.to_thread(lambda: client.download_blob().readall())
            elif self.context.LakehouseName and self.context.on_fabric:
                raw = await Local_File_Management("/lakehouse/default/Files").read(
                    f"{self.context.PathInLakehouse or ''}/{path}".lstrip("/"),
                    file_name,
                )
            elif self.context.LakehouseName:
                remote_path = "/".join(
                    part.strip("/")
                    for part in (
                        f"{self.context.LakehouseName}.Lakehouse/Files",
                        self.context.PathInLakehouse or "",
                        path,
                        file_name,
                    )
                    if part
                )
                client = self.ftm.fsc.get_file_client(remote_path)
                raw = await asyncio.to_thread(lambda: client.download_file().readall())
            else:
                raise RuntimeError("Snapshot storage is not configured")
            if raw is None:
                return None
            result = json.loads(raw)
            if not isinstance(result, dict):
                raise TypeError("Expected JSON object")
            return result
        except ResourceNotFoundError:
            return None
        except (AzureError, OSError, ValueError, TypeError, RuntimeError) as exc:
            raise RuntimeError(
                f"Snapshot control read failed ({type(exc).__name__})"
            ) from None

    @staticmethod
    def _validate_snapshot_target(path: str, file_name: str) -> None:
        folder = PurePosixPath(path)
        if (
            folder.is_absolute()
            or not folder.parts
            or ".." in folder.parts
            or "\\" in path
            or PurePosixPath(file_name).name != file_name
            or "\\" in file_name
            or not file_name.endswith(".json")
        ):
            raise ValueError("A relative module folder and JSON basename are required")

    async def read(self, path="", file_name=""):
        """sumary_line

        Keyword arguments:
        argument -- description
        Return: returns a file
        """
        try:
            if self.context.OutputPath:
                content = await self.lfm.read(path=path, file_name=file_name)

            elif self.context.StorageAccountContainerName:
                root = self.context.StorageAccountContainerRootPath
                if root:
                    path = f"{root}/{path}{file_name}"
                else:
                    path = f"{path}{file_name}"

                print(
                    f"[READ] Attempting to read blob: container={self.context.StorageAccountContainerName} path={path}"
                )
                content = await self.bfm.read_from_file(blob_name=path)
                if content is None:
                    print(
                        f"[READ] Blob not found or empty: {path} — will create fresh state"
                    )
                else:
                    print(f"[READ] Successfully read blob: {path}")

            elif self.context.LakehouseName:
                # TODO: create a directory
                # TODO: upload/stream to location

                path = f"{self.context.LakehouseName}.Lakehouse/Files/{self.context.PathInLakehouse}/{path}"
                path = path.replace("//", "/")
                content = await self.ftm.read(file_name=file_name, path=path)
                if content is not None:
                    content = content.decode("utf-8")

                # await self.ftm.write_json_to_file(path=path, file_name=file_name, json_data=content)
            else:
                print("No storage location found")
                sys.exit()

            return content
        except Exception as e:
            # Re-raise so callers can tell a failed read from a genuinely missing file (None)
            self.context.logger.error(f"Error reading file: {e}")
            print(f"Error: {e}")
            raise
