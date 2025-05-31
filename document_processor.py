from typing import List, Dict
from langchain.schema import Document
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_community.document_loaders import PyPDFLoader, TextLoader


class DocumentProcessor:
    """Handles document loading and processing operations"""
    
    def __init__(self, chunk_size: int = 500, chunk_overlap: int = 50):
        self.text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap
        )
    
    def load_documents(self, resume_path: str, job_desc_path: str) -> List[Document]:
        """Load resume and job description documents"""
        documents = []
        
        try:
            # Load resume
            if resume_path.endswith('.pdf'):
                resume_loader = PyPDFLoader(resume_path)
                resume_docs = resume_loader.load()
            else:
                resume_loader = TextLoader(resume_path, encoding='utf-8')
                resume_docs = resume_loader.load()
            
            # Load job description
            job_loader = TextLoader(job_desc_path, encoding='utf-8')
            job_docs = job_loader.load()
            
        except FileNotFoundError as e:
            raise FileNotFoundError(f"Could not find file: {e}")
        except Exception as e:
            raise Exception(f"Error loading documents: {e}")
        
        # Add metadata
        for doc in resume_docs:
            doc.metadata['source_type'] = 'resume'
        for doc in job_docs:
            doc.metadata['source_type'] = 'job_description'
        
        documents.extend(resume_docs)
        documents.extend(job_docs)
        
        return documents
    
    def split_documents(self, documents: List[Document]) -> List[Document]:
        """Split documents into chunks"""
        return self.text_splitter.split_documents(documents)
    
    def extract_content(self, documents: List[Document]) -> Dict[str, str]:
        """Extract content from documents by type"""
        resume_docs = [doc for doc in documents if doc.metadata.get('source_type') == 'resume']
        job_docs = [doc for doc in documents if doc.metadata.get('source_type') == 'job_description']
        
        return {
            'resume_content': '\n'.join([doc.page_content for doc in resume_docs]),
            'job_description': '\n'.join([doc.page_content for doc in job_docs])
        }
