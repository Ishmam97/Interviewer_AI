from interview_system import InterviewSystem
from models import InterviewConfig
from dotenv import load_dotenv

load_dotenv()

def interactive_interview_mode(interview_system: InterviewSystem, resume_path: str, job_desc_path: str):
    """Run interactive interview mode"""
    print("\n" + "="*50)
    print("INTERACTIVE INTERVIEW MODE")
    print("="*50)
    
    # Start interactive session
    state = interview_system.start_interactive_interview(resume_path, job_desc_path)
    
    # Interactive Q&A loop
    while state['current_question_idx'] < len(state['interview_plan']):
        # Get next question
        question = interview_system.get_next_question(state)
        
        if not question:
            break
            
        # Ask the question
        print(f"\nInterviewer: {question}")
        
        # Get candidate response
        candidate_answer = input("Candidate: ")
        
        if candidate_answer.lower() in ['quit', 'exit', 'stop']:
            print("Interview terminated by user.")
            break
        
        # Process the answer
        state = interview_system.process_candidate_answer(state, candidate_answer)
        
        print(f"[Note taken - Score: {state['interview_notes'][-1]['score']}/10]")
    
    # Generate final report
    state = interview_system.generate_final_report(state)
    print("\n" + "="*50)
    print("FINAL INTERVIEW REPORT")
    print("="*50)
    print(state['interview_report'])


def automated_interview_mode(interview_system: InterviewSystem, resume_path: str, job_desc_path: str):
    """Run automated interview mode (for testing/demo)"""
    print("\n" + "="*50)
    print("AUTOMATED INTERVIEW MODE")
    print("="*50)
    
    # This would be used for testing with pre-defined responses
    result = interview_system.conduct_full_interview(resume_path, job_desc_path)
    
    if "error" in result:
        print(f"Error: {result['error']}")
    else:
        print("Interview completed successfully!")
        print(f"Questions asked: {len(result.get('interview_notes', []))}")


def demo_rag_search(interview_system: InterviewSystem):
    """Demonstrate RAG search functionality"""
    print("\n" + "="*50)
    print("RAG SEARCH DEMO")
    print("="*50)
    
    while True:
        query = input("\nEnter search query (or 'quit' to exit): ")
        if query.lower() in ['quit', 'exit']:
            break
        
        results = interview_system.search_context(query)
        
        print(f"\nFound {len(results)} relevant documents:")
        for i, (doc, score) in enumerate(results, 1):
            print(f"\n{i}. Score: {score:.3f}")
            print(f"Content: {doc.page_content[:200]}...")
            print(f"Source: {doc.metadata.get('source_type', 'unknown')}")


def main():
    """Main application entry point"""
    import os
    
    # Configuration
    config = InterviewConfig(
        max_questions=5,
        chunk_size=500,
        chunk_overlap=50,
        rag_k_results=3,
        temperature=0.3,
        model_name="gpt-4.1-nano-2025-04-14",
        index_path="./interview_faiss_index"
    )
    
    # Initialize the interview system
    api_key = os.getenv("OPENAI_API_KEY", "")
    if not api_key:
        print("❌ Please set OPENAI_API_KEY environment variable")
        return
    
    interview_system = InterviewSystem(api_key, config)
    
    # File paths
    resume_path = "resume.pdf"
    job_desc_path = "job_desc.txt"
    
    # Check if files exist
    if not os.path.exists(resume_path):
        print(f"❌ Resume file not found: {resume_path}")
        return
    
    if not os.path.exists(job_desc_path):
        print(f"❌ Job description file not found: {job_desc_path}")
        return
    
    # Main menu
    while True:
        print("\n" + "="*50)
        print("INTERVIEW SYSTEM MAIN MENU")
        print("="*50)
        print("1. Interactive Interview Mode")
        print("2. Automated Interview Mode (Demo)")
        print("3. RAG Search Demo")
        print("4. Rebuild FAISS Index")
        print("5. Exit")
        
        choice = input("\nEnter your choice (1-5): ").strip()
        
        try:
            if choice == "1":
                interactive_interview_mode(interview_system, resume_path, job_desc_path)
            
            elif choice == "2":
                automated_interview_mode(interview_system, resume_path, job_desc_path)
            
            elif choice == "3":
                # Setup RAG system first
                interview_system.setup_rag_system(resume_path, job_desc_path)
                demo_rag_search(interview_system)
            
            elif choice == "4":
                print("🔧 Rebuilding FAISS index...")
                interview_system.setup_rag_system(resume_path, job_desc_path, force_rebuild=True)
                print("✅ Index rebuilt successfully!")
            
            elif choice == "5":
                print("Goodbye! 👋")
                break
            
            else:
                print("❌ Invalid choice. Please enter 1-5.")
                
        except KeyboardInterrupt:
            print("\n\nOperation interrupted by user.")
            continue
        except Exception as e:
            print(f"❌ An error occurred: {e}")
            continue


if __name__ == "__main__":
    main()