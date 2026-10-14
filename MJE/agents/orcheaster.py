from fastapi import Request
from agent.ingestion import IngestionAgent
from database.services.extraction_output_service import ExtractionOutputService
from database.db_models.work_queue import WorkQueue
from database.services.work_queue_service import WorkQueueService
from utility.audit import record_case_as_wq
from agent.agent import AgentInterface
from semantic_kernel import Kernel

from semantic_kernel.functions import KernelArguments
from agent.anomaly_detection import AnomalyDetectionAgent
from agent.approver import ApproverAgent
from agent.extraction import ExtractionAgent
from agent.publisher import PublisherAgent
from agent.enrichment import EnrichmentAgent
from database.database_manager import  SessionFactory
from database.db_models.email import EmailMaster
from database.services.email_service import EmailMasterService
from database.transaction_manager import TransactionManager
from utility.constants import AGENT_TYPE
from dto.agent_parameters import AgentParameter, AnomalyAgentParameter, ApproverAgentParameter, ExtractionAgentParameter, IngetionAgentParameter, PublisherAgentParameter, EnrichmentAgentParameter, OrchestratorAgentParameter
from database.services.email_service import EmailMasterService
from agent.base_agent import BaseAgent


class OrchestratorAgent(AgentInterface, BaseAgent):
    """This Agent is a supervisor agent and do the orchestration"""

    def __init__(
        self, trigger_type: str, case_id: str, req: Request = None, wq_id=None
    ):
        super().__init__(case_id, agent_name="Orchestrator")
        self.trigger_type = trigger_type
        self.kernel = Kernel()
        self.wq_id = wq_id
        self.transaction_manager = TransactionManager(SessionFactory)
        self.extraction_output_service = ExtractionOutputService(
            self.transaction_manager
        )
        self.email_master_service = EmailMasterService(self.transaction_manager)
        self.work_queue_service = WorkQueueService(self.transaction_manager)
        self.req = req
        self.case_id = case_id
        self.email_master = None
        self.__register_agents()

    def __register_agents(self):
        """Create Instance of semantic kernel and register All Agents/plugins"""
        # Create and save the work queue entry
        self.ingestion = IngestionAgent(
            case_id=self.case_id, trigger_type=AGENT_TYPE.INGESTION_AGENT.value
        )
        self.kernel.add_plugin(self.ingestion, "ingestion")
        self.extraction = ExtractionAgent(
            case_id=self.case_id, trigger_type=AGENT_TYPE.EXTRACTION_AGENT.value
        )
        self.kernel.add_plugin(self.extraction, "extraction")
        self.enrichment = EnrichmentAgent(
            case_id=self.case_id, trigger_type=AGENT_TYPE.ENRICHMENT_AGENT.value
        )
        self.kernel.add_plugin(self.enrichment, "enrichment")
        '''self.kernel.add_plugin(
            AnomlalyDetectionAgent(
                case_id=self.case_id,
                trigger_type=AGENT_TYPE.ANOMALY_DETECTION_AGENT.value,
            ),
            "anomaly_detection",
        )'''
        self.anomaly_detection = AnomalyDetectionAgent(
            case_id=self.case_id,trigger_type=AGENT_TYPE.ANOMALY_DETECTION_AGENT.value
        )
        self.kernel.add_plugin(self.enrichment, "anomaly_detection")
        self.kernel.add_plugin(
            ApproverAgent(
                case_id=self.case_id, trigger_type=AGENT_TYPE.APPROVER_AGENT.value
            ),
            "approver",
        )
        self.kernel.add_plugin(
            PublisherAgent(
                case_id=self.case_id, trigger_type=AGENT_TYPE.PUBLISHER_AGENT.value
            ),
            "publisher",
        )

    async def __call_ingestion_agent(self) -> None:
    
        ingestion_agent_parameter = IngetionAgentParameter(
            AGENT_TYPE.INGESTION_AGENT, req=self.req
        )
        await self.kernel.invoke(
            plugin_name="ingestion",
            function_name="process",
            arguments=KernelArguments(parameters=ingestion_agent_parameter),
        )
        self.wq = self.ingestion.wq
        self.wq_id = self.ingestion.wq_id
        self.email_master = self.ingestion.email_master

    async def __call_enrichment_agent(self) -> None:
        self.enrichment.wq_id = self.wq_id
        rule_agent_parameter = EnrichmentAgentParameter()
        await self.kernel.invoke(
            plugin_name="enrichment",
            function_name="process",
            arguments=KernelArguments(parameters=rule_agent_parameter),
        )

    async def __call_approval_agent(self) -> None:
        approver_agent_parameter = ApproverAgentParameter()
        await self.kernel.invoke(
            plugin_name="approver",
            function_name="process",
            arguments=KernelArguments(parameters=approver_agent_parameter),
        )

    async def __call_publisher_agent(self) -> None:
        publisher_agent_parameter = PublisherAgentParameter()
        await self.kernel.invoke(
            plugin_name="publisher",
            function_name="process",
            arguments=KernelArguments(parameters=publisher_agent_parameter),
        )

    async def __call_anomaly_detection_agent(self) -> None:
        anomaly_detection_agent_parameter = AnomalyAgentParameter()
        await self.kernel.invoke(
            plugin_name="anomaly_detection",
            function_name="process",
            arguments=KernelArguments(parameters=anomaly_detection_agent_parameter),
        )

    async def __call_extraction_agent(self, email_master: EmailMaster = None) -> None:
        self.extraction.wq_id = self.wq_id
        self._log_info(
            f"Orchestrator calling Extraction Agent with wq_id {self.wq_id} "
        )
        extraction_agent_parameter = ExtractionAgentParameter(
            case_id=self.case_id, email_master=email_master, wq=self.wq
        )
        await self.kernel.invoke(
            plugin_name="extraction",
            function_name="process",
            arguments=KernelArguments(parameters=extraction_agent_parameter),
        )

    def get_agent_type_from_stage(self, stage: str) -> str:
        match stage:
            case "INGESTION":
                return AGENT_TYPE.INGESTION_AGENT
            case "EXTRACTION":
                return AGENT_TYPE.EXTRACTION_AGENT
            case "ENRICHMENT":
                return AGENT_TYPE.ENRICHMENT_AGENT
            case "ANOMALY_DETECTION":
                return AGENT_TYPE.ANOMALY_DETECTION_AGENT
            case "APPROVAL":
                return AGENT_TYPE.APPROVER_AGENT
            case "PUBLISHER":
                return AGENT_TYPE.PUBLISHER_AGENT
            case _:
                return AGENT_TYPE.EXTRACTION_AGENT

    def get_next_agent(self, current_stage: str) -> str:
        """Determines the next agent in the sequence."""
        sequence = [
            AGENT_TYPE.INGESTION_AGENT.value,
            AGENT_TYPE.EXTRACTION_AGENT.value,
            AGENT_TYPE.ENRICHMENT_AGENT.value,
            AGENT_TYPE.ANOMALY_DETECTION_AGENT.value,
            AGENT_TYPE.APPROVER_AGENT.value,
            AGENT_TYPE.PUBLISHER_AGENT.value,
        ]
        try:
            current_index = sequence.index(current_stage)
            if current_index + 1 < len(sequence):
                return sequence[current_index + 1]
            return None  # End of workflow
        except ValueError:
            return None  # Stage not in sequence

    # @record_case_as_wq( AGENT_TYPE.ORCHESTRATOR_AJENT.value)
    async def auditable_process(self, arguments: AgentParameter) -> None:
        """Orchestrator agent plays the role of orchestration and delegate the task in Order as
        1. Extraction agent
        2. Rule agent
        3. Annomaly detection agent
        4. Approver agent
        5. Posting Agent"""
        orchestrator_param: OrchestratorAgentParameter = arguments
        # email_master = orchestrator_param.email_master

        # If resuming a workflow, load the necessary context
        if orchestrator_param.start_agent != AGENT_TYPE.INGESTION_AGENT and self.wq_id:
            self.wq = self.work_queue_service.get_work_queue(self.wq_id)
            if self.wq and self.wq.email_id:
                self.email_master = (
                    await self.email_master_service.find_email_master_by_id(
                        self.wq.email_id
                    )
                )

        match orchestrator_param.start_agent:
            case AGENT_TYPE.INGESTION_AGENT:
                await self.__call_ingestion_agent()
                await self.__call_extraction_agent(email_master=self.email_master)
                await self.__call_enrichment_agent()
                await self.__call_anomaly_detection_agent()
                await self.__call_approval_agent()
                await self.__call_publisher_agent()

            case AGENT_TYPE.EXTRACTION_AGENT:
                await self.__call_extraction_agent(email_master=self.email_master)
                await self.__call_enrichment_agent()
                await self.__call_anomaly_detection_agent()
                await self.__call_approval_agent()
                await self.__call_publisher_agent()
            case AGENT_TYPE.ENRICHMENT_AGENT:
                await self.__call_enrichment_agent()
                await self.__call_anomaly_detection_agent()
                await self.__call_approval_agent()
                await self.__call_publisher_agent()
            case AGENT_TYPE.ANOMALY_DETECTION_AGENT:
                await self.__call_anomaly_detection_agent()
                await self.__call_approval_agent()
                await self.__call_publisher_agent()
            case AGENT_TYPE.APPROVER_AGENT:
                await self.__call_approval_agent()
                await self.__call_publisher_agent()
            case AGENT_TYPE.PUBLISHER_AGENT:
                await self.__call_publisher_agent()
            case _:
                self._log_info(
                    f"Agent does not exist {orchestrator_param.start_agent} "
                )
