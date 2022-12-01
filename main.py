from fastapi import FastAPI
import asyncio
import os
import logging
import datetime

is_running = False
app = FastAPI()

logging.basicConfig(level=logging.DEBUG,format='[%(name)s] - %(levelname)s - %(message)s')
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
        async def read_stdout(stdout):
            while True:
                buf = await stdout.readline()
                if not buf:
                    break
                logger.debug(buf.decode().strip())
        async def read_stderr(stderr):
            while True:
                buf = await stderr.readline()
                if not buf:
                    break
                logger.error(buf.decode().strip())

        if self.is_running:
            logger.error("Sync already running")
            return
        logger.info("Starting sync:%s" % type)
        self.is_running = True
        self.status['job_started'] = str(datetime.datetime.now())
        if type == 'Full':
            cmd_line = 'gphotos-sync /storage'
        elif type == 'Albums':
            cmd_line = 'gphotos-sync --skip-files /storage'
        try:
            proc = await asyncio.create_subprocess_shell(cmd=cmd_line,stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.PIPE)
            await asyncio.gather(
                read_stderr(proc.stderr),
                read_stdout(proc.stdout)
            )
        except Exception as e:
            logger.error(e)

        self.status['job_started'] = None
        self.status['job_last_run'] = str(datetime.datetime.now())
        self.is_running = False
        logger.info("Finished sync:%s" % type)

    async def get_status(self):
        self.status['running'] = self.is_running
        return self.status
    
    async def periodic_sync(self):
        while self.enabled:
            await self.Process('Full')
            delay = os.getenv('SYNC_INTERVAL')
            if not delay:
                delay = 30
            await asyncio.sleep(int(delay))

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
