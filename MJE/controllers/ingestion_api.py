from fastapi import APIRouter
from agent.ingestion import IngestionAgent
from agent.extraction import ExtractionAgent
from agent.orchestrator import OrchestratorAgent
from agent.approver import ApproverAgent
from dto.agent_parameters import ApproverAgentParameter
from dto.agent_parameters import IngetionAgentParameter, OrchestratorAgentParameter, ExtractionAgentParameter
from dto.outbound_request import ExtractedDataModelDTO
from dto.request_dtos import ExtractedMailDetailsDTO, Test, ApprovalTriggerDTO
from database.services.work_queue_service import WorkQueueService
from database.transaction_manager import TransactionManager
from utility.constants import AGENT_TYPE, EMAIL_TRIGGER, MANUAL_TRIGGER
from utility.logger import logger
from semantic_kernel.functions import KernelArguments
from database.database_manager import  SessionFactory

router = APIRouter()

@router.post("/processBusinessRule/")
async def extractInformaton(data: list[ExtractedDataModelDTO]):
    logger.info(f"The request  received {data}")
    out_put=[]
    return out_put
    
@router.post("/manual/")
async def manual(data: Test):
    logger.info(f"The request  received {data}")
    try:
        orchestrator = OrchestratorAgent(trigger_type=EMAIL_TRIGGER,case_id=data.caseId)
        orchestratorAgentParameter = OrchestratorAgentParameter(AGENT_TYPE.ENRICHMENT,data)
       
        logger.info(f"The request  received2 ")
        await orchestrator.auditable_process(arguments=orchestratorAgentParameter)
    except Exception as e:
       logger.error(f"Error occurred {e}", exc_info=True)
    return {"data": data, "q": 'received'}       

@router.post("/extraction/")
async def extract(data: ExtractedMailDetailsDTO):
    logger.info(f"The request  received {data}")
    try:
        extraction = ExtractionAgent(trigger_type=EMAIL_TRIGGER, case_id=data.caseId)
        logger.info(f"eml_file_path= {data.emlFilePath}")
        logger.info(f"attachment_file_path= {data.attachments}")
        extractionAgentParameter = ExtractionAgentParameter(eml_file_path=data.emlFilePath, attachment_file_path=data.attachments)
        response = await extraction.auditable_process(arguments=extractionAgentParameter)
        return {"Status": "Success", "Message": response}
    except Exception as e:
       logger.error(f"Error occurred {e}", exc_info=True)
       return {"Status": "Fail", "Message": e}
    

@router.post("/email/")
async def ingest(data: ExtractedMailDetailsDTO):
    logger.info(f"The request  received {data}")
    try:
        

        
        orchestrator = OrchestratorAgent(trigger_type=EMAIL_TRIGGER, case_id=data.caseId, req=data)
        orchestratorAgentParameter = OrchestratorAgentParameter(start_agent=AGENT_TYPE.INGESTION_AGENT)
        await orchestrator.auditable_process(arguments=orchestratorAgentParameter)

    except Exception as e:                                                                
       logger.error(f"Error occurred {e}", exc_info=True)
    return {"Status": "Success", "Message": 'received'}

@router.post("/trigger/agent_workflow/") 
async def trigger_agent_workflow(data: ExtractedMailDetailsDTO):
    logger.info(f"The request received for agent workflow trigger: {data}")
    try:
        tm = TransactionManager(SessionFactory)
        wq_service = WorkQueueService(tm)
        latest_wq = wq_service.get_latest_work_queue_by_case_id(data.caseId)
        logger.info(f"Latest work queue: {latest_wq}")

        if not latest_wq:
            orchestrator = OrchestratorAgent(trigger_type=MANUAL_TRIGGER, case_id=data.caseId, req=data)
            orchestrator_param = OrchestratorAgentParameter(start_agent=AGENT_TYPE.INGESTION_AGENT)
            await orchestrator.auditable_process(arguments=orchestrator_param)

            return {"Status": "Success", "Message": f"Orchestrator started for case {data.caseId} from agent{AGENT_TYPE.INGESTION_AGENT} "}
            
        else:
            logger.info(f"Existing workflow found for case {data.caseId}, latest work queue status: {latest_wq.status}, stage: {latest_wq.stage}")
            start_agent = None
            # logger.info(f"Agent does not exist {latest_wq.stage} ")
            logger.info(f"wq found {latest_wq.status}")
            if latest_wq.status in ["Started", "Error"]:
                orchestrator = OrchestratorAgent(trigger_type=MANUAL_TRIGGER, case_id=data.caseId, req=data)
                start_agent = orchestrator.get_agent_type_from_stage(latest_wq.stage)
                logger.info(f"start ajent{start_agent}")
            elif latest_wq.status == "Completed":
                orchestrator = OrchestratorAgent(trigger_type=MANUAL_TRIGGER, case_id=data.caseId, req=data)
                start_agent = orchestrator.get_next_agent(latest_wq.stage)

            if not start_agent:
                return {"Status": "Success", "Message": f"Workflow for case {data.caseId} is already complete or stage is unknown."}

            orchestrator = OrchestratorAgent(trigger_type=MANUAL_TRIGGER, case_id=data.caseId, req=data, wq_id=latest_wq.id)
            orchestrator_param = OrchestratorAgentParameter(start_agent=start_agent)
            await orchestrator.auditable_process(arguments=orchestrator_param)

        return {"Status": "Success", "Message": f"Orchestrator started for case {data.caseId} from agent {start_agent}"}
    except Exception as e:
        logger.error(f"Error occurred in agent_workflow trigger: {e}", exc_info=True)
        return {"Status": "Fail", "Message": str(e)}      


@router.post("/approval/test")
async def approval_test(dto: ApprovalTriggerDTO):
    """Trigger ApproverAgent Test API"""
    try:
        params = ApproverAgentParameter(
            wq_id=dto.wq_id,
        )
        agent = ApproverAgent(case_id=str(dto.wq_id), trigger_type=AGENT_TYPE.APPROVER_AGENT.value)
        agent.wq_id = dto.wq_id
        result = await agent.auditable_process(params)
        if result.get("created_jes"):
            agent.case_id = str(result["created_jes"][0]["case_id"])
        
        return {"Status": "Success", "Message": f"Approval workflow executed. Created {len(result['created_jes'])} journal entries for {len(result['created_jes'])} case_ids.", "result": result}
    except Exception as e:
        logger.error(f"Approval test error: {e}", exc_info=True)
        return {"Status": "Fail", "Message": str(e)}
