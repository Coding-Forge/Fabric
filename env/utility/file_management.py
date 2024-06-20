import json
from env.utility.fabric import File_Table_Management
from env.utility.blob import Blob_File_Management
from env.utility.local import Local_File_Management
# from env.utility.helps import Bob



class File_Management(File_Table_Management, Blob_File_Management, Local_File_Management):

    def __init__(self):
        # self.bob = Bob()
        # self.settings = "lakehouse"
        self.bfm = Blob_File_Management()
        self.lfm = Local_File_Management()
        self.ftm = File_Table_Management()
        self._settings = None
        pass


    def content(self, context):
        self._settings = context
        

    async def save(self, path:str, file_name:str, content):
        """
        param: path is the location to where the content will be saved
        param: file_name is the name of the file to be saved
        param: content is a dictionary that is converted to bytes and saved as the path and file name
        """

        if not self._settings:
            print("No settings found, make sure to pass in or set the settings object")
            return

        try:

            if isinstance(content, dict) or isinstance(content, list):
                content = json.dumps(content)
                content = content.encode('utf-8')
            else:
                content = content.encode('utf-8')

        #save file to storage
            if self._settings.StorageAccountContainerName:
                root = self._settings.StorageAccountContainerRootPath
                if root:
                    path = f"{root}/{path}{file_name}"
                else:
                    path = f"{path}{file_name}"
                    
                #print(path)
                await self.bfm.write_to_file(blob_name=path, content=content)
            elif self._settings.OutputPath:
                await self.lfm.save(path=path, file_name=file_name, content=content)    
            elif self._settings.LakehouseName:
                path = f"{self._settings.LakehouseName}.Lakehouse/Files/{self._settings.PathInLakehouse}/{path}"   
                path = path.replace("//","/")
                
                await self.ftm.write_json_to_file(path=path, file_name=file_name, json_data=content)
            else:
                print("No storage location found")
                exit()

        except Exception as e:
            print(f"Error: {e}")


    async def read(self, path="", file_name=""):
        """sumary_line
        
        Keyword arguments:
        argument -- description
        Return: returns a file
        """
        try:

            if self._settings.StorageAccountContainerName:
                root = self._settings.StorageAccountContainerRootPath
                if root:
                    path = f"{root}/{path}{file_name}"
                else:
                    path = f"{path}{file_name}"

                content = await self.bfm.read_from_file(blob_name=path)
                
            elif self._settings.OutputPath:
                await self.lfm.save(path=path, file_name=file_name, content=content)    
            
            elif self._settings.LakehouseName:
                #TODO: create a directory
                #TODO: upload/stream to location
                
                path = f"{self._settings.LakehouseName}.Lakehouse/Files/{self._settings.PathInLakehouse}/{path}"   
                path = path.replace("//","/")
                content = await self.ftm.read(file_name=file_name, path=path)
                content = content.decode('utf-8')

            
                # await self.ftm.write_json_to_file(path=path, file_name=file_name, json_data=content)
            else:
                print("No storage location found")
                exit()

            return content
        except Exception as e:
            print(f"Error: {e}")
