import json
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

        print("storage account container name", self.context.StorageAccountContainerName)
        if self.context.StorageAccountContainerName:
            self.bfm = Blob_File_Management()
            self.bfm.set_context(self.context)
        
        elif self.context.get_LakehouseName():
            self.ftm = File_Table_Management()
            self.ftm.set_context(self.context)
        else:
            self.lfm = Local_File_Management()
            self.lfm.set_context(self.context)

    async def save(self, path:str, file_name:str, content):
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

            if isinstance(content, dict) or isinstance(content, list):
                content = json.dumps(content)
                content = content.encode('utf-8')
            else:
                content = content.encode('utf-8')


        #save file to storage
            if self.context.StorageAccountContainerName:
                root = self.context.StorageAccountContainerRootPath
                if root:
                    path = f"{root}/{path}{file_name}"
                else:
                    path = f"{path}{file_name}"
                    
                print("What is the content?", content)
                await self.bfm.write_to_file(blob_name=path, content=content)
            elif self.context.OutputPath:
                await self.lfm.save(path=path, file_name=file_name, content=content)    
            elif self.context.LakehouseName:
                if self.context.on_fabric:
                    path = f"/lakehouse/default/Files/{self.context.PathInLakehouse}/{path}"
                else:
                    path = f"{self.context.LakehouseName}.Lakehouse/Files/{self.context.PathInLakehouse}/{path}"                   

                path = path.replace("//","/")
                
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
                root = self.context.StorageAccountContainerRootPath
                if root:
                    path = f"{root}/{path}{file_name}"
                else:
                    path = f"{path}{file_name}"

                content = await self.bfm.read_from_file(blob_name=path)
                
            elif self.context.OutputPath:
                await self.lfm.save(path=path, file_name=file_name, content=content)    
            
            elif self.context.LakehouseName:
                #TODO: create a directory
                #TODO: upload/stream to location
                
                path = f"{self.context.LakehouseName}.Lakehouse/Files/{self.context.PathInLakehouse}/{path}"   
                path = path.replace("//","/")
                content = await self.ftm.read(file_name=file_name, path=path)
                content = content.decode('utf-8')

            
                # await self.ftm.write_json_to_file(path=path, file_name=file_name, json_data=content)
            else:
                print("No storage location found")
                exit()

            return content
        except Exception as e:
            self.context.logger.error("Error reading file")
            print(f"Error: {e}")
