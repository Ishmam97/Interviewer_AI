from typing import List, Tuple, Optional
from langchain.schema import Document
from langchain_community.vectorstores import FAISS
from langchain_openai import OpenAIEmbeddings


class RAGSystem:
    """Manages vector store operations for RAG functionality"""
    
    def __init__(self, embeddings: OpenAIEmbeddings, index_path: str = "./interview_faiss_index"):
        self.embeddings = embeddings
        self.index_path = index_path
        self.vector_store: Optional[FAISS] = None
    
    def load_existing_index(self) -> bool:
        """Load existing FAISS index if available"""
        try:
            self.vector_store = FAISS.load_local(
                self.index_path, 
                self.embeddings,
                allow_dangerous_deserialization=True
            )
            print("✅ Loaded existing FAISS index")
            return True
        except FileNotFoundError:
            print("⚠️ No existing FAISS index found")
            return False
        except Exception as e:
            print(f"⚠️ Could not load existing index: {e}")
            return False
    
    def create_index(self, documents: List[Document]) -> None:
        """Create new FAISS index from documents"""
        print("🔧 Building new FAISS index...")
        
        self.vector_store = FAISS.from_documents(
            documents=documents,
            embedding=self.embeddings
        )
        
        self.save_index()
        print("💾 FAISS index saved successfully")
    
    def save_index(self) -> None:
        """Save current FAISS index"""
        if self.vector_store:
            self.vector_store.save_local(self.index_path)
    
    def add_documents(self, documents: List[Document]) -> None:
        """Add new documents to existing FAISS index"""
        if not self.vector_store:
            raise ValueError("Vector store not initialized. Create index first.")
        
        self.vector_store.add_documents(documents)
        self.save_index()
        print(f"✅ Added {len(documents)} new document chunks to FAISS index")
    
    def similarity_search(self, query: str, k: int = 3) -> List[Document]:
        """Search for similar documents"""
        if not self.vector_store:
            return []
        
        return self.vector_store.similarity_search(query, k=k)
    
    def get_context(self, query: str, k: int = 3) -> str:
        """Get relevant context as formatted string"""
        relevant_docs = self.similarity_search(query, k=k)
        return "\n".join([doc.page_content for doc in relevant_docs])
