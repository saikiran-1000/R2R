from utility.constants import AGENT_TYPE
from agent.agent import AgentInterface
from agent.agents_exception import ExtractionError
from agent.readers import reader_factory
from database.db_models.email import EmailContent, EmailMaster
from database.services.email_service import EmailMasterService
from dto.agent_parameters import AgentParameter, ExtractionAgentParameter
from database.transaction_manager import TransactionManager
from database.database_manager import SessionFactory
from database.services.extraction_output_service import ExtractionOutputService
from database.db_models.extraction import ExtractionOutput
from utility.audit import record_case_as_wq, wq_audit
from utility.json_utils import build_safe_kwargs
from database.services.work_queue_service import WorkQueueService
from agent.services.mje_extraction_service import MJEExtractionService
from agent.base_agent import BaseAgent
from agent.readers.excel_template_reader import ExcelTemplateReader


class ExtractionAgent(AgentInterface, BaseAgent):
     """This Agent will do the extraction of information from email content using LLM service"""
     
     def __init__(self, trigger_type: str, case_id: str, wq_id=None):
          super().__init__(case_id, agent_name=AGENT_TYPE.EXTRACTION_AGENT.value)
          self.trigger_type=trigger_type
          self.trace_id = case_id
          self._svc = MJEExtractionService()
          self.transaction_manager = TransactionManager(SessionFactory)
          self.extraction_output_service = ExtractionOutputService(self.transaction_manager)
          self.email_master_service = EmailMasterService(self.transaction_manager)
          self.work_queue_service = WorkQueueService(self.transaction_manager)
          self.wq_id = wq_id
          self._excel_reader = ExcelTemplateReader()
         

     @record_case_as_wq( AGENT_TYPE.EXTRACTION_AGENT.value)
     async def auditable_process(self, arguments: AgentParameter) -> None:
        """
        Executes the auditable extraction process. 
        Creates an audit entry at the start and end of execution.
        Invokes the LLM for extraction and persists results in the extraction_output table.
        """

        extraction_param: ExtractionAgentParameter = arguments

        email_master: EmailMaster = await self.validate_email_content(extraction_param)
        email_content = email_master.contents
        email_subject = email_master.email_subject
        email_received_date = email_master.email_received_date
        extraction_output_objs = []

        wq_id = self.wq_id
        for file in email_content:
            file_path = file.content_path
            if self._is_excel_ext(ext=file.content_type.lower()):
                file_bytes = self._read_file_bytes(file_path)
                rows = self._excel_reader.parse_excel(file_bytes, content_type=file.content_type)
                if rows:
                    await self._process_extraction_data(rows, wq_id, file, email_master, extraction_output_objs)
                    continue
                else:
                    self._log_info(f"Excel file is not matching with any Template, switching to LLM extraction flow.")
            input_data = await self._read_input_file(file, file_path)
            if input_data:
                result = await self._extract_information(input_data, file, email_subject, email_received_date)
                self._log_info(f"Raw Extraction Result: {type(result)}")
                await self._process_extraction_data(result, wq_id, file, email_master, extraction_output_objs)
                self._log_debug(
                    f"For file type {file.content_type} extraction_output_objs: \n{extraction_output_objs}"
                )
            else:
                self._log_warning(f"Not able to extract data from  file {file_path}")
        # Update extraction outputs with email-sourced specific_code and intent
        extraction_output_objs_updated = await self._update_extraction_output_list(
            extraction_output_objs
        )
        # Filter out empty extraction outputs
        extraction_output_objs_filtered = await self._remove_empty_extraction_outputs(
            extraction_output_objs_updated
        )
        self.extraction_output_service.save_all_extraction_output(
            objs_persist=extraction_output_objs_filtered
        )


     @wq_audit("_read_input_file", AGENT_TYPE.EXTRACTION_AGENT.value)
     async def _read_input_file(self, file: EmailContent, file_path: str):
        """Method to read the input file based on content type

         Args:
             file (EmailContent): file object
             file_path (str): path of the file

         Returns:
             _type_: data read from the file
        """
        # Identify the reader from factory  based on file content_type
        reader = reader_factory.FileReaderFactory.get_reader(file.content_type)
        self._log_info(f"Going to read file {file_path} - for extraction")
        input_data = reader.read(file_path) if reader else None
        self._log_info(f"File data:\n {input_data}")
        return input_data


     @wq_audit("_extract_information", AGENT_TYPE.EXTRACTION_AGENT.value)
     async def _extract_information(self, input_data, file, email_subject, email_received_date) -> dict:
        """Method to extract information from the input data using LLM service

         Args:
             input_data: Excel -> dict (already JSON-like by sheet), Text/Email -> str
             file (EmailContent): file object
             email_subject (str): subject of the email
         Returns:
            dict: _extracted information
        """
        result = self._svc.run(input_data=input_data, file_type=file.content_type, email_subject=email_subject, email_received_date=email_received_date)
        self._log_debug(f"Extracted information: \n{result['extracted']}")
        return result


     @wq_audit("_build_extraction_outputs", AGENT_TYPE.EXTRACTION_AGENT.value )
     async def _build_extraction_outputs(
        self, result: dict, wq_id: str, file, email_master
    ) -> list[ExtractionOutput]:
        """Method to build extraction output objects from the extracted result

         Args:
             result (dict): extracted information
             wq_id (str): work queue id
             file (EmailContent): file object
             email_master (EmailMaster): email master object
         Returns:
            list[ExtractionOutput]: list of extraction output objects
        """
        self._log_info(f"Raw Extraction Result: {result}")
        try:
            journal_entry = result["extracted"]["journal_entries"]
        except:
            raise ExtractionError("Error in extraction: Token limit exceeded. Please reduce the number of input journal entries.")

        self._log_debug(f"journal_entry: \n{journal_entry}")

        journal_list = [
            {
                **journal,
                "wq_id": wq_id,
                "email_content_id": file.id,
                "email": email_master.email_from,
                "created_by": AGENT_TYPE.EXTRACTION_AGENT.value,
                "updated_by": AGENT_TYPE.EXTRACTION_AGENT.value,
            }
            for journal in journal_entry
        ]
        self._log_debug(f"Journal list: \n{journal_list}")
        extraction_outputs = [
            ExtractionOutput(**build_safe_kwargs(ExtractionOutput, d))
            for d in journal_list or []
        ]
        self._log_info(
            f"For file type {file.content_type} extraction_output: \n{extraction_outputs}"
        )
        return extraction_outputs

   
     @wq_audit("_update_extraction_output_list", AGENT_TYPE.EXTRACTION_AGENT.value)
     async def _update_extraction_output_list(
        self,
        extraction_output_list: list["ExtractionOutput"],
     ) -> list["ExtractionOutput"]:
        """
        Method to update the extraction output list:
        - Extract `specific_code` and `intent` from the ExtractionOutput object(s)
        where `extracted_from == "email"`.
        - Update all other ExtractionOutput objects (where `extracted_from != "email"`)
        with those same `specific_code` and `intent` values.

        Args:
            extraction_output_list (list[ExtractionOutput]): list of extraction output objects

        Returns:
            list[ExtractionOutput]: updated extraction output list
        """

        # Step 1: Find email-sourced extraction output
        email_output = next(
            (obj for obj in extraction_output_list if self._safe_getattr(obj, "extracted_from", None) == "email"),
            None,
        )

        # If no email-based object exists, return as-is
        if not email_output:
            return extraction_output_list

        # Step 2: Extract the specific_code and intent from email output
        email_specific_code = self._safe_getattr(email_output, "specific_code", None)
        email_intent = self._safe_getattr(email_output, "intent", None)

        # Step 3: Propagate these values to all non-email items
        for obj in extraction_output_list:
            if self._safe_getattr(obj, "extracted_from", None) != "email":
                if self._is_blank(self._safe_getattr(obj, "specific_code", None)):
                    setattr(obj, "specific_code", email_specific_code)
                if self._is_blank(self._safe_getattr(obj, "intent", None)):
                    setattr(obj, "intent", email_intent)

        return extraction_output_list

    
     @wq_audit("_remove_empty_extraction_outputs", AGENT_TYPE.EXTRACTION_AGENT.value)
     async def _remove_empty_extraction_outputs(
        self,
        extraction_output_list: list["ExtractionOutput"],
     ) -> list["ExtractionOutput"]:
        """
        Remove ExtractionOutput objects where cost_center, company_code, currency_key,
        account, and document_amount are all null or empty.
        Args:
            extraction_output_list (list[ExtractionOutput]): list of extraction output objects
        Returns:
            list[ExtractionOutput]: filtered extraction output list
        """

        filtered_list = []
        for obj in extraction_output_list:
            # Retrieve field values safely
            cost_center = self._safe_getattr(obj, "cost_center", None)
            company_code = self._safe_getattr(obj, "company_code", None)
            currency_key = self._safe_getattr(obj, "currency_key", None)
            account = self._safe_getattr(obj, "account", None)
            document_amount = self._safe_getattr(obj, "document_amount", None)

            # Keep only if at least one field is not blank
            if not (
                self._is_blank(cost_center)
                and self._is_blank(company_code)
                and self._is_blank(currency_key)
                and self._is_blank(account)
                and self._is_blank(document_amount)
            ):
                filtered_list.append(obj)

        return filtered_list
   

     @wq_audit( "Validate_email_content", AGENT_TYPE.EXTRACTION_AGENT.value )
     async def validate_email_content(
        self, extraction_param: ExtractionAgentParameter
    ) -> EmailMaster:
        """Method to validate the email content and return the email master object

         Args:
             extraction_param (ExtractionAgentParameter): extraction agent parameter object
         Raises:
             ExtractionError: if case does not exist or there is no content to extract
         Returns:
            EmailMaster: email master object
        """
        email_master = extraction_param.email_master
        if email_master is None:
            email_master: EmailMaster = (
                await self.email_master_service.find_email_master_by_case_id(
                    self.case_id
                )
            )

        if email_master is None:
            raise ExtractionError(f"Case doesnot exit in the system {self.case_id}")

        email_content: list[EmailContent] = email_master.contents

        if email_content is None:
            raise ExtractionError("There is nothing to extract")

        return email_master
    
    
     @wq_audit("_process_extraction_data", AGENT_TYPE.EXTRACTION_AGENT.value)
     async def _process_extraction_data(
        self, data, wq_id, file, email_master, extraction_output_objs
    ) -> None:
        """Method to process the extraction data and build extraction output objects

         Args:
             data: extracted data
             wq_id (str): work queue id
             file (EmailContent): file object
             email_master (EmailMaster): email master object
             extraction_output_objs: list to append extraction output objects
        Returns: None
        """
        if not data:
            return

        extraction_outputs = await self._build_extraction_outputs(
            data, wq_id, file, email_master
        )
        extraction_output_objs.extend(extraction_outputs)

