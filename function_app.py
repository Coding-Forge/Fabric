import asyncio
import logging

import azure.functions as func

from app.monitor import main as Monitor

app = func.FunctionApp()

# Runs once daily at 02:00 UTC. Azure Functions uses 6-field NCRONTAB:
# {second} {minute} {hour} {day} {month} {day-of-week}
# To change the time, adjust the hour field (e.g. "0 0 6 * * *" = 6:00 AM UTC)
@app.schedule(schedule="0 0 2 * * *", arg_name="myTimer", run_on_startup=True,
              use_monitor=False) 
def Fabric_Monitor(myTimer: func.TimerRequest) -> None:
    if myTimer.past_due:
        logging.info('The timer is past due!')
    
    asyncio.run(Monitor())
