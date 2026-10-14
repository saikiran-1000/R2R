from agent.agent import AgentInterface
from database.database_manager import SessionFactory
from database.db_models.email import EmailMaster
from database.services.email_service import EmailMasterService
from database.transaction_manager import TransactionManager
from dto.agent_parameters import IngetionAgentParameter
from dto.request_dtos import ExtractedMailDetailsDTO
from utility.audit import _create_work_queue
from utility.constants import AGENT_TYPE
from utility.logger import logger
from database.transaction_manager import TransactionManager
from database.services.work_queue_service import WorkQueueService


class IngestionAgent(AgentInterface):
    
    def __init__(self,case_id:str,trigger_type:str, email_master=None ):
        super().__init__(case_id,agent_name=AGENT_TYPE.INGESTION_AGENT.value) 
        self.trigger_type=trigger_type  
        self.transaction_manager = TransactionManager(SessionFactory)
        self.email_master_service= EmailMasterService(self.transaction_manager)
        self.email_master=email_master
           
    
    # @record_case_as_wq( AGENT_TYPE.INGESTION_AGENT.value)
    async def auditable_process(self, arguments: IngetionAgentParameter)->EmailMaster:  

        self.req=arguments.req
        logger.info(f"Email data received for ingestion:\n {self.req}")
        region = self.transaction_manager.region_master_repository.find_by_folder_name(
            self.req.folderName.split("#")[-1]
            if self.req.folderName and "#" in self.req.folderName
            else self.req.folderName
        )
        self.region_id = region.id  
        email_data: ExtractedMailDetailsDTO = arguments.req 
        email_master = EmailMaster.from_dto(email_data, self.region_id)
        
        # Save EmailMaster
        self.email_master = self.email_master_service.save_email_master(obj_persist=email_master) 
        region_id = self.region_id

        work_queue_service = WorkQueueService(self.transaction_manager)
        self.wq = _create_work_queue("Started", AGENT_TYPE.INGESTION_AGENT.value, work_queue_service, region_id=region_id, email_master_id=self.email_master.id)
        self.wq_id=self.wq.id
        return self.email_master
        
