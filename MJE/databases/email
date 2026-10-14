import json
from sqlalchemy import  Column, DateTime, Integer, String, func, Boolean, ForeignKey
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship
from database.database_manager import Base,  db_schema
from dto.request_dtos import ExtractedMailDetailsDTO
from pathlib import Path
import os
from utility.logger import logger
from database.db_models.region_master import RegionMaster


class EmailMaster(Base):
    __tablename__ = 'r2r_emails'
    __table_args__ = {"schema": db_schema} 

    id = Column(Integer, primary_key=True, autoincrement=True)
    trace_id=Column(String, nullable=False)
    email_subject = Column(String, nullable=True)
    email_from = Column(String, nullable=True)
    email_to = Column(String, nullable=True)
    inbox_folder = Column(String, nullable=True)
    email_cc = Column(String, nullable=True)
    email_bcc = Column(String, nullable=True)
    email_received_date = Column(String, nullable=True)
    has_attachment = Column(Boolean, default=False)
    download_status = Column(String, nullable=True)
    region_id = Column(Integer, ForeignKey(f"{db_schema}.r2r_regions.id"), nullable=True)
    email_path = Column(String, nullable=True)
    email_file_name = Column(String, nullable=True)
    email_json = Column(JSONB, nullable=True)
    created_by = Column(String, default="Engine")
    created_date = Column(DateTime, default=func.now())
    updated_date = Column(DateTime, default=func.now(), onupdate=func.now())
    updated_by = Column(String, default="Engine")
    contents = relationship("EmailContent")
    @classmethod
    def from_dto(cls, email_data:ExtractedMailDetailsDTO,region_id:int)->object:
        email_master = EmailMaster()
        folder_name = email_data.folderName.split("#")[-1] if email_data.folderName and "#" in email_data.folderName else email_data.folderName
        # Populate fields manually
        email_master.trace_id = email_data.caseId
        email_master.email_subject = email_data.subject
        email_master.email_from = email_data.from_
        email_master.email_to = ",".join(email_data.to) if email_data.to else None
        email_master.inbox_folder = folder_name
        email_master.email_cc = ",".join(email_data.cc) if email_data.cc else None
        email_master.email_bcc = ",".join(email_data.bcc) if email_data.bcc else None
        email_master.email_received_date = email_data.receiveDate
        email_master.has_attachment = bool(email_data.attachments)
        email_master.download_status = "Downloaded"  # or custom logic
        # Region ID logic
        

        email_master.email_path = email_data.emlFilePath
        plain_body_file_path = email_data.plainBodyFilePath
        email_file_name = os.path.basename(plain_body_file_path) if plain_body_file_path else None
        email_master.email_file_name = email_file_name
        email_master.email_json = email_data.model_dump_json()
        email_master.created_by = "CoraMail"
        email_master.updated_by = "CoraMail"        
        email_master.region_id = region_id

        # Populate EmailContent for each attachment
        email_content = email_data.attachments
        for attachment in email_content:
            email_content = EmailContent(
                #email_id=email_master.id,
                content_category="Attachment",
                content_type=Path(attachment).suffix,
                content_path=attachment,
                content_file_name=Path(attachment).name,
                pid=None,  # Set parent id if needed
                active_flag=True,
                created_by="Engine" #doubt
            )
            email_master.contents.append(email_content)

        email_content = EmailContent(
                #email_id=email_master.id,
                content_category="Body",
                content_type=Path(email_data.plainBodyFilePath).suffix,
                content_path=email_data.plainBodyFilePath,
                content_file_name=Path(email_data.plainBodyFilePath).name,
                pid=None,  # Set parent id if needed
                active_flag=True,
                created_by="Engine" #doubt
            )
        email_master.contents.append(email_content)
        return email_master

class EmailContent(Base):
    __tablename__ = 'r2r_email_contents'
    __table_args__ = {"schema": db_schema}

    id = Column(Integer, primary_key=True, autoincrement=True)
    email_id = Column(Integer, ForeignKey(f"{db_schema}.r2r_emails.id"))  # FK to EmailMaster.id (should match type)
    content_category = Column(String, nullable=True)  # Attachment/body/embedded
    content_type = Column(String, nullable=True)      # PDF/EXCEL/WORD/EMAIL
    content_path = Column(String, nullable=True)      # HTML PATH
    content_file_name = Column(String, nullable=True)
    pid = Column(String, nullable=True)               # Parent ID
    active_flag = Column(Boolean, default=True)       # Y = True
    created_by = Column(String, nullable=True)        # INGESTION_AGENT/Application Login ID/OHR ID
    created_date = Column(DateTime, default=func.now())
    

# class RegionMaster(Base):                       
#     __tablename__ = 'R2R_REGIONS'
#     __table_args__ = {"schema": db_schema}

#     id = Column(Integer, primary_key=True, autoincrement=True)
#     master_region_code = Column(String, nullable=True)
#     region_code = Column(String, nullable=True)
#     region_email_id = Column(String, nullable=True)
#     folder_name = Column(String, nullable=True)
