import asyncio
import os


class Local_File_Management:

    def __init__(self, root_path:str=None):
        self.root_path = root_path
        self.context = None

    def set_context(self, context):
        """Bind the context and default the root path to the configured output path."""
        self.context = context
        if self.root_path is None:
            self.root_path = getattr(context, "OutputPath", None)

    async def save(self, path:str, file_name:str, content):
        """
        Write bytes to ``<root_path>/<path>/<file_name>`` without changing the process working directory.

        :param path: Location, relative to the root path, where the content is saved.
        :param file_name: Name of the file to write.
        :param content: Bytes to write.
        :raises OSError: If the directory or file cannot be written.
        """
        directory = os.path.abspath(os.path.join(self.root_path or "", path))
        file_path = os.path.join(directory, file_name)

        def _write() -> None:
            os.makedirs(directory, exist_ok=True)
            with open(file_path, "wb") as file:
                file.write(content)

        try:
            await asyncio.to_thread(_write)
        except OSError as e:
            print(f"Error: {e}")
            raise

    async def read(self, path: str, file_name: str) -> str | None:
        """Read ``<root_path>/<path>/<file_name>`` as UTF-8 text.

        :param path: Location, relative to the root path.
        :param file_name: Name of the file to read.
        :return: The file text, or ``None`` when the file does not exist.
        :raises OSError: If the file exists but cannot be read.
        """
        file_path = os.path.join(os.path.abspath(os.path.join(self.root_path or "", path)), file_name)

        def _read() -> str | None:
            try:
                with open(file_path, encoding="utf-8") as file:
                    return file.read()
            except FileNotFoundError:
                return None

        return await asyncio.to_thread(_read)