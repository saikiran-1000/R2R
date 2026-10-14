
from fastapi import FastAPI,Request
from controllers.ingestion_apis import router as ingestion_router
from starlette.middleware.base import BaseHTTPMiddleware
from database.database_manager import engine



from utility.audit_manager import lifespan
from utility.logger import logger,case_id_var
from database.database_manager import Base

# Ensure all DB models are imported so SQLAlchemy registers them before create_all()
from database.db_models.approval_rules import ApprovalRules
from database.db_models.designations import Designations
from database.db_models.email import EmailContent, EmailMaster
from database.db_models.extraction import ExtractionOutput
from database.db_models.journal_entries import JournalEntry
from database.db_models.journal_entry_type import JournalEntryType
from database.db_models.process_output_model import ProcessOutputModel
from database.db_models.region_master import RegionMaster
from database.db_models.requests import ApprovalRequest
from database.db_models.work_queue import WorkQueue
from database.db_models.work_queue_audit import WorkQueueAudit

Base.metadata.create_all(engine) # Initialize the database schema and pool


class SelectiveMiddleware(BaseHTTPMiddleware):
    async def dispatch(self,request: Request, call_next):
      
      """Only purpose is to extract the uniqie ID from the request and attach with the case id 
      for logging.It will only inject case_id for/email,/manual api not for other APIs.Here /docs and /openapi.json is swagger apis.
      """
      logger.info(f"Request path is {request.url.path=}")
      if request.url.path.startswith("/docs") or request.url.path.startswith("/openapi.json"):
           return await call_next(request)
          
      payload = await request.json()
      case_id = payload.get("caseId")
      token = case_id_var.set(case_id)
      # Optional: Log the start of the request
      logger.info("Starting request processing")
      try:
        response = await call_next(request)
        return response
      finally:
        # This unbinding happens automatically, but it's good practice
        # to show it for clarity in case you need to manage context manually.
        logger.info("Finished request processing")
        case_id_var.reset(token)
       
          



app = FastAPI(lifespan=lifespan)


app.include_router(ingestion_router)

app.add_middleware(SelectiveMiddleware)


      
