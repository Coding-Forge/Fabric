import os
import json
import posixpath
from env.utility.fabric import File_Table_Management
from env.utility.blob import Blob_File_Management
from env.utility.local import Local_File_Management
# from env.utility.helps import Bob



class File_Management(File_Table_Management, Blob_File_Management, Local_File_Management):

    def __init__(self):
        # self.bob = Bob()
        # self.settings = "lakehouse"
        self.bfm = None # Blob_File_Management()
        self.lfm = None #Local_File_Management()
        self.ftm = None #File_Table_Management()
        self.context = None

    def content(self, context):
        self.context = context

        if self.context.StorageAccountContainerName:
            self.bfm = Blob_File_Management()
            self.bfm.set_context(self.context)
        
        elif self.context.get_LakehouseName():
            self.ftm = File_Table_Management()
            self.ftm.set_context(self.context)
        else:
            self.lfm = Local_File_Management()
            self.lfm.set_context(self.context)

    def _blob_path(self, path: str, file_name: str) -> str:
        parts = [
            self.context.StorageAccountContainerRootPath or "",
            path or "",
            file_name or "",
        ]
        return posixpath.join(*(part.strip("/") for part in parts if part))

    def _lakehouse_path(self, path: str) -> str:
        lakehouse_path = self.context.PathInLakehouse or ""
        base = "/lakehouse/default/Files" if self.context.on_fabric else f"{self.context.LakehouseName}.Lakehouse/Files"
        return posixpath.join(base, lakehouse_path.strip("/"), path.strip("/"))

    async def save(self, path:str, file_name:str, content):
        """
        param: path is the location to where the content will be saved
        param: file_name is the name of the file to be saved
        param: content is a dictionary that is converted to bytes and saved as the path and file name
        """
        if not content:
            print("No content to save")
            return

        if not self.context:
            print("No settings found, make sure to pass in or set the settings object")
            return

        try:

            if isinstance(content, bytes):
                pass
            elif isinstance(content, dict) or isinstance(content, list):
                content = json.dumps(content)
                content = content.encode('utf-8')
            else:
                content = content.encode('utf-8')

        #save file to storage
            if self.context.StorageAccountContainerName:
                path = self._blob_path(path, file_name)

                if os.environ.get("DRY_RUN", "").lower() in ("1", "true", "yes"):
                    print(f"\n{'='*60}")
                    print(f"[DRY RUN] Would write to blob: {path}")
                    print(f"{'='*60}")
                    try:
                        print(json.dumps(json.loads(content.decode("utf-8")), indent=2)[:4000])
                    except Exception:
                        print(content[:4000])
                    print(f"{'='*60}\n")
                else:
                    await self.bfm.write_to_file(blob_name=path, content=content)
            elif self.context.OutputPath:
                await self.lfm.save(path=path, file_name=file_name, content=content)    
            elif self.context.LakehouseName:
                path = self._lakehouse_path(path)
                await self.ftm.write_json_to_file(path=path, file_name=file_name, json_data=content)
            else:
                print("No storage location found")
                exit()

        except Exception as e:
            self.context.logger.error("Error saving file to storage")
            print(f"Error: {e}")


    async def read(self, path="", file_name=""):
        """sumary_line
        
        Keyword arguments:
        argument -- description
        Return: returns a file
        """
        try:

            if self.context.StorageAccountContainerName:
                path = self._blob_path(path, file_name)

                print(f"[READ] Attempting to read blob: container={self.context.StorageAccountContainerName} path={path}")
                content = await self.bfm.read_from_file(blob_name=path)
                if content is None:
                    print(f"[READ] Blob not found or empty: {path} - will create fresh state")
                else:
                    print(f"[READ] Successfully read blob: {path}")
                
            elif self.context.OutputPath:
                content = await self.lfm.read(path=path, file_name=file_name)
            
            elif self.context.LakehouseName:
                path = self._lakehouse_path(path)
                content = await self.ftm.read(file_name=file_name, path=path)
                if content is not None:
                    content = content.decode('utf-8')

            
                # await self.ftm.write_json_to_file(path=path, file_name=file_name, json_data=content)
            else:
                print("No storage location found")
                exit()

            return content
        except Exception as e:
            self.context.logger.error("Error reading file")
            print(f"Error: {e}")
