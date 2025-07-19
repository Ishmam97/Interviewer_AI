from typing import List, Tuple, Optional
from langchain.schema import Document
from langchain_openai import OpenAIEmbeddings
import os

# Try to import FAISS with fallback to CPU version
try:
    from langchain_community.vectorstores import FAISS
    FAISS_AVAILABLE = True
    print("✅ FAISS with GPU support loaded")
except ImportError as e:
    print(f"⚠️ Failed to load FAISS: {e}")
    try:
        # Try to install and import faiss-cpu as fallback
        import subprocess
        import sys
        print("🔄 Attempting to install faiss-cpu as fallback...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "faiss-cpu"])
        from langchain_community.vectorstores import FAISS
        FAISS_AVAILABLE = True
        print("✅ FAISS CPU fallback installed and loaded")
    except Exception as fallback_error:
        print(f"❌ Failed to install faiss-cpu fallback: {fallback_error}")
        FAISS_AVAILABLE = False


class RAGSystem:
    """Manages vector store operations for RAG functionality"""
    
    def __init__(self, embeddings: OpenAIEmbeddings, index_path: str = "./interview_faiss_index"):
        if not FAISS_AVAILABLE:
            raise ImportError("FAISS is not available. Please install faiss-cpu or faiss-gpu")
        
        self.embeddings = embeddings
        self.index_path = index_path
        self.vector_store: Optional[FAISS] = None
    
    def load_existing_index(self) -> bool:
        """Load existing FAISS index if available"""
        if not FAISS_AVAILABLE:
            print("❌ FAISS not available, cannot load index")
            return False
            
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
        if not FAISS_AVAILABLE:
            raise ImportError("FAISS is not available, cannot create index")
            
        print("🔧 Building new FAISS index...")
        
        try:
            self.vector_store = FAISS.from_documents(
                documents=documents,
                embedding=self.embeddings
            )
            
            self.save_index()
            print("💾 FAISS index saved successfully")
        except Exception as e:
            print(f"❌ Failed to create FAISS index: {e}")
            # Try with CPU-only settings if available
            try:
                import faiss
                faiss.omp_set_num_threads(1)  # Use single thread for CPU
                self.vector_store = FAISS.from_documents(
                    documents=documents,
                    embedding=self.embeddings
                )
                self.save_index()
                print("💾 FAISS index created with CPU fallback")
            except Exception as cpu_error:
                print(f"❌ CPU fallback also failed: {cpu_error}")
                raise
    
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
