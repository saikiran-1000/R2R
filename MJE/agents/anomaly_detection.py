import json
import requests
from dataclasses import dataclass
from typing import List, Optional
 
from utility.constants import AGENT_TYPE
from utility.audit import record_case_as_wq
from utility.logger import logger
 
from database.db_models.process_output_model import ProcessOutputModel
from database.database_manager import SessionFactory
from sqlalchemy.orm import Session
 
from agent.agent import AgentInterface
from agent.agents_exception import AnomalyDetectionError
from dto.agent_parameters import AgentParameter, AnomalyAgentParameter
 
 
@dataclass
class AnomalyJournal:
    company_code: Optional[str]
    journal_id: Optional[str]
    posting_date: Optional[str]
    created_by: Optional[str]
    journal_name: Optional[str]
    amount_credited: Optional[float]
    amount_debited: Optional[float]
    currency_code: Optional[str]
    gl_code: Optional[str]
    profit_center: Optional[str]
    cost_center: Optional[str]
    fiscal_period: Optional[str]
    document_date: Optional[str]
    document_id: Optional[str]
    country_code: Optional[str]
    account_name: Optional[str]
    conversion_rate: Optional[float]
 
 
class AnomalyDetectionAgent(AgentInterface):
    """Agent that retrieves R2R_PROCESS_OUTPUT_MODEL rows by wq_id,
    builds anomaly record objects, and posts them to MJAD API.
    """
 
    def __init__(self, case_id, trigger_type: str, wq_id: Optional[int] = None):
        super().__init__(case_id, trigger_type)
        self.wq_id = wq_id
        self.session_factory = SessionFactory
        self.actual_url = "http://54.144.109.20:8000/mjad_analysis"
 
    @record_case_as_wq(AGENT_TYPE.ANOMALY_DETECTION_AGENT.value)
    async def auditable_process(self, arguments: AgentParameter):
        """Main entrypoint for anomaly detection agent."""
        try:
            _ = AnomalyAgentParameter
        except Exception:
            pass
 
        records = self.get_records_by_wq()
        logger.info(f"Anomaly records fetched: {len(records)}")
 
        # Convert to API-expected format
        data_json = [self.map_record_to_api_format(r) for r in records]
 
        payload = {
            "Data": data_json,
            "AccountName": "Genpact",
            "DataType": "Current",  # or "Historical"
        }
 
        logger.info(f"Posting {len(data_json)} records to anomaly API...")
 
        try:
            logger.info(f"Payload being sent to API: {json.dumps(payload, indent=2)}")
            response = requests.post(self.actual_url, json=payload, timeout=60)
            response.raise_for_status()
            server_response = response.json()
            logger.info(f"Anomaly API response: {server_response}")
            return server_response
        except requests.RequestException as e:
            logger.error(f"Error calling anomaly API: {e}")
            raise AnomalyDetectionError(f"Error calling anomaly API: {e}")
 
    def map_record_to_api_format(self, record: AnomalyJournal) -> dict:
        """Map internal fields to API's expected human-readable keys."""
        return {
            "Company Code": record.company_code,
            "Journal ID": record.journal_id,
            "Posting Date": record.posting_date,
            "Created By": record.created_by,
            "Journal Name": record.journal_name,
            "Amount Credited": record.amount_credited,
            "Amount Debited": record.amount_debited,
            "Currency Code": record.currency_code,
            "GL Code": record.gl_code,
            "Profit Center": record.profit_center,
            "Cost Center": record.cost_center,
            "Fiscal Period": record.fiscal_period,
            "Document Date": record.document_date,
            "Document ID": record.document_id,
            "Country Code": record.country_code,
            "Account Name": record.account_name,
            "Conversion Rate": record.conversion_rate,
        }
 
    def get_records_by_wq(self) -> List[AnomalyJournal]:
        """Fetch all rows from R2R_PROCESS_OUTPUT_MODEL for given wq_id and map directly to AnomalyRecord."""
        if not self.wq_id:
            raise AnomalyDetectionError("wq_id is required to fetch records")
 
        session: Session = self.session_factory()
        try:
            rows = (
                session.query(ProcessOutputModel)
                .filter(ProcessOutputModel.wq_id == self.wq_id)
                .all()
            )
 
            results: List[AnomalyJournal] = []
            for r in rows:
                rec = AnomalyJournal(
                    company_code=r.company_code,
                    journal_id=r.id,
                    posting_date=r.posting_date,
                    created_by=r.created_by,
                    journal_name=r.header_text or r.line_item_text,
                    amount_credited=r.amount,  # add logic if posting key is available
                    amount_debited=r.amount,
                    currency_code=r.currency,
                    gl_code=None,
                    profit_center=r.profit_center,
                    cost_center=r.cost_center,
                    fiscal_period=None,
                    document_date=r.document_date,
                    document_id=None,
                    country_code=r.business_place,
                    account_name=r.partner,
                    conversion_rate=r.exchange_rate,
                )
                results.append(rec)
 
            logger.info(f"Retrieved {len(results)} anomaly records for wq_id={self.wq_id}")
            return results
 
        except Exception as e:
            logger.error(f"Error fetching records for wq_id={self.wq_id}: {e}")
            raise AnomalyDetectionError(f"Database error while fetching records: {e}")
        finally:
            session.close()
