from fastapi import FastAPI,Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse
import asyncio
import os
import logging
import datetime
import aiopath,aiosqlite

app = FastAPI()
app.mount("/static", StaticFiles(directory='static'),name='static')
templates = Jinja2Templates(directory="templates")
LOGLEVEL = os.environ.get('LOGLEVEL', 'INFO').upper()
logging.basicConfig(level=LOGLEVEL,format='[%(name)s] - %(levelname)s - %(message)s')
logger=logging.getLogger('main')
logger.critical('Starting')

status={}
class Runner:
    def __init__(self) -> None:
        self.enabled = True
        self.is_running=False
        self.status={}
        self.sync_log=[]
        self.metadata = {}
        pass
    async def Process(self,type='Full'):
        async def read_stdout(stdout):
            while True:
                buf = await stdout.readline()
                if not buf:
                    break
                logger.debug(buf.decode().strip())
                self.sync_log+=[buf.decode().strip()]
        async def read_stderr(stderr):
            while True:
                buf = await stderr.readline()
                if not buf:
                    break
                logger.error(buf.decode().strip())
                self.sync_log+=[buf.decode().strip()]

        if self.is_running:
            logger.error("Sync already running")
            return
        logger.info("Starting sync:%s" % type)
        self.sync_log=[]
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
            await self.filesystem_sync()
        except Exception as e:
            logger.error(e)

        self.status['job_started'] = None
        self.status['job_last_run'] = str(datetime.datetime.now())
        self.is_running = False
        logger.info("Finished sync:%s" % type)

    async def get_status(self):
        self.status['running'] = self.is_running
        self.status['log']=self.sync_log
        return self.status
    
    async def periodic_sync(self, delay = 300):
        while self.enabled:
            await self.Process('Full')
            await asyncio.sleep(delay)

    async def filesystem_sync(self):
        logger.info('Reading state from gphotos')
        scan_fs = False
        try:
            async with aiosqlite.connect('/storage/gphotos.sqlite') as db:
                
                query = """select 'photos',count(*) from SyncFiles
                            UNION ALL
                            select 'albums',count(*) from Albums
                            UNION ALL 
                            select 'last_index', LastIndex from Globals
                        """
                async with db.execute(query) as cursor:
                    async for row in cursor:
                        if row[1] != self.status.get(row[0],0): scan_fs = True #something has changed
                        self.status[row[0]]=row[1]
                
                async with db.execute('SELECT AlbumName,Size,StartDate from Albums WHERE Downloaded = 1') as cursor:
                    async for row in cursor:
                        if not row[0] in self.metadata:
                            self.metadata[row[0]]={}
                            self.metadata[row[0]]['update']=str(row[2])
                        self.metadata[row[0]]['size']=row[1]
                        self.metadata[row[0]]['start_date']=str(row[2])
        except Exception as e:
            logger.error("Problem with scanning database: %s" % e)  
        if scan_fs:  
            logger.debug("Reading paths on disk")
            try:
                album_path = aiopath.AsyncPath('/storage/albums')
                albums_on_disk = [f async for f in album_path.glob("**")]
            
                for album_on_disk in albums_on_disk:
                    logger.debug("Checking:%s" % str(album_on_disk))
                    for album_name in self.metadata:
                        if album_name in str(album_on_disk):
                            self.metadata[album_name]['path']=str(album_on_disk)
                            if not 'files' in self.metadata[album_name]:
                                    logger.debug("listing files in :%s" % str(album_on_disk))
                                    self.metadata[album_name]['files']={}
                                    files_in_album = [f async for f in album_on_disk.glob("*")]
                                    for file in files_in_album:
                                        self.metadata[album_name]['files'][file.name] = {
                                            'path' : str(file) ,
                                        }
            except Exception as e:
                logger.error("Problem with directory scan:%s" % e)
        pass
runner = Runner()

@app.on_event('startup')
async def startup_event_setup() -> None:
    interval = int(os.getenv('SYNC_INTERVAL')) if os.getenv('SYNC_INTERVAL') else 300
    asyncio.create_task(runner.periodic_sync(interval))
    pass
@app.get("/", response_class=HTMLResponse)
async def root(request: Request):
    return templates.TemplateResponse('index.j2',{'request': request,'status':await runner.get_status()})
@app.get("/sync/{type}")
async def get_sync(request: Request, type="all"):
    if type == 'all':
        asyncio.create_task(runner.Process('Full'))
    elif type == 'albums':
        asyncio.create_task(runner.Process('Albums'))
    return await runner.get_status()

@app.get("/albums")
async def get_albums():
    return runner.metadata
@app.get('/status')
async def get_status():
    return await runner.get_status()
