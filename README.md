## Web_App

┌─────────────────────────────────────────────────────────────┐  
│ Frontend (React Web or React Native Mobile)                 │  
│ - Chatbot UI                                                │  
│ - User input/message display                                │  
│ - Conversation history                                      │  
└──────────────────────┬──────────────────────────────────────┘  
                       │ HTTP/WebSocket  
                       ↓  
┌─────────────────────────────────────────────────────────────┐  
│ Backend (FastAPI + Python)                                  │  
│                                                             │  
│ ┌──────────────────────────────────────────────────────────┐  
│ │ RAG Pipeline                                             │  
│ │ 1. User query                                            │  
│ │ 2. Search vector database (Pinecone/Chroma)              │  
│ │ 3. Retrieve relevant documents                           │  
│ │ 4. Pass to LLM with context                              │  
│ │ 5. LLM generates response                                │  
│ │ 6. Return to frontend                                    │  
│ └──────────────────────────────────────────────────────────┘  
└──────────────────────┬──────────────────────────────────────┘  
                       │  
          ┌────────────┼────────────┐  
          ↓            ↓            ↓  
    ┌─────────┐  ┌──────────┐  ┌────────────┐  
    │ Vector  │  │ LLM      │  │ Documents  │  
    │Database │  │ (Claude) │  │ Storage    │  
    │Chroma   │  │ or GPT   │  │ (cloud)    │  
    └─────────┘  └──────────┘  └────────────┘  
