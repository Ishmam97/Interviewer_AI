PLANNING_PROMPT="""
        You are an expert interview planner. Based on the resume and job description provided, 
        create a comprehensive interview plan with 3-4 strategic questions.
        
        Resume Content:
        {resume_content}
        
        Job Description:
        {job_description}
        
        Create questions that:
        1. Assess technical skills mentioned in the job requirements
        2. Evaluate experience relevant to the role
        3. Test problem-solving abilities
        4. Explore cultural fit and soft skills
        5. Identify gaps or areas needing clarification
        
        Return a JSON array of questions with this structure:
        [
            {{
                "question": "specific question text",
                "category": "technical|experience|behavioral|problem_solving",
                "priority": 1-5,
                "expected_skills": ["skill1", "skill2"],
                "follow_up_prompts": ["follow up 1", "follow up 2"]
            }}
        ]
        
        Order questions by priority and natural flow.
        """
ANALYSIS_PROMPT="""
        Analyze this interview response in the context of the resume and job requirements.
        
        Question: {question}
        Candidate Response: {response}
        
        Relevant Context from Resume/Job Description:
        {rag_context}
        
        Previous Conversation:
        {conversation_history}
        
        Provide analysis in this format:
        SCORE: [1-10]
        STRENGTHS: [key strengths demonstrated]
        CONCERNS: [areas of concern or missing information]
        FOLLOW_UP: [suggested follow-up questions if needed]
        OBSERVATIONS: [detailed observations]
        """
REPORT_PROMPT="""
        Generate a comprehensive interview report based on the following information:
        
        Resume Summary:
        {resume_content}
        
        Job Requirements:
        {job_description}
        
        Interview Notes:
        {interview_notes}
        
        Generate a professional report with these sections:
        
        # INTERVIEW REPORT
        
        ## CANDIDATE OVERVIEW
        [Brief summary of candidate background]
        
        ## INTERVIEW SUMMARY
        [Overall interview performance and key highlights]
        
        ## DETAILED ASSESSMENT
        
        ### Technical Skills
        [Assessment of technical capabilities]
        
        ### Experience Relevance
        [How experience aligns with role requirements]
        
        ### Communication & Soft Skills
        [Assessment of communication and interpersonal skills]
        
        ### Problem-Solving Ability
        [Evaluation of analytical and problem-solving skills]
        
        ## STRENGTHS
        [Key strengths identified]
        
        ## AREAS OF CONCERN
        [Potential concerns or gaps]
        
        ## RECOMMENDATION
        [Clear hiring recommendation with reasoning]
        
        ## OVERALL SCORE: [X/10]
        
        Make the report detailed, professional, and actionable for hiring decisions.
        """