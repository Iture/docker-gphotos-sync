from fastapi import FastAPI,Request,HTTPException, BackgroundTasks
import asyncio

from configparser import ConfigParser
import logging
import datetime



is_running = False
app = FastAPI()

cfg = ConfigParser()
cfg.read('config/gphotos-sync.ini')
logging.basicConfig(level=logging.INFO,format='[%(name)s] - %(levelname)s - %(message)s')

logger=logging.getLogger('main')
logger.critical('Starting')

status={}
class Runner:
    def __init__(self) -> None:
        self.enabled = True
        self.is_running=False
        self.status={}
        pass
    async def Process(self,type='Full'):
        if self.is_running:
            logger.error("Sync already running")
            return
        logger.info("Starting sync:%s" % type)
        self.is_running = True
        self.status['job_started'] = str(datetime.datetime.now())
        self.status['job_last_run'] = self.status.get('job_finished',None)
        self.status['job_finished'] = None
        cmd_line = 'for i in {1..15}; do sleep 1;echo $i ; done'
        for i in range(0,10):
            logger.info (i)
            await asyncio.sleep(1) 
        self.status['job_finished'] = str(datetime.datetime.now())
        self.is_running = False
        logger.info("Finished sync:%s" % type)

    async def get_status(self):
        self.status['running'] = self.is_running
        return self.status
    
    async def periodic_sync(self):
        while self.enabled:
            await self.Process('Full')
            await asyncio.sleep(30)



runner = Runner()

@app.on_event('startup')
async def startup_event_setup() -> None:
    asyncio.create_task(runner.periodic_sync())
    pass
@app.get("/")
async def root():
    return {"message": "Hello World"}

@app.get('/sync_all')
async def get_sync_all():
    asyncio.create_task(runner.Process('Full'))
    return await runner.get_status()

@app.get('/sync_albums')
async def get_sync_albums():
    asyncio.create_task(runner.Process('Albums'))
    return await runner.get_status()



@app.get('/status')
async def get_status():
    return await runner.get_status()
