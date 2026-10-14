from database.db_models.process_output_model import ProcessOutputModel
from sqlalchemy import func

class ProcessingOutputModelRepository:
    def __init__(self, session):
        self.session = session

    def save(self, processing_obj: ProcessOutputModel):
        self.session.add(processing_obj)
        self.session.commit()
        return processing_obj

    def find_by_id(self, processing_id: int) -> ProcessOutputModel:
        return self.session.query(ProcessOutputModel).filter(ProcessOutputModel.id == processing_id).first()

    def delete(self, processing_id: int):
        obj = self.find_by_id(processing_id)
        if obj:
            self.session.delete(obj)
            self.session.commit()

    def find_by_wq_id(self, wq_id: int) -> ProcessOutputModel:
        return self.session.query(ProcessOutputModel).filter(ProcessOutputModel.wq_id == wq_id).first()        

    def get_all(self):
        return self.session.query(ProcessOutputModel).all()

    def find_distinct_case_ids_by_wq_id(self, wq_id: int) -> list[int]:
        return self.session.query(ProcessOutputModel.case_id).filter(ProcessOutputModel.wq_id == wq_id).distinct().all()

    def find_max_version_by_wq_id_and_case_id(self, wq_id: int, case_id: int) -> int:
        return self.session.query(func.max(ProcessOutputModel.version)).filter(
            ProcessOutputModel.wq_id == wq_id, ProcessOutputModel.case_id == case_id
        ).scalar()

    def find_company_code_by_wq_id_and_case_id(self, wq_id: int, case_id: int) -> str:
        return self.session.query(ProcessOutputModel.company_code).filter(
            ProcessOutputModel.wq_id == wq_id, ProcessOutputModel.case_id == case_id
        ).first()[0]
     # groups cases for wq_id and case_id basis posting key to get aggregate sum of amount
    def find_grouped_by_posting_key_max_version(self, wq_id: int, case_id: int, max_version: int):
        return self.session.query(
            ProcessOutputModel.posting_key,
            func.sum(ProcessOutputModel.amount).label('total_amount')
        ).filter(
            ProcessOutputModel.wq_id == wq_id,
            ProcessOutputModel.case_id == case_id,
            ProcessOutputModel.version == max_version
        ).group_by(ProcessOutputModel.posting_key).all()
