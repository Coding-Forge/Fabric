import os
import yaml

class Local_File_Management:

    def __init__(self, root_path:str=None):
        self.root_path = root_path

    def set_context(self, context):
        self.root_path = context.OutputPath or "Data"
    
    async def save(self, path:str, file_name:str, content):
        """
        param: path is the location to where the content will be saved
        param: file_name is the name of the file to be saved
        param: content is a dictionary that is converted to bytes and saved as the path and file name
        """
        
        try:

            path = os.path.join(self.root_path, path)
            cwd = os.getcwd()
            os.makedirs(path, exist_ok=True)
            os.chdir(path)

            with open(file_name, "wb") as file:
                file.write(content)

            # change the directory back to the original
            os.chdir(cwd)
        except Exception as e:
            print(f"Error: {e}")
            exit()

    async def read(self, path: str = "", file_name: str = ""):
        file_path = os.path.join(self.root_path, path, file_name)
        if not os.path.exists(file_path):
            return None
        with open(file_path, "rb") as file:
            raw = file.read()
        if file_name.lower().endswith((".yaml", ".yml")):
            return yaml.safe_load(raw) or {}
        return raw.decode("utf-8")
