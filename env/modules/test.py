import asyncio

async def main(context=None):
    """
    Activity    
    """

    config = await context.read(file_name="state.yaml")
    print(config)
    
if __name__ == "__main__":
    asyncio.run(main())
